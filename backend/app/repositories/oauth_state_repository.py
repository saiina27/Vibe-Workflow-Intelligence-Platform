from sqlalchemy.orm import Session

from app.models.oauth_state import OAuthState


def create_state(
    db: Session,
    oauth_state: OAuthState,
) -> OAuthState:
    db.add(oauth_state)
    db.commit()
    db.refresh(oauth_state)

    return oauth_state


def get_state(
    db: Session,
    state: str,
) -> OAuthState | None:
    return (
        db.query(OAuthState)
        .filter(
            OAuthState.state == state
        )
        .first()
    )


def delete_state(
    db: Session,
    oauth_state: OAuthState,
) -> None:
    db.delete(oauth_state)
    db.commit()
