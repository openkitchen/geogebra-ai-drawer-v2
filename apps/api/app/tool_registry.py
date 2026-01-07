from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Type

from pydantic import BaseModel

from . import protocol_v2


@dataclass(frozen=True)
class ToolSpec:
    name: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_canvas_state",
        input_model=protocol_v2.GetCanvasStateInput,
        output_model=protocol_v2.GetCanvasStateOutput,
    ),
    ToolSpec(
        name="eval_expression",
        input_model=protocol_v2.EvalExpressionInput,
        output_model=protocol_v2.EvalExpressionOutput,
    ),
    ToolSpec(
        name="eval_numeric",
        input_model=protocol_v2.EvalNumericInput,
        output_model=protocol_v2.EvalNumericOutput,
    ),
    ToolSpec(
        name="exec_geogebra_commands",
        input_model=protocol_v2.ExecGeogebraCommandsInput,
        output_model=protocol_v2.ExecGeogebraCommandsOutput,
    ),
    ToolSpec(
        name="delete_objects",
        input_model=protocol_v2.DeleteObjectsInput,
        output_model=protocol_v2.DeleteObjectsOutput,
    ),
)

SUPPORTED_TOOL_NAMES: tuple[str, ...] = tuple(spec.name for spec in TOOL_SPECS)
_TOOL_BY_NAME: Mapping[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def get_tool_spec(tool_name: str) -> ToolSpec | None:
    return _TOOL_BY_NAME.get(tool_name)


def validate_tool_input(tool_name: str, payload: Any) -> dict[str, Any]:
    spec = get_tool_spec(tool_name)
    if not spec:
        raise ValueError(f"unsupported tool: {tool_name}")
    model = spec.input_model.model_validate(payload)
    return model.model_dump(mode="json", exclude_none=True)


def validate_tool_output(tool_name: str, payload: Any) -> dict[str, Any]:
    spec = get_tool_spec(tool_name)
    if not spec:
        raise ValueError(f"unsupported tool: {tool_name}")
    model = spec.output_model.model_validate(payload)
    return model.model_dump(mode="json", exclude_none=True)


def get_tools_schema_bundle() -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for spec in TOOL_SPECS:
        tools[spec.name] = {
            "input_schema": spec.input_model.model_json_schema(),
            "output_schema": spec.output_model.model_json_schema(),
        }
    return {
        "supported_tools": list(SUPPORTED_TOOL_NAMES),
        "tools": tools,
    }

