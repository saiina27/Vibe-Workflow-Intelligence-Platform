from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import create_user
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.core.auth_limits import (
    client_ip,
    signup_global,
    signup_per_ip,
    wait_text,
)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post(
    "/",
    response_model=UserResponse,
)
def register_user(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    ip = client_ip(request)
    wait = signup_per_ip.wait_seconds(ip)

    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many sign-ups from your network. Try again in {wait_text(wait)}.",
            headers={"Retry-After": str(wait)},
        )

    if signup_global.wait_seconds("all"):
        raise HTTPException(
            status_code=429,
            detail="Sign-ups are paused for today. Please try again tomorrow.",
        )

    signup_per_ip.hit(ip)
    signup_global.hit("all")

    try:
        return create_user(
            db,
            user_data,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user
    