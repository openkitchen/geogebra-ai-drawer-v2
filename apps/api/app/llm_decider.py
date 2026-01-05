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
    EvalNumericInput,
    GetCanvasStateInput,
)


ALLOWED_TOOL_NAMES = {"get_canvas_state", "exec_geogebra_commands", "eval_expression", "eval_numeric", "delete_objects"}


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


_SINGLE_FENCED_BLOCK_RE = re.compile(r"^```([^\r\n]*)\r?\n([\s\S]*?)\r?\n```$")


def _unwrap_single_fenced_block(text: str) -> tuple[str, dict[str, Any] | None]:
    """If the entire string is a single fenced code block (e.g. ```plaintext ... ```), unwrap it.

    Our web UI currently renders plain text (not Markdown), so showing fences literally is noisy.
    """
    raw = (text or "").strip()
    if not raw:
        return raw, None
    m = _SINGLE_FENCED_BLOCK_RE.match(raw)
    if not m:
        return text, None
    lang = (m.group(1) or "").strip().lower() or None
    body = (m.group(2) or "").strip()
    return body, {"kind": "fence_unwrap", "lang": lang}


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

    # Allow chained env refs, e.g. MOONSHOT_API_KEY=${KIMI_API_KEY}.
    # Expand a few rounds to avoid infinite loops on accidental cycles.
    out = raw
    for _ in range(6):
        expanded = _ENV_REF_RE.sub(repl, out)
        if expanded == out:
            break
        out = expanded
    return out


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

    ls_endpoint = (os.getenv("LANGSMITH_ENDPOINT") or "").strip()
    if ls_endpoint and not (os.getenv("LANGCHAIN_ENDPOINT") or "").strip():
        os.environ.setdefault("LANGCHAIN_ENDPOINT", ls_endpoint)


def _maybe_load_env_files() -> None:
    global _ENV_FILES_LOADED
    if _ENV_FILES_LOADED:
        return
    _ENV_FILES_LOADED = True

    root = _repo_root()
    # Always prefer this worktree's env files.
    primary: list[Path] = [root / ".env.local", root / ".env"]
    for path in primary:
        if path.is_file():
            _load_env_file(path)

    # Optional: load an additional env file to fill missing values (e.g. secrets).
    # NOTE: this does NOT override existing env vars or values already loaded above.
    override = (os.getenv("V2_ENV_FILE") or "").strip()
    if override:
        override_path = Path(override)
        if not override_path.is_absolute():
            # Treat relative override paths as repo-root relative, not CWD relative.
            override_path = root / override_path
        if override_path.is_file():
            _load_env_file(override_path)

    _maybe_alias_langsmith_env_vars()


def _parse_csv_env(key: str) -> list[str]:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return []
    parts: list[str] = []
    for seg in raw.split(","):
        s = seg.strip()
        if s:
            parts.append(s)
    dedup: list[str] = []
    for r in parts:
        if r not in dedup:
            dedup.append(r)
    return dedup


def _fallback_roles() -> list[str]:
    _maybe_load_env_files()

    explicit = _parse_csv_env("V2_LLM_FALLBACK_ROLES")
    if explicit:
        return explicit

    # If v1-style role routing is present, try common roles that might be configured.
    raw_bindings = os.getenv("LLM_ROLE_BINDINGS_JSON") or ""
    if raw_bindings.strip():
        try:
            expanded = _expand_env_refs(_strip_wrapping_quotes(raw_bindings))
            bindings = json.loads(expanded)
        except Exception:
            bindings = None

        if isinstance(bindings, dict):
            order = ["fast", "fallback", "repair", "gemini_fast", "gemini_think", "main"]
            roles = [r for r in order if isinstance(bindings.get(r), str) and r.strip()]
            if roles:
                return roles

    # Last resort: try "fast" if aliases exist (even if it may not be bound).
    if (os.getenv("LLM_MODEL_ALIASES_JSON") or "").strip():
        return ["fast"]

    return []


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
    cfg = load_llm_config_for_role(role=role)
    if cfg is not None or role is not None:
        return cfg

    # If the default role isn't configured, fall back to any configured role.
    for r in _fallback_roles():
        cfg2 = load_llm_config_for_role(role=r)
        if cfg2 is not None:
            return cfg2

    return None


