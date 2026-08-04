from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/")
def health():
    return {
        "status": "healthy",
        "message": "Welcome to Vibe 🚀"
    }