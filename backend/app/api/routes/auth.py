from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.schemas.auth import TokenResponse
from app.services.auth_service import authenticate_user
from app.core.auth_limits import client_ip, login_failures, wait_text

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip = client_ip(request)
    wait = login_failures.wait_seconds(ip)

    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {wait_text(wait)}.",
            headers={"Retry-After": str(wait)},
        )

    token = authenticate_user(
        db,
        form_data.username,   # email yahan aayegi
        form_data.password,
    )

    if not token:
        login_failures.hit(ip)

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    return {
        "access_token": token,
        "token_type": "bearer",
    }