@lru_cache(maxsize=8)
def _build_llm(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
    temperature: float,
    timeout_s: float,
) -> ChatOpenAI:
    # NOTE: Use the new langchain-openai parameter names so timeout/retry behavior is effective.
    kwargs: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "api_key": api_key,
        "timeout": timeout_s,
        # We already implement role fallbacks at a higher level; keep low-level retries minimal.
        "max_retries": 0,
        # Many OpenAI-compatible gateways don't support the Responses API yet.
        "use_responses_api": False,
    }
    if base_url:
        kwargs["base_url"] = base_url
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


def _json_compact(value: Any, *, max_chars: int = 2400) -> str:
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = str(value)
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…"


def _extract_latest_canvas_objects_raw(tool_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not tool_results:
        return []

    for entry in reversed(tool_results):
        if entry.get("tool_name") != "get_canvas_state":
            continue
        resume = entry.get("resume")
        if not isinstance(resume, dict) or resume.get("ok") is not True:
            continue
        output = resume.get("output")
        if not isinstance(output, dict):
            continue
        objects = output.get("objects")
        if not isinstance(objects, list):
            continue
        return [o for o in objects if isinstance(o, dict)]

    return []


def _count_canvas_object_types(objects: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in objects:
        typ = obj.get("type")
        if not isinstance(typ, str) or not typ.strip():
            continue
        key = typ.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _compact_action_ledger(tool_results: list[dict[str, Any]] | None, *, max_actions: int = 6) -> list[dict[str, Any]]:
    if not tool_results:
        return []

    actions: list[dict[str, Any]] = []
    for entry in reversed(tool_results):
        tool_name = entry.get("tool_name")
        if tool_name not in {"exec_geogebra_commands", "delete_objects"}:
            continue

        resume = entry.get("resume")
        ok = isinstance(resume, dict) and resume.get("ok") is True
        output = resume.get("output") if isinstance(resume, dict) else None

        action: dict[str, Any] = {
            "run_id": entry.get("run_id"),
            "tool_name": tool_name,
            "tool_call_id": entry.get("tool_call_id"),
            "ok": ok,
        }

        if tool_name == "exec_geogebra_commands":
            inp = entry.get("input")
            if isinstance(inp, dict) and isinstance(inp.get("commands"), list):
                action["commands_preview"] = [str(x) for x in inp.get("commands", [])[:8]]

            if ok and isinstance(output, dict):
                created = output.get("created_objects")
                deleted = output.get("deleted_objects")
                dialogs = output.get("dialogs")
                warnings = output.get("quality_warnings")
                if isinstance(created, list):
                    action["created_objects"] = [str(x) for x in created if isinstance(x, str) and x.strip()][:30]
                if isinstance(deleted, list):
                    action["deleted_objects"] = [str(x) for x in deleted if isinstance(x, str) and x.strip()][:30]
                if isinstance(dialogs, list):
                    action["dialogs"] = [str(x) for x in dialogs if isinstance(x, str) and x.strip()][:6]
                if isinstance(warnings, list):
                    action["quality_warnings"] = [str(x) for x in warnings if isinstance(x, str) and x.strip()][:6]

        if tool_name == "delete_objects" and ok and isinstance(output, dict):
            deleted = output.get("deleted_objects")
            failed = output.get("failed_objects")
            if isinstance(deleted, list):
                action["deleted_objects"] = [str(x) for x in deleted if isinstance(x, str) and x.strip()][:60]
            if isinstance(failed, list):
                action["failed_objects_count"] = len([x for x in failed if isinstance(x, dict)])

        actions.append(action)
        if len(actions) >= max_actions:
            break

    actions.reverse()
    return actions


def _build_created_by_map(action_ledger: list[dict[str, Any]]) -> dict[str, str]:
    created_by: dict[str, str] = {}
    for action in action_ledger:
        run_id = action.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            continue
        created = action.get("created_objects")
        if not isinstance(created, list):
            continue
        for name in created:
            if isinstance(name, str) and name.strip():
                created_by.setdefault(name.strip(), run_id.strip())
    return created_by


def _build_object_provenance(*, canvas_objects: list[dict[str, Any]], action_ledger: list[dict[str, Any]]) -> dict[str, str]:
    created_by = _build_created_by_map(action_ledger)
    out: dict[str, str] = {}
    for obj in canvas_objects:
        name = obj.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        out[name.strip()] = created_by.get(name.strip(), "unknown")
    return out


def _extract_canvas_diff(tool_results: list[dict[str, Any]] | None, *, max_names: int = 20) -> dict[str, Any] | None:
    if not tool_results:
        return None

    latest_entry: dict[str, Any] | None = None
    latest_objects: list[dict[str, Any]] | None = None
    for entry in reversed(tool_results):
        if entry.get("tool_name") != "get_canvas_state":
            continue
        resume = entry.get("resume")
        if not isinstance(resume, dict) or resume.get("ok") is not True:
            continue
        output = resume.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("objects"), list):
            continue
        latest_entry = entry
        latest_objects = [o for o in output.get("objects", []) if isinstance(o, dict)]
        break

    if latest_entry is None or latest_objects is None:
        return None

    latest_run_id = latest_entry.get("run_id")

    prev_objects: list[dict[str, Any]] | None = None
    for entry in reversed(tool_results):
        if entry is latest_entry:
            continue
        if entry.get("tool_name") != "get_canvas_state":
            continue
        if latest_run_id and entry.get("run_id") == latest_run_id:
            continue
        resume = entry.get("resume")
        if not isinstance(resume, dict) or resume.get("ok") is not True:
            continue
        output = resume.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("objects"), list):
            continue
        prev_objects = [o for o in output.get("objects", []) if isinstance(o, dict)]
        break

    if prev_objects is None:
        return None

    def compact(o: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": o.get("name"),
            "type": o.get("type"),
            "visible": o.get("visible"),
            "valueString": o.get("valueString"),
            "definitionString": o.get("definitionString"),
        }

    prev_by_name = {str(o.get("name")): compact(o) for o in prev_objects if isinstance(o.get("name"), str)}
    latest_by_name = {str(o.get("name")): compact(o) for o in latest_objects if isinstance(o.get("name"), str)}

    prev_names = set(prev_by_name.keys())
    latest_names = set(latest_by_name.keys())

    new_names = sorted(list(latest_names - prev_names))[:max_names]
    removed_names = sorted(list(prev_names - latest_names))[:max_names]

    changed: list[dict[str, Any]] = []
    for name in sorted(list(prev_names & latest_names)):
        a = prev_by_name.get(name) or {}
        b = latest_by_name.get(name) or {}
        fields = ["type", "visible", "valueString", "definitionString"]
        changed_fields = [f for f in fields if a.get(f) != b.get(f)]
        if changed_fields:
            changed.append({"name": name, "changed_fields": changed_fields})
        if len(changed) >= max_names:
            break

    return {
        "new_objects": new_names,
        "removed_objects": removed_names,
        "changed_objects": changed,
    }


