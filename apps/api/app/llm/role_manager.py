from __future__ import annotations

import json
import os
from typing import Any, Literal

from .models import RoleMetadata

Capability = Literal["basic", "standard", "advanced"]


def _parse_json_env(key: str) -> Any | None:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _capability_rank(value: str) -> int:
    v = (value or "").strip().lower()
    if v == "advanced":
        return 3
    if v == "standard":
        return 2
    return 1


class RoleManager:
    """Capability-only role selection.

    We keep it intentionally simple:
    - scenarios declare a minimum capability
    - roles are selected from configured metadata (optional) + safe defaults
    """

    def __init__(self) -> None:
        self._roles = self._load_role_metadata()

    def _load_role_metadata(self) -> dict[str, RoleMetadata]:
        # Optional JSON to override/extend role metadata:
        # {
        #   "fast": {"capability_tier":"basic","preferred_for":["intent","summary","plan"]},
        #   "main": {"capability_tier":"advanced","preferred_for":["command_gen","final_answer","repair"]}
        # }
        raw = _parse_json_env("V2_LLM_ROLE_METADATA_JSON")
        out: dict[str, RoleMetadata] = {}

        def add(name: str, cap: str, preferred_for: list[str] | tuple[str, ...]) -> None:
            pf = tuple([str(x).strip() for x in preferred_for if isinstance(x, str) and x.strip()])
            out[name] = RoleMetadata(name=name, capability_tier=cap, preferred_for=pf)

        # Safe defaults that match current behavior expectations.
        add("fast", "basic", ["intent", "summary", "plan"])
        add("main", "advanced", ["command_gen", "final_answer"])
        add("repair", "advanced", ["repair"])
        add("fallback", "standard", ["final_answer", "command_gen"])

        if isinstance(raw, dict):
            for role, meta in raw.items():
                if not isinstance(role, str) or not role.strip() or not isinstance(meta, dict):
                    continue
                cap = str(meta.get("capability_tier") or meta.get("capability") or "").strip().lower()
                if cap not in {"basic", "standard", "advanced"}:
                    cap = out.get(role, RoleMetadata(role, "basic")).capability_tier
                pf_raw = meta.get("preferred_for") or meta.get("preferredFor") or []
                if not isinstance(pf_raw, list):
                    pf_raw = []
                add(role.strip(), cap, pf_raw)

        return out

    def select_role(self, *, scenario: str, min_capability: Capability = "basic") -> str:
        scenario_s = (scenario or "").strip()
        min_rank = _capability_rank(min_capability)

        # 1) Find roles that explicitly prefer this scenario and satisfy min capability.
        candidates = [
            r
            for r, meta in self._roles.items()
            if scenario_s in meta.preferred_for and _capability_rank(meta.capability_tier) >= min_rank
        ]
        if candidates:
            # Prefer lowest capability that still satisfies min (cost/latency tends to correlate).
            candidates.sort(key=lambda r: _capability_rank(self._roles[r].capability_tier))
            return candidates[0]

        # 2) Otherwise, find any role that satisfies min capability (prefer lower).
        candidates2 = [r for r, meta in self._roles.items() if _capability_rank(meta.capability_tier) >= min_rank]
        if candidates2:
            candidates2.sort(key=lambda r: _capability_rank(self._roles[r].capability_tier))
            return candidates2[0]

        # 3) Last resort.
        return "fast"


# Backward-compatible helper for callers that only need a single role string.
_ROLE_MANAGER = RoleManager()


def select_role(*, scenario: str, min_capability: Capability = "basic") -> str:
    return _ROLE_MANAGER.select_role(scenario=scenario, min_capability=min_capability)


