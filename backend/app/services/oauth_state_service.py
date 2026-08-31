
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.oauth_state import OAuthState
from app.repositories import oauth_state_repository


OAUTH_STATE_TTL_MINUTES = 10


def create_oauth_state(
    db: Session,
    user_id: int,
    provider: str,
    code_verifier: str | None = None,
) -> OAuthState:
    provider = provider.lower().strip()

    if not provider:
        raise ValueError(
            "OAuth provider cannot be empty."
        )

    state = secrets.token_urlsafe(32)

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=OAUTH_STATE_TTL_MINUTES
        )
    )

    oauth_state = OAuthState(
        user_id=user_id,
        provider=provider,
        state=state,
        code_verifier=code_verifier,
        expires_at=expires_at,
    )

    return oauth_state_repository.create_state(
        db=db,
        oauth_state=oauth_state,
    )


def consume_oauth_state(
    db: Session,
    state: str,
    provider: str,
) -> OAuthState:
    if not state:
        raise ValueError(
            "OAuth state cannot be empty."
        )

    provider = provider.lower().strip()

    oauth_state = oauth_state_repository.get_state(
        db=db,
        state=state,
    )

    if oauth_state is None:
        raise ValueError(
            "Invalid OAuth state."
        )

    if oauth_state.provider != provider:
        raise ValueError(
            "OAuth state provider mismatch."
        )

    now = datetime.now(timezone.utc)

    expires_at = oauth_state.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(
            tzinfo=timezone.utc
        )

    if expires_at <= now:
        oauth_state_repository.delete_state(
            db=db,
            oauth_state=oauth_state,
        )

        raise ValueError(
            "OAuth state has expired."
        )

    # OAuth state is single-use.
    oauth_state_repository.delete_state(
        db=db,
        oauth_state=oauth_state,
    )

    return oauth_state