@lru_cache(maxsize=8)
def _load_prompt_asset(rel_path: str) -> str:
    root = _repo_root()
    path = root / rel_path
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


@lru_cache(maxsize=8)
def _load_prompt_dir(rel_dir: str, *, suffix: str = ".md") -> list[str]:
    root = _repo_root()
    dir_path = root / rel_dir
    try:
        files = sorted([p for p in dir_path.iterdir() if p.is_file() and p.name.endswith(suffix)], key=lambda p: p.name)
    except Exception:
        return []

    parts: list[str] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if text:
            parts.append(text)
    return parts


def _compose_prompt_parts(parts: list[str]) -> str:
    cleaned = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return "\n\n---\n\n".join(cleaned)


def _format_memory_context(
    *,
    memory_summary: str | None,
    recent_messages: list[dict[str, Any]] | None,
    max_chars: int = 1600,
) -> str:
    lines: list[str] = []
    summary = (memory_summary or "").strip()
    if summary:
        lines.append("conversation_summary:")
        lines.append(summary)

    if recent_messages:
        items: list[str] = []
        for m in recent_messages[-16:]:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            text = m.get("text")
            if role not in {"user", "assistant"}:
                continue
            if not isinstance(text, str):
                continue
            t = text.strip()
            if not t:
                continue
            t = t if len(t) <= 400 else (t[:400] + "…")
            items.append(f"{role}: {t}")
        if items:
            lines.append("recent_messages:")
            lines.extend(items)

    blob = "\n".join(lines).strip()
    if not blob:
        return ""
    if len(blob) <= max_chars:
        return blob
    return blob[:max_chars] + "…"


