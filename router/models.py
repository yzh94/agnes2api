import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_db, AvailableModel
from service.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Models"], dependencies=[Depends(verify_api_key)])


def _openai_format(models) -> dict[str, Any]:
    """OpenAI 原生格式：{"object": "list", "data": [...]}"""
    data = []
    for m in models:
        created_ts = int(m.created_at.timestamp()) if m.created_at else int(time.time())
        data.append({
            "id": m.name,
            "object": "model",
            "created": created_ts,
            "owned_by": m.provider
        })
    return {"object": "list", "data": data}


def _gemini_format(models) -> dict[str, Any]:
    """Gemini 原生格式：{"models": [...]}"""
    data = []
    for m in models:
        data.append({
            "name": f"models/{m.name}",
            "version": "1.0",
            "displayName": m.name,
            "description": f"{m.provider} {m.type} model",
            "supportedGenerationMethods": ["generateContent"]
        })
    return {"models": data}


def _anthropic_format(models) -> dict[str, Any]:
    """Anthropic 原生格式：{"data": [{"type": "model", ...}], "has_more": ...}"""
    data = []
    for m in models:
        created_at = m.created_at.isoformat() if m.created_at else datetime.now().isoformat()
        data.append({
            "type": "model",
            "id": m.name,
            "display_name": f"{m.provider} {m.name}",
            "created_at": created_at,
        })
    result: dict[str, Any] = {
        "data": data,
        "has_more": False,
    }
    if data:
        result["first_id"] = data[0]["id"]
        result["last_id"] = data[-1]["id"]
    return result


@router.get("/v1/models")
async def list_openai_models(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """按请求头自适应格式的可用模型列表接口。

    格式自适应规则：
    - 含 x-goog-api-key 头 -> Gemini 格式（{"models": [...]}）
    - 含 x-api-key + anthropic-version 头 -> Anthropic 格式（{"data": [...]}）
    - 其余（Authorization Bearer）-> OpenAI 格式（{"object": "list", "data": [...]}）
    """
    result = await db.execute(select(AvailableModel).where(AvailableModel.is_active == True))
    models = result.scalars().all()

    if "x-goog-api-key" in request.headers:
        return _gemini_format(models)
    if "x-api-key" in request.headers and "anthropic-version" in request.headers:
        return _anthropic_format(models)
    return _openai_format(models)


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
    return _gemini_format(models)