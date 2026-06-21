from fastapi import APIRouter
from app.engine.router import ModelRouter

router = APIRouter()


@router.get("/models")
async def list_models():
    router = ModelRouter()
    return {"models": router.list_vision_providers()}
