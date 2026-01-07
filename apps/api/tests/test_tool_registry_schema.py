from __future__ import annotations

from app.protocol_v2 import get_protocol_schema_v2
from app.tool_registry import SUPPORTED_TOOL_NAMES


def test_schema_includes_supported_tools_and_tool_schemas() -> None:
    schema = get_protocol_schema_v2()

    assert schema["protocol_version"] == "v2"
    assert schema["supported_tools"] == list(SUPPORTED_TOOL_NAMES)

    tools = schema["tools"]
    assert isinstance(tools, dict)

    for name in SUPPORTED_TOOL_NAMES:
        assert name in tools
        spec = tools[name]
        assert "input_schema" in spec
        assert "output_schema" in spec

