from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import UserCreate
from app.utils.security import hash_password


def create_user(
    db: Session,
    user_data: UserCreate,
):
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
        full_name=user_data.full_name,
        email=user_data.email,
        hashed_password=hashed_password,
    )

    return user_repository.create_user(
        db,
        user,
    )