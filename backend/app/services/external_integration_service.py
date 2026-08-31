from sqlalchemy.orm import Session

from app.mcp.oauth.base import OAuthToken
from app.mcp.oauth.encryption import encrypt_token
from app.models.external_integration import ExternalIntegration
from app.repositories import external_integration_repository


SUPPORTED_PROVIDERS = {
    "github",
    "slack",
}


def get_user_integration(
    db: Session,
    user_id: int,
    provider: str,
):
    provider = provider.lower().strip()

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported integration provider: {provider}"
        )

    return external_integration_repository.get_integration(
        db=db,
        user_id=user_id,
        provider=provider,
    )


def save_oauth_token(
    db: Session,
    user_id: int,
    provider: str,
    token: OAuthToken,
):
    provider = provider.lower().strip()

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported integration provider: {provider}"
        )

    if not token.access_token:
        raise ValueError(
            "OAuth access token cannot be empty."
        )

    encrypted_access_token = encrypt_token(
        token.access_token
    )

    encrypted_refresh_token = (
        encrypt_token(token.refresh_token)
        if token.refresh_token
        else None
    )

    existing = external_integration_repository.get_integration(
        db=db,
        user_id=user_id,
        provider=provider,
    )

    if existing:
        existing.access_token = encrypted_access_token
        existing.refresh_token = encrypted_refresh_token
        existing.expires_at = token.expires_at
        existing.scope = token.scope
        existing.provider_user_id = token.provider_user_id

        return external_integration_repository.update_integration(
            db=db,
            integration=existing,
        )

    integration = ExternalIntegration(
        user_id=user_id,
        provider=provider,
        provider_user_id=token.provider_user_id,
        access_token=encrypted_access_token,
        refresh_token=encrypted_refresh_token,
        expires_at=token.expires_at,
        scope=token.scope,
    )

    return external_integration_repository.create_integration(
        db=db,
        integration=integration,
    )


def delete_user_integration(
    db: Session,
    user_id: int,
    provider: str,
) -> bool:
    provider = provider.lower().strip()

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported integration provider: {provider}"
        )

    integration = external_integration_repository.get_integration(
        db=db,
        user_id=user_id,
        provider=provider,
    )

    if not integration:
        return False

    external_integration_repository.delete_integration(
        db=db,
        integration=integration,
    )

    return True