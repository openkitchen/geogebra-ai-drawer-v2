from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

import os

from .client import LlmClient
from .role_manager import RoleManager


Difficulty = Literal["simple", "hard"]


class DifficultyClassification(BaseModel):
    difficulty: Difficulty
    # Safe, user-visible reasons (NOT chain-of-thought). Keep short.
    reasons: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _normalize(self) -> "DifficultyClassification":
        dedup: list[str] = []
        for r in self.reasons:
            if not isinstance(r, str):
                continue
            s = r.strip()
            if not s:
                continue
            if len(s) > 120:
                s = s[:120] + "…"
            if s not in dedup:
                dedup.append(s)
        self.reasons = dedup[:8]
        return self


_DIFFICULTY_SYSTEM = """You are a difficulty classifier for a GeoGebra math assistant.

Return ONLY a JSON object that matches the given schema (no markdown, no extra keys).

We want to decide whether a user request should be handled in:
- simple: direct, quick drawing or short answer (no staged reasoning UI)
- hard: staged solve loop with hypothesis → verification in GeoGebra → revision, and UI-visible progress

Guidelines (use ONLY safe, user-visible reasons; DO NOT reveal chain-of-thought):
- Mark hard when the request likely needs multi-step reasoning, proof-like steps, exploration, or iterative verification.
- Mark simple when it is a straightforward imperative draw request (e.g., \"画一个圆\", \"画三角形ABC\") or a short factual/meta question.
- Reasons should be short and concrete, like \"requires proof\", \"multiple constraints\", \"optimization/trajectory\", \"needs verification\".
- Be conservative about hard: if the user intent is clearly a single construction, prefer simple.
"""


def classify_difficulty(
    *,
    user_text: str,
    run_id: str | None,
    ui_debug: bool,
    context: dict[str, Any] | None = None,
) -> DifficultyClassification | None:
    """Classify difficulty using a small/fast model.

This is intentionally "up-front" routing: the graph uses it to decide whether to
enter staged, tool-verified solve mode.
"""

    role_override = (os.getenv("V2_LLM_DIFFICULTY_ROLE") or "").strip()
    if role_override:
        role = role_override
    else:
        rm = RoleManager()
        role = rm.select_role(scenario="difficulty", min_capability="basic")

    llm = LlmClient(run_id=run_id, ui_debug=ui_debug)

    ctx = context or {}
    ctx_preview = {}
    for k in ("memory_summary",):
        v = ctx.get(k)
        if isinstance(v, str) and v.strip():
            ctx_preview[k] = v.strip()[:600]

    system = SystemMessage(content=_DIFFICULTY_SYSTEM.strip())
    human = HumanMessage(
        content=(
            "Classify this user message as simple vs hard.\n"
            f"user_text: {user_text}\n"
            + (f"context: {ctx_preview}\n" if ctx_preview else "")
        )
    )

    return llm.invoke_structured(
        role=role,
        op="difficulty",
        messages=[system, human],
        output_schema=DifficultyClassification,
    )
