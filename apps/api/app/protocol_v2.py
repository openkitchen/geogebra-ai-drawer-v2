from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, model_validator


PROTOCOL_VERSION = "v2"


class ToolResumePayload(BaseModel):
    tool_call_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    ok: bool = True
    output: Any = None
    error: Any = None

    @model_validator(mode="after")
    def _validate_error(self) -> "ToolResumePayload":
        if not self.ok and self.error is None:
            raise ValueError("error is required when ok=false")
        return self


class CanvasObjectSummary(BaseModel):
    name: str
    type: str | None = None
    visible: bool | None = None
    valueString: str | None = None
    definitionString: str | None = None
    commandString: str | None = None


class GetCanvasStateInput(BaseModel):
    include: list[str] = Field(default_factory=lambda: ["objects"])


class GetCanvasStateOutput(BaseModel):
    objects: list[CanvasObjectSummary] = Field(default_factory=list)


class EvalExpressionInput(BaseModel):
    expression: str = Field(..., min_length=1)


class EvalExpressionOutput(BaseModel):
    ok: bool
    labels: list[str] | None = None
    error: Any = None
    dialogs: list[str] | None = None


class EvalNumericInput(BaseModel):
    expressions: list[str] = Field(..., min_length=1)


class EvalNumericResult(BaseModel):
    expression: str
    ok: bool
    value: float | None = None
    value_string: str | None = None
    temp_label: str | None = None
    error: Any = None


class EvalNumericOutput(BaseModel):
    results: list[EvalNumericResult] = Field(default_factory=list)
    dialogs: list[str] | None = None


class ExecGeogebraCommandsInput(BaseModel):
    commands: list[str] = Field(..., min_length=1)


class ExecGeogebraCommandResult(BaseModel):
    command: str
    ok: bool
    labels: list[str] | None = None
    error: Any = None


class RollbackError(BaseModel):
    object_name: str
    message: str


class ExecGeogebraCommandsOutput(BaseModel):
    results: list[ExecGeogebraCommandResult] = Field(default_factory=list)
    created_objects: list[str] = Field(default_factory=list)
    deleted_objects: list[str] = Field(default_factory=list)
    rolled_back_objects: list[str] | None = None
    rollback_errors: list[RollbackError] | None = None
    dialogs: list[str] | None = None
    preset_applied: Literal["geometry", "algebra"] | None = None
    quality_warnings: list[str] | None = None


class DeleteObjectsInput(BaseModel):
    objects: list[str] = Field(..., min_length=1)


class DeleteObjectsOutput(BaseModel):
    deleted_objects: list[str] = Field(default_factory=list)
    failed_objects: list[RollbackError] | None = None
    dialogs: list[str] | None = None


class RunStartData(BaseModel):
    run_id: str
    thread_id: str
    protocol_version: str = PROTOCOL_VERSION
    llm_enabled: bool | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None


class NodeStartData(BaseModel):
    name: str


class NodeEndData(BaseModel):
    name: str


class PlanItem(BaseModel):
    id: str
    text: str
    done: bool | None = None


class PlanUpdateData(BaseModel):
    plan: list[PlanItem]


class TokenData(BaseModel):
    text_delta: str
    channel: Literal["content", "reasoning", "meta"] | None = None


class ToolStartData(BaseModel):
    tool_name: str
    tool_call_id: str
    input: Any


class FrontendToolInterruptData(BaseModel):
    kind: Literal["frontend_tool"] = "frontend_tool"
    tool_name: str
    tool_call_id: str
    input: Any


class ToolEndData(BaseModel):
    tool_name: str
    tool_call_id: str
    output: Any
    ok: bool
    error: Any = None


class BudgetData(BaseModel):
    model_calls_used: int | None = None
    model_calls_limit: int | None = None
    tool_calls_used: int | None = None
    tool_calls_limit: int | None = None


class FinalAnswer(BaseModel):
    explanation: str
    overlay_text: Any = None


class FinalData(BaseModel):
    answer: FinalAnswer


class RunEndData(BaseModel):
    pass


class RunStartEvent(BaseModel):
    event: Literal["run_start"] = "run_start"
    data: RunStartData


