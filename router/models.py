import logging
import time
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_db, AvailableModel
from service.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Models"], dependencies=[Depends(verify_api_key)])


@router.get("/v1/models")
async def list_openai_models(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """OpenAI 兼容的可用模型列表接口。

    返回所有启用状态的模型，包装为 OpenAI 的原生 JSON 格式：
    {"object": "list", "data": [...]}
    """
    result = await db.execute(select(AvailableModel).where(AvailableModel.is_active == True))
    models = result.scalars().all()

    data = []
    for m in models:
        created_ts = int(m.created_at.timestamp()) if m.created_at else int(time.time())
        data.append({
            "id": m.name,
            "object": "model",
            "created": created_ts,
            "owned_by": m.provider
        })

    return {
        "object": "list",
        "data": data
    }


@router.get("/v1beta/models")
async def list_gemini_models(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Gemini 兼容的可用模型列表接口。

    返回所有启用状态的模型，包装为 Gemini 的原生 JSON 格式：
    {"models": [...]}
    """
    result = await db.execute(select(AvailableModel).where(AvailableModel.is_active == True))
    models = result.scalars().all()

    data = []
    for m in models:
        data.append({
            "name": f"models/{m.name}",
            "version": "1.0",
            "displayName": m.name,
            "description": f"{m.provider} {m.type} model",
            "supportedGenerationMethods": ["generateContent"]
        })

    return {
        "models": data
    }