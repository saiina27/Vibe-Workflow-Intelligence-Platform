import os
from datetime import datetime, timedelta

from app.models.workspace import Workspace
from app.services import dev_events_service as dev

DEFAULT_HOURS = 6


def stale_after() -> timedelta | None:
    """How old saved history may get. AUTO_SYNC_HOURS=0 turns auto-sync off."""

    raw = (os.getenv("AUTO_SYNC_HOURS") or "").strip()

    try:
        hours = float(raw) if raw else DEFAULT_HOURS
    except ValueError:
        hours = DEFAULT_HOURS

    if hours == 0:
        return None

    if hours < 0:
        hours = DEFAULT_HOURS

    return timedelta(hours=hours)


def is_stale(repo, now: datetime | None = None) -> bool:
    limit = stale_after()

    if limit is None:
        return False

    synced = repo.last_synced_at

    if synced is None:
        return True

    return (now or datetime.utcnow()) - synced >= limit


def stale_targets(db, user_id: int, now: datetime | None = None) -> list:
    """[(workspace_id, [stale tracked repos])] for the user's workspaces."""

    now = now or datetime.utcnow()
    out = []

    workspaces = (
        db.query(Workspace)
        .filter(Workspace.user_id == user_id)
        .order_by(Workspace.id)
        .all()
    )

    for workspace in workspaces:
        repos = [
            r
            for r in dev.list_tracked_repos(db, workspace.id)
            if is_stale(r, now)
        ]

        if repos:
            out.append((workspace.id, repos))

    return out


def _make_call(db, workspace_id: int, user_id: int, registry):
    """A read-only GitHub caller, the same one the manual sync uses."""

    from app.ai.tools.context import ToolContext
    from app.ai.tools.executor import ToolExecutor
    from app.mcp.runtime import mcp_permission_service

    mcp_permission_service.add_workspace_plugin(workspace_id, "github")

    executor = ToolExecutor(
        registry,
        ToolContext(db=db, workspace_id=workspace_id, user_id=user_id),
        mcp_permission_service=mcp_permission_service,
    )

    def call(tool_name: str, arguments: dict):
        if tool_name not in dev.ALLOWED_SYNC_TOOLS:
            raise PermissionError(f"Tool '{tool_name}' is not allowed for sync.")

        return executor.execute(tool_name=tool_name, arguments=arguments)

    return call


def run_auto_sync(db, user_id: int, registry, now=None, make_call=None) -> list:
    """Sync the tracked repos whose saved history is too old. Never raises
    for one failing repo: the others still run."""

    make_call = make_call or _make_call
    results = []

    for workspace_id, repos in stale_targets(db, user_id, now):
        call = make_call(db, workspace_id, user_id, registry)

        for repo in repos:
            name = repo.full_name

            try:
                result = dev.sync_repo(db, workspace_id, name, call, repo)
                results.append(result)

                print(
                    f"🔄 Auto-sync {name}: {result.get('events', 0)} events "
                    f"({result.get('new', 0)} new)"
                )

            except Exception as exc:
                db.rollback()
                results.append({"repo": name, "error": str(exc)[:200]})
                print(f"🔄 Auto-sync failed for {name}: {str(exc)[:120]}")

    if not results:
        print("🔄 Auto-sync: saved history is fresh")

    return results
