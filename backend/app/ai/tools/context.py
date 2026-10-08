from dataclasses import dataclass, field

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ToolContext:
    """
    Runtime context available to Vibe tools.

    This context is controlled by the application and must
    never be supplied by the LLM as tool-call arguments.
    """

    db: Session
    workspace_id: int
    user_id: int

    # Application-controlled request-level restriction.
    #
    # None means no additional request restriction.
    allowed_tools: frozenset[str] | None = field(
        default=None
    )

    # Optional request-level MCP plugin restriction.
    #
    # None means no additional plugin restriction.
    allowed_mcp_plugins: frozenset[str] | None = field(
        default=None
    )

    # Current chat. Set by the application, never by the LLM, so tools
    # can exclude the conversation that is asking.
    chat_id: int | None = None

    def is_tool_allowed(
        self,
        tool_name: str,
    ) -> bool:
        """
        Check whether a tool is allowed for this request.
        """

        if self.allowed_tools is None:
            return True

        return tool_name in self.allowed_tools

    def is_mcp_plugin_allowed(
        self,
        plugin_name: str,
    ) -> bool:
        """
        Check whether an MCP plugin is allowed
        for this request.
        """

        if self.allowed_mcp_plugins is None:
            return True

        return plugin_name in self.allowed_mcp_plugins