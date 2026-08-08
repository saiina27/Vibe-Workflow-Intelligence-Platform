from fastapi import APIRouter

from app.ai.usage_metrics import usage_metrics


router = APIRouter(tags=["Health"])


@router.get("/")
def health():
    return {
        "status": "healthy",
        "message": "Welcome to Vibe 🚀"
    }


@router.get("/ai-metrics")
def ai_metrics():
    return usage_metrics.get_metrics()