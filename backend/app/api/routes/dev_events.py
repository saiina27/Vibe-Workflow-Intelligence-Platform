import json
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.tools.context import ToolContext
from app.ai.tools.executor import ToolExecutor
from app.ai.tools.registry import ToolRegistry
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.mcp.runtime import mcp_integration_manager, mcp_permission_service
from app.services import code_index_service as cidx
from app.services import digest_service
from app.services import dev_events_service as svc
from app.services.external_integration_service import get_user_integration
from app.services.workspace_service import require_workspace_access

router = APIRouter(
    prefix="/workspaces/{workspace_id}",
    tags=["Developer history"],
)


class TrackedRepoIn(BaseModel):
    full_name: str


def _repo_json(row):
    return {
        "id": row.id,
        "full_name": row.full_name,
        "last_synced_at": row.last_synced_at,
    }


def _event_json(row):
    return {
        "id": row.id,
        "source": row.source,
        "repo": row.repo,
        "event_type": row.event_type,
        "title": row.title,
        "author": row.author,
        "url": row.url,
        "detail": row.detail,
        "occurred_at": row.occurred_at,
    }


@asynccontextmanager
async def github_caller(db: Session, workspace_id: int, user_id: int):
    """
    Yield call(tool_name, arguments) that runs a read-only GitHub tool
    through the normal ToolExecutor (permissions included).
    """

    if get_user_integration(db=db, user_id=user_id, provider="github") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub is not connected.",
        )

    registry = ToolRegistry()

    mcp_permission_service.add_workspace_plugin(workspace_id, "github")

    await mcp_integration_manager.connect_github(
        db=db,
        user_id=user_id,
        registry=registry,
    )

    context = ToolContext(db=db, workspace_id=workspace_id, user_id=user_id)
    executor = ToolExecutor(
        registry,
        context,
        mcp_permission_service=mcp_permission_service,
    )

    def call(tool_name: str, arguments: dict):
        if tool_name not in svc.ALLOWED_SYNC_TOOLS:
            raise PermissionError(f"Tool '{tool_name}' is not allowed for sync.")

        return executor.execute(tool_name=tool_name, arguments=arguments)

    # The GitHub connection is shared with the chat. Closing it here
    # would break a chat answer that is using it, so it is left open.
    yield call


