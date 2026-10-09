from app.ai.tools.context import ToolContext


class ToolPermissionService:
    """
    Application-controlled tool permission policy.

    The LLM never controls permissions.

    Permission resolution order:

        workspace-specific rules
                ↓
        user-specific rules
                ↓
        default allow-list
                ↓
        request-scoped ToolContext restriction
                ↓
        effective allowed tools

    The final permission set is always controlled by
    the application.

    Important:

        ToolContext.allowed_tools is an additional
        request-level restriction.

        It can only reduce permissions.
        It can never grant a tool that the underlying
        workspace/user/default policy does not allow.
    """

    # ========================================================
    # DEFAULT PERMISSIONS
    # ========================================================

    DEFAULT_ALLOWED_TOOLS = {
        "search_memory",
        "search_knowledge",
        "search_web",
        "search_chats",
        "search_history",
        "github",

        # ====================================================
        # MCP INTEGRATIONS
        # ====================================================

        "slack",
    }

    def __init__(self):
        """
        Temporary in-memory permission configuration.

        Sprint 11:
            - Workspace-level allow-list
            - User-level allow-list
            - Request-level restriction through ToolContext

        Sprint 12:
            - MCP integration permissions

        Future:
            Persistent permission storage can be added
            without changing the ToolRouter contract.
        """

        self._workspace_allowlist: dict[
            int,
            set[str],
        ] = {}

        self._user_allowlist: dict[
            int,
            set[str],
        ] = {}

    # ========================================================
    # WORKSPACE PERMISSIONS
    # ========================================================

    def set_workspace_tools(
        self,
        workspace_id: int,
        tools: set[str],
    ) -> None:
        """
        Set the allowed tools for a specific workspace.

        Workspace-level permissions override user-level
        permissions and the default allow-list.
        """

        self._workspace_allowlist[workspace_id] = set(
            tools
        )

    # ========================================================
    # USER PERMISSIONS
    # ========================================================

    def set_user_tools(
        self,
        user_id: int,
        tools: set[str],
    ) -> None:
        """
        Set the allowed tools for a specific user.

        User-level permissions are used only when no
        workspace-specific permission exists.
        """

        self._user_allowlist[user_id] = set(
            tools
        )

    # ========================================================
    # RESOLVE BASE PERMISSIONS
    # ========================================================

    def _get_base_allowed_tools(
        self,
        context: ToolContext,
    ) -> set[str]:
        """
        Resolve the base application permission policy.

        Priority:

            1. Workspace-specific allow-list
            2. User-specific allow-list
            3. Default allow-list
        """

        # ----------------------------------------------------
        # WORKSPACE OVERRIDE
        # ----------------------------------------------------

        if context.workspace_id in self._workspace_allowlist:

            return set(
                self._workspace_allowlist[
                    context.workspace_id
                ]
            )

        # ----------------------------------------------------
        # USER OVERRIDE
        # ----------------------------------------------------

        if context.user_id in self._user_allowlist:

            return set(
                self._user_allowlist[
                    context.user_id
                ]
            )

        # ----------------------------------------------------
        # DEFAULT ALLOW-LIST
        # ----------------------------------------------------

        return set(
            self.DEFAULT_ALLOWED_TOOLS
        )

    # ========================================================
    # RESOLVE EFFECTIVE PERMISSIONS
    # ========================================================

    def get_allowed_tools(
        self,
        context: ToolContext,
    ) -> set[str]:
        """
        Resolve the final effective tool allow-list.

        Permission resolution:

            Base policy
                ↓
            Workspace / User / Default
                ↓
            ToolContext restriction
                ↓
            Effective allowed tools

        ToolContext.allowed_tools is treated as an
        additional restriction.

        Therefore:

            effective_tools =
                base_allowed_tools
                ∩
                context.allowed_tools

        If ToolContext.allowed_tools is None,
        the complete base permission set is returned.
        """

        # ----------------------------------------------------
        # STEP 1: RESOLVE BASE APPLICATION POLICY
        # ----------------------------------------------------

        base_allowed_tools = (
            self._get_base_allowed_tools(
                context
            )
        )

        # ----------------------------------------------------
        # STEP 2: NO REQUEST-LEVEL RESTRICTION
        # ----------------------------------------------------

        if context.allowed_tools is None:

            return base_allowed_tools

        # ----------------------------------------------------
        # STEP 3: APPLY REQUEST-LEVEL RESTRICTION
        # ----------------------------------------------------

        request_allowed_tools = set(
            context.allowed_tools
        )

        # ----------------------------------------------------
        # STEP 4: INTERSECTION
        # ----------------------------------------------------

        return (
            base_allowed_tools
            & request_allowed_tools
        )

    # ========================================================
    # SINGLE TOOL CHECK
    # ========================================================

    def is_allowed(
        self,
        tool_name: str,
        context: ToolContext,
    ) -> bool:
        """
        Check whether a specific tool is allowed
        for the current request context.
        """

        if not tool_name:
            return False

        return tool_name in self.get_allowed_tools(
            context
        )


# ============================================================
# SHARED PERMISSION SERVICE
# ============================================================

tool_permission_service = ToolPermissionService()