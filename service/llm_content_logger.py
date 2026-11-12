"""LLM 请求内容日志写入服务。

将每次成功完成的 LLM 调用的输入/输出内容以 JSONL 格式持久化到
logs/llm/{username}.jsonl，每个用户独立一个文件。
不跨天滚动、不删除旧文件。
写入通过 asyncio.create_task 后台执行，不阻塞主流程；IO 异常仅记录
warning，不影响 LLM 响应返回。
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta

from config import settings

logger = logging.getLogger(__name__)

# 本地时区 UTC+8
_LOCAL_TZ = timezone(timedelta(hours=8))

# 日志目录
_LOG_DIR = os.path.join("logs", "llm")

# 用户名缓存：user_id -> username
_username_cache: dict[int, str] = {}


def _now_local() -> datetime:
    """返回当前本地时间（UTC+8）。"""
    return datetime.now(_LOCAL_TZ)


async def _get_username(user_id: int) -> str:
    """根据 user_id 获取用户名，带本地缓存。"""
    if user_id in _username_cache:
        return _username_cache[user_id]
    try:
        from models.database import AsyncSessionLocal, User
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User.username).where(User.id == user_id))
            username = result.scalar_one_or_none()
            if username:
                _username_cache[user_id] = username
                return username
    except Exception as e:
        logger.warning(f"获取用户名失败 user_id={user_id}: {e}")
    # 降级：使用 user_id 作为文件名
    return f"user_{user_id}"


class LlmContentLogger:
    """LLM 内容 JSONL 日志写入器。

    协程安全：通过 asyncio.Lock 保证同一文件内多条记录顺序追加，
    不出现行交错。每个用户独立文件，不跨天滚动。
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        # 缓存文件句柄：filepath -> file handle
        self._file_handles: dict[str, object] = {}

    def write_log(self, record: dict) -> None:
        """异步追加一条日志记录到对应用户的 JSONL 文件。

        通过 asyncio.create_task 后台执行，立即返回不阻塞。
        当 llm_content_log_enabled=False 时直接 return。
        IO 异常仅记录 warning，不抛异常。
        """
        if not settings.llm_content_log_enabled:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._write(record))
        except RuntimeError:
            # 不在事件循环中，静默跳过
            pass

    async def _write(self, record: dict) -> None:
        """实际执行文件写入（受锁保护）。"""
        async with self._lock:
            try:
                user_id = record.get("user_id", 0)
                username = await _get_username(user_id)
                filepath = os.path.join(_LOG_DIR, f"{username}.jsonl")

                # 确保目录存在
                os.makedirs(_LOG_DIR, exist_ok=True)

                # 补充时间戳（确保用写入时刻）
                record.setdefault("timestamp", _now_local().isoformat())

                # 打开或复用文件句柄
                if filepath not in self._file_handles:
                    self._file_handles[filepath] = open(filepath, "a", encoding="utf-8")
                fp = self._file_handles[filepath]

                # 序列化并写入单行（default=str 兜底不可序列化对象）
                line = json.dumps(record, ensure_ascii=False, default=str)
                fp.write(line + "\n")
                fp.flush()
            except Exception as e:
                logger.warning(f"LLM 内容日志写入失败: {e}")

    def close(self) -> None:
        """关闭所有文件句柄（服务关闭时调用）。"""
        for fp in self._file_handles.values():
            try:
                fp.close()
            except Exception:
                pass
        self._file_handles.clear()


# 模块级单例
_instance: LlmContentLogger | None = None


def get_llm_content_logger() -> LlmContentLogger:
    """获取 LlmContentLogger 单例。"""
    global _instance
    if _instance is None:
        _instance = LlmContentLogger()
    return _instance
