from typing import Any

from app.ai.tools.registry import ToolRegistry
from app.ai.tools.context import ToolContext
from app.mcp.permissions import MCPPermissionService
from app.mcp.tool_adapter import MCPToolAdapter


class ToolExecutor:
    """
    Executes registered Vibe tools.

    The LLM controls only tool arguments.
    All authorization remains application-controlled.

    MCP tools receive an additional authorization check:

        ToolContext restriction
                ↓
        MCP plugin permission
                ↓
        MCP tool permission
                ↓
        Tool execution
    """

    def __init__(
        self,
        registry: ToolRegistry,
        context: ToolContext,
        mcp_permission_service: MCPPermissionService | None = None,
    ):
        self.registry = registry
        self.context = context
        self.mcp_permission_service = (
            mcp_permission_service
        )

    # ========================================================
    # EXECUTE TOOL
    # ========================================================

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute a registered tool.

        The LLM supplies only tool arguments.

        ToolContext and all authorization decisions
        remain application-controlled.
        """

        # ====================================================
        # VALIDATE TOOL NAME
        # ====================================================

        if not tool_name or not tool_name.strip():
            raise ValueError(
                "Tool name cannot be empty."
            )

        tool_name = tool_name.strip()

        # ====================================================
        # REQUEST-SCOPED PERMISSION
        # ====================================================

        if not self.context.is_tool_allowed(
            tool_name
        ):
            raise PermissionError(
                f"Tool '{tool_name}' is not allowed "
                "for the current request."
            )

        # ====================================================
        # RESOLVE REGISTERED TOOL
        # ====================================================

        try:
            tool = self.registry.get(
                tool_name
            )

        except Exception as exc:
            raise RuntimeError(
                f"Unable to resolve tool "
                f"'{tool_name}': {exc}"
            ) from exc

        # ====================================================
        # MCP AUTHORIZATION
        # ====================================================

        if isinstance(tool, MCPToolAdapter):

            if self.mcp_permission_service is None:
                raise PermissionError(
                    "MCP permission service is not configured."
                )

            if not self.mcp_permission_service.is_tool_allowed(
                plugin_name=tool.plugin_name,
                tool_name=tool.name,
                context=self.context,
            ):
                raise PermissionError(
                    f"MCP tool '{tool.name}' from plugin "
                    f"'{tool.plugin_name}' is not allowed "
                    "for the current request."
                )

        # ====================================================
        # NORMALIZE ARGUMENTS
        # ====================================================

        if arguments is None:
            arguments = {}

        if not isinstance(
            arguments,
            dict,
        ):
            raise ValueError(
                f"Arguments for tool "
                f"'{tool_name}' must be a JSON object."
            )

        # ====================================================
        # EXECUTE
        # ====================================================

        try:
            return tool.execute(
                **arguments
            )

        except TypeError as exc:
            raise RuntimeError(
                f"Invalid arguments for tool "
                f"'{tool_name}': {exc}"
            ) from exc

        except Exception as exc:
            raise RuntimeError(
                f"Tool '{tool_name}' execution failed: "
                f"{exc}"
            ) from exc