def _clean_commands(commands: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for c in commands:
        if not isinstance(c, str):
            continue
        s = c.strip()
        if not s:
            continue
        normalized = re.sub(r"\s+", "", s).lower()
        # Never allow tool names to leak into commands.
        if (
            "get_canvas_state" in s
            or "exec_geogebra_commands" in s
            or "eval_expression" in s
            or "eval_numeric" in s
            or "delete_objects" in s
        ):
            continue
        # Disallow UI-only / JS-API-only operations. Canvas hygiene and label visibility are handled
        # deterministically in the frontend tool runner.
        if normalized.startswith(
            (
                "showlabel(",
                "setlabelvisible(",
                "label(",
                "setcaption(",
                "setcolor(",
                "setlinethickness(",
                "setlinestyle(",
                "setvisibleinview(",
                "showaxes(",
                "showgrid(",
            )
        ):
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
    memory_summary: str | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    ui_debug: bool = False,
) -> list[str] | None:
    requested_role = "repair" if (runtime_feedback or "").strip() else "main"
    phase_pack = "repair" if (runtime_feedback or "").strip() else "draw"

    remaining = max(0, int(tool_calls_limit) - int(tool_calls_used))
    canvas_objects = _compact_canvas_objects(tool_results)
    raw_objects = _extract_latest_canvas_objects_raw(tool_results)
    object_type_counts = _count_canvas_object_types(raw_objects)
    action_ledger = _compact_action_ledger(tool_results)
    object_provenance = _build_object_provenance(canvas_objects=canvas_objects, action_ledger=action_ledger)
    canvas_diff = _extract_canvas_diff(tool_results)
    memory_ctx = _format_memory_context(memory_summary=memory_summary, recent_messages=recent_messages)

    system_parts: list[str] = [
        _load_prompt_asset("prompts/v2/command_gen_system.md"),
        _load_prompt_asset("prompts/geogebra-constraints.md"),
        _load_prompt_asset(f"prompts/packs/{phase_pack}.md"),
        *_load_prompt_dir("prompts/scenarios"),
    ]
    commandbook = _load_prompt_asset("prompts/commandbook.json")
    if commandbook:
        system_parts.append("Commandbook (JSON, reference):\n" + commandbook)
    system = SystemMessage(content=_compose_prompt_parts(system_parts))

    feedback_text = (runtime_feedback or "").strip()
    human = HumanMessage(
        content=(
            f"user_text: {user_text}\n"
            + (f"{memory_ctx}\n" if memory_ctx else "")
            + f"tool_calls_used: {tool_calls_used}\n"
            + f"tool_calls_limit: {tool_calls_limit}\n"
            + f"remaining_tool_calls: {remaining}\n"
            + f"canvas_objects (latest, up to 12): {canvas_objects}\n"
            + f"canvas_object_type_counts: {_json_compact(object_type_counts, max_chars=600)}\n"
            + f"action_ledger: {_json_compact(action_ledger, max_chars=1400)}\n"
            + f"object_provenance (for canvas_objects): {_json_compact(object_provenance, max_chars=800)}\n"
            + (f"canvas_diff (prev turn -> now): {_json_compact(canvas_diff, max_chars=1200)}\n" if canvas_diff else "")
            + f"runtime_feedback: {feedback_text}\n"
        )
    )

    roles_to_try = [requested_role] + [r for r in _fallback_roles() if r != requested_role]
    roles_to_try = roles_to_try[:3]

    for role in roles_to_try:
        cfg = load_llm_config(role=role)
        if cfg is None:
            continue

        llm = _build_llm(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
            temperature=cfg.temperature,
            timeout_s=cfg.timeout_s,
        )

        _trace_llm_event(
            run_id=run_id,
            ui_debug=ui_debug,
            name="command_gen.start",
            data={
                "requested_role": requested_role,
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
        structured = llm.with_structured_output(ExecGeogebraCommandsInput)

        def invoke_structured(messages: list[Any]) -> ExecGeogebraCommandsInput | None:
            try:
                result = structured.invoke(
                    messages, config=_build_runnable_config(run_id=run_id, op="command_gen", role=role)
                )
            except Exception as e:
                if run_id:
                    trace_exception(
                        run_id=run_id,
                        ui_debug=ui_debug,
                        where=f"generate_geogebra_commands.structured_invoke[{role}]",
                        exc=e,
                    )
                return None
            if isinstance(result, ExecGeogebraCommandsInput):
                return result
            return None

        def invoke_json_fallback() -> list[str] | None:
            try:
                msg = llm.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="command_gen", role=role))
            except Exception as e:
                if run_id:
                    trace_exception(
                        run_id=run_id,
                        ui_debug=ui_debug,
                        where=f"generate_geogebra_commands.json_invoke[{role}]",
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
                    "requested_role": requested_role,
                    "role": role,
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
                "requested_role": requested_role,
                "role": role,
                "mode": "json_fallback" if fallback else "none",
                "took_ms": took_ms,
                "commands_count": len(fallback) if fallback else 0,
                "commands_preview": (fallback or [])[:8],
            },
        )

        if fallback:
            return fallback

    _trace_llm_event(
        run_id=run_id,
        ui_debug=ui_debug,
        name="command_gen.failed",
        data={"requested_role": requested_role, "roles_tried": roles_to_try},
    )
    return None


