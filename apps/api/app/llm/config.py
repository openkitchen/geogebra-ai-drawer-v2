from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import LlmConfig

_ENV_REF_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")

_ENV_FILES_LOADED = False


def _repo_root() -> Path:
    # apps/api/app/llm/config.py -> repo root
    return Path(__file__).resolve().parents[4]


def _strip_wrapping_quotes(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    return s


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


def _load_env_file(path: Path) -> None:
    try:
        from dotenv import dotenv_values  # type: ignore
    except Exception:
        return

    try:
        # Keep raw ${VAR} (do not interpolate) so we can expand refs after all env files are loaded.
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
    # NOTE: Role fallback is intentionally disabled in v2.
    return []


def load_llm_config_for_role(*, role: str | None) -> LlmConfig | None:
    """Resolve model config for a given role.

    This keeps the same behavior as the legacy implementation in `llm_decider.py`.
    """

    _maybe_load_env_files()
    resolved_role = (role or os.getenv("V2_LLM_ROLE") or "main").strip() or "main"

    def read_temperature_timeout(*, resolved_role: str) -> tuple[float, float]:
        try:
            temperature = float(os.getenv("V2_LLM_TEMPERATURE") or "0")
        except ValueError:
            temperature = 0.0

        role_timeout_key = f"V2_LLM_TIMEOUT_S_{resolved_role.upper()}"
        timeout_env = os.getenv(role_timeout_key) or os.getenv("V2_LLM_TIMEOUT_S") or ""
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

        temperature, timeout_s = read_temperature_timeout(resolved_role=resolved_role)
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

        temperature, timeout_s = read_temperature_timeout(resolved_role=resolved_role)
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

            temperature, timeout_s = read_temperature_timeout(resolved_role=resolved_role)
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
    """Backward-compatible entrypoint used across the codebase.
    
    NOTE: No fallback behavior. If the requested role is not configured, returns None.
    This ensures explicit failure when the requested model is unavailable.
    """

    return load_llm_config_for_role(role=role)


@lru_cache(maxsize=8)
def list_fallback_roles() -> tuple[str, ...]:
    """Expose fallback roles as a stable tuple for other modules."""

    return tuple(_fallback_roles())
