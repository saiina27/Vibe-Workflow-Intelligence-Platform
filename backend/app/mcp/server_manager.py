from __future__ import annotations

from dataclasses import dataclass

from mcp import StdioServerParameters

from app.mcp.client import MCPClient


@dataclass(frozen=True)
class MCPServerConfig:
    """
    Provider-independent MCP server configuration.

    Supported transports:
        - stdio
        - streamable_http

    Integration-specific behavior remains outside the
    server manager.
    """

    name: str

    # Transport type.
    #
    # "stdio"            -> local/process MCP server
    # "streamable_http"  -> remote MCP server
    transport: str = "stdio"

    # --------------------------------------------------------
    # STDIO CONFIGURATION
    # --------------------------------------------------------

    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None
    cwd: str | None = None

    # --------------------------------------------------------
    # HTTP CONFIGURATION
    # --------------------------------------------------------

    url: str | None = None

    def __post_init__(self) -> None:
        """
        Validate the transport-specific configuration.
        """

        transport = self.transport.strip().lower()

        if transport not in {
            "stdio",
            "streamable_http",
        }:
            raise ValueError(
                f"Unsupported MCP transport '{self.transport}'."
            )

        if transport == "stdio":
            if not self.command or not self.command.strip():
                raise ValueError(
                    "MCP stdio server command cannot be empty."
                )

        elif transport == "streamable_http":
            if not self.url or not self.url.strip():
                raise ValueError(
                    "MCP Streamable HTTP server URL cannot be empty."
                )

    # ========================================================
    # TRANSPORT
    # ========================================================

    @property
    def normalized_transport(self) -> str:
        """
        Return the normalized transport name.
        """

        return self.transport.strip().lower()

    # ========================================================
    # STDIO PARAMETERS
    # ========================================================

    def to_parameters(self) -> StdioServerParameters:
        """
        Convert Vibe configuration into official MCP SDK
        stdio server parameters.

        This method is only valid for stdio servers.
        """

        if self.normalized_transport != "stdio":
            raise ValueError(
                "Stdio parameters are only available for "
                "stdio MCP servers."
            )

        if not self.command or not self.command.strip():
            raise ValueError(
                "MCP stdio server command cannot be empty."
            )

        return StdioServerParameters(
            command=self.command,
            args=list(self.args),
            env=self.env,
            cwd=self.cwd,
        )


class MCPServerManager:
    """
    Manages configured MCP server connections.

    Responsibilities:
        - Register MCP server configurations.
        - Connect using the configured transport.
        - Retrieve active clients.
        - Disconnect individual servers.
        - Disconnect all servers.

    Supported transports:
        - stdio
        - streamable HTTP

    This class is intentionally integration-agnostic.
    """

    def __init__(self) -> None:
        self._configs: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}

    # ========================================================
    # SERVER REGISTRATION
    # ========================================================

    def register_server(
        self,
        config: MCPServerConfig,
    ) -> None:
        """
        Register an MCP server configuration.

        Registration does not establish a connection.
        """

        name = config.name.strip()

        if not name:
            raise ValueError(
                "MCP server name cannot be empty."
            )

        if name in self._configs:
            raise ValueError(
                f"MCP server '{name}' is already registered."
            )

        self._configs[name] = config

    # ========================================================
    # SERVER LOOKUP
    # ========================================================

    def get_config(
        self,
        name: str,
    ) -> MCPServerConfig:
        """
        Retrieve a registered server configuration.
        """

        config = self._configs.get(name)

        if config is None:
            raise ValueError(
                f"MCP server '{name}' is not registered."
            )

        return config

    def get_client(
        self,
        name: str,
    ) -> MCPClient:
        """
        Retrieve an active MCP client.
        """

        client = self._clients.get(name)

        if client is None:
            raise RuntimeError(
                f"MCP server '{name}' is not connected."
            )

        return client

    def list_servers(self) -> list[str]:
        """
        Return all registered server names.
        """

        return list(self._configs.keys())

    def list_connected_servers(self) -> list[str]:
        """
        Return all currently connected server names.
        """

        return list(self._clients.keys())

    # ========================================================
    # CONNECT
    # ========================================================

    async def connect(
        self,
        name: str,
        access_token: str | None = None,
    ) -> MCPClient:
        """
        Connect to one registered MCP server.

        Transport behavior:

            stdio
                ↓
            MCPClient.connect()

            streamable_http
                ↓
            MCPClient.connect_http()

        access_token is used only for Streamable HTTP
        authentication.
        """

        if name in self._clients:
            return self._clients[name]

        config = self.get_config(name)

        client = MCPClient()

        try:
            if config.normalized_transport == "stdio":
                client.connect(
                    config.to_parameters()
                )

            elif config.normalized_transport == "streamable_http":
                client.connect_http(
                    url=config.url or "",
                    access_token=access_token,
                )

            else:
                raise ValueError(
                    f"Unsupported MCP transport "
                    f"'{config.transport}'."
                )

        except Exception:
            client.close()
            raise

        self._clients[name] = client

        return client

    # ========================================================
    # DISCONNECT
    # ========================================================

    async def disconnect(
        self,
        name: str,
    ) -> None:
        """
        Disconnect one MCP server.
        """

        client = self._clients.pop(name, None)

        if client is None:
            return

        client.close()

    # ========================================================
    # DISCONNECT ALL
    # ========================================================

    async def disconnect_all(self) -> None:
        """
        Disconnect every active MCP server.
        """

        clients = list(self._clients.items())

        self._clients.clear()

        for _, client in clients:
            client.close()