class NodeStartEvent(BaseModel):
    event: Literal["node_start"] = "node_start"
    data: NodeStartData


class NodeEndEvent(BaseModel):
    event: Literal["node_end"] = "node_end"
    data: NodeEndData


class PlanUpdateEvent(BaseModel):
    event: Literal["plan_update"] = "plan_update"
    data: PlanUpdateData


class DifficultyUpdateData(BaseModel):
    difficulty: Literal["simple", "hard"]
    hard_mode: bool = False
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class DifficultyUpdateEvent(BaseModel):
    event: Literal["difficulty_update"] = "difficulty_update"
    data: DifficultyUpdateData


class PhaseUpdateData(BaseModel):
    # A monotonically increasing sequence number per run (UI can sort/merge).
    seq: int
    phase: str
    summary: str | None = None
    hypothesis: str | None = None
    verification: str | None = None
    result: str | None = None
    next: str | None = None


class PhaseUpdateEvent(BaseModel):
    event: Literal["phase_update"] = "phase_update"
    data: PhaseUpdateData


class TokenEvent(BaseModel):
    event: Literal["token"] = "token"
    data: TokenData


class ToolStartEvent(BaseModel):
    event: Literal["tool_start"] = "tool_start"
    data: ToolStartData


class InterruptEvent(BaseModel):
    event: Literal["interrupt"] = "interrupt"
    data: FrontendToolInterruptData


class ToolEndEvent(BaseModel):
    event: Literal["tool_end"] = "tool_end"
    data: ToolEndData


class BudgetEvent(BaseModel):
    event: Literal["budget"] = "budget"
    data: BudgetData


class FinalEvent(BaseModel):
    event: Literal["final"] = "final"
    data: FinalData


class RunEndEvent(BaseModel):
    event: Literal["run_end"] = "run_end"
    data: RunEndData


RunStreamEvent = Union[
    RunStartEvent,
    NodeStartEvent,
    NodeEndEvent,
    PlanUpdateEvent,
    DifficultyUpdateEvent,
    PhaseUpdateEvent,
    TokenEvent,
    ToolStartEvent,
    InterruptEvent,
    ToolEndEvent,
    BudgetEvent,
    FinalEvent,
    RunEndEvent,
]


class RunInput(BaseModel):
    user_text: str = Field(..., min_length=1)


class UIContext(BaseModel):
    locale: str = "zh-CN"
    debug: bool = False
    plan_mode: bool = True
    # Optional structured hint from the UI (NOT derived from text parsing).
    # This is useful for suggestion chips and other deterministic UI actions.
    intent_hint: dict[str, Any] | None = None


class RunStreamRequest(BaseModel):
    input: RunInput
    ui_context: UIContext = Field(default_factory=UIContext)


class ResumeCommand(BaseModel):
    resume: ToolResumePayload


class ResumeRequest(BaseModel):
    command: ResumeCommand


def get_protocol_schema_v2() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "schemas": {
            "ToolResumePayload": ToolResumePayload.model_json_schema(),
            "RunStreamEvent": TypeAdapter(RunStreamEvent).json_schema(),
            "GetCanvasStateInput": GetCanvasStateInput.model_json_schema(),
            "GetCanvasStateOutput": GetCanvasStateOutput.model_json_schema(),
            "EvalExpressionInput": EvalExpressionInput.model_json_schema(),
            "EvalExpressionOutput": EvalExpressionOutput.model_json_schema(),
            "EvalNumericInput": EvalNumericInput.model_json_schema(),
            "EvalNumericOutput": EvalNumericOutput.model_json_schema(),
            "ExecGeogebraCommandsInput": ExecGeogebraCommandsInput.model_json_schema(),
            "ExecGeogebraCommandsOutput": ExecGeogebraCommandsOutput.model_json_schema(),
            "DeleteObjectsInput": DeleteObjectsInput.model_json_schema(),
            "DeleteObjectsOutput": DeleteObjectsOutput.model_json_schema(),
            "RunStreamRequest": RunStreamRequest.model_json_schema(),
            "ResumeRequest": ResumeRequest.model_json_schema(),
        },
    }
