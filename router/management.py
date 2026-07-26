import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from models.database import get_db, User, ClientKey, UpstreamKey, SystemConfig
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manage", tags=["Management"])

import jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import anyio
import bcrypt
from config import settings
security = HTTPBearer()


# ====================
# Helper Functions
# ====================

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前已登录用户。"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def _trigger_hot_reload(db: AsyncSession) -> None:
    """当上游 Key 发生变化时，热重载内存中的 Key Pool。"""
    result = await db.execute(select(UpstreamKey).where(UpstreamKey.status == "active"))
    db_keys = result.scalars().all()
    active_keys = [{"key": k.key, "weight": k.weight} for k in db_keys]

    from service.key_stats import get_key_stats_manager
    from service.simple_key_pool import get_key_pool_manager

    stats_manager = get_key_stats_manager()
    for k in active_keys:
        stats_manager.register_key(k["key"])

    key_pool = get_key_pool_manager()
    await key_pool.initialize(active_keys)


# ====================
# Request/Response Models
# ====================

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: Optional[datetime.datetime] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpstreamKeyCreateRequest(BaseModel):
    name: str
    key: str


class UpstreamKeyResponse(BaseModel):
    id: int
    name: str
    key: str
    weight: int
    status: str
    disabled_reason: Optional[str] = None
    disabled_at: Optional[datetime.datetime] = None
    user_id: Optional[int] = None


class KeyCreateRequest(BaseModel):
    name: str


class KeyResponse(BaseModel):
    id: int
    name: str
    key: str
    status: str
    quota: float
    used_quota: float
    user_id: int


# ====================
# API Endpoints
# ====================

@router.post("/login", response_model=TokenResponse)
async def login_for_access_token(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """登录接口（固定 admin 用户）。"""
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalars().first()

    # Bootstrap first admin
    if req.username == "admin" and not user:
        hashed = await anyio.to_thread.run_sync(
            lambda: bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
        )
        user = User(username="admin", password_hash=hashed, role="admin")
        db.add(user)
        await db.commit()
        await db.refresh(user)

    is_valid = False
    if user:
        is_valid = await anyio.to_thread.run_sync(
            lambda: bcrypt.checkpw(
                req.password.encode("utf-8"), user.password_hash.encode("utf-8")
            )
        )

    if not user or not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: User = Depends(get_current_user),
):
    return MeResponse(
        id=user.id, username=user.username, role=user.role,
        created_at=user.created_at
    )


@router.put("/password")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户的密码。"""
    is_valid = await anyio.to_thread.run_sync(
        lambda: bcrypt.checkpw(
            req.old_password.encode("utf-8"), user.password_hash.encode("utf-8")
        )
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="旧密码不正确")

    hashed = await anyio.to_thread.run_sync(
        lambda: bcrypt.hashpw(req.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    )
    user.password_hash = hashed
    await db.commit()
    return {"status": "success"}


# --- ClientKey (授权密钥管理) ---

@router.get("/keys", response_model=List[KeyResponse])
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[KeyResponse]:
    """获取授权密钥。"""
    result = await db.execute(select(ClientKey).where(ClientKey.user_id == current_user.id))
    return result.scalars().all()


@router.post("/keys", response_model=KeyResponse)
async def create_key(
    req: KeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyResponse:
    """创建授权密钥。"""
    result = await db.execute(select(ClientKey).where(ClientKey.user_id == current_user.id))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="每用户仅 1 把授权密钥")

    new_key = f"sk-agnes-{uuid.uuid4().hex}"
    client_key = ClientKey(user_id=current_user.id, key=new_key, name=req.name, quota=-1.0, used_quota=0.0)
    db.add(client_key)
    await db.commit()
    await db.refresh(client_key)
    return client_key


@router.post("/keys/reset", response_model=KeyResponse)
async def reset_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyResponse:
    """重置授权密钥。删旧建新。"""
    result = await db.execute(select(ClientKey).where(ClientKey.user_id == current_user.id))
    client_key = result.scalars().first()
    if not client_key:
        raise HTTPException(status_code=404, detail="Key not found")

    old_name = client_key.name
    old_used_quota = client_key.used_quota

    await db.delete(client_key)
    await db.commit()

    new_key = f"sk-agnes-{uuid.uuid4().hex}"
    new_client_key = ClientKey(user_id=current_user.id, key=new_key, name=old_name, quota=-1.0, used_quota=old_used_quota)
    db.add(new_client_key)
    await db.commit()
    await db.refresh(new_client_key)
    return new_client_key


@router.put("/keys/{key_id}/status")
async def toggle_key_status(
    key_id: int,
    status_val: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """启用/停用授权密钥。"""
    if status_val not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    result = await db.execute(select(ClientKey).where(ClientKey.id == key_id))
    client_key = result.scalars().first()
    if not client_key:
        raise HTTPException(status_code=404, detail="Key not found")

    if client_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    client_key.status = status_val
    await db.commit()
    return {"status": "success", "new_status": client_key.status}


@router.delete("/keys/{key_id}")
async def delete_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除授权密钥。"""
    result = await db.execute(select(ClientKey).where(ClientKey.id == key_id))
    client_key = result.scalars().first()
    if not client_key:
        raise HTTPException(status_code=404, detail="Key not found")

    if client_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(client_key)
    await db.commit()
    return {"status": "success"}


