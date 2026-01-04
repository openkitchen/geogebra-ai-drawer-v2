import json
import sys
import os
from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema

sys.path.append(os.path.dirname(__file__))

from app.protocol_v2 import (
    ToolResumePayload,
    CanvasObjectSummary,
    GetCanvasStateInput, GetCanvasStateOutput,
    EvalExpressionInput, EvalExpressionOutput,
    EvalNumericInput, EvalNumericResult, EvalNumericOutput,
    ExecGeogebraCommandsInput, ExecGeogebraCommandResult, RollbackError, ExecGeogebraCommandsOutput,
    DeleteObjectsInput, DeleteObjectsOutput,
    RunStartData, NodeStartData, NodeEndData,
    PlanItem, PlanUpdateData,
    TokenData,
    ToolStartData, FrontendToolInterruptData, ToolEndData,
    BudgetData,
    FinalAnswer, FinalData,
    RunEndData,
    RunStartEvent, NodeStartEvent, NodeEndEvent, PlanUpdateEvent, TokenEvent, ToolStartEvent, InterruptEvent, ToolEndEvent, BudgetEvent, FinalEvent, RunEndEvent,
    RunStreamEvent,
    RunInput, UIContext,
    RunStreamRequest, ResumeCommand, ResumeRequest,
)

if __name__ == "__main__":
    
    models = [
        (RunStreamRequest, 'validation'),
        (ResumeRequest, 'validation'),
        (RunInput, 'validation'),
        (UIContext, 'validation'),
        (ResumeCommand, 'validation'),
        (ToolResumePayload, 'validation'),
        (CanvasObjectSummary, 'validation'),
        (GetCanvasStateInput, 'validation'), (GetCanvasStateOutput, 'validation'),
        (EvalExpressionInput, 'validation'), (EvalExpressionOutput, 'validation'),
        (EvalNumericInput, 'validation'), (EvalNumericResult, 'validation'), (EvalNumericOutput, 'validation'),
        (ExecGeogebraCommandsInput, 'validation'), (ExecGeogebraCommandResult, 'validation'), 
        (RollbackError, 'validation'), (ExecGeogebraCommandsOutput, 'validation'),
        (DeleteObjectsInput, 'validation'), (DeleteObjectsOutput, 'validation'),
        (RunStartData, 'validation'),
        (NodeStartData, 'validation'),
        (NodeEndData, 'validation'),
        (PlanItem, 'validation'), (PlanUpdateData, 'validation'),
        (TokenData, 'validation'),
        (ToolStartData, 'validation'),
        (FrontendToolInterruptData, 'validation'),
        (ToolEndData, 'validation'),
        (BudgetData, 'validation'),
        (FinalAnswer, 'validation'), (FinalData, 'validation'),
        (RunEndData, 'validation'),
        (RunStartEvent, 'validation'),
        (NodeStartEvent, 'validation'),
        (NodeEndEvent, 'validation'),
        (PlanUpdateEvent, 'validation'),
        (TokenEvent, 'validation'),
        (ToolStartEvent, 'validation'),
        (InterruptEvent, 'validation'),
        (ToolEndEvent, 'validation'),
        (BudgetEvent, 'validation'),
        (FinalEvent, 'validation'),
        (RunEndEvent, 'validation'),
    ]
    
    _, top_level_defs = models_json_schema(models, ref_template="#/definitions/{model}")
    
    # Flatten $defs if present in the output of models_json_schema
    if "$defs" in top_level_defs:
        top_level_defs.update(top_level_defs["$defs"])
        del top_level_defs["$defs"]

    adapter = TypeAdapter(RunStreamEvent)
    union_schema = adapter.json_schema(ref_template="#/definitions/{model}")
    
    # Also flatten $defs from the union schema if present
    if "$defs" in union_schema:
        for k, v in union_schema["$defs"].items():
            if k not in top_level_defs:
                top_level_defs[k] = v
        del union_schema["$defs"]
        
    top_level_defs["RunStreamEvent"] = union_schema

    # Patch to ensure 'event' is required in all definitions where it is a constant/enum
    # This fixes TypeScript Union discrimination
    for name, schema in top_level_defs.items():
        if isinstance(schema, dict) and "properties" in schema and "event" in schema["properties"]:
            # If event is present, make it required
            if "required" not in schema:
                schema["required"] = []
            if "event" not in schema["required"]:
                schema["required"].append("event")
    
    combined_schema = {
        "title": "ProtocolV2",
        "type": "object",
        "properties": { k: {"$ref": f"#/definitions/{k}"} for k in top_level_defs.keys() },
        "definitions": top_level_defs
    }
    
    print(json.dumps(combined_schema, indent=2))
