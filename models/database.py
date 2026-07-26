import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import func
from config import settings

logger = logging.getLogger(__name__)

# 确保 data 目录存在（容器内运行时需要）
_db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(_db_dir, exist_ok=True)

# 创建异步数据库引擎（SQLite + aiosqlite）
engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="admin")  # 单用户模式固定为 admin
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)


class ClientKey(Base):
    __tablename__ = "client_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False, unique=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    status = Column(String(20), default="active")  # 'active' or 'disabled'
    quota = Column(Float, default=-1.0)  # -1 means unlimited
    used_quota = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UpstreamKey(Base):
    __tablename__ = "upstream_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    weight = Column(Integer, default=1)
    status = Column(String(20), default="active")  # 'active' or 'disabled'
    disabled_reason = Column(Text, nullable=True)  # 自动禁用原因
    disabled_at = Column(DateTime(timezone=True), nullable=True)  # 自动禁用时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    client_key_id = Column(Integer, ForeignKey("client_keys.id", ondelete="SET NULL"), index=True, nullable=True)
    upstream_key = Column(String(100), nullable=False)
    model = Column(String(50), nullable=False)
    tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemConfig(Base):
    __tablename__ = "system_configs"

    key = Column(String(50), primary_key=True)
    value = Column(String(255), nullable=False)


class AvailableModel(Base):
    __tablename__ = "available_models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    provider = Column(String(50), nullable=False)
    type = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    is_pinned = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


async def get_db():
    """获取数据库会话的依赖函数"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库表（仅 create_all，不做增量迁移）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully")


async def seed_defaults():
    """写入默认数据：admin 用户 + 三个默认模型。"""
    import anyio
    import bcrypt
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        # 1. 确保 admin 用户存在
        result = await session.execute(select(User).where(User.username == "admin"))
        admin_user = result.scalars().first()
        if not admin_user:
            hashed = await anyio.to_thread.run_sync(
                lambda: bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
            )
            admin_user = User(username="admin", password_hash=hashed, role="admin")
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)
            logger.info(f"已创建默认 admin 用户 (id={admin_user.id})")

        # 2. 写入默认可用模型（如果表中为空）
        result = await session.execute(select(AvailableModel).limit(1))
        if not result.scalars().first():
            default_models = [
                AvailableModel(name="agnes-2.0-flash", provider="shared", type="text", is_active=True),
                AvailableModel(name="agnes-image-2.1-flash", provider="shared", type="image", is_active=True),
                AvailableModel(name="agnes-video-v2.0", provider="shared", type="video", is_active=True),
            ]
            session.add_all(default_models)
            await session.commit()
            logger.info("已写入默认可用模型")
