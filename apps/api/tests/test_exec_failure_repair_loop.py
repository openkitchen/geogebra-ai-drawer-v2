from app.canvas.validators import verify_canvas
from app.graph.utils import build_runtime_feedback


def test_verify_canvas_fails_on_exec_failure():
    ok, issues = verify_canvas({"intent": {}, "last_exec_had_failure": True})
    assert ok is False
    assert "exec_geogebra_commands_failed" in issues


def test_verify_canvas_fails_on_exec_failure_with_rollback():
    ok, issues = verify_canvas(
        {
            "intent": {},
            "last_exec_had_failure": True,
            "last_exec_rolled_back_objects": ["A", "B"],
        }
    )
    assert ok is False
    assert "exec_geogebra_commands_failed:rolled_back" in issues


def test_build_runtime_feedback_includes_failed_commands_and_rollback():
    state = {
        "tool_results": [
            {
                "tool_name": "exec_geogebra_commands",
                "resume": {
                    "ok": False,
                    "output": {
                        "results": [
                            {"command": "A=(0,0)", "ok": True},
                            {"command": "Vector(perpA)", "ok": False, "error": {"message": "Undefined variable"}},
                        ],
                        "rolled_back_objects": ["A"],
                    },
                },
            }
        ],
        "last_exec_dialogs": [],
        "last_exec_had_failure": True,
        "last_exec_created_objects": ["A"],
    }

    feedback = build_runtime_feedback(state, ["exec_geogebra_commands_failed"])
    assert 'Command failed: "Vector(perpA)" (Undefined variable)' in feedback
    assert "Rolled back: A." in feedback
