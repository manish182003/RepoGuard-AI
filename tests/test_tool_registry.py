import pytest
from app.tools.registry import ToolRegistry


def sample_calculator(a: int, b: int) -> int:
    return a + b


async def async_sample_echo(text: str) -> str:
    return f"echo: {text}"


@pytest.mark.asyncio
async def test_tool_registry_registration_and_execution():
    registry = ToolRegistry()
    registry.register_tool(
        name="add",
        description="Add two numbers",
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        handler=sample_calculator,
    )

    defs = registry.get_tool_definitions()
    assert len(defs) == 1
    assert defs[0]["name"] == "add"

    result = await registry.execute_tool("add", {"a": 5, "b": 10})
    assert result.success is True
    assert result.output == "15"


@pytest.mark.asyncio
async def test_tool_registry_async_handler():
    registry = ToolRegistry()
    registry.register_tool(
        name="echo",
        description="Echo string",
        parameters_schema={},
        handler=async_sample_echo,
    )

    result = await registry.execute_tool("echo", {"text": "hello"})
    assert result.success is True
    assert result.output == "echo: hello"


@pytest.mark.asyncio
async def test_tool_registry_unregistered_and_invalid_args():
    registry = ToolRegistry()

    res1 = await registry.execute_tool("nonexistent", {})
    assert res1.success is False
    assert "not registered" in res1.error

    registry.register_tool("add", "add", {}, sample_calculator)
    res2 = await registry.execute_tool("add", {"invalid_arg": 123})
    assert res2.success is False
    assert "Invalid arguments" in res2.error
