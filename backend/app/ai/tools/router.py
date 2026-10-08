from app.ai.tools.context import ToolContext
from app.ai.tools.knowledge_tool import KnowledgeTool
from app.ai.tools.chat_search_tool import ChatSearchTool
from app.ai.tools.memory_tool import MemoryTool
from app.ai.tools.permissions import (
    tool_permission_service,
)
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.web_search_tool import WebSearchTool
from app.mcp.runtime import (
    mcp_integration_manager,
    mcp_permission_service,
)


class ToolRouter:
    """
    Builds the request-scoped tool registry for Vibe.

    Both native Vibe tools and MCP tools are exposed
    through the same ToolRegistry boundary.

    MCP remains MCP-standard internally; the rest of
    Vibe only sees registered BaseTool-compatible tools.
    """

    def __init__(self):
        self.permission_service = (
            tool_permission_service
        )

        self.mcp_integration_manager = (
            mcp_integration_manager
        )

    async def build_registry(
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
        # EARLIER VIBE CHATS
        # ====================================================

        if "search_chats" in allowed_tools:

            registry.register(
                ChatSearchTool(context)
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

        # ====================================================
        # SLACK MCP
        # ====================================================

        if "slack" in allowed_tools:

            try:

                mcp_permission_service.add_workspace_plugin(
                    context.workspace_id,
                    "slack",
                )

                registered = (
                    await self.mcp_integration_manager
                    .connect_slack(
                        db=context.db,
                        user_id=context.user_id,
                        registry=registry,
                    )
                )

                print(
                    "🔌 Slack MCP connected."
                )

                print(
                    f"🔌 Slack MCP tools registered: "
                    f"{registered}"
                )

            except Exception as exc:

                print(
                    "Slack MCP unavailable: "
                    f"{exc}"
                )

        # ====================================================
        # GITHUB MCP
        # ====================================================

        if "github" in allowed_tools:

            try:

                from app.services.external_integration_service import (
                    get_user_integration,
                )

                github_integration = get_user_integration(
                    db=context.db,
                    user_id=context.user_id,
                    provider="github",
                )

                if github_integration is None:

                    print(
                        "GitHub MCP unavailable: "
                        "GitHub is not connected."
                    )

                else:

                    mcp_permission_service.add_workspace_plugin(
                        context.workspace_id,
                        "github",
                    )

                    registered = (
                        await self.mcp_integration_manager
                        .connect_github(
                            db=context.db,
                            user_id=context.user_id,
                            registry=registry,
                        )
                    )

                    print(
                        "🔌 GitHub MCP connected."
                    )

                    print(
                        f"🔌 GitHub MCP tools registered: "
                        f"{registered}"
                    )

            except Exception as exc:

                print(
                    "GitHub MCP unavailable: "
                    f"{exc}"
                )

        return registry