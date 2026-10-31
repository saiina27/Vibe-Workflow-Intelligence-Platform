from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.jwt import create_access_token
from app.utils.security import hash_password, verify_password


# Checked when the email is unknown, so a missing account and a wrong
# password take about the same time.
try:
    _DUMMY_HASH = hash_password("not-a-real-password")
except Exception:
    _DUMMY_HASH = ""


def _password_ok(password: str, hashed: str) -> bool:
    """A password check that never raises: any problem means "no"."""

    try:
        return bool(verify_password(password, hashed))
    except Exception:
        return False


def authenticate_user(
    db: Session,
    email: str,
    password: str,
):
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user:
        _password_ok(password, _DUMMY_HASH)
        return None

    if not _password_ok(
        password,
        user.hashed_password,
    ):
        return None

    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
        }
    )

    return token
