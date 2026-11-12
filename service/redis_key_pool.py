"""基于 Redis 的分布式 API Key 池管理器（LRU 轮询 + 二态）。

功能：
- 从 Redis 管理 Key 池状态（分布式）
- LRU 选取：last_used_at 最旧优先（UTC epoch，取 Redis 服务器时钟，Lua 原子选取）
- 二态管理：active / disabled，可归责失败即禁用，恢复只走失败 Key 巡检
- 滑动窗口与失败原因分类计数（纯观测）

Redis 数据结构：
- KEY:POOL:{key_hash} → Hash (Key 状态和元数据，含 last_used_at)
- KEY:POOL:WIN:{key_hash} → List (近期成败滑动窗口，观测用)
- KEY:POOL:fail_reasons → Hash (失败原因分类计数)
- KEY:LOCK:{key_hash} → String (分布式锁)

与现有 stats 系统的命名空间隔离：
- Key Pool: KEY:POOL:*
- Stats: stats:*
"""

import asyncio
import json
import logging
import time
from typing import Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Redis 键前缀
KEY_POOL_PREFIX = "KEY:POOL:"
KEY_LOCK_PREFIX = "KEY:LOCK:"
# 每 Key 近期成败滑动窗口（List，"1"/"0"，最多 WINDOW_SIZE 条；观测用，不参与选取）
KEY_WINDOW_PREFIX = "KEY:POOL:WIN:"
# 失败原因分类计数（Hash: reason -> count）
KEY_FAIL_REASONS = "KEY:POOL:fail_reasons"

# 失败原因分类
FAIL_REASON_RATE_LIMIT = "rate_limit"   # 429 限流
FAIL_REASON_AUTH = "auth"               # 401/403 鉴权
FAIL_REASON_SERVER = "server"           # 408/5xx 服务端错误
FAIL_REASON_NETWORK = "network"         # 网络异常（节点级，不归咎 Key，禁用豁免）
FAIL_REASON_ZERO_CHUNK = "zero_chunk"   # 流式连接成功但零数据

# LRU 选取脚本：在候选中过滤 active，取 last_used_at 最小者并原子回写当前时间。
# 时间取自 Redis 服务器时钟（TIME 命令返回 Unix epoch，即格林尼治时间），
# 规避多 Worker 本地时钟漂移；选取与回写原子完成，避免并发撞车。
LUA_PICK_KEY = """
local prefix = KEYS[1]
local now = tonumber(redis.call('TIME')[1])
local best = nil
local best_score = nil
for i = 1, #ARGV do
    local masked = ARGV[i]
    if redis.call('HGET', prefix .. masked, 'status') == 'active' then
        local raw = redis.call('HGET', prefix .. masked, 'last_used_at')
        local score = 0
        if raw then
            score = tonumber(raw) or 0
        end
        if best_score == nil or score < best_score then
            best_score = score
            best = masked
        end
    end
end
if best then
    redis.call('HSET', prefix .. best, 'last_used_at', now)
end
return best or ''
"""


class KeyPoolStatus:
    """单个 API Key 的池状态信息（二态：active / disabled）。"""

    def __init__(
        self,
        key: str,
        masked: str,
        prefix_type: str,
        status: str = "active",
        last_used_at: int = 0,
        disabled_at: Optional[int] = None,
        disabled_reason: Optional[str] = None,
        total_success: int = 0,
        total_failure: int = 0,
    ):
        self.key = key
        self.masked = masked
        self.prefix_type = prefix_type
        self.status = status
        self.last_used_at = last_used_at
        self.disabled_at = disabled_at
        self.disabled_reason = disabled_reason
        self.total_success = total_success
        self.total_failure = total_failure

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @staticmethod
    def _iso(ts: Optional[float]) -> Optional[str]:
        """UTC epoch → ISO 8601（UTC）字符串，供前端本地化展示。"""
        if not ts:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "masked": self.masked,
            "status": self.status,
            "prefix_type": self.prefix_type,
            "last_used_at": self.last_used_at,
            "disabled_at": self.disabled_at,
            "disabled_reason": self.disabled_reason,
            "total_success": self.total_success,
            "total_failure": self.total_failure,
        }

    def to_api_dict(self) -> dict:
        """返回给 API 接口使用的字典格式。"""
        return {
            "key_prefix": self.masked,
            "status": self.status,
            "prefix_type": self.prefix_type,
            "last_used_at": self._iso(self.last_used_at),
            "disabled_at": self._iso(self.disabled_at),
            "disabled_reason": self.disabled_reason,
            "total_success": self.total_success,
            "total_failure": self.total_failure,
        }

    @staticmethod
    def from_dict(data: dict) -> "KeyPoolStatus":
        # 兼容 Redis 读取出来的字符串数值
        def to_int(v, default=0):
            try:
                return int(v) if v and str(v).strip() else default
            except (ValueError, TypeError):
                return default

        def to_opt_int(v, default=None):
            try:
                return int(v) if v and str(v).strip() else default
            except (ValueError, TypeError):
                return default

        reason = data.get("disabled_reason")
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8")

        return KeyPoolStatus(
            key=data.get("key", ""),
            masked=data.get("masked") or data.get("key_prefix") or "",
            prefix_type=data.get("prefix_type", "other"),
            status=data.get("status", "active"),
            last_used_at=to_int(data.get("last_used_at"), 0),
            disabled_at=to_opt_int(data.get("disabled_at")),
            disabled_reason=reason or None,
            total_success=to_int(data.get("total_success"), 0),
            total_failure=to_int(data.get("total_failure"), 0),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_api_dict())

    @staticmethod
    def from_json(json_str: str) -> "KeyPoolStatus":
        return KeyPoolStatus.from_dict(json.loads(json_str))


