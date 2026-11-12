import json
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import get_db, User, ClientKey
from router.management import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discord", tags=["Discord Auth"])

DISCORD_AUTH_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"


async def _discord_post(path: str, body: dict, extra_headers: dict | None = None) -> dict:
    headers = {"Content-Type": "application/x-www-form-urlencoded", **(extra_headers or {})}
    async with httpx.AsyncClient() as client:
        resp = await client.post(path, data=body, headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def _discord_get(path: str, token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(path, headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


def _build_auth_url(state: str) -> str:
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return f"{DISCORD_AUTH_URL}?{urlencode(params)}"


def _get_redis():
    """获取 Redis 客户端单例，避免每次请求新建连接。"""
    import redis as redis_lib
    from config import settings as cfg
    return redis_lib.from_url(cfg.redis_conn_string, decode_responses=True)


def _store_state(state: str) -> None:
    """将授权 state 存入 Redis，设置 10 分钟过期，防止 CSRF。"""
    r = _get_redis()
    r.setex(f"discord_oauth_state:{state}", 600, "1")


def _validate_state(state: str) -> bool:
    """校验 state 是否合法（一次性消耗）。"""
    r = _get_redis()
    return r.delete(f"discord_oauth_state:{state}") == 1


@router.get("/authorize")
async def discord_authorize(state: str = Query(...)):
    """返回 Discord 授权页 URL，前端用 window.open 打开。"""
    if not settings.discord_client_id or not settings.discord_client_secret:
        raise HTTPException(status_code=503, detail="Discord OAuth not configured")
    _store_state(state)
    return {"authorize_url": _build_auth_url(state)}


@router.get("/callback", response_class=HTMLResponse)
async def discord_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Discord OAuth 回调：换取 access_token，查询用户信息，完成登录/注册。"""
    if not settings.discord_client_id or not settings.discord_client_secret:
        raise HTTPException(status_code=503, detail="Discord OAuth not configured")

    # 校验 state，防止 CSRF（一次性消耗）
    if not _validate_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    # 换取 Discord access token
    token_data = await _discord_post(
        DISCORD_TOKEN_URL,
        {
            "client_id": settings.discord_client_id,
            "client_secret": settings.discord_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.discord_redirect_uri,
        },
    )
    discord_access_token = token_data.get("access_token")
    if not discord_access_token:
        raise HTTPException(status_code=400, detail="Failed to exchange Discord code for token")

    # 获取 Discord 用户信息
    try:
        discord_user = await _discord_get(DISCORD_USER_URL, discord_access_token)
    except httpx.HTTPStatusError as e:
        logger.warning(f"Discord user info fetch failed: {e.response.status_code}")
        raise HTTPException(status_code=401, detail="Failed to get Discord user information")

    discord_id = str(discord_user["id"])
    discord_username = discord_user.get("username", "discord_user")
    discriminator = discord_user.get("discriminator", "0")
    display_name = f"{discord_username}#{discriminator}" if discriminator != "0" else discord_username

    # 查找或创建本地用户
    result = await db.execute(select(User).where(User.discord_id == discord_id))
    user = result.scalars().first()

    if user:
        # 已有账号：更新 Discord 信息（用户名可能变更）
        user.discord_username = display_name
        await db.commit()
        await db.refresh(user)
        logger.info(f"Discord login: user {user.username} logged in via Discord id={discord_id}")
    else:
        # 新用户：自动注册
        safe_username = display_name[:50]
        base_username = safe_username
        counter = 1
        while True:
            try:
                existing = await db.execute(select(User).where(User.username == safe_username))
                if not existing.scalars().first():
                    break
                safe_username = f"{base_username[:40]}{counter}"
                counter += 1
                if counter > 999:
                    raise HTTPException(status_code=400, detail="Discord username conflict, please contact admin")
            except IntegrityError:
                await db.rollback()
                safe_username = f"{base_username[:40]}{counter}"
                counter += 1
                if counter > 999:
                    raise HTTPException(status_code=400, detail="Discord username conflict, please contact admin")

        user = User(
            username=safe_username,
            password_hash="",  # OAuth 用户无密码
            role="user",
            discord_id=discord_id,
            discord_username=display_name,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

        # 自动创建客户端授权密钥
        new_key = f"sk-agnes-{secrets.token_hex(16)}"
        client_key = ClientKey(
            user_id=user.id, key=new_key, name="Default", quota=-1.0, used_quota=0.0
        )
        db.add(client_key)
        await db.commit()
        await db.refresh(client_key)
        logger.info(f"Discord auto-register: user {user.username} created from Discord id={discord_id}")

    access_token = create_access_token(data={"sub": user.username})
    role = user.role
    username = user.username

    # 使用 json.dumps 安全序列化，防止特殊字符破坏 JS 语法
    js_username = json.dumps(username)
    js_role = json.dumps(role)
    js_access_token = json.dumps(access_token)

    html = f"""<!DOCTYPE html>
<html>
<head><title>登录中...</title></head>
<body>
<script>
  var token = {js_access_token};
  var role = {js_role};
  var username = {js_username};
  try {{
    localStorage.setItem('agnes2api_token', token);
    localStorage.setItem('agnes2api_role', role);
    localStorage.setItem('agnes2api_username', username);
  }} catch(e) {{}}
  window.opener.postMessage({{ type: 'DISCORD_AUTH_SUCCESS', token, role, username }}, '*');
  window.close();
</script>
</body>
</html>"""
    return html
