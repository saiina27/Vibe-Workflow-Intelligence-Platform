import asyncio
import threading
import time

MIN_INTERVAL = 120

_LOCK = threading.Lock()
_LAST: dict[int, float] = {}


def should_warm(user_id: int, now: float | None = None) -> bool:
    """At most one warm-up per user every MIN_INTERVAL seconds."""

    now = time.monotonic() if now is None else now

    with _LOCK:
        last = _LAST.get(user_id)

        if last is not None and now - last < MIN_INTERVAL:
            return False

        _LAST[user_id] = now

        return True


def warm_github(user_id: int) -> None:
    """
    Connect GitHub MCP and discover its tools in the background (after the
    page loads), so the first question does not pay for the connection.
    Never raises. The chat shares the same connection and tool list.
    """

    if not should_warm(user_id):
        return

    started = time.perf_counter()
    db = None

    try:
        from app.ai.tools.registry import ToolRegistry
        from app.db.session import SessionLocal
        from app.mcp.runtime import mcp_integration_manager

        db = SessionLocal()

        asyncio.run(
            mcp_integration_manager.connect_github(
                db=db,
                user_id=user_id,
                registry=ToolRegistry(),
            )
        )

        print(
            f"🔥 GitHub MCP warmed up in "
            f"{(time.perf_counter() - started) * 1000:.0f} ms"
        )

    except Exception as exc:
        with _LOCK:
            _LAST.pop(user_id, None)

        print(f"🔥 GitHub MCP warm-up skipped: {exc}")

    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