def generate_final_answer(
    *,
    user_text: str,
    tool_calls_used: int,
    tool_calls_limit: int,
    tool_results: list[dict[str, Any]] | None,
    memory_summary: str | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
    ui_debug: bool = False,
) -> str | None:
    canvas_objects = _compact_canvas_objects(tool_results)
    executed_commands = _compact_exec_commands(tool_results)
    raw_objects = _extract_latest_canvas_objects_raw(tool_results)
    object_type_counts = _count_canvas_object_types(raw_objects)
    action_ledger = _compact_action_ledger(tool_results)
    object_provenance = _build_object_provenance(canvas_objects=canvas_objects, action_ledger=action_ledger)
    canvas_diff = _extract_canvas_diff(tool_results)
    memory_ctx = _format_memory_context(memory_summary=memory_summary, recent_messages=recent_messages)

    system = SystemMessage(content=_load_prompt_asset("prompts/v2/final_system.md"))

    human = HumanMessage(
        content=(
            f"user_text: {user_text}\n"
            + (f"{memory_ctx}\n" if memory_ctx else "")
            + f"tool_calls_used: {tool_calls_used}\n"
            + f"tool_calls_limit: {tool_calls_limit}\n"
            + f"executed_commands (latest, up to 12): {executed_commands}\n"
            + f"canvas_objects (latest, up to 12): {canvas_objects}\n"
            + f"canvas_object_type_counts: {_json_compact(object_type_counts, max_chars=600)}\n"
            + f"action_ledger: {_json_compact(action_ledger, max_chars=1400)}\n"
            + f"object_provenance (for canvas_objects): {_json_compact(object_provenance, max_chars=800)}\n"
            + (f"canvas_diff (prev turn -> now): {_json_compact(canvas_diff, max_chars=1200)}\n" if canvas_diff else "")
        )
    )

    roles_to_try = ["main"] + [r for r in _fallback_roles() if r != "main"]
    roles_to_try = roles_to_try[:3]

    for role in roles_to_try:
        cfg = load_llm_config(role=role)
        if cfg is None:
            continue

        llm = _build_llm(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model,
            temperature=cfg.temperature,
            timeout_s=cfg.timeout_s,
        )

        _trace_llm_event(
            run_id=run_id,
            ui_debug=ui_debug,
            name="final.start",
            data={
                "role": role,
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
        try:
            msg = llm.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="final", role=role))
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where=f"generate_final_answer.invoke[{role}]", exc=e)
            continue

        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            took_ms = int((time.time() - t0) * 1000)
            _trace_llm_event(
                run_id=run_id,
                ui_debug=ui_debug,
                name="final.bad_response",
                data={
                    "role": role,
                    "took_ms": took_ms,
                    "reason": "non_string_content",
                    "content_type": type(content).__name__,
                    "usage": _extract_usage_metadata(msg),
                },
            )
            continue

        text = content.strip()
        if not text:
            took_ms = int((time.time() - t0) * 1000)
            _trace_llm_event(
                run_id=run_id,
                ui_debug=ui_debug,
                name="final.bad_response",
                data={
                    "role": role,
                    "took_ms": took_ms,
                    "reason": "empty_text",
                    "usage": _extract_usage_metadata(msg),
                },
            )
            continue

        # If the model wraps the whole reply in ```plaintext``` (or similar), unwrap it so the UI
        # doesn't show the fences literally.
        raw_text = text
        text, unwrap_info = _unwrap_single_fenced_block(text)

        took_ms = int((time.time() - t0) * 1000)
        _trace_llm_event(
            run_id=run_id,
            ui_debug=ui_debug,
            name="final.ok",
            data={
                "role": role,
                "took_ms": took_ms,
                "text_preview": _preview_text(text, limit=320),
                "raw_text_preview": _preview_text(raw_text, limit=320) if unwrap_info else None,
                "unwrap": unwrap_info,
                "usage": _extract_usage_metadata(msg),
            },
        )
        return text

    _trace_llm_event(
        run_id=run_id,
        ui_debug=ui_debug,
        name="final.failed",
        data={"roles_tried": roles_to_try},
    )
    return None


