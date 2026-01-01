from __future__ import annotations

import os
import re
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError, model_validator

from .debug_trace import trace_exception, trace_line
from .protocol_v2 import (
    DeleteObjectsInput,
    ExecGeogebraCommandsInput,
    EvalExpressionInput,
    GetCanvasStateInput,
)


ALLOWED_TOOL_NAMES = {"get_canvas_state", "exec_geogebra_commands", "eval_expression", "delete_objects"}


class ActDecision(BaseModel):
    next_step_kind: Literal["tool", "final"]
    next_tool_name: str | None = None
    next_tool_input: dict[str, Any] | None = None
    answer_text: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> "ActDecision":
        if self.next_step_kind == "tool":
            if not self.next_tool_name:
                raise ValueError("next_tool_name is required when next_step_kind=tool")
            if self.next_tool_name not in ALLOWED_TOOL_NAMES:
                raise ValueError(f"unsupported tool: {self.next_tool_name}")
            if not isinstance(self.next_tool_input, dict):
                raise ValueError("next_tool_input is required when next_step_kind=tool")

        if self.next_step_kind == "final":
            if not isinstance(self.answer_text, str) or not self.answer_text.strip():
                raise ValueError("answer_text is required when next_step_kind=final")

        return self


@dataclass(frozen=True)
class LlmConfig:
    api_key: str = field(repr=False)
    base_url: str | None
    model: str
    temperature: float
    timeout_s: float


def _preview_text(value: Any, *, limit: int = 320) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    return s if len(s) <= limit else (s[:limit] + "…")


def _trace_llm_event(*, run_id: str | None, ui_debug: bool, name: str, data: dict[str, Any]) -> None:
    if not run_id:
        return
    trace_line(run_id=run_id, ui_debug=ui_debug, kind="llm", payload={"name": name, "data": data})


def _extract_usage_metadata(msg: Any) -> dict[str, Any] | None:
    usage = getattr(msg, "usage_metadata", None)
    if isinstance(usage, dict):
        return usage

    response_metadata = getattr(msg, "response_metadata", None)
    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage")
        if isinstance(token_usage, dict):
            return token_usage
        usage2 = response_metadata.get("usage")
        if isinstance(usage2, dict):
            return usage2

    return None


def _build_runnable_config(*, run_id: str | None, op: str, role: str) -> dict[str, Any] | None:
    if not run_id:
        return None
    return {
        "tags": ["geogebra-v2", op, f"role:{role}"],
        "metadata": {"run_id": run_id, "role": role},
    }


def _strip_wrapping_quotes(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s


_ENV_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env_refs(raw: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return os.getenv(key) or ""

    return _ENV_REF_RE.sub(repl, raw)


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


_ENV_FILES_LOADED = False


def _repo_root() -> Path:
    # apps/api/app/llm_decider.py -> repo root
    return Path(__file__).resolve().parents[3]


def _load_env_file(path: Path) -> None:
    try:
        from dotenv import dotenv_values  # type: ignore
    except Exception:
        return

    try:
        # python-dotenv interpolates ${VAR} by default, which breaks our JSON env values that
        # intentionally reference other vars (e.g. ${VECTORENGINE_API_KEY}) that may be loaded
        # from a later env file. We want to keep the raw string and expand refs ourselves later.
        values = dotenv_values(path, interpolate=False)
    except Exception:
        return

    for key, value in values.items():
        if value is None:
            continue
        os.environ.setdefault(key, str(value))


def _maybe_alias_langsmith_env_vars() -> None:
    # LangChain/LangSmith commonly use LANGCHAIN_* env vars for tracing, but our docs may mention
    # LANGSMITH_* for convenience. Support both (do not override existing LANGCHAIN_* values).
    ls_key = (os.getenv("LANGSMITH_API_KEY") or "").strip()
    if ls_key and not (os.getenv("LANGCHAIN_API_KEY") or "").strip():
        os.environ.setdefault("LANGCHAIN_API_KEY", ls_key)

    ls_project = (os.getenv("LANGSMITH_PROJECT") or "").strip()
    if ls_project and not (os.getenv("LANGCHAIN_PROJECT") or "").strip():
        os.environ.setdefault("LANGCHAIN_PROJECT", ls_project)

    ls_tracing = (os.getenv("LANGSMITH_TRACING") or "").strip()
    if ls_tracing and not (os.getenv("LANGCHAIN_TRACING_V2") or "").strip():
        os.environ.setdefault("LANGCHAIN_TRACING_V2", ls_tracing)


def _maybe_load_env_files() -> None:
    global _ENV_FILES_LOADED
    if _ENV_FILES_LOADED:
        return
    _ENV_FILES_LOADED = True

    override = os.getenv("V2_ENV_FILE")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))

    root = _repo_root()
    candidates.extend([root / ".env.local", root / ".env"])

    # v1 sibling worktree fallback (local dev convenience)
    candidates.extend(
        [
            root.parent / "geogebra-ai-drawer" / ".env.local",
            root.parent / "geogebra-ai-drawer" / ".env",
        ]
    )

    for path in candidates:
        if path.is_file():
            _load_env_file(path)

    _maybe_alias_langsmith_env_vars()


