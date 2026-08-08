from fastapi import APIRouter

from app.api.routes import health, users, auth, workspaces, chats, messages, memories


api_router = APIRouter()


api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(chats.router)
api_router.include_router(messages.router)
api_router.include_router(memories.router)