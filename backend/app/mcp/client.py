
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from contextlib import AsyncExitStack
from typing import Any, Coroutine, TypeVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)


T = TypeVar("T")


class MCPClient:
    """
    Vibe's provider-independent MCP client.

    MCP transport/session lifecycle is owned by ONE dedicated
    asyncio task running on ONE dedicated event loop.

    This is required by AnyIO/MCP because context managers such
    as stdio_client() and streamable_http_client() own cancel
    scopes/task groups that must be exited from the same task
    that entered them.

    Public Vibe-facing methods remain synchronous.
    Actual MCP operations execute on the dedicated event loop.
    """

    def __init__(self) -> None:
        # ----------------------------------------------------
        # Dedicated runtime
        # ----------------------------------------------------

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._ready = threading.Event()
        self._stopped = threading.Event()

        self._startup_error: BaseException | None = None

        # ----------------------------------------------------
        # MCP state
        # ----------------------------------------------------

        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

        # Connection lifecycle task.
        #
        # IMPORTANT:
        # This task enters AND exits the MCP transport/session
        # context managers.
        self._lifecycle_task: asyncio.Task[Any] | None = None

        # Signals lifecycle task to close the MCP connection.
        self._shutdown_event: asyncio.Event | None = None

        # Protect public state transitions.
        self._state_lock = threading.Lock()

    # ========================================================
    # INTERNAL EVENT LOOP
    # ========================================================

    def _start_runtime(self) -> None:
        """
        Start the dedicated MCP asyncio runtime.
        """

        with self._state_lock:
            if self._thread is not None:
                return

            self._ready.clear()
            self._stopped.clear()
            self._startup_error = None

            self._thread = threading.Thread(
                target=self._runtime_thread,
                name="vibe-mcp-client",
                daemon=True,
            )

            self._thread.start()

        self._ready.wait()

        if self._startup_error is not None:
            error = self._startup_error

            self._thread = None
            self._loop = None

            raise RuntimeError(
                "Failed to start MCP client runtime."
            ) from error

    def _runtime_thread(self) -> None:
        """
        Own the asyncio event loop for this MCP client.
        """

        loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)

        self._loop = loop
        self._ready.set()

        try:
            loop.run_forever()

        finally:
            try:
                pending = asyncio.all_tasks(loop)

                for task in pending:
                    task.cancel()

                if pending:
                    loop.run_until_complete(
                        asyncio.gather(
                            *pending,
                            return_exceptions=True,
                        )
                    )

                loop.run_until_complete(
                    loop.shutdown_asyncgens()
                )

            finally:
                loop.close()

                self._loop = None
                self._stopped.set()

    # ========================================================
    # SUBMIT
    # ========================================================

    def _submit(
        self,
        coroutine: Coroutine[Any, Any, T],
    ) -> T:
        """
        Execute one coroutine on the MCP client's owning
        event loop.
        """

        self._start_runtime()

        loop = self._loop

        if loop is None:
            raise RuntimeError(
                "MCP client event loop is not available."
            )

        future: Future[T] = asyncio.run_coroutine_threadsafe(
            coroutine,
            loop,
        )

        return future.result()

    # ========================================================
    # CONNECTION STATE
    # ========================================================

    @property
    def is_connected(self) -> bool:
        """
        Return whether an MCP session is active.
        """

        return self._session is not None

    # ========================================================
    # STDIO CONNECTION
    # ========================================================

    def connect(
        self,
        server: StdioServerParameters,
    ) -> None:
        """
        Connect to an MCP server using stdio transport.

        The lifecycle task owns the entire MCP context:

            enter stdio_client()
                    ↓
            enter ClientSession()
                    ↓
               initialize()
                    ↓
               wait shutdown
                    ↓
            exit ClientSession()
                    ↓
            exit stdio_client()

        This guarantees AnyIO cancel scopes are exited by
        the same task that entered them.
        """

        return self._submit(
            self._connect_stdio(server)
        )

    async def _connect_stdio(
        self,
        server: StdioServerParameters,
    ) -> None:
        """
        Start the MCP lifecycle task for stdio.
        """

        self._ensure_not_connected()

        self._shutdown_event = asyncio.Event()

        self._lifecycle_task = asyncio.create_task(
            self._stdio_lifecycle(
                server
            )
        )

        try:
            await self._wait_for_connection()

        except Exception:
            await self._request_shutdown()

            lifecycle_task = self._lifecycle_task

            if lifecycle_task is not None:
                await lifecycle_task

            self._lifecycle_task = None

            raise

    async def _stdio_lifecycle(
        self,
        server: StdioServerParameters,
    ) -> None:
        """
        Own the COMPLETE stdio MCP lifecycle.

        This coroutine must remain alive for the lifetime of
        the MCP connection so that AsyncExitStack exits from
        this same task.
        """

        shutdown_event = self._shutdown_event

        if shutdown_event is None:
            raise RuntimeError(
                "MCP shutdown event is not initialized."
            )

        exit_stack = AsyncExitStack()

        self._exit_stack = exit_stack

        try:
            read_stream, write_stream = (
                await exit_stack.enter_async_context(
                    stdio_client(server)
                )
            )

            session = (
                await exit_stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream,
                    )
                )
            )

            self._session = session

            await session.initialize()

            # Keep THIS SAME TASK alive until shutdown.
            await shutdown_event.wait()

        finally:
            self._session = None
            self._exit_stack = None

            await exit_stack.aclose()

    # ========================================================
    # STREAMABLE HTTP CONNECTION
    # ========================================================

    def connect_http(
        self,
        url: str,
        access_token: str | None = None,
    ) -> None:
        """
        Connect using MCP Streamable HTTP.
        """

        if not url or not url.strip():
            raise ValueError(
                "MCP HTTP server URL cannot be empty."
            )

        return self._submit(
            self._connect_http(
                url=url,
                access_token=access_token,
            )
        )

    async def _connect_http(
        self,
        url: str,
        access_token: str | None = None,
    ) -> None:
        """
        Start the MCP Streamable HTTP lifecycle task.
        """

        self._ensure_not_connected()

        self._shutdown_event = asyncio.Event()

        self._lifecycle_task = asyncio.create_task(
            self._http_lifecycle(
                url=url,
                access_token=access_token,
            )
        )

        try:
            await self._wait_for_connection()

        except Exception:
            await self._request_shutdown()

            lifecycle_task = self._lifecycle_task

            if lifecycle_task is not None:
                await lifecycle_task

            self._lifecycle_task = None

            raise

    async def _http_lifecycle(
        self,
        url: str,
        access_token: str | None = None,
    ) -> None:
        """
        Own the COMPLETE Streamable HTTP MCP lifecycle.

        The same task enters and exits all MCP/AnyIO context
        managers.
        """

        shutdown_event = self._shutdown_event

        if shutdown_event is None:
            raise RuntimeError(
                "MCP shutdown event is not initialized."
            )

        headers: dict[str, str] = {}

        if access_token:
            headers["Authorization"] = (
                f"Bearer {access_token}"
            )

        http_client = create_mcp_http_client(
            headers=headers or None,
        )

        exit_stack = AsyncExitStack()

        self._exit_stack = exit_stack

        try:
            read_stream, write_stream = (
                await exit_stack.enter_async_context(
                    streamable_http_client(
                        url.strip(),
                        http_client=http_client,
                    )
                )
            )

            session = (
                await exit_stack.enter_async_context(
                    ClientSession(
                        read_stream,
                        write_stream,
                    )
                )
            )

            self._session = session

            await session.initialize()

            # Keep THIS SAME TASK alive.
            await shutdown_event.wait()

        finally:
            self._session = None
            self._exit_stack = None

            await exit_stack.aclose()

    # ========================================================
    # CONNECTION READY
    # ========================================================

    async def _wait_for_connection(
        self,
    ) -> None:
        """
        Wait until the lifecycle task has either initialized
        the MCP session or failed.

        The lifecycle task itself remains alive after this
        method returns.
        """

        lifecycle_task = self._lifecycle_task

        if lifecycle_task is None:
            raise RuntimeError(
                "MCP lifecycle task was not created."
            )

        # Poll briefly while the lifecycle task initializes.
        #
        # This avoids returning before _session is available,
        # while still allowing the lifecycle task to remain
        # alive after initialization.
        while self._session is None:

            if lifecycle_task.done():
                exception = lifecycle_task.exception()

                if exception is not None:
                    raise RuntimeError(
                        "MCP connection lifecycle failed."
                    ) from exception

                raise RuntimeError(
                    "MCP lifecycle task exited before "
                    "connection was established."
                )

            await asyncio.sleep(0.001)

    # ========================================================
    # STATE VALIDATION
    # ========================================================

    def _ensure_not_connected(self) -> None:
        """
        Prevent multiple connections on one MCP client.
        """

        if self._session is not None:
            raise RuntimeError(
                "MCP client is already connected."
            )

        if self._lifecycle_task is not None:
            raise RuntimeError(
                "MCP client lifecycle is already running."
            )

    def _require_session(self) -> ClientSession:
        """
        Return the active MCP session.
        """

        session = self._session

        if session is None:
            raise RuntimeError(
                "MCP client is not connected."
            )

        return session

    # ========================================================
    # TOOL DISCOVERY
    # ========================================================

    def list_tools(self) -> list[Any]:
        """
        Discover MCP tools.
        """

        return self._submit(
            self._list_tools()
        )

    async def _list_tools(self) -> list[Any]:
        session = self._require_session()

        result = await session.list_tools()

        return list(result.tools)

    # ========================================================
    # TOOL EXECUTION
    # ========================================================

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        Execute one MCP tool on the same async runtime that
        owns the MCP connection.
        """

        if not tool_name or not tool_name.strip():
            raise ValueError(
                "MCP tool name cannot be empty."
            )

        return self._submit(
            self._call_tool(
                tool_name=tool_name,
                arguments=arguments,
            )
        )

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        session = self._require_session()

        try:

            return await session.call_tool(
                tool_name.strip(),
                arguments or {},
            )

        except Exception as exc:

            # Debug visibility: the MCP SDK's generic
            # "Server returned an error response" message hides
            # the underlying HTTP status/body from a remote
            # streamable_http server (e.g. GitHub's hosted MCP
            # endpoint). Surface whatever detail the exception
            # actually carries so the real cause (auth scope,
            # rate limit, etc.) shows up in logs instead of a
            # generic label.
            print(
                f"🔍 MCP call_tool raw exception for "
                f"'{tool_name}': {type(exc).__name__}: {exc!r}"
            )

            for attr in (
                "status_code",
                "response",
                "code",
                "data",
            ):

                if hasattr(exc, attr):

                    print(
                        f"🔍 MCP exception.{attr} = "
                        f"{getattr(exc, attr)!r}"
                    )

            error_obj = getattr(exc, "error", None)

            if error_obj is not None:

                print(
                    f"🔍 MCP exception.error = {error_obj!r}"
                )

            raise

    # ========================================================
    # CLEANUP SIGNAL
    # ========================================================

    async def _request_shutdown(self) -> None:
        """
        Signal the lifecycle task to exit.

        IMPORTANT:
        We do NOT call AsyncExitStack.aclose() here.

        The lifecycle task itself must perform the exit.
        """

        loop = self._loop

        if loop is None:
            return

        shutdown_event = self._shutdown_event

        if shutdown_event is not None:
            shutdown_event.set()

    # ========================================================
    # CLEANUP
    # ========================================================

    def close(self) -> None:
        """
        Close the MCP connection safely.

        The shutdown signal is sent to the owning event loop.
        The lifecycle task then exits its own AsyncExitStack.

        Therefore:

            SAME TASK ENTERS
            SAME TASK EXITS

        which prevents AnyIO cancel-scope errors.
        """

        loop = self._loop

        if loop is None:
            return

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._shutdown_and_wait(),
                loop,
            )

            future.result()

        finally:
            loop.call_soon_threadsafe(
                loop.stop
            )

            thread = self._thread

            if (
                thread is not None
                and thread is not threading.current_thread()
            ):
                thread.join(
                    timeout=10
                )

            self._thread = None
            self._loop = None
            self._lifecycle_task = None
            self._shutdown_event = None
            self._exit_stack = None
            self._session = None

    async def _shutdown_and_wait(self) -> None:
        """
        Signal the lifecycle task and wait for it to finish.

        The lifecycle task performs the actual AsyncExitStack
        cleanup.
        """

        lifecycle_task = self._lifecycle_task

        if lifecycle_task is None:
            return

        shutdown_event = self._shutdown_event

        if shutdown_event is not None:
            shutdown_event.set()

        try:
            await lifecycle_task

        finally:
            self._lifecycle_task = None
            self._shutdown_event = None
            self._session = None
            self._exit_stack = None