def decide_next_step(
    *,
    user_text: str,
    tool_calls_used: int,
    tool_calls_limit: int,
    tool_results: list[dict[str, Any]] | None,
    memory_summary: str | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
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
    raw_objects = _extract_latest_canvas_objects_raw(tool_results)
    object_type_counts = _count_canvas_object_types(raw_objects)
    action_ledger = _compact_action_ledger(tool_results)
    object_provenance = _build_object_provenance(canvas_objects=canvas_objects, action_ledger=action_ledger)
    canvas_diff = _extract_canvas_diff(tool_results)
    diagnostics = canvas_diagnostics or {}
    repair_hint_text = (repair_hint or "").strip()
    memory_ctx = _format_memory_context(memory_summary=memory_summary, recent_messages=recent_messages)

    system_text = _load_prompt_asset("prompts/v2/act_system.md")
    system = SystemMessage(content=(system_text + f"\n\nRemaining tool calls in this run: {remaining}").strip())

    human = HumanMessage(
        content=(
            f"user_text: {user_text}\n"
            + (f"{memory_ctx}\n" if memory_ctx else "")
            + f"tool_calls_used: {tool_calls_used}\n"
            + f"tool_calls_limit: {tool_calls_limit}\n"
            + f"canvas_objects (latest, up to 12): {canvas_objects}\n"
            + f"canvas_object_type_counts: {_json_compact(object_type_counts, max_chars=600)}\n"
            + f"action_ledger: {_json_compact(action_ledger, max_chars=1400)}\n"
            + f"object_provenance (for canvas_objects): {_json_compact(object_provenance, max_chars=800)}\n"
            + (f"canvas_diff (prev turn -> now): {_json_compact(canvas_diff, max_chars=1200)}\n" if canvas_diff else "")
            + f"canvas_diagnostics: {diagnostics}\n"
            + f"repair_hint: {repair_hint_text}\n"
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
                '  "next_tool_name": "get_canvas_state" | "eval_expression" | "eval_numeric" | "exec_geogebra_commands" | "delete_objects" | null,\n'
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
            elif decision.next_tool_name == "eval_numeric":
                EvalNumericInput.model_validate(decision.next_tool_input)
            elif decision.next_tool_name == "exec_geogebra_commands":
                ExecGeogebraCommandsInput.model_validate(decision.next_tool_input)
            elif decision.next_tool_name == "delete_objects":
                DeleteObjectsInput.model_validate(decision.next_tool_input)
        except ValidationError:
            return None

    return decision


class PlanSteps(BaseModel):
    steps: list[str]

    @model_validator(mode="after")
    def _validate(self) -> "PlanSteps":
        clean = [s.strip() for s in self.steps if isinstance(s, str) and s.strip()]
        if not clean:
            raise ValueError("steps must be a non-empty list of strings")
        self.steps = clean[:8]
        return self


def generate_plan(
    *,
    user_text: str,
    memory_summary: str | None,
    recent_messages: list[dict[str, Any]] | None,
    run_id: str | None = None,
    ui_debug: bool = False,
) -> list[str] | None:
    cfg = load_llm_config(role=os.getenv("V2_LLM_PLAN_ROLE") or "main")
    if cfg is None:
        return None

    llm = _build_llm(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
        timeout_s=cfg.timeout_s,
    )

    memory_ctx = _format_memory_context(memory_summary=memory_summary, recent_messages=recent_messages)
    system_text = _load_prompt_asset("prompts/v2/plan_system.md")
    system = SystemMessage(content=system_text)
    human = HumanMessage(content=f"user_text: {user_text}\n" + (f"{memory_ctx}\n" if memory_ctx else ""))

    structured = llm.with_structured_output(PlanSteps)

    def invoke_structured() -> PlanSteps | None:
        try:
            result = structured.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="plan", role="plan"))
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where="generate_plan.structured_invoke", exc=e)
            return None
        if isinstance(result, PlanSteps):
            return result
        return None

    def invoke_json_fallback() -> list[str] | None:
        try:
            msg = llm.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="plan", role="plan"))
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where="generate_plan.json_invoke", exc=e)
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
        steps = payload.get("steps")
        if not isinstance(steps, list):
            return None
        clean = [s.strip() for s in steps if isinstance(s, str) and s.strip()]
        return clean[:8] if clean else None

    out = invoke_structured()
    if out is not None:
        return out.steps
    return invoke_json_fallback()


