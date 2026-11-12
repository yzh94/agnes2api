import logging
import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, case, or_
from sqlalchemy.exc import OperationalError
from models.database import get_db, User, ClientKey, UsageLog, UpstreamKey, SystemConfig, Announcement
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
    """获取当前已登录用户（不校验 role）。"""
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


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user(credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return user


async def _trigger_hot_reload(db: AsyncSession) -> None:
    """当上游 Key 发生变化时，热重载内存和 Redis 中的 Key 池（委托至 service 层可复用实现）。"""
    from service.key_validation import trigger_hot_reload
    await trigger_hot_reload(db)


# ====================
# Request/Response Models
# ====================

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "user"


class RegisterRequest(BaseModel):
    username: str
    password: str


class UpstreamKeyCreateRequest(BaseModel):
    name: str
    key: str


class UpstreamKeyResponse(BaseModel):
    id: int
    name: str
    key: str
    status: str
    disabled_reason: Optional[str] = None
    disabled_at: Optional[datetime.datetime] = None
    # Key 池最后使用时间（ISO 8601 UTC；从未使用或池缺失时为 None）
    last_used_at: Optional[str] = None
    user_id: Optional[int] = None
    owner_name: Optional[str] = None

    # 允许从 ORM 对象构造（list_upstream_keys 直接传入 UpstreamKey 实例）
    model_config = {"from_attributes": True}


class UpstreamKeySummary(BaseModel):
    """上游 Key 全量状态汇总（跨分页，统计当前用户可见的全部 Key）。"""
    total: int
    active: int
    disabled: int


class UpstreamKeyListResponse(BaseModel):
    items: list[UpstreamKeyResponse]
    total: int
    page: int
    page_size: int
    summary: UpstreamKeySummary
    # 上次定时失败 Key 巡检时间（北京时间 ISO 字符串，取自 Redis；无记录时为 None）
    last_validation_at: Optional[str] = None


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


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: Optional[datetime.datetime] = None


class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: Optional[datetime.datetime] = None
    has_upstream_key: bool
    text_total: int = 0
    text_success: int = 0
    text_failure: int = 0
    image_total: int = 0
    image_success: int = 0
    image_failure: int = 0
    video_total: int = 0
    video_success: int = 0
    video_failure: int = 0
    discord_id: str | None = None
    discord_username: str | None = None


class UserListResponse(BaseModel):
    items: list[UserListItem]
    total: int
    page: int
    page_size: int


class UserPasswordResetRequest(BaseModel):
    new_password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class SystemConfigResponse(BaseModel):
    key: str
    value: str


class AvailableModelCreate(BaseModel):
    name: str
    provider: str
    type: str


class AvailableModelUpdate(BaseModel):
    name: str
    provider: str
    type: str
    is_active: bool


class AvailableModelResponse(BaseModel):
    id: int
    name: str
    provider: str
    type: str
    is_active: bool
    created_at: Optional[datetime.datetime] = None


class AnnouncementCreate(BaseModel):
    title: str
    content: str
    is_pinned: bool = False
    sort_order: int = 0


class AnnouncementUpdate(BaseModel):
    title: str
    content: str
    is_active: bool = True
    is_pinned: bool = False
    sort_order: int = 0


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    is_active: bool
    is_pinned: bool
    sort_order: int
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None


# ====================
# API Endpoints
# ====================

@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """自助注册 — 已关闭，仅允许 Discord 注册"""
    raise HTTPException(status_code=403, detail="自助注册已关闭，请使用 Discord 账号注册")


@router.post("/login", response_model=TokenResponse)
async def login_for_access_token(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    try:
        result = await db.execute(select(User).where(User.username == req.username))
    except OperationalError as e:
        if "discord_id" in str(e):
            raise HTTPException(
                status_code=503,
                detail="数据库 schema 未就绪，请联系管理员执行迁移：ALTER TABLE users ADD COLUMN discord_id VARCHAR(30) NULL, ADD COLUMN discord_username VARCHAR(100) NULL;",
            )
        raise
    user = result.scalars().first()

    # Bootstrap first admin
    if req.username == "admin" and req.password == "admin123" and not user:
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
    return TokenResponse(access_token=access_token, role=user.role)


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
    # 验证旧密码
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


# --- ClientKey ---

@router.get("/keys", response_model=list[KeyResponse])
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KeyResponse]:
    """获取授权密钥。所有用户（含 admin）只看自己的。"""
    result = await db.execute(select(ClientKey).where(ClientKey.user_id == current_user.id))
    return result.scalars().all()


@router.post("/keys", response_model=KeyResponse)
async def create_key(
    req: KeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyResponse:
    """创建授权密钥。每用户仅 1 把，只能创建自己的。"""
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
    """重置授权密钥。删旧建新，保留用户统计。只能重置自己的。"""
    result = await db.execute(select(ClientKey).where(ClientKey.user_id == current_user.id))
    client_key = result.scalars().first()
    if not client_key:
        raise HTTPException(status_code=404, detail="Key not found")

    old_name = client_key.name
    old_used_quota = client_key.used_quota

    # 删除旧密钥
    from service.redis_key_pool import get_key_pool_manager
    pool_mgr = get_key_pool_manager()
    pool_mgr.redis.delete(f"AUTH:KEY:{client_key.key}")
    await db.delete(client_key)
    await db.commit()

    # 创建新密钥（统计按 user_id 键，不受影响）
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
    """启用/停用授权密钥。只能操作自己的。"""
    if status_val not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    result = await db.execute(select(ClientKey).where(ClientKey.id == key_id))
    client_key = result.scalars().first()
    if not client_key:
        raise HTTPException(status_code=404, detail="Key not found")

    if client_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    client_key.status = status_val
    if status_val == "disabled":
        from service.redis_key_pool import get_key_pool_manager
        pool_mgr = get_key_pool_manager()
        pool_mgr.redis.delete(f"AUTH:KEY:{client_key.key}")

    await db.commit()
    return {"status": "success", "new_status": client_key.status}


@router.delete("/keys/{key_id}")
async def delete_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除授权密钥。只能删除自己的。"""
    result = await db.execute(select(ClientKey).where(ClientKey.id == key_id))
    client_key = result.scalars().first()
    if not client_key:
        raise HTTPException(status_code=404, detail="Key not found")

    if client_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    from service.redis_key_pool import get_key_pool_manager
    pool_mgr = get_key_pool_manager()
    pool_mgr.redis.delete(f"AUTH:KEY:{client_key.key}")

    await db.delete(client_key)
    await db.commit()
    return {"status": "success"}


# --- UpstreamKey ---

@router.get("/upstream-keys", response_model=UpstreamKeyListResponse)
async def list_upstream_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str = Query(None, description="按通道别名或 Key 内容模糊筛选"),
    status: str = Query(None, description="按状态筛选：active / disabled（数据来自 Redis）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpstreamKeyListResponse:
    """分页获取上游 Key，status/summary 均以 Redis 实时状态为准。

    - user 过滤与 search（name/key）走 MySQL（Redis 不存这些字段）
    - status 筛选、summary 统计、行级 status/disabled_at/reason/last_used_at 全部来自 Redis
    - 候选集全量加载到内存后做 Redis 状态 overlay、筛选与内存分页
    """
    is_admin = current_user.role == "admin"

    # 1. MySQL 取候选集（user 过滤 + search），不分页
    base_filter = [] if is_admin else [UpstreamKey.user_id == current_user.id]
    if search and search.strip():
        kw = f"%{search.strip()}%"
        base_filter.append(or_(UpstreamKey.name.like(kw), UpstreamKey.key.like(kw)))

    query = select(UpstreamKey).where(*base_filter).order_by(UpstreamKey.id.asc())
    result = await db.execute(query)
    candidates = result.scalars().all()

    # 2. 批量读取候选集的 Redis 状态（一次 pipeline）
    from service.redis_key_pool import get_key_pool_manager, KEY_POOL_PREFIX
    pool_mgr = get_key_pool_manager()
    redis = pool_mgr.redis

    redis_rows: list[dict] = []
    if candidates:
        pipe = redis.pipeline(transaction=False)
        for k in candidates:
            masked = pool_mgr._compute_key_prefix(k.key)
            pipe.hgetall(f"{KEY_POOL_PREFIX}{masked}")
        try:
            redis_rows = list(pipe.execute())
        except Exception as e:
            logger.warning(f"批量读取 Redis Key 状态失败: {e}")
            redis_rows = [{} for _ in candidates]

    # 3. 计算每条记录的有效状态（Redis 优先，缺失回退 MySQL）
    def _effective_status(rd: dict, db_status: str) -> str:
        s = rd.get("status") if rd else None
        if isinstance(s, bytes):
            s = s.decode("utf-8")
        return s or db_status

    effective = [_effective_status(r, k.status) for k, r in zip(candidates, redis_rows)]

    # 4. summary 基于 Redis 实时状态（全候选集，不受 status 筛选影响）
    total = len(candidates)
    active_count = sum(1 for s in effective if s == "active")
    summary = UpstreamKeySummary(
        total=total,
        active=active_count,
        disabled=total - active_count,
    )

    # 5. status 筛选（白名单：active / disabled）
    status_filter = status if status in ("active", "disabled") else None
    if status_filter:
        filtered = [
            (k, r, s) for k, r, s in zip(candidates, redis_rows, effective)
            if s == status_filter
        ]
    else:
        filtered = list(zip(candidates, redis_rows, effective))

    # 6. 内存分页
    filtered_total = len(filtered)
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]

    # 7. admin 填充 owner_name（仅当前页子集）
    if is_admin and page_rows:
        from models.database import User as UserModel
        page_keys = [row[0] for row in page_rows]
        user_ids = {k.user_id for k in page_keys if k.user_id}
        user_map = {}
        if user_ids:
            user_result = await db.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
            user_map = {u.id: u.username for u in user_result.scalars().all()}
        for k in page_keys:
            k.owner_name = user_map.get(k.user_id)

    # 8. 组装当前页响应（行级字段以 Redis 为准）
    from datetime import datetime, timezone

    def _dt_or_none(val) -> Optional[datetime]:
        """Redis 时间戳（秒）→ datetime；空值/解析失败返回 None。"""
        if not val:
            return None
        try:
            return datetime.fromtimestamp(int(val), tz=timezone.utc)
        except Exception:
            return None

    items = []
    for k, rd, eff_status in page_rows:
        item = UpstreamKeyResponse.model_validate(k)
        item.status = eff_status
        if rd:
            disabled_at_raw = rd.get("disabled_at")
            if isinstance(disabled_at_raw, bytes):
                disabled_at_raw = disabled_at_raw.decode("utf-8")
            # disabled_at 字段类型为 datetime，Redis 优先，缺失回退 MySQL
            redis_disabled_at = _dt_or_none(disabled_at_raw)
            item.disabled_at = redis_disabled_at if redis_disabled_at is not None else item.disabled_at

            reason = rd.get("disabled_reason")
            if isinstance(reason, bytes):
                reason = reason.decode("utf-8")
            item.disabled_reason = reason or None

            last_used_raw = rd.get("last_used_at")
            if isinstance(last_used_raw, bytes):
                last_used_raw = last_used_raw.decode("utf-8")
            # last_used_at 字段类型为 str，返回 ISO 字符串
            lu_dt = _dt_or_none(last_used_raw)
            item.last_used_at = lu_dt.isoformat() if lu_dt else None
        items.append(item)

    # 读取上次定时失败 Key 巡检时间（Redis；失败不阻断列表接口）
    last_validation_at = None
    try:
        from service.key_validation_scheduler import LAST_RUN_TS_KEY
        last_validation_at = redis.get(LAST_RUN_TS_KEY)
        if isinstance(last_validation_at, bytes):
            last_validation_at = last_validation_at.decode("utf-8")
    except Exception as e:
        logger.warning(f"读取上次定时检验时间失败: {e}")

    return UpstreamKeyListResponse(
        items=items,
        total=filtered_total,
        page=page,
        page_size=page_size,
        summary=summary,
        last_validation_at=last_validation_at,
    )


@router.post("/upstream-keys", response_model=UpstreamKeyResponse)
async def create_upstream_key(
    req: UpstreamKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UpstreamKeyResponse:
    """创建上游 Key。上传时自动检验，失败则禁用。"""
    from service.key_validator import validate_key

    # 普通用户
    if current_user.role != "admin":
        target_user_id = current_user.id
        target_weight = 1
    else:
        target_user_id = current_user.id
        target_weight = 1

    # 先检验 Key
    success, message = await validate_key(req.key)

    up_key = UpstreamKey(
        user_id=target_user_id,
        name=req.name,
        key=req.key,
        weight=target_weight,
        status="disabled" if not success else "active",
    )
    if not success:
        up_key.disabled_reason = f"上传检验失败: {message}"

    db.add(up_key)
    try:
        await db.commit()
        await db.refresh(up_key)
        await _trigger_hot_reload(db)

        # 如果禁用了，检查用户速率
        if not success and target_user_id:
            from models.database import UpstreamKey as UK
            from sqlalchemy import select
            uk_result = await db.execute(
                select(UK.id).where(
                    UK.user_id == target_user_id,
                    UK.status == "active"
                ).limit(1)
            )
            if not uk_result.scalar_one_or_none():
                from service.rate_limit import refresh_user_tier
                refresh_user_tier(target_user_id)
        elif success and target_user_id:
            # 检验成功，刷新用户速率（可能有 active Key）
            from service.rate_limit import refresh_user_tier
            refresh_user_tier(target_user_id)
        return up_key
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create upstream key: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/upstream-keys/{key_id}/status")
async def toggle_upstream_key_status(
    key_id: int,
    status_val: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用上游 Key。仅 admin。Redis 先写保证路由即时生效，再落 MySQL 并热重载。"""
    from datetime import datetime, timezone
    if status_val not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    # 1. 先写 Redis（运行时真相源，立即对路由与展示生效）
    from service.redis_key_pool import get_key_pool_manager
    pool_mgr = get_key_pool_manager()
    masked = pool_mgr._compute_key_prefix(up_key.key)
    if status_val == "disabled":
        await pool_mgr.force_disable(masked, reason="手动禁用")
    else:
        await pool_mgr.activate_key(masked)

    # 2. 落 MySQL（持久化镜像）
    up_key.status = status_val
    if status_val == "active":
        up_key.disabled_reason = None
        up_key.disabled_at = None
    else:
        up_key.disabled_at = datetime.now(timezone.utc)
        if not up_key.disabled_reason:
            up_key.disabled_reason = "手动禁用"

    await db.commit()

    # 3. 热重载（以 MySQL 为准重建 Redis，保证多 worker 一致）
    await _trigger_hot_reload(db)

    # 刷新用户档位
    if up_key.user_id:
        from service.rate_limit import refresh_user_tier
        refresh_user_tier(up_key.user_id)

    return {"status": "success", "new_status": up_key.status}


@router.delete("/upstream-keys/clean-disabled", response_model=dict)
async def clean_disabled_keys(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除所有 status = 'disabled' 的上游 Key。"""
    result = await db.execute(select(UpstreamKey).where(UpstreamKey.status == "disabled"))
    disabled_keys = result.scalars().all()

    if not disabled_keys:
        return {"status": "ok", "message": "没有需要清理的 Key", "deleted": 0}

    deleted = 0
    for up_key in disabled_keys:
        # 清理统计数据
        from service.key_stats import get_key_stats_manager
        get_key_stats_manager().unregister_key(up_key.key)
        # 即时从 Redis 池移除
        try:
            from service.redis_key_pool import get_key_pool_manager
            await get_key_pool_manager().remove_key(up_key.key)
        except Exception as e:
            logger.warning(f"清理 Key 时移除 Redis 失败: {e}")

        await db.delete(up_key)
        deleted += 1

    await db.commit()

    # 热重载
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
    """删除上游 Key。普通用户只能删除自己的，admin 任意。"""
    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    if current_user.role != "admin" and up_key.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    full_key = up_key.key
    target_user_id = up_key.user_id

    await db.delete(up_key)
    await db.commit()

    # 清理被删除 Key 的统计数据
    from service.key_stats import get_key_stats_manager
    get_key_stats_manager().unregister_key(full_key)
    # 即时从 Redis 池移除（热重载前先清，保证路由立即不选该 Key）
    try:
        from service.redis_key_pool import get_key_pool_manager
        await get_key_pool_manager().remove_key(full_key)
    except Exception as e:
        logger.warning(f"删除 Key 时移除 Redis 失败: {e}")

    await _trigger_hot_reload(db)

    # 刷新用户档位
    if target_user_id:
        from service.rate_limit import refresh_user_tier
        refresh_user_tier(target_user_id)

    return {"status": "success"}


@router.post("/upstream-keys/{key_id}/validate", response_model=dict)
async def validate_upstream_key(
    key_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """手动检验指定 Key。失败则禁用，成功则启用（保持 Redis/DB 一致）。"""
    from service.key_validator import validate_key
    from service.key_disable import disable_key_and_check_user_rate

    result = await db.execute(select(UpstreamKey).where(UpstreamKey.id == key_id))
    up_key = result.scalars().first()
    if not up_key:
        raise HTTPException(status_code=404, detail="Key not found")

    # 执行检验
    success, message = await validate_key(up_key.key)

    if success:
        # 检验通过：如果之前是 disabled，恢复为 active
        if up_key.status == "disabled":
            up_key.status = "active"
            up_key.disabled_reason = None
            up_key.disabled_at = None
            await db.commit()
            await _trigger_hot_reload(db)
            from service.rate_limit import refresh_user_tier
            refresh_user_tier(up_key.user_id or 0)
            message = "检验通过，Key 已恢复为启用"
        else:
            message = "检验通过"

        # 检验本身也是一次真实使用：刷新 Redis last_used_at 并 LRU 队尾重排
        # （与定时巡检恢复路径 key_validation.py 的语义一致）
        try:
            from service.redis_key_pool import get_key_pool_manager
            pool_mgr = get_key_pool_manager()
            await pool_mgr.activate_key(pool_mgr._compute_key_prefix(up_key.key))
        except Exception as e:
            logger.warning(f"手动检验通过后刷新 last_used_at 失败: {e}")

        return {"status": "ok", "message": message, "validated": True}
    else:
        # 检验失败：禁用（disable_key_and_check_user_rate 内部已 commit）
        await disable_key_and_check_user_rate(db, up_key, f"手动检验失败: {message}")
        await _trigger_hot_reload(db)
        return {"status": "ok", "message": f"检验失败，Key 已禁用: {message}", "validated": False}


@router.post("/upstream-keys/validate-all", response_model=dict)
async def validate_all_upstream_keys(
    admin: User = Depends(get_current_admin),
    concurrency: int = Query(default=100, ge=1, le=200),
) -> dict:
    """后台启动失败 Key 巡检，立即返回；进度与结果通过 GET /validate-all/status 轮询。

    异步任务化：失败 Key 巡检耗时可达数十秒，同步等待会撑爆前端 axios 30s 与网关超时。
    """
    from service.key_validation import start_full_validation_background

    return start_full_validation_background(concurrency=concurrency)


@router.get("/upstream-keys/validate-all/status", response_model=dict)
async def get_validate_all_status(
    admin: User = Depends(get_current_admin),
) -> dict:
    """查询失败 Key 巡检进度/结果（status: idle | running | success | failed）。"""
    from service.key_validation import get_validation_state

    return get_validation_state()


# --- Dashboard ---

@router.get("/dashboard/me")
async def get_user_dashboard(
    current_user: User = Depends(get_current_user),
):
    """获取当前登录用户的当日（北京时间）模型统计数据。

    该接口只读取 Redis 的当日实时统计，不回退 UsageLog，保证与每日重置口径一致：
    北京时间凌晨重置后，这里的统计应立即归零。
    """
    def calc_rate(total, success):
        return round((success / total * 100), 2) if total > 0 else 0.0

    def empty_stats():
        return {
            "text": {"total": 0, "success": 0, "failure": 0, "success_rate": 0.0},
            "image": {"total": 0, "success": 0, "failure": 0, "success_rate": 0.0},
            "video": {"total": 0, "success": 0, "failure": 0, "success_rate": 0.0},
            "summary": {"total": 0, "success": 0, "failure": 0, "success_rate": 0.0},
        }

    def normalize_stats(raw: dict) -> dict:
        stats = empty_stats()
        for mt in ("text", "image", "video"):
            model_stats = raw.get(mt) or {}
            total = int(model_stats.get("total", 0) or 0)
            success = int(model_stats.get("success", 0) or 0)
            failure = int(model_stats.get("failure", 0) or 0)
            stats[mt] = {
                "total": total,
                "success": success,
                "failure": failure,
                "success_rate": calc_rate(total, success),
            }

        summary_total = sum(stats[mt]["total"] for mt in ("text", "image", "video"))
        summary_success = sum(stats[mt]["success"] for mt in ("text", "image", "video"))
        summary_failure = sum(stats[mt]["failure"] for mt in ("text", "image", "video"))
        stats["summary"] = {
            "total": summary_total,
            "success": summary_success,
            "failure": summary_failure,
            "success_rate": calc_rate(summary_total, summary_success),
        }
        return stats

    from service.key_stats import get_key_stats_manager
    stats_manager = get_key_stats_manager()
    redis_stats = stats_manager.get_user_stats(current_user.id)
    return normalize_stats(redis_stats)


@router.get("/upstream-stats")
async def get_upstream_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取上游渠道的健康度统计（admin 专用）。"""
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


@router.get("/upstream-url-stats")
async def get_upstream_url_stats(
    admin: User = Depends(get_current_admin),
):
    """获取上游 Base URL 的健康度统计（最近 100 次滑动窗口成功率）。仅 admin。"""
    from service.url_manager import get_url_manager
    return get_url_manager().get_health_stats()


# --- Admin Dashboard ---

@router.get("/admin/dashboard")
async def get_admin_dashboard(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
):
    """管理员看板：Key 池全 Key 聚合统计 + 用户请求次数排名（分页，北京时间当日）。仅 admin。"""
    from service.key_stats import get_key_stats_manager

    # 1. Key 池模型统计：全部上游 Key 的全局聚合（按模型分类），北京时间 0 点重置后归零
    stats_mgr = get_key_stats_manager()
    key_pool = stats_mgr.get_total_stats()

    # 1.1 请求级成功率（用户视角：重试后成功即成功，每个请求只记一次）
    request_level = stats_mgr.get_request_level_stats()

    # 1.2 Key 池失败原因分类计数（限流/鉴权/服务端/网络/空流）
    failure_reasons: dict = {}
    try:
        from service.redis_key_pool import get_key_pool_manager
        pool_status = await get_key_pool_manager().get_pool_status()
        failure_reasons = pool_status.get("failure_reasons", {}) or {}
    except Exception:
        failure_reasons = {}

    # 2. 用户请求次数排名（分页）
    all_user_stats = stats_mgr.get_all_user_stats()

    # 获取所有有请求的用户 ID
    user_ids = [us.get("user_id", 0) for us in all_user_stats if us.get("user_id")]
    user_map: dict[int, str] = {}
    if user_ids:
        uid_result = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        user_map = {u.id: u.username for u in uid_result.scalars().all()}

    user_ranking = []
    for us in all_user_stats:
        uid = us.get("user_id", 0)
        total = us.get("summary", {}).get("total", 0)
        if total > 0:
            username = user_map.get(uid, f"user_{uid}")
            user_ranking.append({
                "user_id": uid,
                "username": username,
                "total_requests": total,
                "success_rate": us.get("summary", {}).get("success_rate", 0.0),
                "text_requests": us.get("text", {}).get("total", 0),
                "text_success_rate": us.get("text", {}).get("success_rate", 0.0),
                "image_requests": us.get("image", {}).get("total", 0),
                "image_success_rate": us.get("image", {}).get("success_rate", 0.0),
                "video_requests": us.get("video", {}).get("total", 0),
                "video_success_rate": us.get("video", {}).get("success_rate", 0.0),
            })

    # 按总请求数降序排列
    user_ranking.sort(key=lambda x: x["total_requests"], reverse=True)

    # 分页
    total_users = len(user_ranking)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_ranking = user_ranking[start:end]

    return {
        "key_pool": key_pool,
        "request_level": request_level,
        "failure_reasons": failure_reasons,
        "user_ranking": paginated_ranking,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_users,
            "total_pages": (total_users + page_size - 1) // page_size if total_users > 0 else 0,
        },
    }



@router.get("/dashboard/timeline")
async def get_dashboard_timeline(
    minutes: int = Query(30, ge=1, le=120),
    current_user: User = Depends(get_current_user),
):
    """获取模型调用时间序列（分钟粒度，任意登录用户可查）。"""
    from service.key_stats import get_key_stats_manager
    stats_mgr = get_key_stats_manager()
    return stats_mgr.get_model_timeline(minutes)


# --- User Management ---

@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """分页列出用户及其统计。仅 admin。"""
    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()

    result = await db.execute(
        select(User)
        .order_by(User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().all()
    user_ids = [u.id for u in users]

    active_upstream_user_ids = set()
    if user_ids:
        uk_result = await db.execute(
            select(UpstreamKey.user_id)
            .where(
                UpstreamKey.user_id.in_(user_ids),
                UpstreamKey.status == "active",
            )
            .distinct()
        )
        active_upstream_user_ids = set(uk_result.scalars().all())

    from service.key_stats import get_key_stats_manager
    stats_mgr = get_key_stats_manager()

    user_list = []
    for u in users:
        # 获取用户统计
        user_stats = stats_mgr.get_user_stats(u.id)

        user_list.append(UserListItem(
            id=u.id, username=u.username, role=u.role,
            is_active=u.is_active, created_at=u.created_at,
            has_upstream_key=u.id in active_upstream_user_ids,
            text_total=user_stats.get("text", {}).get("total", 0),
            text_success=user_stats.get("text", {}).get("success", 0),
            text_failure=user_stats.get("text", {}).get("failure", 0),
            image_total=user_stats.get("image", {}).get("total", 0),
            image_success=user_stats.get("image", {}).get("success", 0),
            image_failure=user_stats.get("image", {}).get("failure", 0),
            video_total=user_stats.get("video", {}).get("total", 0),
            video_success=user_stats.get("video", {}).get("success", 0),
            video_failure=user_stats.get("video", {}).get("failure", 0),
            discord_id=u.discord_id,
            discord_username=u.discord_username,
        ))
    return UserListResponse(items=user_list, total=total, page=page, page_size=page_size)


@router.post("/users")
async def create_user(
    req: RegisterRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """admin 创建用户。"""
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already taken")

    hashed = await anyio.to_thread.run_sync(
        lambda: bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    )
    user = User(username=req.username, password_hash=hashed, role="user")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.put("/users/{user_id}/password")
async def reset_user_password(
    user_id: int,
    req: UserPasswordResetRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """admin 重置用户密码。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    hashed = await anyio.to_thread.run_sync(
        lambda: bcrypt.hashpw(req.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    )
    user.password_hash = hashed
    await db.commit()
    return {"status": "success"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除用户。admin 专用。上游 Key 归 admin，ClientKey 删除。"""
    # 禁止删除自己
    result = await db.execute(select(User).where(User.username == admin.username))
    self = result.scalars().first()
    if self and self.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. 将其上游 Key 归 admin
    admin_result = await db.execute(select(User).where(User.role == "admin").limit(1))
    admin_user = admin_result.scalars().first()
    if admin_user:
        await db.execute(
            update(UpstreamKey).where(UpstreamKey.user_id == user_id).values(user_id=admin_user.id)
        )

    # 2. 删除其 ClientKey
    ck_result = await db.execute(select(ClientKey).where(ClientKey.user_id == user_id))
    ck = ck_result.scalars().first()
    if ck:
        from service.redis_key_pool import get_key_pool_manager
        pool_mgr = get_key_pool_manager()
        pool_mgr.redis.delete(f"AUTH:KEY:{ck.key}")
        await db.delete(ck)

    # 3. 删除用户
    await db.delete(user)
    await db.commit()

    # 4. 清用户统计
    from service.key_stats import get_key_stats_manager
    get_key_stats_manager().reset_stats(user_id=user_id)

    return {"status": "success"}


# --- System Config ---

@router.get("/system-config", response_model=list[SystemConfigResponse])
async def get_system_config(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取系统配置。若表为空则自动写入默认值。"""
    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()

    # 若为空，写入默认值（幂等，ensure_system_config_initialized 也做同样检查）
    if not configs:
        from service.system_config import DEFAULT_SYSTEM_CONFIGS
        for k, v in DEFAULT_SYSTEM_CONFIGS:
            db.add(SystemConfig(key=k, value=v))
        await db.commit()
        result = await db.execute(select(SystemConfig))
        configs = result.scalars().all()

    # 同步到 Redis
    from service.system_config import _sync_configs_to_redis
    _sync_configs_to_redis(configs)

    return configs


@router.put("/system-config/{key}")
async def update_system_config(
    key: str,
    req: SystemConfigResponse,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新系统配置（upsert + 同步 Redis）。"""
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    cfg = result.scalars().first()
    if cfg:
        cfg.value = req.value
    else:
        # 不存在则创建（upsert）
        cfg = SystemConfig(key=key, value=req.value)
        db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    # 同步到 Redis
    from service.system_config import _sync_configs_to_redis
    _sync_configs_to_redis([cfg])

    return {"status": "success"}


# --- Available Models ---

from models.database import AvailableModel

@router.get("/models", response_model=list[AvailableModelResponse])
async def list_models(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取所有模型配置（admin 专用）。"""
    result = await db.execute(select(AvailableModel))
    return result.scalars().all()


@router.post("/models", response_model=AvailableModelResponse)
async def create_model(
    req: AvailableModelCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建模型配置。"""
    result = await db.execute(select(AvailableModel).where(AvailableModel.name == req.name))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Model name already exists")

    model = AvailableModel(
        name=req.name,
        provider=req.provider,
        type=req.type,
        is_active=True
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


@router.put("/models/{model_id}", response_model=AvailableModelResponse)
async def update_model(
    model_id: int,
    req: AvailableModelUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新模型配置。"""
    result = await db.execute(select(AvailableModel).where(AvailableModel.id == model_id))
    model = result.scalars().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # 检查名字冲突
    if model.name != req.name:
        name_check = await db.execute(select(AvailableModel).where(AvailableModel.name == req.name))
        if name_check.scalars().first():
            raise HTTPException(status_code=400, detail="Model name already exists")

    model.name = req.name
    model.provider = req.provider
    model.type = req.type
    model.is_active = req.is_active

    await db.commit()
    await db.refresh(model)
    return model


@router.delete("/models/{model_id}")
async def delete_model(
    model_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除模型配置。"""
    result = await db.execute(select(AvailableModel).where(AvailableModel.id == model_id))
    model = result.scalars().first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    await db.delete(model)
    await db.commit()
    return {"status": "success"}


# --- Announcements ---

@router.get("/announcements", response_model=list[AnnouncementResponse])
async def list_announcements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有启用的公告（按置顶、排序、时间倒序）。"""
    result = await db.execute(
        select(Announcement)
        .where(Announcement.is_active == True)
        .order_by(
            Announcement.is_pinned.desc(),
            Announcement.sort_order.asc(),
            Announcement.created_at.desc()
        )
    )
    return result.scalars().all()


@router.post("/announcements", response_model=AnnouncementResponse)
async def create_announcement(
    req: AnnouncementCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建公告（admin 专用）。"""
    announcement = Announcement(
        title=req.title,
        content=req.content,
        is_active=True,
        is_pinned=req.is_pinned,
        sort_order=req.sort_order,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)
    return announcement


@router.put("/announcements/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: int,
    req: AnnouncementUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新公告（admin 专用）。"""
    result = await db.execute(
        select(Announcement).where(Announcement.id == announcement_id)
    )
    announcement = result.scalars().first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    announcement.title = req.title
    announcement.content = req.content
    announcement.is_active = req.is_active
    announcement.is_pinned = req.is_pinned
    announcement.sort_order = req.sort_order

    await db.commit()
    await db.refresh(announcement)
    return announcement


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除公告（admin 专用）。"""
    result = await db.execute(
        select(Announcement).where(Announcement.id == announcement_id)
    )
    announcement = result.scalars().first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    await db.delete(announcement)
    await db.commit()
    return {"status": "success"}