class RedisKeyPoolManager:
    """基于 Redis 的分布式 API Key 池管理器。

    管理多个 API Key 的 LRU 选取与二态状态（active/disabled）。
    支持多 Worker 分布式部署，所有状态存储在 Redis 中。

    选取规则：
    - 候选 = 注册 Key - exclude（重试换 Key 排除），且 status == active
    - 取 last_used_at 最小者（最旧未用；0/缺失视为从未使用，最优先）
    - 选中即由 Lua 脚本原子回写 Redis 服务器当前时间
    """

    # 近期成败滑动窗口大小与最小样本数（仅观测展示用）
    WINDOW_SIZE = 50
    WINDOW_MIN_SAMPLES = 10

    # 分布式锁 TTL（秒）
    LOCK_TTL = 10

    def __init__(self, redis_conn_string: str):
        """初始化 Redis Key Pool 管理器。

        Args:
            redis_conn_string: Redis 连接字符串
                              格式: redis://[:password@]host:port/db
        """
        import redis as redis_lib

        self._redis_conn_string = redis_conn_string
        self._redis_lib = redis_lib
        self._redis: Optional[redis_lib.Redis] = None
        self._key_statuses: dict[str, KeyPoolStatus] = {}  # masked_key -> status
        self._registered_keys: list[str] = []  # 注册的完整 keys

        self._connect()

    def _connect(self):
        """建立 Redis 连接。"""
        try:
            self._redis = self._redis_lib.from_url(
                self._redis_conn_string,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self._redis.ping()
            logger.info("Redis Key Pool Manager 连接成功")
        except Exception as e:
            logger.error(f"Redis Key Pool Manager 连接失败: {e}")
            raise

    @property
    def redis(self) -> Any:
        """获取 Redis 连接，如果断开则尝试重连。"""
        if self._redis is None:
            self._connect()
        try:
            if self._redis:
                self._redis.ping()
        except Exception as e:
            logger.warning(f"Redis 连接断开，尝试重连... {e}")
            self._connect()
        return self._redis

    def _compute_key_prefix(self, key: str) -> str:
        """计算 API Key 的前缀显示（脱敏）。"""
        if len(key) > 8:
            return key[:8] + "***"
        else:
            return key + "***"

    def _get_prefix_type(self, key: str) -> str:
        """获取 Key 的前缀类型。"""
        if key.startswith("cpk-"):
            return "cpk"
        elif key.startswith("sk-"):
            return "sk"
        else:
            return "other"

    async def initialize(self, keys, key_statuses: Optional[dict[str, dict]] = None):
        """初始化 Key 池，将所有 Key 写入 Redis。

        以 MySQL 状态为准重建 Redis：active/disabled 由 key_statuses 决定，
        保留各 Key 的历史计数（total_success/total_failure）与 last_used_at
        （使用时序跨热重载保持连续）。

        Args:
            keys: API Key 字符串列表
            key_statuses: 可选，masked_prefix -> {"status", "disabled_at", "disabled_reason"}，
                          来自 MySQL，用于在 Redis 中还原禁用状态；缺省时一律 active。
        """
        # 兼容处理
        if not keys:
            self._registered_keys = []
        elif isinstance(keys[0], str):
            self._registered_keys = list(keys)
        else:
            self._registered_keys = [k["key"] for k in keys]

        key_statuses = key_statuses or {}

        # 清空本地缓存，避免禁用/删除的 Key 残留为 active
        self._key_statuses.clear()

        # 批量读取旧状态（一次性 pipeline），用于保留计数与 last_used_at
        old_states: dict[str, dict] = {}
        if self._registered_keys:
            pipe_read = self.redis.pipeline(transaction=False)
            for key in self._registered_keys:
                masked = self._compute_key_prefix(key)
                pipe_read.hgetall(f"{KEY_POOL_PREFIX}{masked}")
            results = pipe_read.execute()
            for key, val in zip(self._registered_keys, results):
                old_states[self._compute_key_prefix(key)] = val or {}

        pipe = self.redis.pipeline(transaction=True)

        for key in self._registered_keys:
            masked = self._compute_key_prefix(key)
            prefix_type = self._get_prefix_type(key)

            old_data = old_states.get(masked, {})
            old_last_used = old_data.get("last_used_at", "0") or "0"
            old_total_success = old_data.get("total_success", "0")
            old_total_failure = old_data.get("total_failure", "0")

            # 以传入的 MySQL 状态为准（缺省 active）
            db_state = key_statuses.get(masked, {})
            status = db_state.get("status", "active")
            disabled_at = db_state.get("disabled_at", "")
            disabled_reason = db_state.get("disabled_reason", "")

            # 删除旧的（如果存在），重建状态
            pipe.delete(f"{KEY_POOL_PREFIX}{masked}")
            mapping = {
                "key": key,
                "masked": masked,
                "prefix_type": prefix_type,
                "status": status,
                "last_used_at": str(old_last_used),
                "disabled_at": str(disabled_at) if disabled_at else "",
                "total_success": str(old_total_success),
                "total_failure": str(old_total_failure),
            }
            if disabled_reason:
                mapping["disabled_reason"] = disabled_reason
            pipe.hset(f"{KEY_POOL_PREFIX}{masked}", mapping=mapping)

            # 本地缓存
            self._key_statuses[masked] = KeyPoolStatus(
                key=key,
                masked=masked,
                prefix_type=prefix_type,
                status=status,
                last_used_at=int(old_last_used) if str(old_last_used).isdigit() else 0,
                disabled_at=int(disabled_at) if str(disabled_at).isdigit() else None,
                disabled_reason=disabled_reason or None,
                total_success=int(old_total_success) if str(old_total_success).isdigit() else 0,
                total_failure=int(old_total_failure) if str(old_total_failure).isdigit() else 0,
            )

        pipe.execute()
        logger.info(f"Key Pool 初始化完成，共 {len(self._registered_keys)} 个 Key（LRU 模式）")

    async def get_next_key(self, exclude: Optional[set] = None) -> Optional[str]:
        """LRU 获取下一个用于请求的 API Key（最旧未用优先）。

        Lua 脚本原子完成"过滤 active + 取最旧 + 回写使用时间"，
        保证多 Worker 环境下不撞车，且时间取自 Redis 服务器时钟。

        Args:
            exclude: 需要排除的完整 Key 集合（如本次请求已失败过的 Key），
                     保证重试一定换到不同的 Key

        Returns:
            API Key 的脱敏前缀，如果没有可用 Key 则返回 None
        """
        try:
            if not self._registered_keys:
                logger.error("没有已注册的 API Key")
                return None

            # 构建候选列表（排除重试已失败的 Key）
            excluded_masked = {self._compute_key_prefix(k) for k in exclude} if exclude else set()
            candidates = [
                self._compute_key_prefix(k)
                for k in self._registered_keys
                if self._compute_key_prefix(k) not in excluded_masked
            ]
            if not candidates:
                logger.warning("所有 Key 均已被本次请求排除，无可用 Key")
                return None

            # Lua 原子选取（无 active 候选时返回空串）
            masked_key = self.redis.eval(
                LUA_PICK_KEY, 1, KEY_POOL_PREFIX, *candidates
            )
            if not masked_key:
                logger.error("没有可用的 API Key（全部处于 disabled 状态）")
                return None

            return masked_key

        except Exception as e:
            logger.error(f"获取下一个 Key 失败: {e}")
            # 降级：返回第一个注册的 key
            if self._registered_keys:
                return self._compute_key_prefix(self._registered_keys[0])
            return None

    async def get_key(self, exclude: Optional[set] = None) -> Optional[str]:
        """获取下一个可用的完整 API Key。

        封装了 LRU 选取逻辑和完整 Key 查找。

        Args:
            exclude: 需要排除的完整 Key 集合（重试时避免重复选到已失败 Key）

        Returns:
            完整 API Key，如果没有可用 Key 则返回 None
        """
        masked = await self.get_next_key(exclude=exclude)
        if not masked:
            return None
        return self._get_full_key(masked)

    def _get_full_key(self, masked_key: str) -> Optional[str]:
        """根据脱敏前缀获取完整 Key。

        Args:
            masked_key: Key 的脱敏前缀 (如 "cpk-abc1***")

        Returns:
            完整 Key，如果找不到则返回 None
        """
        # 先从本地缓存查找
        status = self._key_statuses.get(masked_key)
        if status and status.key:
            return status.key

        # 从 registered_keys 查找
        for key in self._registered_keys:
            if self._compute_key_prefix(key) == masked_key:
                return key

        # 从 Redis 查找
        data = self.redis.hget(f"{KEY_POOL_PREFIX}{masked_key}", "key")
        if data:
            return data

        return None

    async def record_success(self, key: str):
        """记录请求成功（计数与观测窗口；二态下成功不改变状态）。

        Args:
            key: API Key 或其脱敏前缀
        """
        masked = self._compute_key_prefix(key)

        try:
            pipe = self.redis.pipeline(transaction=True)
            pipe.hincrby(f"{KEY_POOL_PREFIX}{masked}", "total_success", 1)
            # 近期成败滑动窗口：记成功
            pipe.lpush(f"{KEY_WINDOW_PREFIX}{masked}", "1")
            pipe.ltrim(f"{KEY_WINDOW_PREFIX}{masked}", 0, self.WINDOW_SIZE - 1)
            pipe.execute()

            # 更新本地缓存
            if masked in self._key_statuses:
                self._key_statuses[masked].total_success += 1

        except Exception as e:
            logger.error(f"记录成功失败: {e}")

    async def record_failure(self, key: str, reason: str = FAIL_REASON_SERVER, degradable: bool = True):
        """记录请求失败。二态规则：可归责失败即禁用。

        - 可归责失败（rate_limit/auth/server/zero_chunk）→ 立即禁用：
          Redis status=disabled（实时生效，下一轮选取即跳过）
          + 异步写 DB（复用 disable_key_and_check_user_rate，不做热重载）
        - network（节点级故障）→ 仅观测计数，窗口豁免，禁用豁免
        - 客户端参数错误不进入本方法（调用方不记 Key 失败）
        - 禁用后若池内 active 归零，立即触发一次失败 Key 巡检（与定时/手动巡检锁互斥）

        Args:
            key: API Key 或其脱敏前缀
            reason: 失败原因分类 (rate_limit | auth | server | network | zero_chunk)
            degradable: 兼容保留参数；False 仅出现在 network 场景，语义同禁用豁免
        """
        masked = self._compute_key_prefix(key)

        try:
            now = int(time.time())
            # 获取当前状态
            current_data = self.redis.hgetall(f"{KEY_POOL_PREFIX}{masked}")
            if not current_data:
                logger.warning(f"Key {masked} 不存在于 Key Pool 中")
                return

            current_status = current_data.get("status", "active")

            pipe = self.redis.pipeline(transaction=True)
            # 失败原因分类计数（观测面板用）
            pipe.hincrby(KEY_FAIL_REASONS, reason, 1)
            # 近期成败滑动窗口：网络异常非 Key 质量问题，不进窗口
            if reason != FAIL_REASON_NETWORK:
                pipe.lpush(f"{KEY_WINDOW_PREFIX}{masked}", "0")
                pipe.ltrim(f"{KEY_WINDOW_PREFIX}{masked}", 0, self.WINDOW_SIZE - 1)
            pipe.hincrby(f"{KEY_POOL_PREFIX}{masked}", "total_failure", 1)

            # 失败即禁用：仅对 active 生效；network 豁免
            should_disable = (
                degradable
                and reason != FAIL_REASON_NETWORK
                and current_status == "active"
            )
            if should_disable:
                pipe.hset(f"{KEY_POOL_PREFIX}{masked}", mapping={
                    "status": "disabled",
                    "disabled_at": str(now),
                    "disabled_reason": f"请求失败自动禁用: {reason}",
                })

            pipe.execute()

            # 更新本地缓存
            if masked in self._key_statuses:
                self._key_statuses[masked].total_failure += 1
                if should_disable:
                    self._key_statuses[masked].status = "disabled"
                    self._key_statuses[masked].disabled_at = now
                    self._key_statuses[masked].disabled_reason = f"请求失败自动禁用: {reason}"

            if should_disable:
                logger.warning(f"Key {masked} 因 {reason} 失败，已禁用（二态）")
                # 异步写 DB（不做热重载：Redis 实时状态已保证路由生效）
                self._schedule_db_disable(masked, reason)
                # 归零保护：池内无 active Key 时立即触发失败 Key 巡检
                await self._trigger_inspection_if_pool_empty()

        except Exception as e:
            logger.error(f"记录失败失败: {e}")

    def _schedule_db_disable(self, masked_key: str, reason: str):
        """异步将运行时禁用写入 DB（含用户无 active Key 时的速率降级）。"""
        async def _do_disable():
            from models.database import AsyncSessionLocal, UpstreamKey
            from sqlalchemy import select

            try:
                async with AsyncSessionLocal() as db:
                    full = self._get_full_key(masked_key)
                    result = await db.execute(
                        select(UpstreamKey).where(UpstreamKey.key == full)
                    )
                    up_key = result.scalars().first()
                    if up_key and up_key.status != "disabled":
                        from service.key_disable import disable_key_and_check_user_rate
                        await disable_key_and_check_user_rate(
                            db, up_key, f"请求失败自动禁用: {reason}"
                        )
            except Exception as e:
                logger.error(f"运行时禁用写入 DB 失败: {masked_key} | {e}")

        try:
            asyncio.create_task(_do_disable())
        except RuntimeError:
            # 无事件循环时跳过 DB 同步，Redis 状态仍实时生效
            logger.warning(f"无事件循环，跳过 DB 禁用同步: {masked_key}")

    async def _trigger_inspection_if_pool_empty(self):
        """池内 active 归零时立即触发一次失败 Key 巡检。

        复用手动/定时巡检的 Redis 锁互斥：拿不到锁说明巡检已在跑，直接跳过。
        """
        try:
            pipe = self.redis.pipeline(transaction=False)
            for key in self._registered_keys:
                masked = self._compute_key_prefix(key)
                pipe.hget(f"{KEY_POOL_PREFIX}{masked}", "status")
            results = pipe.execute()
            active_count = sum(1 for s in results if s == "active")
            if active_count > 0:
                return

            logger.warning("Key 池内已无 active Key，立即触发失败 Key 巡检")
            from service.key_validation import start_full_validation_background
            outcome = start_full_validation_background()
            if outcome.get("status") == "already_running":
                logger.info("失败 Key 巡检已在运行中，跳过立即触发")
        except Exception as e:
            logger.error(f"归零保护触发巡检失败: {e}")

    async def activate_key(self, masked_key: str):
        """激活指定 Key（disabled → active），last_used_at 更新为当前时间（队尾重排）。"""
        now = int(time.time())
        pipe = self.redis.pipeline(transaction=True)
        pipe.hset(f"{KEY_POOL_PREFIX}{masked_key}", mapping={
            "status": "active",
            "disabled_at": "",
            "disabled_reason": "",
            "last_used_at": str(now),
        })
        pipe.execute()

        # 更新本地缓存
        if masked_key in self._key_statuses:
            self._key_statuses[masked_key].status = "active"
            self._key_statuses[masked_key].disabled_at = None
            self._key_statuses[masked_key].disabled_reason = None
            self._key_statuses[masked_key].last_used_at = now

        logger.info(f"Key {masked_key} 已激活（LRU 队尾重新入队）")

    async def force_disable(self, masked_key: str, reason: str = "手动禁用"):
        """强制禁用指定 Key（管理端点调用）。"""
        try:
            now = int(time.time())
            pipe = self.redis.pipeline(transaction=True)
            pipe.hset(f"{KEY_POOL_PREFIX}{masked_key}", mapping={
                "status": "disabled",
                "disabled_at": str(now),
                "disabled_reason": reason,
            })
            pipe.execute()

            # 更新本地缓存
            if masked_key in self._key_statuses:
                self._key_statuses[masked_key].status = "disabled"
                self._key_statuses[masked_key].disabled_at = now
                self._key_statuses[masked_key].disabled_reason = reason

            logger.info(f"Key {masked_key} 已手动强制禁用: {reason}")
        except Exception as e:
            logger.error(f"强制禁用失败: {e}")

    async def remove_key(self, key: str):
        """从 Redis 池中移除指定 Key（删除时清理）。"""
        masked = self._compute_key_prefix(key)
        try:
            pipe = self.redis.pipeline(transaction=True)
            pipe.delete(f"{KEY_POOL_PREFIX}{masked}")
            pipe.delete(f"{KEY_WINDOW_PREFIX}{masked}")
            pipe.execute()
        except Exception as e:
            logger.warning(f"从 Redis 移除 Key {masked} 失败: {e}")

        self._registered_keys = [k for k in self._registered_keys if self._compute_key_prefix(k) != masked]
        self._key_statuses.pop(masked, None)

    async def get_pool_status(self) -> dict:
        """获取 Key 池状态（含失败原因分类与近期成功率观测）。"""
        try:
            # 批量读取状态哈希 + 滑动窗口，避免逐个 Redis 调用
            pipe = self.redis.pipeline(transaction=False)
            for key in self._registered_keys:
                masked = self._compute_key_prefix(key)
                pipe.hgetall(f"{KEY_POOL_PREFIX}{masked}")
                pipe.lrange(f"{KEY_WINDOW_PREFIX}{masked}", 0, -1)
            pipe.hgetall(KEY_FAIL_REASONS)
            results = pipe.execute()

            n = len(self._registered_keys)
            fail_reasons_raw = results[2 * n] or {}

            all_statuses = []
            active_count = 0
            disabled_count = 0

            for i, key in enumerate(self._registered_keys):
                masked = self._compute_key_prefix(key)
                data = results[2 * i]
                window = results[2 * i + 1] or []
                if data:
                    status = KeyPoolStatus.from_dict(data)
                    entry = status.to_api_dict()
                    # 近期成功率（滑动窗口，观测用）
                    if window:
                        entry["recent_success_rate"] = round(
                            sum(1 for v in window if v == "1") / len(window) * 100, 1
                        )
                        entry["recent_samples"] = len(window)
                    else:
                        entry["recent_success_rate"] = None
                        entry["recent_samples"] = 0
                    all_statuses.append(entry)
                    if status.is_active:
                        active_count += 1
                    else:
                        disabled_count += 1

            # 失败原因分类计数（int 化）
            failure_reasons = {}
            for reason, count in fail_reasons_raw.items():
                try:
                    failure_reasons[reason] = int(count)
                except (ValueError, TypeError):
                    failure_reasons[reason] = 0

            return {
                "status": "ok",
                "total_keys": len(self._registered_keys),
                "active_keys": active_count,
                "disabled_keys": disabled_count,
                "failure_reasons": failure_reasons,
                "keys": all_statuses,
            }
        except Exception as e:
            logger.error(f"获取 Key 池状态失败: {e}")
            return {
                "status": "error",
                "message": str(e),
                "failure_reasons": {},
                "keys": [],
            }

    async def reset_all_keys(self):
        """重置所有 Key 状态（二态：一律 active；保留 last_used_at，清空观测数据）。"""
        pipe = self.redis.pipeline(transaction=True)

        for key in self._registered_keys:
            masked = self._compute_key_prefix(key)
            pipe.hset(f"{KEY_POOL_PREFIX}{masked}", mapping={
                "status": "active",
                "disabled_at": "",
                "disabled_reason": "",
            })
            # 清空滑动窗口
            pipe.delete(f"{KEY_WINDOW_PREFIX}{masked}")

        # 清空失败原因计数
        pipe.delete(KEY_FAIL_REASONS)

        pipe.execute()

        # 本地缓存同步
        for masked in self._key_statuses:
            self._key_statuses[masked].status = "active"
            self._key_statuses[masked].disabled_at = None
            self._key_statuses[masked].disabled_reason = None

        logger.info("所有 Key 状态已重置（active，观测数据已清空，last_used_at 保留）")


# 全局单例
_key_pool_manager: Optional[RedisKeyPoolManager] = None
_pool_lock = __import__("threading").Lock()


def get_key_pool_manager() -> RedisKeyPoolManager:
    """获取全局 Key Pool 管理器实例。"""
    global _key_pool_manager
    if _key_pool_manager is None:
        with _pool_lock:
            if _key_pool_manager is None:
                from config import settings
                redis_conn = settings.redis_conn_string
                if not redis_conn:
                    raise RuntimeError("Redis 连接字符串未配置，无法初始化 Key Pool Manager")
                _key_pool_manager = RedisKeyPoolManager(redis_conn)
    return _key_pool_manager
