from dataclasses import replace
import secrets
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.mcp.oauth.slack import SlackOAuthProvider
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.mcp.oauth.github import GitHubOAuthProvider
from app.models.user import User
from app.services.external_integration_service import save_oauth_token
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

    return {
        "message": "GitHub connected successfully.",
        "provider": integration.provider,
        "provider_user_id": integration.provider_user_id,
    }

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

    return {
        "message": "Slack connected successfully.",
        "provider": integration.provider,
        "provider_user_id": integration.provider_user_id,
    }

