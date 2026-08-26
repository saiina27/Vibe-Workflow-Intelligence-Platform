from app.ai.tools.context import ToolContext
from app.ai.tools.knowledge_tool import KnowledgeTool
from app.ai.tools.memory_tool import MemoryTool
from app.ai.tools.permissions import (
    tool_permission_service,
)
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.web_search_tool import WebSearchTool


class ToolRouter:
    """
    Builds the request-scoped tool registry for Vibe.

    The application controls which tools are exposed
    to the AI provider for each request.

    Tool instances receive the application-controlled
    ToolContext. The LLM only receives tool definitions
    and controls tool arguments.
    """

    def __init__(self):
        self.permission_service = (
            tool_permission_service
        )

    def build_registry(
        self,
        context: ToolContext,
    ) -> ToolRegistry:

        registry = ToolRegistry()

        allowed_tools = (
            self.permission_service.get_allowed_tools(
                context
            )
        )

        # ====================================================
        # WORKSPACE MEMORY
        # ====================================================

        if "search_memory" in allowed_tools:

            registry.register(
                MemoryTool(context)
            )

        # ====================================================
        # WORKSPACE KNOWLEDGE
        # ====================================================

        if "search_knowledge" in allowed_tools:

            registry.register(
                KnowledgeTool(context)
            )

        # ====================================================
        # PUBLIC WEB SEARCH
        # ====================================================

        if "search_web" in allowed_tools:

            try:

                registry.register(
                    WebSearchTool(context)
                )

            except RuntimeError as exc:

                print(
                    "Web search tool unavailable: "
                    f"{exc}"
                )

        return registry