def load_llm_config_for_role(*, role: str | None) -> LlmConfig | None:
    _maybe_load_env_files()

    def read_temperature_timeout() -> tuple[float, float]:
        try:
            temperature = float(os.getenv("V2_LLM_TEMPERATURE") or "0")
        except ValueError:
            temperature = 0.0

        timeout_env = os.getenv("V2_LLM_TIMEOUT_S") or ""
        if not timeout_env:
            timeout_ms = os.getenv("LLM_TIMEOUT_MS") or ""
            if timeout_ms:
                try:
                    timeout_env = str(float(timeout_ms) / 1000.0)
                except ValueError:
                    timeout_env = ""
        if not timeout_env:
            timeout_env = "20"

        try:
            timeout_s = float(timeout_env)
        except ValueError:
            timeout_s = 20.0

        return temperature, timeout_s

    def parse_json_env(key: str) -> Any | None:
        raw = os.getenv(key)
        if not raw:
            return None
        try:
            expanded = _expand_env_refs(_strip_wrapping_quotes(raw))
            return json.loads(expanded)
        except Exception:
            return None

    def load_from_explicit_key(api_key: str) -> LlmConfig | None:
        model = os.getenv("V2_LLM_MODEL") or os.getenv("OPENAI_MODEL") or ""
        if not model.strip():
            return None

        base_url = (
            os.getenv("V2_LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
            or None
        )

        temperature, timeout_s = read_temperature_timeout()
        return LlmConfig(
            api_key=api_key,
            base_url=base_url,
            model=model.strip(),
            temperature=temperature,
            timeout_s=timeout_s,
        )

    def load_from_aliases(*, role: str) -> LlmConfig | None:
        aliases = parse_json_env("LLM_MODEL_ALIASES_JSON")
        role_bindings = parse_json_env("LLM_ROLE_BINDINGS_JSON")
        if not isinstance(aliases, list) or not isinstance(role_bindings, dict):
            return None

        alias_id = role_bindings.get(role)
        if not isinstance(alias_id, str) or not alias_id.strip():
            return None

        chosen: dict[str, Any] | None = None
        for entry in aliases:
            if isinstance(entry, dict) and entry.get("id") == alias_id:
                chosen = entry
                break
        if chosen is None:
            return None

        provider = str(chosen.get("provider") or "")
        if provider not in {"openai", "openai-compatible"}:
            return None

        api_key = str(chosen.get("apiKey") or "").strip()
        if not api_key:
            return None

        model = str(chosen.get("modelId") or chosen.get("model") or "").strip()
        if not model:
            models = chosen.get("models")
            if isinstance(models, dict):
                model = str(models.get("main") or "").strip()
        if not model:
            return None

        base_url_value = chosen.get("baseURL") or chosen.get("baseUrl") or chosen.get("base_url")
        base_url = str(base_url_value).strip() if isinstance(base_url_value, str) else None
        if provider == "openai-compatible" and not base_url:
            return None

        temperature, timeout_s = read_temperature_timeout()
        return LlmConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    # 1) Explicit v2-style config (direct env vars) — for deployments.
    explicit_api_key = (os.getenv("V2_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if explicit_api_key:
        explicit_cfg = load_from_explicit_key(explicit_api_key)
        if explicit_cfg is not None:
            return explicit_cfg

    # 2) Reuse v1-style aliases + role bindings — recommended for local dev.
    resolved_role = (role or os.getenv("V2_LLM_ROLE") or "main").strip() or "main"
    cfg = load_from_aliases(role=resolved_role)
    if cfg is not None:
        return cfg

    # 3) Backward-compatible: reuse v1-style endpoints JSON if present.
    endpoints = parse_json_env("LLM_ENDPOINTS_JSON")
    if isinstance(endpoints, list):
        preferred_id = os.getenv("V2_LLM_ENDPOINT_ID") or os.getenv("LLM_AUTO_PREFERRED_ENDPOINT_ID") or ""
        candidates = []
        for ep in endpoints:
            if not isinstance(ep, dict):
                continue
            provider = str(ep.get("provider") or "")
            if provider not in {"openai", "openai-compatible"}:
                continue
            api_key_value = ep.get("apiKey")
            if not isinstance(api_key_value, str) or not api_key_value.strip():
                continue
            model = None
            models = ep.get("models")
            if isinstance(models, dict) and isinstance(models.get("main"), str):
                model = models["main"]
            if not model:
                continue
            base_url = ep.get("baseURL")
            base_url_str = str(base_url) if isinstance(base_url, str) and base_url.strip() else None
            ep_id = str(ep.get("id") or "")
            candidates.append(
                {
                    "id": ep_id,
                    "api_key": api_key_value.strip(),
                    "base_url": base_url_str,
                    "model": str(model).strip(),
                    "provider": provider,
                }
            )

        if candidates:
            chosen = None
            if preferred_id:
                for c in candidates:
                    if c["id"] == preferred_id:
                        chosen = c
                        break
            if chosen is None:
                chosen = candidates[0]

            if chosen["provider"] == "openai-compatible" and not chosen["base_url"]:
                return None

            temperature, timeout_s = read_temperature_timeout()
            return LlmConfig(
                api_key=chosen["api_key"],
                base_url=chosen["base_url"],
                model=chosen["model"],
                temperature=temperature,
                timeout_s=timeout_s,
            )

    # 4) Convenience: allow reusing VectorEngine key if you also set V2_LLM_BASE_URL + V2_LLM_MODEL.
    vectorengine_key = (os.getenv("VECTORENGINE_API_KEY") or "").strip()
    if vectorengine_key:
        return load_from_explicit_key(vectorengine_key)

    return None


def load_llm_config(role: str | None = None) -> LlmConfig | None:
    # Backward compatible function name used across the codebase.
    return load_llm_config_for_role(role=role)


@lru_cache(maxsize=8)
def _build_llm(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    temperature: float,
    timeout_s: float,
) -> ChatOpenAI:
    kwargs: dict[str, Any] = {
        "model_name": model,
        "temperature": temperature,
        "openai_api_key": api_key,
        "request_timeout": timeout_s,
        # Many OpenAI-compatible gateways don't support the Responses API yet.
        "use_responses_api": False,
    }
    if base_url:
        kwargs["openai_api_base"] = base_url
    return ChatOpenAI(**kwargs)


def _compact_canvas_objects(tool_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not tool_results:
        return []

    for entry in reversed(tool_results):
        if entry.get("tool_name") != "get_canvas_state":
            continue
        resume = entry.get("resume")
        if not isinstance(resume, dict):
            continue
        output = resume.get("output")
        if not isinstance(output, dict):
            continue
        objects = output.get("objects")
        if not isinstance(objects, list):
            continue

        compact: list[dict[str, Any]] = []
        for obj in objects[:12]:
            if not isinstance(obj, dict):
                continue
            compact.append(
                {
                    "name": obj.get("name"),
                    "type": obj.get("type"),
                    "visible": obj.get("visible"),
                    "valueString": obj.get("valueString"),
                    "definitionString": obj.get("definitionString"),
                }
            )
        return compact

    return []


def _compact_exec_commands(tool_results: list[dict[str, Any]] | None) -> list[str]:
    if not tool_results:
        return []

    for entry in reversed(tool_results):
        if entry.get("tool_name") != "exec_geogebra_commands":
            continue
        tool_input = entry.get("input")
        if isinstance(tool_input, dict) and isinstance(tool_input.get("commands"), list):
            return [str(x) for x in tool_input.get("commands")[:12]]

    return []


@lru_cache(maxsize=8)
def _load_prompt_asset(rel_path: str) -> str:
    root = _repo_root()
    path = root / rel_path
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _clean_commands(commands: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for c in commands:
        if not isinstance(c, str):
            continue
        s = c.strip()
        if not s:
            continue
        # Never allow tool names to leak into commands.
        if "get_canvas_state" in s or "exec_geogebra_commands" in s or "eval_expression" in s:
            continue
        cleaned.append(s)
    return cleaned[:80]


def generate_geogebra_commands(
    *,
    user_text: str,
    tool_calls_used: int,
    tool_calls_limit: int,
    tool_results: list[dict[str, Any]] | None,
    runtime_feedback: str | None,
    run_id: str | None = None,
    ui_debug: bool = False,
) -> list[str] | None:
    role = "repair" if (runtime_feedback or "").strip() else "main"
    cfg = load_llm_config(role=role)
    if cfg is None:
        _trace_llm_event(run_id=run_id, ui_debug=ui_debug, name="command_gen.config_missing", data={"role": role})
        return None

    llm = _build_llm(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
        timeout_s=cfg.timeout_s,
    )

    remaining = max(0, int(tool_calls_limit) - int(tool_calls_used))
    canvas_objects = _compact_canvas_objects(tool_results)
    commandbook = _load_prompt_asset("prompts/commandbook.json")
    constraints = _load_prompt_asset("prompts/geogebra-constraints.md")

    _trace_llm_event(
        run_id=run_id,
        ui_debug=ui_debug,
        name="command_gen.start",
        data={
            "role": role,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "remaining_tool_calls": remaining,
            "user_text_preview": _preview_text(user_text, limit=160),
            "has_runtime_feedback": bool((runtime_feedback or "").strip()),
            "canvas_objects_compact_count": len(canvas_objects),
        },
    )
    t0 = time.time()

    system = SystemMessage(
        content=(
            "You are GeoGebraTutor.\n"
            "You generate GeoGebra Classic commands for a browser canvas.\n"
            "Follow constraints and avoid fragile constructions.\n"
            "\n"
            "Rules:\n"
            f"- Remaining frontend tool calls (this run): {remaining}\n"
            "- Return a COMPLETE command list for the user's request (not a patch).\n"
            "- Prefer stable labels (A,B,C,O,c,T,...) so we can verify and refer to them.\n"
            "- For key objects (circle/triangle/important lines), ALWAYS use explicit assignment labels (e.g. c = Circle(...), T = Polygon(...)).\n"
            "- Avoid Point(circle) that can coincide with existing points; prefer Rotate/Intersect/explicit construction when choosing points on a circle.\n"
            "- If you need to delete and redraw, include Delete(...) commands ONLY if you are sure; otherwise regenerate cleanly.\n"
            "\n"
            "Output format (STRICT):\n"
            "Return ONLY a JSON object: {\"commands\": string[]}.\n"
            "No markdown. No extra keys.\n"
            "\n"
            f"{constraints}\n"
            "\n"
            "Commandbook (JSON, reference):\n"
            f"{commandbook}\n"
        )
    )

    feedback_text = (runtime_feedback or "").strip()
    human = HumanMessage(
        content=(
            f"user_text: {user_text}\n"
            f"tool_calls_used: {tool_calls_used}\n"
            f"tool_calls_limit: {tool_calls_limit}\n"
            f"canvas_objects (latest, up to 12): {canvas_objects}\n"
            f"runtime_feedback: {feedback_text}\n"
        )
    )

    structured = llm.with_structured_output(ExecGeogebraCommandsInput)

    def invoke_structured(messages: list[Any]) -> ExecGeogebraCommandsInput | None:
        try:
            result = structured.invoke(messages, config=_build_runnable_config(run_id=run_id, op="command_gen", role=role))
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where="generate_geogebra_commands.structured_invoke", exc=e)
            return None
        if isinstance(result, ExecGeogebraCommandsInput):
            return result
        return None

    def invoke_json_fallback() -> list[str] | None:
        try:
            msg = llm.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="command_gen", role=role))
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where="generate_geogebra_commands.json_invoke", exc=e)
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
        commands = payload.get("commands")
        if not isinstance(commands, list):
            return None
        return _clean_commands(commands)

    result = invoke_structured([system, human])
    if result is not None:
        commands = _clean_commands(result.commands)
        took_ms = int((time.time() - t0) * 1000)
        _trace_llm_event(
            run_id=run_id,
            ui_debug=ui_debug,
            name="command_gen.ok",
            data={
                "mode": "structured_output",
                "took_ms": took_ms,
                "commands_count": len(commands),
                "commands_preview": commands[:8],
            },
        )
        return commands if commands else None

    fallback = invoke_json_fallback()
    took_ms = int((time.time() - t0) * 1000)
    _trace_llm_event(
        run_id=run_id,
        ui_debug=ui_debug,
        name="command_gen.result",
        data={
            "mode": "json_fallback" if fallback else "none",
            "took_ms": took_ms,
            "commands_count": len(fallback) if fallback else 0,
            "commands_preview": (fallback or [])[:8],
        },
    )
    return fallback if fallback else None


def generate_final_answer(
    *,
    user_text: str,
    tool_calls_used: int,
    tool_calls_limit: int,
    tool_results: list[dict[str, Any]] | None,
    run_id: str | None = None,
    ui_debug: bool = False,
) -> str | None:
    cfg = load_llm_config(role="main")
    if cfg is None:
        _trace_llm_event(run_id=run_id, ui_debug=ui_debug, name="final.config_missing", data={"role": "main"})
        return None

    llm = _build_llm(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
        timeout_s=cfg.timeout_s,
    )

    canvas_objects = _compact_canvas_objects(tool_results)
    executed_commands = _compact_exec_commands(tool_results)

    _trace_llm_event(
        run_id=run_id,
        ui_debug=ui_debug,
        name="final.start",
        data={
            "role": "main",
            "model": cfg.model,
            "base_url": cfg.base_url,
            "user_text_preview": _preview_text(user_text, limit=160),
            "tool_calls_used": tool_calls_used,
            "tool_calls_limit": tool_calls_limit,
            "executed_commands_count": len(executed_commands),
            "canvas_objects_compact_count": len(canvas_objects),
        },
    )
    t0 = time.time()

    system = SystemMessage(
        content=(
            "You are a GeoGebra tutor.\n"
            "Write a final response in Chinese for a child.\n"
            "Do NOT use emojis.\n"
            "Be strictly truthful: ONLY describe drawings that are supported by executed_commands/canvas_objects.\n"
            "If the user asked to draw something but it is NOT present, say it was not drawn yet and what you can do next.\n"
            "If the user asked to draw, explain what you actually drew in short steps and mention object names when helpful.\n"
            "If the user asked for explanation only, do NOT talk about drawing unless the user asked.\n"
            "Keep it short and clear.\n"
        )
    )

    human = HumanMessage(
        content=(
            f"user_text: {user_text}\n"
            f"tool_calls_used: {tool_calls_used}\n"
            f"tool_calls_limit: {tool_calls_limit}\n"
            f"executed_commands (latest, up to 12): {executed_commands}\n"
            f"canvas_objects (latest, up to 12): {canvas_objects}\n"
        )
    )

    try:
        msg = llm.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="final", role="main"))
    except Exception as e:
        if run_id:
            trace_exception(run_id=run_id, ui_debug=ui_debug, where="generate_final_answer.invoke", exc=e)
        return None

    content = getattr(msg, "content", None)
    if not isinstance(content, str):
        took_ms = int((time.time() - t0) * 1000)
        _trace_llm_event(
            run_id=run_id,
            ui_debug=ui_debug,
            name="final.bad_response",
            data={
                "took_ms": took_ms,
                "reason": "non_string_content",
                "content_type": type(content).__name__,
                "usage": _extract_usage_metadata(msg),
            },
        )
        return None

    text = content.strip()
    if not text:
        took_ms = int((time.time() - t0) * 1000)
        _trace_llm_event(
            run_id=run_id,
            ui_debug=ui_debug,
            name="final.bad_response",
            data={
                "took_ms": took_ms,
                "reason": "empty_text",
                "usage": _extract_usage_metadata(msg),
            },
        )
        return None

    took_ms = int((time.time() - t0) * 1000)
    _trace_llm_event(
        run_id=run_id,
        ui_debug=ui_debug,
        name="final.ok",
        data={
            "took_ms": took_ms,
            "text_preview": _preview_text(text, limit=320),
            "usage": _extract_usage_metadata(msg),
        },
    )

    return text


