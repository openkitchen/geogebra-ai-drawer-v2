from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any, Callable, TypeVar

from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel

from ..debug_trace import trace_exception, trace_line, trace_reasoning_to_file
from .config import load_llm_config
from .errors import LlmInvocationError

TModel = TypeVar("TModel", bound=BaseModel)


def _extract_json_object(raw: str) -> str | None:
    s = raw.strip()
    if not s:
        return None
    if s.startswith("{") and s.endswith("}"):
        return s
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return s[start : end + 1]


@lru_cache(maxsize=8)
def _build_llm(*, api_key: str, base_url: str | None, model: str, temperature: float, timeout_s: float) -> ChatOpenAI:
    # NOTE: Use the new langchain-openai parameter names so timeout/retry behavior is effective.
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
        "timeout": timeout_s,
        # We already implement fallback at higher levels; keep low-level retries minimal.
        "max_retries": 0,
        # Many OpenAI-compatible gateways don't support the Responses API yet.
        "use_responses_api": False,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


class LlmClient:
    """Thin wrapper around LangChain ChatOpenAI with common fallbacks.

    Goals:
    - centralize role-based config resolution
    - provide structured-output first, JSON fallback second
    - keep tracing consistent (without tying callers to LangSmith specifics)
    """

    def __init__(self, *, run_id: str | None = None, ui_debug: bool = False) -> None:
        self._run_id = run_id
        self._ui_debug = ui_debug

    def _get_llm(self, *, role: str) -> ChatOpenAI | None:
        cfg = load_llm_config(role=role)
        if cfg is None:
            return None
        return _build_llm(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
            temperature=cfg.temperature,
            timeout_s=cfg.timeout_s,
        )

    def invoke_structured(
        self,
        *,
        role: str,
        op: str,
        messages: list[Any],
        output_schema: type[TModel],
        json_fallback_parser: Callable[[dict[str, Any]], TModel] | None = None,
    ) -> TModel | None:
        """Invoke with structured output; fallback to plain JSON parsing if needed.

        - `json_fallback_parser`: if provided, we use it to validate/convert fallback JSON dict.
          Otherwise we try `output_schema.model_validate`.
        """

        llm = self._get_llm(role=role)
        if llm is None:
            return None

        # Some OpenAI-compatible gateways/models don't support LangChain's structured output
        # (typically implemented via response_format / tool schema). They may return errors like:
        # - 400/429 with message containing "Model not support"
        # In that case, we should silently fall back to prompt-based JSON parsing (same model),
        # without spamming exception traces.
        def _is_structured_unsupported(err: BaseException) -> bool:
            msg = str(err)
            return "Model not support" in msg or "model not support" in msg or "response_format" in msg

        t0 = time.time()
        result = None
        try:
            structured = llm.with_structured_output(output_schema)
            result = structured.invoke(messages)
        except Exception as e:
            # If structured output isn't supported, do NOT trace as exception; just fall back.
            if self._run_id and not _is_structured_unsupported(e):
                trace_exception(
                    run_id=self._run_id,
                    ui_debug=self._ui_debug,
                    where=f"llm.invoke_structured[{op}][{role}]",
                    exc=e,
                )
            result = None

        if isinstance(result, output_schema):
            return result

        # JSON fallback
        try:
            msg = llm.invoke(messages)
        except Exception as e:
            if self._run_id:
                trace_exception(
                    run_id=self._run_id,
                    ui_debug=self._ui_debug,
                    where=f"llm.invoke_json_fallback[{op}][{role}]",
                    exc=e,
                )
            return None

        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            return None

        blob = _extract_json_object(content)
        if not blob:
            return None

        try:
            payload = json.loads(blob)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None

        try:
            if json_fallback_parser is not None:
                return json_fallback_parser(payload)
            return output_schema.model_validate(payload)
        except Exception:
            return None

    def invoke_text(
        self, 
        *, 
        role: str, 
        op: str, 
        messages: list[Any],
        stream: bool = False,
        token_callback: Callable[[str], None] | None = None,
    ) -> str | None:
        """Invoke LLM for text generation.
        
        Args:
            role: LLM role (main, fast, fallback)
            op: Operation name for tracing
            messages: List of messages
            stream: If True, use streaming (requires token_callback)
            token_callback: Called for each token delta when streaming
        """
        llm = self._get_llm(role=role)
        if llm is None:
            return None
        
        if stream and token_callback:
            # Streaming mode
            try:
                # In Dev mode, use the raw OpenAI SDK streaming path so we can capture
                # OpenAI-compatible non-standard delta fields (e.g. reasoning_content)
                # that LangChain may drop.
                if self._ui_debug and self._run_id:
                    cfg = load_llm_config(role=role)
                    if cfg is not None:
                        try:
                            def _lc_messages_to_openai(messages_in: list[Any]) -> list[dict[str, Any]]:
                                out: list[dict[str, Any]] = []
                                for m in messages_in:
                                    m_type = getattr(m, "type", None)  # e.g. "system" | "human" | "ai" | "tool"
                                    content = getattr(m, "content", None)
                                    if not isinstance(content, str):
                                        content = str(content) if content is not None else ""

                                    role_name = "user"
                                    if m_type == "system":
                                        role_name = "system"
                                    elif m_type == "human":
                                        role_name = "user"
                                    elif m_type == "ai":
                                        role_name = "assistant"
                                    elif m_type == "tool":
                                        role_name = "tool"

                                    msg: dict[str, Any] = {"role": role_name, "content": content}
                                    tool_call_id = getattr(m, "tool_call_id", None)
                                    if role_name == "tool" and isinstance(tool_call_id, str) and tool_call_id:
                                        msg["tool_call_id"] = tool_call_id
                                    out.append(msg)
                                return out

                            client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
                            openai_messages = _lc_messages_to_openai(messages)

                            trace_line(
                                run_id=self._run_id,
                                ui_debug=self._ui_debug,
                                kind="openai_stream_start",
                                payload={
                                    "op": op,
                                    "role": role,
                                    "model": cfg.model,
                                    "base_url": cfg.base_url,
                                    "messages": [{"role": m.get("role"), "content_len": len(str(m.get("content") or ""))} for m in openai_messages],
                                },
                            )

                            full_text = ""
                            chunk_count = 0
                            sent_delta_keys = False
                            reasoning_total = ""

                            stream_resp = client.chat.completions.create(
                                model=cfg.model,
                                messages=openai_messages,
                                temperature=cfg.temperature,
                                stream=True,
                                stream_options={"include_usage": True},
                            )

                            for chunk in stream_resp:
                                chunk_count += 1
                                try:
                                    choices = getattr(chunk, "choices", None)
                                    if not choices:
                                        continue
                                    delta_obj = getattr(choices[0], "delta", None)
                                except Exception:
                                    continue

                                delta_dict: dict[str, Any] = {}
                                try:
                                    if delta_obj is not None:
                                        delta_dict = delta_obj.model_dump(exclude_none=True)  # type: ignore[attr-defined]
                                except Exception:
                                    delta_dict = {}

                                if delta_dict and not sent_delta_keys:
                                    sent_delta_keys = True
                                    trace_line(
                                        run_id=self._run_id,
                                        ui_debug=self._ui_debug,
                                        kind="openai_stream_delta_keys",
                                        payload={"keys": sorted(delta_dict.keys())},
                                    )

                                # Content delta
                                content_delta = delta_dict.get("content")
                                if isinstance(content_delta, str) and content_delta:
                                    token_callback(content_delta)
                                    full_text += content_delta

                                # Reasoning / thinking deltas (non-standard)
                                reasoning_delta = (
                                    delta_dict.get("reasoning_content")
                                    or delta_dict.get("reasoning")
                                    or delta_dict.get("thinking")
                                )
                                if isinstance(reasoning_delta, str) and reasoning_delta:
                                    reasoning_total += reasoning_delta

                                # Log raw-ish chunk info (bounded)
                                if chunk_count <= 200:
                                    try:
                                        chunk_dump = chunk.model_dump(exclude_none=True)  # type: ignore[attr-defined]
                                    except Exception:
                                        chunk_dump = {"_dump_error": True}
                                    trace_line(
                                        run_id=self._run_id,
                                        ui_debug=self._ui_debug,
                                        kind="openai_stream_chunk",
                                        payload={
                                            "chunk_num": chunk_count,
                                            "delta": delta_dict,
                                            "delta_keys": sorted(delta_dict.keys()) if delta_dict else [],
                                            "content_delta_len": len(content_delta) if isinstance(content_delta, str) else 0,
                                            "reasoning_delta_len": len(reasoning_delta) if isinstance(reasoning_delta, str) else 0,
                                            "chunk_dump": chunk_dump,
                                        },
                                    )

                            reasoning_meta = None
                            if self._run_id:
                                reasoning_meta = trace_reasoning_to_file(
                                    run_id=self._run_id, op=op, role=role, text=reasoning_total
                                )
                            include_reasoning_preview = reasoning_meta is not None

                            trace_line(
                                run_id=self._run_id,
                                ui_debug=self._ui_debug,
                                kind="openai_stream_end",
                                payload={
                                    "chunks": chunk_count,
                                    "content_len": len(full_text),
                                    "reasoning_len": len(reasoning_total),
                                    "reasoning_preview": (reasoning_total[:240] if include_reasoning_preview else None),
                                    **(reasoning_meta or {}),
                                },
                            )

                            main_text = full_text.strip() if full_text.strip() else ""
                            return main_text if main_text else None
                        except Exception as e:
                            # Fall back to LangChain streaming (same model) if the raw path fails.
                            trace_exception(
                                run_id=self._run_id,
                                ui_debug=self._ui_debug,
                                where=f"llm.invoke_text_openai_stream[{op}][{role}]",
                                exc=e,
                            )

                full_text = ""
                reasoning_total = ""
                chunk_count = 0
                
                # Debug: log stream start
                if self._ui_debug and self._run_id:
                    trace_line(
                        run_id=self._run_id,
                        ui_debug=self._ui_debug,
                        kind="llm_stream_start",
                        payload={"op": op, "role": role, "messages_count": len(messages)},
                    )
                
                # LangChain's stream() returns AIMessageChunk objects
                # Each chunk's content is typically incremental (delta), not cumulative
                stream_gen = llm.stream(messages)
                for chunk in stream_gen:
                    chunk_count += 1
                    content = getattr(chunk, "content", None)
                    additional_kwargs = getattr(chunk, "additional_kwargs", None)
                    
                    # Debug: log every chunk (even empty ones)
                    if self._ui_debug and self._run_id:
                        trace_line(
                            run_id=self._run_id,
                            ui_debug=self._ui_debug,
                            kind="llm_chunk",
                            payload={
                                "chunk_num": chunk_count,
                                "has_content": content is not None,
                                "content_type": type(content).__name__ if content is not None else None,
                                "content_len": len(content) if isinstance(content, str) else 0,
                                "content_preview": (content[:50] if isinstance(content, str) else str(content)[:50]) if content else None,
                                "additional_kwargs_keys": list(additional_kwargs.keys()) if isinstance(additional_kwargs, dict) else None,
                            },
                        )

                    # Some OpenAI-compatible gateways may attach reasoning deltas in additional_kwargs.
                    if isinstance(additional_kwargs, dict):
                        reasoning_delta = (
                            additional_kwargs.get("reasoning") or
                            additional_kwargs.get("thinking") or
                            additional_kwargs.get("reasoning_content")
                        )
                        if isinstance(reasoning_delta, str) and reasoning_delta:
                            reasoning_total += reasoning_delta
                    
                    if isinstance(content, str) and content:
                        # Determine if content is cumulative or incremental
                        # Most providers send incremental deltas, but check both cases
                        if full_text and content.startswith(full_text):
                            # Cumulative: extract only the new part
                            delta = content[len(full_text):]
                        else:
                            # Incremental: use the whole content as delta
                            delta = content
                        
                        if delta:
                            # Debug: log token delta
                            if self._ui_debug and self._run_id:
                                trace_line(
                                    run_id=self._run_id,
                                    ui_debug=self._ui_debug,
                                    kind="llm_token",
                                    payload={
                                        "delta_preview": delta[:50],
                                        "delta_len": len(delta),
                                        "full_len": len(full_text),
                                        "chunk_num": chunk_count,
                                    },
                                )
                            
                            # Send token delta via callback (this should trigger SSE events)
                            token_callback(delta)
                            full_text += delta
                
                # Extract thinking/reasoning content from the final message
                # Note: streaming may not preserve metadata, so we try to get it from the last chunk
                thinking_content = None
                response_metadata = getattr(chunk, "response_metadata", None) if 'chunk' in locals() else None
                if isinstance(response_metadata, dict):
                    thinking_content = (
                        response_metadata.get("thinking") or
                        response_metadata.get("reasoning") or
                        response_metadata.get("reasoning_content") or
                        response_metadata.get("cached_content")
                    )

                main_text = full_text.strip() if full_text.strip() else ""
                reasoning_text = reasoning_total
                if (not reasoning_text.strip()) and isinstance(thinking_content, str):
                    reasoning_text = thinking_content
                if self._run_id:
                    reasoning_meta = trace_reasoning_to_file(run_id=self._run_id, op=op, role=role, text=reasoning_text)
                    if self._ui_debug and self._run_id:
                        trace_line(
                            run_id=self._run_id,
                            ui_debug=self._ui_debug,
                            kind="llm_stream_end",
                            payload={
                                "op": op,
                                "role": role,
                                "chunk_count": chunk_count,
                                "final_text_len": len(full_text),
                                "reasoning_len": len(reasoning_text or ""),
                                **(reasoning_meta or {}),
                            },
                        )
                
                # Combine thinking content with main content if available
                if isinstance(thinking_content, str) and thinking_content.strip():
                    combined = f"[思考过程]\n{thinking_content.strip()}\n\n[回答]\n{main_text}"
                    return combined if combined.strip() else None
                
                return main_text if main_text else None
            except Exception as e:
                if self._run_id:
                    trace_exception(
                        run_id=self._run_id,
                        ui_debug=self._ui_debug,
                        where=f"llm.invoke_text_stream[{op}][{role}]",
                        exc=e,
                    )
                return None
        else:
            # Non-streaming mode (original behavior)
            try:
                msg = llm.invoke(messages)
            except Exception as e:
                if self._run_id:
                    trace_exception(
                        run_id=self._run_id,
                        ui_debug=self._ui_debug,
                        where=f"llm.invoke_text[{op}][{role}]",
                        exc=e,
                    )
                return None
            
            # Extract thinking/reasoning content from response_metadata if available
            # (e.g., for Gemini 2.0 Flash Thinking models)
            thinking_content = None
            response_metadata = getattr(msg, "response_metadata", None)
            if isinstance(response_metadata, dict):
                # Check for thinking/reasoning content in various possible fields
                thinking_content = (
                    response_metadata.get("thinking") or
                    response_metadata.get("reasoning") or
                    response_metadata.get("reasoning_content") or
                    response_metadata.get("cached_content")  # Some models use this
                )
            
            # Also check if the message itself has thinking content (e.g., in additional_kwargs)
            if thinking_content is None:
                additional_kwargs = getattr(msg, "additional_kwargs", None)
                if isinstance(additional_kwargs, dict):
                    thinking_content = (
                        additional_kwargs.get("thinking") or
                        additional_kwargs.get("reasoning") or
                        additional_kwargs.get("reasoning_content")
                    )
            
            # Get the main content
            content = getattr(msg, "content", None)
            main_text = content.strip() if isinstance(content, str) and content.strip() else ""

            if self._run_id:
                trace_reasoning_to_file(run_id=self._run_id, op=op, role=role, text=(thinking_content or ""))
            
            # Combine thinking content with main content if available
            if isinstance(thinking_content, str) and thinking_content.strip():
                # Prepend thinking content to the main answer
                combined = f"[思考过程]\n{thinking_content.strip()}\n\n[回答]\n{main_text}"
                return combined if combined.strip() else None
            
            return main_text if main_text else None


def raise_on_none(value: Any, *, message: str) -> Any:
    """Small helper to convert None-returning calls into exceptions when desired."""

    if value is None:
        raise LlmInvocationError(message)
    return value