@router.get("/tracked-repos")
def get_tracked_repos(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    return [_repo_json(r) for r in svc.list_tracked_repos(db, workspace_id)]


@router.post("/tracked-repos", status_code=status.HTTP_201_CREATED)
def add_repo(
    workspace_id: int,
    body: TrackedRepoIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    try:
        row = svc.add_tracked_repo(db, workspace_id, body.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _repo_json(row)


@router.delete("/tracked-repos/{repo_id}")
def remove_repo(
    workspace_id: int,
    repo_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    name = next(
        (r.full_name for r in svc.list_tracked_repos(db, workspace_id) if r.id == repo_id),
        None,
    )

    if not svc.delete_tracked_repo(db, workspace_id, repo_id):
        raise HTTPException(status_code=404, detail="Repository not found")

    if name:
        cidx.delete_repo_index(db, workspace_id, name)

    return {"message": "Repository removed"}


@router.get("/github/repos")
async def list_github_repos(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Best-effort list of the user's repos for a dropdown."""

    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    async with github_caller(db, workspace_id, current_user.id) as call:

        def work():
            me = svc.result_text(call("get_me", {}))

            try:
                login = json.loads(me).get("login")
            except (ValueError, AttributeError):
                login = None

            if not login:
                return []

            found = call(
                "search_repositories",
                {"query": f"user:{login}", "perPage": 30, "minimal_output": True},
            )

            return svc.parse_repo_names(svc.result_text(found))

        names = await run_in_threadpool(work)

    return {"repos": names}


@router.post("/dev-events/sync")
async def sync_dev_events(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    repos = svc.list_tracked_repos(db, workspace_id)

    if not repos:
        raise HTTPException(status_code=400, detail="Add a repository first.")

    async with github_caller(db, workspace_id, current_user.id) as call:

        def work():
            results = []

            for repo in repos:
                try:
                    results.append(
                        svc.sync_repo(db, workspace_id, repo.full_name, call, repo)
                    )
                except Exception as exc:
                    db.rollback()
                    results.append(
                        {"repo": repo.full_name, "error": str(exc)[:200]}
                    )

            return results

        results = await run_in_threadpool(work)

    return {"results": results}


@router.get("/dev-events")
def get_dev_events(
    workspace_id: int,
    repo: str | None = None,
    event_type: str | None = None,
    days: int = 30,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    rows = svc.list_events(
        db,
        workspace_id,
        repo=repo,
        event_type=event_type,
        days=days,
        limit=limit,
    )

    return [_event_json(r) for r in rows]


@router.get("/code-index/status")
def code_index_status(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    return [
        cidx.index_status(db, workspace_id, r.full_name)
        for r in svc.list_tracked_repos(db, workspace_id)
    ]


@router.post("/code-index/run")
async def code_index_run(
    workspace_id: int,
    repo: str,
    scan: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Index one tracked repository in a 40 second batch. Press again until done."""

    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    tracked = {r.full_name for r in svc.list_tracked_repos(db, workspace_id)}

    if repo not in tracked:
        raise HTTPException(status_code=404, detail="Repository is not tracked.")

    try:
        async with github_caller(db, workspace_id, current_user.id) as call:

            def work():
                return cidx.run_batch(db, workspace_id, repo, call, scan=scan)

            return await run_in_threadpool(work)

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)[:200])


@router.get("/digest")
def get_digest(
    workspace_id: int,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """A copy-ready summary of the period, built from saved data only."""

    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    return digest_service.build_digest(db, workspace_id, days)


# ------------------------------------------------------------
# Slack watch words (Slack can only be searched by word)
# ------------------------------------------------------------

from pydantic import BaseModel

from app.services import slack_sync_service as slack_svc


class SlackTermCreate(BaseModel):
    term: str


def _term_json(term):
    return {
        "id": term.id,
        "term": term.term,
        "last_synced_at": term.last_synced_at.isoformat() if term.last_synced_at else None,
    }


@asynccontextmanager
async def slack_caller(db: Session, workspace_id: int, user_id: int):
    """call(tool_name, arguments) for the one read-only Slack search tool."""

    if get_user_integration(db=db, user_id=user_id, provider="slack") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack is not connected.",
        )

    registry = ToolRegistry()

    mcp_permission_service.add_workspace_plugin(workspace_id, "slack")

    await mcp_integration_manager.connect_slack(
        db=db, user_id=user_id, registry=registry
    )

    executor = ToolExecutor(
        registry,
        ToolContext(db=db, workspace_id=workspace_id, user_id=user_id),
        mcp_permission_service=mcp_permission_service,
    )

    def call(tool_name: str, arguments: dict):
        if tool_name not in slack_svc.ALLOWED_SLACK_SYNC_TOOLS:
            raise PermissionError(f"Tool '{tool_name}' is not allowed for sync.")

        return executor.execute(tool_name=tool_name, arguments=arguments)

    # The Slack connection is shared with the chat, so it stays open.
    yield call


@router.get("/slack-terms")
def get_slack_terms(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    return [_term_json(t) for t in slack_svc.list_terms(db, workspace_id)]


@router.post("/slack-terms")
def add_slack_term(
    workspace_id: int,
    body: SlackTermCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    try:
        return _term_json(slack_svc.add_term(db, workspace_id, body.term))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/slack-terms/{term_id}")
def remove_slack_term(
    workspace_id: int,
    term_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    if not slack_svc.delete_term(db, workspace_id, term_id):
        raise HTTPException(status_code=404, detail="Watch word not found")

    return {"deleted": True}


@router.post("/slack-sync")
async def sync_slack(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    if not slack_svc.list_terms(db, workspace_id):
        raise HTTPException(status_code=400, detail="Add a watch word first.")

    async with slack_caller(db, workspace_id, current_user.id) as call:
        results = await run_in_threadpool(
            lambda: slack_svc.sync_terms(db, workspace_id, call)
        )

    return {"results": results}


@router.delete("/slack-events")
def clear_slack_events(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove every saved Slack message of this workspace."""

    require_workspace_access(db=db, workspace_id=workspace_id, user_id=current_user.id)

    return {"deleted": slack_svc.delete_slack_events(db, workspace_id)}