def decide_next_step(
    *,
    user_text: str,
    tool_calls_used: int,
    tool_calls_limit: int,
    tool_results: list[dict[str, Any]] | None,
    canvas_diagnostics: dict[str, Any] | None = None,
    repair_hint: str | None = None,
) -> ActDecision | None:
    cfg = load_llm_config(role="main")
    if cfg is None:
        return None

    llm = _build_llm(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
        timeout_s=cfg.timeout_s,
    )

    remaining = max(0, int(tool_calls_limit) - int(tool_calls_used))
    canvas_objects = _compact_canvas_objects(tool_results)
    diagnostics = canvas_diagnostics or {}
    repair_hint_text = (repair_hint or "").strip()

    system = SystemMessage(
        content=(
            "You are a GeoGebra tutor.\n"
            "You cannot directly access GeoGebra; you must request a frontend tool when needed.\n"
            "You must follow the output schema strictly.\n"
            "\n"
            "Available tools:\n"
            "- get_canvas_state: input { include: [\"objects\"] }\n"
            "- eval_expression: input { expression: string }\n"
            "- exec_geogebra_commands: input { commands: string[] }\n"
            "\n"
            "Rules:\n"
            f"- You have {remaining} tool calls remaining in this run.\n"
            "- If remaining tool calls is 0, you MUST choose next_step_kind=final.\n"
            "- Tool calls are limited, so plan ahead.\n"
            "- If the user asks to draw multiple things, try to include ALL required commands in as few exec_geogebra_commands calls as possible (ideally one).\n"
            "- If the canvas already has relevant objects (e.g. a circle), prefer reusing them instead of creating duplicates unless the user asks to restart.\n"
            "- Prefer giving explicit labels to important objects (e.g. T = Polygon(A, B, C)) so the user can refer to them.\n"
            "- After drawing/modifying, verify the result using canvas_objects and/or eval_expression.\n"
            "- If the result does not match the user's request or looks degenerate (e.g. zero-length segments / zero-area polygons), you MUST fix it before finishing (tool budget permitting).\n"
            "- Only request exec_geogebra_commands if the user explicitly asks to draw/create/modify objects on the canvas.\n"
            "- If the user complains that a requested drawing is missing/wrong, treat it as a request to fix the drawing (use exec_geogebra_commands if needed).\n"
            "- If the user asks for explanation only (no drawing), choose next_step_kind=final.\n"
            "- If the user says do NOT draw, do NOT call exec_geogebra_commands.\n"
            "- If you request a tool, do NOT include any explanation in the tool input.\n"
            "- GeoGebra commands must be plain commands only; no tool names inside commands.\n"
            "- If you can answer without more tools, choose next_step_kind=final.\n"
            "- final.answer_text must be in Chinese and child-friendly.\n"
            "- Do NOT use emojis.\n"
            "- If repair_hint is present, you MUST choose next_step_kind=tool with exec_geogebra_commands to fix the issue.\n"
            "- When next_step_kind=final, always provide answer_text.\n"
        )
    )

    human = HumanMessage(
        content=(
            f"user_text: {user_text}\n"
            f"tool_calls_used: {tool_calls_used}\n"
            f"tool_calls_limit: {tool_calls_limit}\n"
            f"canvas_objects (latest, up to 12): {canvas_objects}\n"
            f"canvas_diagnostics: {diagnostics}\n"
            f"repair_hint: {repair_hint_text}\n"
            "\n"
            "Decide the next step."
        )
    )

    structured = llm.with_structured_output(ActDecision)

    def invoke_structured(messages: list[Any]) -> ActDecision | None:
        try:
            result = structured.invoke(messages)
        except Exception:
            return None
        if isinstance(result, ActDecision):
            return result
        return None

    def invoke_json_fallback() -> ActDecision | None:
        json_human = HumanMessage(
            content=(
                f"user_text: {user_text}\n"
                f"tool_calls_used: {tool_calls_used}\n"
                f"tool_calls_limit: {tool_calls_limit}\n"
                f"canvas_objects (latest, up to 12): {canvas_objects}\n"
                "\n"
                "Return ONLY a JSON object that matches this schema:\n"
                "{\n"
                '  "next_step_kind": "tool" | "final",\n'
                '  "next_tool_name": "get_canvas_state" | "exec_geogebra_commands" | null,\n'
                '  "next_tool_input": object | null,\n'
                '  "answer_text": string | null\n'
                "}\n"
                "No markdown. No extra keys.\n"
            )
        )
        try:
            msg = llm.invoke([system, json_human])
        except Exception:
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

        try:
            return ActDecision.model_validate(payload)
        except Exception:
            return None

    decision = invoke_structured([system, human]) or invoke_json_fallback()
    if decision is None:
        return None

    if remaining == 0 and decision.next_step_kind == "tool":
        # Retry once with a stronger constraint reminder (some gateways are loose on JSON/schema).
        retry_human = HumanMessage(
            content=(
                f"user_text: {user_text}\n"
                f"tool_calls_used: {tool_calls_used}\n"
                f"tool_calls_limit: {tool_calls_limit}\n"
                f"canvas_objects (latest, up to 12): {canvas_objects}\n"
                "\n"
                "IMPORTANT: Remaining tool calls is 0, so you MUST output next_step_kind=final with answer_text."
            )
        )
        decision = invoke_structured([system, retry_human]) or decision

    if remaining == 0 and decision.next_step_kind == "tool":
        return None

    if decision.next_step_kind == "tool":
        try:
            if decision.next_tool_name == "get_canvas_state":
                GetCanvasStateInput.model_validate(decision.next_tool_input)
            elif decision.next_tool_name == "eval_expression":
                EvalExpressionInput.model_validate(decision.next_tool_input)
            elif decision.next_tool_name == "exec_geogebra_commands":
                ExecGeogebraCommandsInput.model_validate(decision.next_tool_input)
            elif decision.next_tool_name == "delete_objects":
                DeleteObjectsInput.model_validate(decision.next_tool_input)
        except ValidationError:
            return None

    return decision
