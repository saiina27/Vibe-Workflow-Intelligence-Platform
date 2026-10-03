from dataclasses import replace
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.mcp.oauth.slack import SlackOAuthProvider
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.core.config import settings
from app.mcp.oauth.github import GitHubOAuthProvider
from app.models.user import User
import asyncio
from fastapi.concurrency import run_in_threadpool
from app.mcp.runtime import mcp_integration_manager
from pydantic import BaseModel, Field
import httpx
from app.mcp.oauth.encryption import encrypt_token
from app.models.external_integration import ExternalIntegration
from app.repositories import external_integration_repository
from app.services.external_integration_service import (
    get_user_integration,
    save_oauth_token,
)
from app.services.oauth_state_service import (
    consume_oauth_state,
    create_oauth_state,
)


router = APIRouter(
    prefix="/oauth",
    tags=["OAuth"],
)


github_provider = GitHubOAuthProvider()
slack_provider = SlackOAuthProvider()


def _drop_github_runtime(user_id: int) -> None:
    """
    Close the cached in-memory GitHub MCP client for this user,
    so the next connect uses the freshly stored token.

    Must run in a worker thread (no running event loop).
    """
    try:
        asyncio.run(
            mcp_integration_manager.disconnect_github(user_id)
        )
    except Exception as exc:
        print(
            f"Failed to close GitHub MCP runtime "
            f"for user {user_id}: {exc!r}"
        )


@router.get("/github/connect")
def github_connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start the GitHub OAuth authorization flow.

    The OAuth state is tied to the authenticated Vibe user
    and is used to protect the callback against CSRF attacks.
    """

    oauth_state = create_oauth_state(
        db=db,
        user_id=current_user.id,
        provider=github_provider.name,
    )

    authorization_url = (
        github_provider.get_authorization_url(
            oauth_state.state
        )
    )

    return {
        "authorization_url": authorization_url,
    }

@router.get("/github/status")
def github_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    integration = get_user_integration(
        db=db,
        user_id=current_user.id,
        provider="github",
    )

    return {
        "connected": integration is not None,
    }

@router.delete("/github/disconnect")
def github_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    integration = get_user_integration(
        db=db,
        user_id=current_user.id,
        provider="github",
    )

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub is not connected.",
        )

    external_integration_repository.delete_integration(
        db=db,
        integration=integration,
    )

    _drop_github_runtime(current_user.id)

    return {
        "disconnected": True,
    }

@router.get("/github/callback")
async def github_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Handle the GitHub OAuth callback.

    The user identity is recovered from the previously
    stored OAuth state, rather than trusting a user ID
    supplied by the browser.
    """

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub OAuth authorization failed: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub authorization code is missing.",
        )

    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is missing.",
        )

    try:
        oauth_state = consume_oauth_state(
            db=db,
            state=state,
            provider=github_provider.name,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        token = await github_provider.exchange_code(
            code
        )

        github_user = await github_provider.get_user(
            token.access_token
        )

        provider_user_id = github_user.get("id")

        if provider_user_id is None:
            raise RuntimeError(
                "GitHub user ID was not returned."
            )

        token = replace(
            token,
            provider_user_id=str(provider_user_id),
        )

        integration = save_oauth_token(
            db=db,
            user_id=oauth_state.user_id,
            provider=github_provider.name,
            token=token,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to complete GitHub OAuth.",
        ) from exc

    return RedirectResponse(
        url=settings.frontend_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.get("/slack/connect")
def slack_connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start the Slack OAuth authorization flow using PKCE.
    """

    # Generate the PKCE verifier.
    code_verifier = (
        slack_provider.generate_code_verifier()
    )

    # Generate the OAuth CSRF state and persist
    # the verifier together with it.
    oauth_state = create_oauth_state(
        db=db,
        user_id=current_user.id,
        provider=slack_provider.name,
        code_verifier=code_verifier,
    )

    # Convert verifier -> S256 challenge.
    code_challenge = (
        slack_provider.generate_code_challenge(
            code_verifier
        )
    )

    authorization_url = (
        slack_provider.get_authorization_url(
            state=oauth_state.state,
            code_challenge=code_challenge,
        )
    )

    return {
        "authorization_url": authorization_url,
    }

@router.get("/slack/status")
def slack_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    integration = get_user_integration(
        db=db,
        user_id=current_user.id,
        provider="slack",
    )

    return {
        "connected": integration is not None,
    }

@router.delete("/slack/disconnect")
def slack_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    integration = get_user_integration(
        db=db,
        user_id=current_user.id,
        provider="slack",
    )

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Slack is not connected.",
        )

    external_integration_repository.delete_integration(
        db=db,
        integration=integration,
    )

    return {
        "disconnected": True,
    }

@router.get("/slack/callback")
async def slack_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Handle the Slack OAuth callback.

    The Vibe user and PKCE verifier are recovered
    from the stored OAuth state.
    """

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slack OAuth authorization failed: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack authorization code is missing.",
        )

    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state is missing.",
        )

    try:
        oauth_state = consume_oauth_state(
            db=db,
            state=state,
            provider=slack_provider.name,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not oauth_state.code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack PKCE code verifier is missing.",
        )

    try:
        token = await slack_provider.exchange_code(
            code=code,
            code_verifier=oauth_state.code_verifier,
        )

        slack_user = await slack_provider.get_user(
            token.access_token
        )

        provider_user_id = (
            slack_user.get("user_id")
        )

        if provider_user_id is None:
            provider_user_id = (
                token.provider_user_id
            )

        if provider_user_id is None:
            raise RuntimeError(
                "Slack user ID was not returned."
            )

        token = replace(
            token,
            provider_user_id=str(
                provider_user_id
            ),
        )

        integration = save_oauth_token(
            db=db,
            user_id=oauth_state.user_id,
            provider=slack_provider.name,
            token=token,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to complete Slack OAuth.",
        ) from exc

    return RedirectResponse(
        url=settings.frontend_url,
        status_code=status.HTTP_302_FOUND,
    )


class GitHubPATRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)


@router.post("/github/pat")
async def github_save_pat(
    payload: GitHubPATRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Connect GitHub using a user-supplied Personal Access Token.

    The token is validated against GitHub, encrypted, and stored
    in the same external_integrations row used by OAuth.
    The token is never returned in any response.
    """

    token = payload.token.strip()

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach GitHub to validate the token.",
        ) from exc

    if response.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub rejected this token. Check it and try again.",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub token validation failed.",
        )

    github_user = response.json()
    provider_user_id = github_user.get("id")

    if provider_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GitHub user ID was not returned.",
        )

    encrypted_token = encrypt_token(token)

    integration = external_integration_repository.get_integration(
        db=db,
        user_id=current_user.id,
        provider="github",
    )

    if integration is None:
        external_integration_repository.create_integration(
            db=db,
            integration=ExternalIntegration(
                user_id=current_user.id,
                provider="github",
                provider_user_id=str(provider_user_id),
                access_token=encrypted_token,
                refresh_token=None,
                expires_at=None,
                scope="pat",
            ),
        )
    else:
        integration.provider_user_id = str(provider_user_id)
        integration.access_token = encrypted_token
        integration.refresh_token = None
        integration.expires_at = None
        integration.scope = "pat"

        external_integration_repository.update_integration(
            db=db,
            integration=integration,
        )

    await run_in_threadpool(
        _drop_github_runtime,
        current_user.id,
    )

    return {
        "connected": True,
        "github_login": github_user.get("login"),
    }
