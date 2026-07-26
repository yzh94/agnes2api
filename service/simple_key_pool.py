"""轻量级 Key Pool 管理器（基于内存 + SQLite）。

替代原 Redis Key Pool Manager，适用于单用户/单进程场景。

功能：
- 从 UpstreamKey DB 读取 active keys，按 weight 加权轮询
- 提供 get_key() → 返回下一个可用的完整 key
- 提供 record_success / record_failure → 更新内存中的统计
- 提供 get_all_status() → 返回每个 key 的状态列表
- 移除健康检查、降级队列、分布式锁等 Redis 专属功能
"""

import logging
import time
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class SimpleKeyPoolManager:
    """轻量级 Key Pool 管理器。"""

    def __init__(self):
        self._keys: List[Dict[str, Any]] = []  # [{key, name, weight, status, ...}]
        self._rotation_list: List[str] = []  # 加权轮询列表 (masked keys)
        self._index: int = 0  # 当前轮询索引
        self._stats: Dict[str, Dict[str, int]] = {}  # masked_key -> {success, failure}
        self._lock: Optional[Any] = None  # 占位，单线程不需要锁

    async def initialize(self, keys: List[Dict[str, Any]]) -> None:
        """初始化 Key Pool。

        Args:
            keys: 上游 key 列表，格式 [{"key": "...", "weight": 1, "status": "active", ...}]
        """
        self._keys = []
        self._stats.clear()

        for item in keys:
            if isinstance(item, dict):
                k = item.get("key", "")
                w = item.get("weight", 1)
                s = item.get("status", "active")
                n = item.get("name", "")
            else:
                k = str(item)
                w = 1
                s = "active"
                n = ""

            masked = self._compute_key_prefix(k)
            entry = {
                "key": k,
                "name": n,
                "masked": masked,
                "weight": w,
                "status": s,
            }
            self._keys.append(entry)
            self._stats[masked] = {"success": 0, "failure": 0}

        await self._build_rotation_list()
        logger.info(f"Simple Key Pool initialized with {len(self._keys)} keys")

    def _compute_key_prefix(self, key: str) -> str:
        """计算 API Key 的前缀显示（脱敏）。"""
        if len(key) > 8:
            return key[:8] + "***"
        return key + "***"

    async def _build_rotation_list(self) -> None:
        """构建加权轮询列表。"""
        self._rotation_list = []
        for entry in self._keys:
            if entry["status"] == "active":
                masked = entry["masked"]
                weight = entry["weight"]
                self._rotation_list.extend([masked] * weight)

        # 如果没有活跃 keys，使用所有 registered keys
        if not self._rotation_list:
            logger.warning("No active upstream keys, using all registered keys as fallback")
            for entry in self._keys:
                self._rotation_list.append(entry["masked"])

        self._index = 0
        logger.info(f"Rotation list built, length: {len(self._rotation_list)}")

    async def get_key(self) -> Optional[str]:
        """获取下一个可用的完整 API Key。

        Returns:
            完整 API Key，如果没有可用 Key 则返回 None
        """
        if not self._rotation_list:
            return None

        key = self._rotation_list[self._index % len(self._rotation_list)]
        self._index += 1

        # 查找完整 key
        for entry in self._keys:
            if entry["masked"] == key:
                return entry["key"]

        return None

    async def record_success(self, key: str) -> None:
        """记录请求成功。"""
        masked = self._compute_key_prefix(key)
        if masked in self._stats:
            self._stats[masked]["success"] += 1

    async def record_failure(self, key: str) -> None:
        """记录请求失败。"""
        masked = self._compute_key_prefix(key)
        if masked in self._stats:
            self._stats[masked]["failure"] += 1

    async def get_all_status(self) -> List[dict]:
        """获取所有 key 的状态。"""
        result = []
        for entry in self._keys:
            masked = entry["masked"]
            stats = self._stats.get(masked, {"success": 0, "failure": 0})
            total = stats["success"] + stats["failure"]
            success_rate = round((stats["success"] / total * 100), 2) if total > 0 else 0.0
            result.append({
                "name": entry.get("name", ""),
                "masked_key": masked,
                "status": entry["status"],
                "weight": entry["weight"],
                "total_requests": total,
                "success": stats["success"],
                "failure": stats["failure"],
                "success_rate": success_rate,
            })
        return result

    async def reload_from_db(self, db_session) -> None:
        """从数据库重新加载 active keys（热重载）。"""
        from models.database import UpstreamKey
        from sqlalchemy import select

        result = await db_session.execute(
            select(UpstreamKey).where(UpstreamKey.status == "active")
        )
        db_keys = result.scalars().all()
        keys = [{"key": k.key, "weight": k.weight, "status": k.status, "name": k.name} for k in db_keys]
        await self.initialize(keys)

    async def reload_with_all(self, db_session) -> None:
        """从数据库重新加载全部 keys（含 disabled）。"""
        from models.database import UpstreamKey
        from sqlalchemy import select

        result = await db_session.execute(select(UpstreamKey))
        db_keys = result.scalars().all()
        keys = [{"key": k.key, "weight": k.weight, "status": k.status, "name": k.name} for k in db_keys]
        await self.initialize(keys)


# 全局单例
_key_pool_manager: Optional[SimpleKeyPoolManager] = None


def get_key_pool_manager() -> SimpleKeyPoolManager:
    """获取全局 Key Pool 管理器实例。"""
    global _key_pool_manager
    if _key_pool_manager is None:
        _key_pool_manager = SimpleKeyPoolManager()
    return _key_pool_manager
