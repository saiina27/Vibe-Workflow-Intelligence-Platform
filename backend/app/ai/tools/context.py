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

    # Application-controlled tool allow-list.
    #
    # None means all currently registered tools are allowed.
    # An explicit set means only those tool names are allowed.
    allowed_tools: frozenset[str] | None = field(
        default=None
    )

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