class MemorySummary(BaseModel):
    summary: str

    @model_validator(mode="after")
    def _validate(self) -> "MemorySummary":
        s = self.summary.strip()
        if not s:
            raise ValueError("summary must be non-empty")
        self.summary = s[:4000]
        return self


def summarize_memory(
    *,
    previous_summary: str | None,
    messages: list[dict[str, Any]],
    run_id: str | None = None,
    ui_debug: bool = False,
) -> str | None:
    role = os.getenv("V2_LLM_SUMMARY_ROLE") or "fast"
    cfg = load_llm_config(role=role)
    if cfg is None:
        return None

    llm = _build_llm(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=0.0,
        timeout_s=cfg.timeout_s,
    )

    prev = (previous_summary or "").strip()
    system_text = _load_prompt_asset("prompts/v2/memory_summary_system.md")
    system = SystemMessage(content=system_text)

    # Keep the input small and structured; do not leak tool outputs here.
    chunks: list[str] = []
    if prev:
        chunks.append("previous_summary:")
        chunks.append(prev)
    chunks.append("messages_to_summarize:")
    for m in messages[-32:]:
        if not isinstance(m, dict):
            continue
        role2 = m.get("role")
        text = m.get("text")
        if role2 not in {"user", "assistant"}:
            continue
        if not isinstance(text, str):
            continue
        t = text.strip()
        if not t:
            continue
        t = t if len(t) <= 500 else (t[:500] + "…")
        chunks.append(f"{role2}: {t}")
    human = HumanMessage(content="\n".join(chunks).strip())

    structured = llm.with_structured_output(MemorySummary)

    def invoke_structured() -> MemorySummary | None:
        try:
            result = structured.invoke(
                [system, human],
                config=_build_runnable_config(run_id=run_id, op="memory_summary", role=role),
            )
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where="summarize_memory.structured_invoke", exc=e)
            return None
        if isinstance(result, MemorySummary):
            return result
        return None

    def invoke_json_fallback() -> str | None:
        try:
            msg = llm.invoke([system, human], config=_build_runnable_config(run_id=run_id, op="memory_summary", role=role))
        except Exception as e:
            if run_id:
                trace_exception(run_id=run_id, ui_debug=ui_debug, where="summarize_memory.json_invoke", exc=e)
            return None
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            return None
        blob = _extract_json_object(content) or ""
        if not blob:
            return None
        try:
            payload = json.loads(blob)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        summary = payload.get("summary")
        if not isinstance(summary, str):
            return None
        s2 = summary.strip()
        return s2[:4000] if s2 else None

    out = invoke_structured()
    if out is not None:
        return out.summary
    return invoke_json_fallback()
