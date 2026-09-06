"""Adapter to the canonical agent-loop execution boundary."""

from agent_loop import execute_tool_result


class ToolExecutionAdapter:
    """Expose the canonical structured execution contract to Runtime."""

    def execute(self, action, arguments=None):
        result = execute_tool_result(
            action,
            arguments or {},
            source="runtime",
        )

        if isinstance(result, dict):
            result.setdefault("requested_tool", action)
            result.setdefault("resolved_tool", action)
            return result

        return {
            "success": True,
            "error": None,
            "output": result,
            "requested_tool": action,
            "resolved_tool": action,
        }
