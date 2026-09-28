from __future__ import annotations

from app.ai.tools.context import ToolContext
from app.mcp.registry import MCPPluginRegistry


class MCPPermissionService:
    """
    Application-controlled permission layer for MCP plugins
    and MCP tools.

    Permission resolution:

        Plugin registered
              ↓
        Plugin enabled
              ↓
        Plugin-level permission
              ↓
        Tool-level permission
              ↓
        ToolContext request restriction

    The MCP server and LLM never control permissions.
    """

    def __init__(
        self,
        registry: MCPPluginRegistry,
    ) -> None:
        self.registry = registry

        # Workspace-level MCP permissions.
        #
        # {
        #     workspace_id: {
        #         "github",
        #         "slack",
        #     }
        # }
        self._workspace_plugins: dict[
            int,
            set[str],
        ] = {}

        # User-level MCP permissions.
        self._user_plugins: dict[
            int,
            set[str],
        ] = {}

        # Optional fine-grained tool permissions.
        #
        # {
        #     ("workspace", 1, "github"): {
        #         "github_get_pull_request",
        #     }
        # }
        self._workspace_tools: dict[
            tuple[int, str],
            set[str],
        ] = {}

        self._user_tools: dict[
            tuple[int, str],
            set[str],
        ] = {}

    # ========================================================
    # PLUGIN PERMISSIONS
    # ========================================================

    def set_workspace_plugins(
        self,
        workspace_id: int,
        plugins: set[str],
    ) -> None:
        """
        Set MCP plugins allowed for a workspace.
        """

        self._workspace_plugins[workspace_id] = set(
            plugins
        )

    def add_workspace_plugin(
        self,
        workspace_id: int,
        plugin_name: str,
    ) -> None:
        """
        Allow one MCP plugin for a workspace without
        removing plugins that are already allowed.
        """

        self._workspace_plugins.setdefault(
            workspace_id,
            set(),
        ).add(plugin_name)

    def set_user_plugins(
        self,
        user_id: int,
        plugins: set[str],
    ) -> None:
        """
        Set MCP plugins allowed for a user.
        """

        self._user_plugins[user_id] = set(
            plugins
        )

    # ========================================================
    # TOOL PERMISSIONS
    # ========================================================

    def set_workspace_tools(
        self,
        workspace_id: int,
        plugin_name: str,
        tools: set[str],
    ) -> None:
        """
        Set MCP tools allowed for a plugin inside a workspace.
        """

        self._workspace_tools[
            (workspace_id, plugin_name)
        ] = set(tools)

    def set_user_tools(
        self,
        user_id: int,
        plugin_name: str,
        tools: set[str],
    ) -> None:
        """
        Set MCP tools allowed for a plugin for a user.
        """

        self._user_tools[
            (user_id, plugin_name)
        ] = set(tools)

    # ========================================================
    # PLUGIN RESOLUTION
    # ========================================================

    def _is_plugin_allowed_by_policy(
        self,
        plugin_name: str,
        context: ToolContext,
    ) -> bool:
        """
        Resolve workspace/user MCP plugin permission.

        Workspace policy has priority over user policy.

        If neither policy exists, the plugin remains denied.

        This is intentional.

        External MCP integrations must be explicitly enabled
        by application policy instead of inheriting Sprint 11's
        internal-tool defaults.
        """

        if context.workspace_id in self._workspace_plugins:
            return plugin_name in self._workspace_plugins[
                context.workspace_id
            ]

        if context.user_id in self._user_plugins:
            return plugin_name in self._user_plugins[
                context.user_id
            ]

        return False

    # ========================================================
    # PLUGIN CHECK
    # ========================================================

    def is_plugin_allowed(
        self,
        plugin_name: str,
        context: ToolContext,
    ) -> bool:
        """
        Check whether an MCP plugin can be used.
        """

        if not plugin_name:
            return False

        try:
            plugin = self.registry.get(
                plugin_name
            )
        except ValueError:
            return False

        if not plugin.enabled:
            return False

        return self._is_plugin_allowed_by_policy(
            plugin_name,
            context,
        )

    # ========================================================
    # TOOL CHECK
    # ========================================================

    def is_tool_allowed(
        self,
        plugin_name: str,
        tool_name: str,
        context: ToolContext,
    ) -> bool:
        """
        Check whether one MCP tool can be executed.

        A tool can only execute when:

            1. Plugin exists.
            2. Plugin is enabled.
            3. Plugin is allowed.
            4. Tool is allowed by the applicable policy.
            5. ToolContext does not restrict the tool.
        """

        if not self.is_plugin_allowed(
            plugin_name,
            context,
        ):
            return False

        workspace_key = (
            context.workspace_id,
            plugin_name,
        )

        user_key = (
            context.user_id,
            plugin_name,
        )

        # Workspace tool policy takes priority.
        if workspace_key in self._workspace_tools:
            allowed = self._workspace_tools[
                workspace_key
            ]

            return (
                tool_name in allowed
                and self._context_allows_tool(
                    tool_name,
                    context,
                )
            )

        # User tool policy.
        if user_key in self._user_tools:
            allowed = self._user_tools[
                user_key
            ]

            return (
                tool_name in allowed
                and self._context_allows_tool(
                    tool_name,
                    context,
                )
            )

        # Plugin permission alone is enough when no
        # fine-grained tool override exists.
        return self._context_allows_tool(
            tool_name,
            context,
        )

    # ========================================================
    # REQUEST-LEVEL RESTRICTION
    # ========================================================

    @staticmethod
    def _context_allows_tool(
        tool_name: str,
        context: ToolContext,
    ) -> bool:
        """
        Apply the request-scoped ToolContext restriction.

        This can only reduce permissions.
        """

        if context.allowed_tools is None:
            return True

        return tool_name in context.allowed_tools
