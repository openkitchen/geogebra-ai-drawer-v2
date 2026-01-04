from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

from .client import LlmClient
from .role_manager import RoleManager


class IntentClassification(BaseModel):
    wants_draw: bool = False
    forbids_drawing: bool = False

    wants_circle: bool = False
    wants_triangle: bool = False

    wants_right_triangle: bool = False
    wants_obtuse_triangle: bool = False
    wants_inscribed_triangle: bool = False

    # Optional quick flags to help routing.
    is_meta_question: bool = False

    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _normalize(self) -> "IntentClassification":
        # If the user forbids drawing, treat wants_draw as false.
        if self.forbids_drawing:
            self.wants_draw = False
        # If meta question, usually not a draw request.
        if self.is_meta_question and not self.forbids_drawing:
            self.wants_draw = False
        return self


IntentScenario = Literal["intent"]


_INTENT_SYSTEM = """You are an intent classifier for a GeoGebra drawing assistant.

Return ONLY a JSON object that matches the given schema (no markdown, no extra keys).

You must infer whether the user is asking to DRAW something on the canvas now,
or asking about/reflecting on something already drawn (meta question).

Guidelines:
- wants_draw=true only when the user is giving an instruction to draw/construct/plot now.
- If the user says they do NOT want drawing (e.g. 不要画/不用画/don't draw), set forbids_drawing=true.
- If the user says things like “你画的/我画的/刚才画/之前画/解释/总结/说明”, treat as meta: is_meta_question=true.
- For geometry details, set wants_circle / wants_triangle / wants_right_triangle / wants_obtuse_triangle / wants_inscribed_triangle.
- Be conservative: when unsure, set wants_draw=false and lower confidence.
"""


def classify_intent(
    *,
    user_text: str,
    run_id: str | None,
    ui_debug: bool,
    context: dict[str, Any] | None = None,
) -> IntentClassification | None:
    """Classify user intent using a cheap/basic model."""

    rm = RoleManager()
    role = rm.select_role(scenario="intent", min_capability="basic")

    llm = LlmClient(run_id=run_id, ui_debug=ui_debug)

    # Keep payload compact; include only small context if provided.
    ctx = context or {}
    ctx_preview = {}
    for k in ("memory_summary",):
        v = ctx.get(k)
        if isinstance(v, str) and v.strip():
            ctx_preview[k] = v.strip()[:600]

    system = SystemMessage(content=_INTENT_SYSTEM.strip())
    human = HumanMessage(
        content=(
            "Classify this user message.\n"
            f"user_text: {user_text}\n"
            + (f"context: {ctx_preview}\n" if ctx_preview else "")
        )
    )

    return llm.invoke_structured(
        role=role,
        op="intent",
        messages=[system, human],
        output_schema=IntentClassification,
    )


