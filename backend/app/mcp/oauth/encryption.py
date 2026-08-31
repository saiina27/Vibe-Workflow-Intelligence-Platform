from cryptography.fernet import Fernet

from app.core.config import settings


def _get_fernet() -> Fernet:
    key = settings.oauth_encryption_key

    if not key:
        raise RuntimeError(
            "OAuth encryption key is not configured."
        )

    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise RuntimeError(
            "Invalid OAuth encryption key."
        ) from exc


def encrypt_token(value: str) -> str:
    if not value:
        raise ValueError(
            "Cannot encrypt an empty token."
        )

    return _get_fernet().encrypt(
        value.encode()
    ).decode()


def decrypt_token(value: str) -> str:
    if not value:
        raise ValueError(
            "Cannot decrypt an empty token."
        )

    return _get_fernet().decrypt(
        value.encode()
    ).decode()