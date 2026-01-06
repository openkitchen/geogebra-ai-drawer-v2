import pytest
from app.llm_decider import _compact_canvas_objects

def test_compact_canvas_objects_limit():
    # Mock tool_results with 40 objects to test the 30 limit.
    objects = [{"name": f"P{i}", "type": "point", "visible": True, "valueString": f"({i},0)", "definitionString": f"({i},0)"} for i in range(40)]
    tool_results = [
        {
            "tool_name": "get_canvas_state",
            "resume": {
                "ok": True,
                "output": {
                    "objects": objects
                }
            }
        }
    ]
    
    compact = _compact_canvas_objects(tool_results)
    
    assert len(compact) == 30
    assert compact[0]["name"] == "P0"
    assert compact[29]["name"] == "P29"

def test_compact_canvas_objects_empty():
    assert _compact_canvas_objects(None) == []
    assert _compact_canvas_objects([]) == []

def test_compact_canvas_objects_wrong_tool():
    tool_results = [
        {
            "tool_name": "exec_geogebra_commands",
            "input": {"commands": ["A=(1,1)"]}
        }
    ]
    assert _compact_canvas_objects(tool_results) == []

from app.llm_decider import _clean_commands

def test_clean_commands_refinement():
    commands = [
        "A = (1, 1)",
        "SetValue(a, 5)",
        "SetColor(A, 255, 0, 0)", # Allowed in style whitelist
        "ShowLabel(A, true)", # Forbidden
        "get_canvas_state()", # Forbidden (tool name)
    ]
    cleaned = _clean_commands(commands)
    
    assert "A = (1, 1)" in cleaned
    assert "SetValue(a, 5)" in cleaned
    assert "SetColor(A, 255, 0, 0)" in cleaned
    assert "ShowLabel(A, true)" not in cleaned
    assert "get_canvas_state()" not in cleaned

from app.llm_decider import _extract_canvas_diff

def test_extract_canvas_diff_value_change():
    # Simulate two get_canvas_state calls: one before, one after modification.
    tool_results = [
        {
            "tool_name": "get_canvas_state",
            "resume": {
                "ok": True,
                "output": {
                    "objects": [
                        {"name": "A", "type": "point", "valueString": "(1, 1)", "definitionString": "(1, 1)"}
                    ]
                }
            }
        },
        {
            "tool_name": "exec_geogebra_commands", 
            "input": {"commands": ["SetValue(A, (2, 2))"]},
            "resume": {"ok": True, "output": {}}
        },
        {
            "tool_name": "get_canvas_state",
            "resume": {
                "ok": True,
                "output": {
                    "objects": [
                        {"name": "A", "type": "point", "valueString": "(2, 2)", "definitionString": "(2, 2)"}
                    ]
                }
            }
        }
    ]
    
    diff = _extract_canvas_diff(tool_results)
    assert diff is not None
    assert len(diff["changed_objects"]) == 1
    change = diff["changed_objects"][0]
    assert change["name"] == "A"
    assert "valueString" in change["changed_fields"]
    assert "definitionString" in change["changed_fields"]
