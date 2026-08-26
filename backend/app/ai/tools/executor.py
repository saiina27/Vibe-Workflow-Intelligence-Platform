from typing import Any

from app.ai.tools.registry import ToolRegistry
from app.ai.tools.context import ToolContext


class ToolExecutor:
    """
    Executes registered Vibe tools.

    Tool instances already contain their
    application-controlled ToolContext.

    The LLM controls only tool arguments.
    It can never provide or override the
    application-controlled tool context.
    """

    def __init__(
        self,
            registry: ToolRegistry,
            context: ToolContext,
    ):
        self.registry = registry
        self.context = context

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

        Execution flow:

            Provider ToolCall
                    ↓
              ToolExecutor
                    ↓
              ToolRegistry
                    ↓
                BaseTool
                    ↓
                Tool Result

        The LLM supplies only the tool arguments.
        ToolContext remains application-controlled.
        """

        # ====================================================
        # VALIDATE TOOL NAME
        # ====================================================

        if not tool_name or not tool_name.strip():

            raise ValueError(
                "Tool name cannot be empty."
            )

        tool_name = tool_name.strip()

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
        # EXECUTE TOOL
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