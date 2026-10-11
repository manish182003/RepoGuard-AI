import inspect
import json
import logging
from typing import Any, Callable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: str
    error: str | None = None


class ToolRegistry:
    """Registry for registering, describing, validating, and executing tools."""

    def __init__(self, max_output_chars: int = 4000):
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, ToolDefinition] = {}
        self.max_output_chars = max_output_chars

    def register_tool(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        """Register a tool handler function with its schema."""
        self._tools[name] = handler
        self._schemas[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters_schema,
        )
        logger.info(f"Registered tool '{name}'")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions suitable for LLM tool calling prompts."""
        return [tool_def.model_dump() for tool_def in self._schemas.values()]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_tool_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    async def execute_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Validate and execute a registered tool handler."""
        if name not in self._tools:
            return ToolResult(
                tool_name=name,
                success=False,
                output="",
                error=f"Tool '{name}' is not registered in the tool registry.",
            )

        handler = self._tools[name]
        try:
            sig = inspect.signature(handler)
            has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            call_args = arguments if has_var_kwargs else {k: v for k, v in arguments.items() if k in sig.parameters}

            # Inspect handler signature if coroutine
            if inspect.iscoroutinefunction(handler):
                result = await handler(**call_args)
            else:
                result = handler(**call_args)

            if isinstance(result, (dict, list)):
                output_str = json.dumps(result, ensure_ascii=False)
            else:
                output_str = str(result)

            # Cap output length to protect token budget
            if len(output_str) > self.max_output_chars:
                output_str = (
                    output_str[: self.max_output_chars]
                    + f"\n... [Output truncated to {self.max_output_chars} chars]"
                )

            return ToolResult(
                tool_name=name,
                success=True,
                output=output_str,
            )
        except TypeError as exc:
            return ToolResult(
                tool_name=name,
                success=False,
                output="",
                error=f"Invalid arguments for tool '{name}': {exc}",
            )
        except Exception as exc:
            logger.exception(f"Tool execution failed for '{name}'")
            return ToolResult(
                tool_name=name,
                success=False,
                output="",
                error=f"Tool execution error: {exc}",
            )
