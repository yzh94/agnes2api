import logging
from fastapi import Depends, Request, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    def __init__(self, message: str, code: str = "invalid_api_key"):
        self.message = message
        self.code = code
        super().__init__(message)


async def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    """验证 API Key。

    认证逻辑（单用户模式）：
    1. 如果配置了 server_api_key，匹配则直接通过
    2. 否则从 DB 的 ClientKey 表验证
    """
    if not settings.server_api_key and not settings.database_url:
        logger.debug("Auth bypassed — no server_api_key or database configured")
        return

    # 优先尝试 Authorization: Bearer
    api_key = credentials.credentials if credentials else None

    # 兼容 Gemini SDK 的 x-goog-api-key 请求头
    if not api_key:
        api_key = request.headers.get("x-goog-api-key")

    if api_key is None:
        raise AuthenticationError(
            message="Missing API key. Provide it via Authorization: Bearer <key> or x-goog-api-key header",
            code="invalid_api_key",
        )

    # 兼容单机配置：server_api_key 作为 master key
    if settings.server_api_key and api_key == settings.server_api_key:
        logger.debug("Auth OK (Config Match)")
        request.state.api_key = api_key
        request.state.user_id = 0
        return

    # 从 DB 验证 client key
    if settings.database_url:
        try:
            from models.database import AsyncSessionLocal, ClientKey
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(ClientKey).where(ClientKey.key == api_key))
                client_key = result.scalars().first()

                if not client_key:
                    raise AuthenticationError("Incorrect API key provided.", "invalid_api_key")

                if client_key.status != "active":
                    raise AuthenticationError("API Key is disabled or expired.", "invalid_api_key")

                request.state.api_key = api_key
                request.state.user_id = client_key.user_id
                request.state.client_key_id = client_key.id
                return
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Auth DB error: {e}")
            raise AuthenticationError("Internal auth error.", "internal_error")

    raise AuthenticationError("Incorrect API key provided.", "invalid_api_key")
