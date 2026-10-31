from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import UserCreate
from app.utils.security import hash_password


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt only uses the first 72 bytes
MAX_NAME_LENGTH = 100


def _validate_signup(user_data: UserCreate) -> str:
    """Check the sign-up input and return the cleaned full name."""

    name = (user_data.full_name or "").strip()

    if not name:
        raise ValueError("Name cannot be empty.")

    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Name must be at most {MAX_NAME_LENGTH} characters.")

    password = user_data.password or ""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            "(about 72 plain characters)."
        )

    return name


def create_user(
    db: Session,
    user_data: UserCreate,
):
    full_name = _validate_signup(user_data)

    existing_user = user_repository.get_user_by_email(
        db,
        user_data.email,
    )

    if existing_user:
        raise ValueError("Email already registered")

    hashed_password = hash_password(
        user_data.password
    )

    user = User(
        full_name=full_name,
        email=user_data.email,
        hashed_password=hashed_password,
    )

    return user_repository.create_user(
        db,
        user,
    )