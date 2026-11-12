import logging
import json
from fastapi import Depends, Request, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from config import settings
from service.redis_key_pool import get_key_pool_manager
from service.rate_limit import enforce_rate_limit, RateLimitError

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
    # database_url 已在配置校验阶段强制非空，旧的空值 bypass 分支为死代码，
    # 已移除。server_api_key 为空时强制走 DB 认证，不再绕过鉴权。

    # 优先尝试 Authorization: Bearer
    api_key = credentials.credentials if credentials else None

    # 兼容 Gemini SDK 的 x-goog-api-key 请求头
    if not api_key:
        api_key = request.headers.get("x-goog-api-key")

    # 兼容 Anthropic SDK 的 x-api-key 请求头
    if not api_key:
        api_key = request.headers.get("x-api-key")

    if api_key is None:
        raise AuthenticationError(
            message="Missing API key. Provide it via Authorization: Bearer <key>, x-goog-api-key or x-api-key header",
            code="invalid_api_key",
        )

    # 兼容单机配置
    if settings.server_api_key and api_key == settings.server_api_key:
        logger.debug("Auth OK (Config Match)")
        request.state.api_key = api_key
        request.state.user_id = 0
        return

    # 如果配置了数据库，通过 Redis 缓存 -> DB 查询来验证
    if settings.database_url:
        try:
            pool_mgr = get_key_pool_manager()
            cache_key = f"AUTH:KEY:{api_key}"
            cached_info = pool_mgr.redis.get(cache_key)

            if cached_info:
                auth_data = json.loads(cached_info)
                if auth_data.get("status") != "active":
                    raise AuthenticationError("API Key is disabled or expired.", "invalid_api_key")
                request.state.api_key = api_key
                request.state.user_id = auth_data.get("user_id")
                request.state.client_key_id = auth_data.get("id")
                # 速率限制（async）
                try:
                    await enforce_rate_limit(request.state.user_id)
                except RateLimitError as e:
                    raise HTTPException(status_code=429, detail={
                        "error": {
                            "message": str(e),
                            "type": "rate_limit_error",
                            "code": "rate_limit_exceeded",
                        }
                    })
                return

            # Cache miss, fetch from DB
            from models.database import AsyncSessionLocal, ClientKey
            from sqlalchemy import select

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(ClientKey).where(ClientKey.key == api_key))
                client_key = result.scalars().first()

                if not client_key:
                    raise AuthenticationError("Incorrect API key provided.", "invalid_api_key")

                if client_key.status != "active":
                    raise AuthenticationError("API Key is disabled or expired.", "invalid_api_key")

                # Cache for 5 minutes
                auth_data = {"user_id": client_key.user_id, "status": client_key.status, "id": client_key.id}
                pool_mgr.redis.setex(cache_key, 300, json.dumps(auth_data))

                request.state.api_key = api_key
                request.state.user_id = client_key.user_id
                request.state.client_key_id = client_key.id

                # 速率限制（async）
                try:
                    await enforce_rate_limit(request.state.user_id)
                except RateLimitError as e:
                    raise HTTPException(status_code=429, detail={
                        "error": {
                            "message": str(e),
                            "type": "rate_limit_error",
                            "code": "rate_limit_exceeded",
                        }
                    })
                return
        except AuthenticationError:
            raise
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Auth DB error: {e}")
            raise AuthenticationError("Internal auth error.", "internal_error")

    raise AuthenticationError("Incorrect API key provided.", "invalid_api_key")
