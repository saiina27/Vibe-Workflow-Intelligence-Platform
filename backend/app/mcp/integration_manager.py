from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.ai.tools.registry import ToolRegistry
from app.core.config import settings
from app.mcp.registry import MCPPluginRegistry
from app.mcp.server_manager import (
    MCPServerConfig,
    MCPServerManager,
)
from app.mcp.tool_discovery import MCPToolDiscovery
from app.mcp.oauth.encryption import decrypt_token
from app.repositories import external_integration_repository


class MCPIntegrationManager:
    """
    Runtime manager for user-specific MCP integrations.

    Responsibilities:

        ExternalIntegration
                ↓
        decrypt OAuth token
                ↓
        user-specific MCP server configuration
                ↓
        MCPServerManager
                ↓
        MCPClient
                ↓
        MCPToolDiscovery
                ↓
        request-scoped ToolRegistry

    Provider-specific configuration is kept at the
    integration boundary. The MCP client and server
    manager remain provider-independent.
    """

    GITHUB_PLUGIN_NAME = "github"
    SLACK_PLUGIN_NAME = "slack"

    GITHUB_IMAGE = (
        "ghcr.io/github/github-mcp-server"
    )

    def __init__(
        self,
        server_manager: MCPServerManager,
        plugin_registry: MCPPluginRegistry,
    ) -> None:
        self.server_manager = server_manager
        self.plugin_registry = plugin_registry

    # ========================================================
    # GITHUB RUNTIME IDENTITY
    # ========================================================

    def _get_github_runtime_name(
        self,
        user_id: int,
    ) -> str:

        if user_id <= 0:
            raise ValueError(
                "User ID must be positive."
            )

        return (
            f"{self.GITHUB_PLUGIN_NAME}:{user_id}"
        )

    # ========================================================
    # SLACK RUNTIME IDENTITY
    # ========================================================

    def _get_slack_runtime_name(
        self,
        user_id: int,
    ) -> str:

        if user_id <= 0:
            raise ValueError(
                "User ID must be positive."
            )

        return (
            f"{self.SLACK_PLUGIN_NAME}:{user_id}"
        )

    # ========================================================
    # GITHUB SERVER CONFIG
    # ========================================================

    GITHUB_REMOTE_MCP_URL = (
        "https://api.githubcopilot.com/mcp/"
    )

    def _build_github_server_config(
        self,
        runtime_name: str,
        access_token: str,
    ) -> MCPServerConfig:
        """
        Uses GitHub's hosted remote MCP server over
        streamable_http, authenticated with the user's
        OAuth access token. This replaces the earlier
        docker-based stdio server, which required a local
        `docker` binary that is not available on Render.
        """

        if not runtime_name:
            raise ValueError(
                "GitHub runtime name cannot be empty."
            )

        if not access_token:
            raise ValueError(
                "GitHub access token cannot be empty."
            )

        return MCPServerConfig(
            name=runtime_name,
            transport="streamable_http",
            url=self.GITHUB_REMOTE_MCP_URL,
        )

    # ========================================================
    # SLACK SERVER CONFIG
    # ========================================================

    def _build_slack_server_config(
        self,
        runtime_name: str,
    ) -> MCPServerConfig:

        if not runtime_name:
            raise ValueError(
                "Slack runtime name cannot be empty."
            )

        if not settings.slack_mcp_url:
            raise RuntimeError(
                "Slack MCP URL is not configured."
            )

        return MCPServerConfig(
            name=runtime_name,
            transport="streamable_http",
            url=settings.slack_mcp_url,
        )

    # ========================================================
    # LOAD GITHUB TOKEN
    # ========================================================

    def _get_github_access_token(
        self,
        db: Session,
        user_id: int,
    ) -> str:

        integration = (
            external_integration_repository.get_integration(
                db=db,
                user_id=user_id,
                provider=self.GITHUB_PLUGIN_NAME,
            )
        )

        if integration is None:
            raise RuntimeError(
                "GitHub is not connected for this user."
            )

        if not integration.access_token:
            raise RuntimeError(
                "GitHub integration has no access token."
            )

        try:
            return decrypt_token(
                integration.access_token
            )

        except Exception as exc:
            raise RuntimeError(
                "Failed to decrypt GitHub access token."
            ) from exc

    # ========================================================
    # LOAD SLACK TOKEN
    # ========================================================

    def _get_slack_access_token(
        self,
        db: Session,
        user_id: int,
    ) -> str:

        integration = (
            external_integration_repository.get_integration(
                db=db,
                user_id=user_id,
                provider=self.SLACK_PLUGIN_NAME,
            )
        )

        if integration is None:
            raise RuntimeError(
                "Slack is not connected for this user."
            )

        if not integration.access_token:
            raise RuntimeError(
                "Slack integration has no access token."
            )

        try:
            return decrypt_token(
                integration.access_token
            )

        except Exception as exc:
            raise RuntimeError(
                "Failed to decrypt Slack access token."
            ) from exc

    # ========================================================
    # REGISTER GITHUB SERVER
    # ========================================================

    def _register_github_server(
        self,
        user_id: int,
        access_token: str,
    ) -> str:

        runtime_name = (
            self._get_github_runtime_name(
                user_id
            )
        )

        if runtime_name in (
            self.server_manager.list_servers()
        ):
            return runtime_name

        config = (
            self._build_github_server_config(
                runtime_name=runtime_name,
                access_token=access_token,
            )
        )

        self.server_manager.register_server(
            config
        )

        return runtime_name

    # ========================================================
    # REGISTER SLACK SERVER
    # ========================================================

    def _register_slack_server(
        self,
        user_id: int,
    ) -> str:

        runtime_name = (
            self._get_slack_runtime_name(
                user_id
            )
        )

        if runtime_name in (
            self.server_manager.list_servers()
        ):
            return runtime_name

        config = (
            self._build_slack_server_config(
                runtime_name=runtime_name,
            )
        )

        self.server_manager.register_server(
            config
        )

        return runtime_name

    # ========================================================
    # CONNECT GITHUB + DISCOVER
    # ========================================================

    async def connect_github(
        self,
        db: Session,
        user_id: int,
        registry: ToolRegistry,
    ) -> int:

        plugin = self.plugin_registry.get(
            self.GITHUB_PLUGIN_NAME
        )

        if not plugin.enabled:
            raise RuntimeError(
                "GitHub MCP plugin is disabled."
            )

        access_token = (
            self._get_github_access_token(
                db=db,
                user_id=user_id,
            )
        )

        runtime_name = (
            self._register_github_server(
                user_id=user_id,
                access_token=access_token,
            )
        )

        client = await self.server_manager.connect(
            runtime_name,
            access_token=access_token,
        )

        discovery = MCPToolDiscovery(
            client=client,
            plugin_name=self.GITHUB_PLUGIN_NAME,
        )

        return await discovery.discover(
            registry
        )

    # ========================================================
    # CONNECT SLACK + DISCOVER
    # ========================================================

    async def connect_slack(
        self,
        db: Session,
        user_id: int,
        registry: ToolRegistry,
    ) -> int:

        plugin = self.plugin_registry.get(
            self.SLACK_PLUGIN_NAME
        )

        if not plugin.enabled:
            raise RuntimeError(
                "Slack MCP plugin is disabled."
            )

        access_token = (
            self._get_slack_access_token(
                db=db,
                user_id=user_id,
            )
        )

        runtime_name = (
            self._register_slack_server(
                user_id=user_id,
            )
        )

        client = await self.server_manager.connect(
            runtime_name,
            access_token=access_token,
        )

        discovery = MCPToolDiscovery(
            client=client,
            plugin_name=self.SLACK_PLUGIN_NAME,
        )

        registered = await discovery.discover(
            registry
        )

        return registered

    # ========================================================
    # SYNC SLACK BRIDGE
    # ========================================================

    def connect_slack_sync(
        self,
        db: Session,
        user_id: int,
        registry: ToolRegistry,
    ) -> int:
        """
        Synchronous bridge for Vibe's existing AI pipeline.

        The MCP implementation remains asynchronous internally.
        """

        try:
            asyncio.get_running_loop()

        except RuntimeError:
            return asyncio.run(
                self.connect_slack(
                    db=db,
                    user_id=user_id,
                    registry=registry,
                )
            )

        raise RuntimeError(
            "connect_slack_sync() cannot be called "
            "from an active asyncio event loop."
        )

    # ========================================================
    # DISCONNECT GITHUB
    # ========================================================

    async def disconnect_github(
        self,
        user_id: int,
    ) -> None:

        runtime_name = (
            self._get_github_runtime_name(
                user_id
            )
        )

        await self.server_manager.disconnect(
            runtime_name
        )

    # ========================================================
    # DISCONNECT SLACK
    # ========================================================

    async def disconnect_slack(
        self,
        user_id: int,
    ) -> None:

        runtime_name = (
            self._get_slack_runtime_name(
                user_id
            )
        )

        await self.server_manager.disconnect(
            runtime_name
        )