# --- UpstreamKey (上游通道管理) ---

@router.get("/upstream-keys", response_model=List[UpstreamKeyResponse])
async def list_upstream_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[UpstreamKeyResponse]:
    """获取上游 Key。"""
    result = await db.execute(select(UpstreamKey))
    return result.scalars().all()


@router.post("/upstream-keys", response_model=UpstreamKeyResponse)
async def create_upstream_key(
    req: UpstreamKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpstreamKeyResponse:
    """创建上游 Key。上传时自动检验，失败则禁用。"""
    from service.key_validator import validate_key

    up_key = UpstreamKey(
        user_id=current_user.id,
        name=req.name,
        key=req.key,
        weight=1,
        status="active",
    )

    # 先检验 Key
    success, message = await validate_key(req.key)
    if not success:
        up_key.status = "disabled"
        up_key.disabled_reason = f"上传检验失败: {message}"

    db.add(up_key)
    try:
        await db.commit()
        await db.refresh(up_key)
        await _trigger_hot_reload(db)
        return up_key
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create upstream key: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/upstream-keys/{key_id}/weight")
async def update_upstream_key_weight(
    key_id: int,
    weight: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """调整上游 Key 权重。"""
    if weight < 1:
        raise HTTPException(status_code=400, detail="Weight must be at least 1")

    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    up_key.weight = weight
    await db.commit()
    await _trigger_hot_reload(db)
    return {"status": "success", "new_weight": up_key.weight}


@router.put("/upstream-keys/{key_id}/status")
async def toggle_upstream_key_status(
    key_id: int,
    status_val: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用上游 Key。"""
    if status_val not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    up_key.status = status_val
    if status_val == "active":
        up_key.disabled_reason = None
        up_key.disabled_at = None

    await db.commit()
    await _trigger_hot_reload(db)
    return {"status": "success", "new_status": up_key.status}


@router.delete("/upstream-keys/clean-disabled", response_model=dict)
async def clean_disabled_keys(
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除所有 status = 'disabled' 的上游 Key。"""
    result = await db.execute(select(UpstreamKey).where(UpstreamKey.status == "disabled"))
    disabled_keys = result.scalars().all()

    if not disabled_keys:
        return {"status": "ok", "message": "没有需要清理的 Key", "deleted": 0}

    deleted = 0
    for up_key in disabled_keys:
        from service.key_stats import get_key_stats_manager
        get_key_stats_manager().unregister_key(up_key.key)

        await db.delete(up_key)
        deleted += 1

    await db.commit()
    await _trigger_hot_reload(db)

    return {
        "status": "ok",
        "message": f"已清理 {deleted} 个无效的 Key",
        "deleted": deleted,
    }


@router.delete("/upstream-keys/{key_id}")
async def delete_upstream_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除上游 Key。"""
    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    full_key = up_key.key

    await db.delete(up_key)
    await db.commit()

    from service.key_stats import get_key_stats_manager
    get_key_stats_manager().unregister_key(full_key)

    await _trigger_hot_reload(db)
    return {"status": "success"}


@router.post("/upstream-keys/{key_id}/validate", response_model=dict)
async def validate_upstream_key(
    key_id: int,
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """手动检验指定 Key。失败则禁用，成功则启用。"""
    from service.key_validator import validate_key
    from service.key_disable import disable_key_and_check_user_rate

    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    success, message = await validate_key(up_key.key)

    if success:
        if up_key.status == "disabled":
            up_key.status = "active"
            up_key.disabled_reason = None
            up_key.disabled_at = None
            await db.commit()
            await _trigger_hot_reload(db)
            return {"status": "ok", "message": "检验通过，Key 已恢复为启用", "validated": True}
        return {"status": "ok", "message": "检验通过", "validated": True}
    else:
        await disable_key_and_check_user_rate(db, up_key, f"手动检验失败: {message}")
        return {"status": "ok", "message": f"检验失败，Key 已禁用: {message}", "validated": False}


@router.post("/upstream-keys/validate-all", response_model=dict)
async def validate_all_upstream_keys(
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    concurrency: int = Query(default=100, ge=1, le=200),
) -> dict:
    """全量检验所有 Key，失败禁用，成功启用。"""
    from service.key_validator import validate_all_keys
    from service.key_disable import disable_key_and_check_user_rate

    result = await db.execute(select(UpstreamKey))
    all_keys = result.scalars().all()

    if not all_keys:
        return {"status": "ok", "message": "没有可检验的 Key", "results": [], "summary": {}}

    results = await validate_all_keys(all_keys, concurrency=concurrency)

    success_count = 0
    fail_count = 0

    for r in results:
        up_key = next((k for k in all_keys if k.id == r["key_id"]), None)
        if not up_key:
            continue

        if not r["success"]:
            if up_key.status != "disabled":
                await disable_key_and_check_user_rate(db, up_key, f"全量检验失败: {r['message']}")
            fail_count += 1
        else:
            if up_key.status == "disabled":
                up_key.status = "active"
                up_key.disabled_reason = None
                up_key.disabled_at = None
            success_count += 1

    try:
        await db.commit()
    except Exception:
        await db.rollback()

    await _trigger_hot_reload(db)

    return {
        "status": "ok",
        "results": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
        },
    }


# --- Dashboard ---

@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
):
    """全局模型成功率看板。"""
    from service.key_stats import get_key_stats_manager
    stats_manager = get_key_stats_manager()
    return stats_manager.get_total_stats()


@router.get("/upstream-stats")
async def get_upstream_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取上游渠道的健康度统计。"""
    result = await db.execute(select(UpstreamKey))
    db_keys = result.scalars().all()

    from service.key_stats import APIKeyStats
    key_map: dict[str, dict] = {}
    for k in db_keys:
        masked = APIKeyStats._compute_key_prefix(k.key)
        key_map[masked] = {"name": k.name, "status": k.status}

    from service.key_stats import get_key_stats_manager
    stats_manager = get_key_stats_manager()
    raw_stats = stats_manager.get_all_stats()

    enriched_stats = []
    for stat in raw_stats:
        prefix = stat.get("key_prefix")
        mapped_info = key_map.get(prefix, {"name": "未知/已删除渠道", "status": "unknown"})
        summary = stat.get("summary", {})

        enriched_stats.append({
            "name": mapped_info["name"],
            "masked_key": prefix,
            "status": mapped_info["status"],
            "total": summary.get("total", 0),
            "success": summary.get("success", 0),
            "failure": summary.get("failure", 0),
            "success_rate": summary.get("success_rate", 0.0),
            "text": stat.get("text", {}),
            "image": stat.get("image", {}),
            "video": stat.get("video", {}),
        })

    enriched_stats.sort(key=lambda x: x["total"], reverse=True)
    return enriched_stats


@router.get("/dashboard/timeline")
async def get_dashboard_timeline(
    hours: int = 24,
    current_user: User = Depends(get_current_user),
):
    """获取模型调用时间序列。"""
    from service.key_stats import get_key_stats_manager
    stats_mgr = get_key_stats_manager()
    return stats_mgr.get_model_timeline(hours)
