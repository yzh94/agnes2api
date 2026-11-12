"""Redis → MySQL 上游 Key 状态同步调度器。

Redis 是运行时真相源（选 Key 与展示均以 Redis 为准），MySQL 是持久化镜像。
运行时失败禁用会异步写 MySQL，但若异步任务失败/延迟，MySQL 状态会落后于 Redis。
本调度器周期性地把 Redis 中每个 key 的 status / disabled_at / disabled_reason
回写到 MySQL，保证 MySQL 始终是 Redis 的新鲜镜像，重启时可据此正确重建 Redis。

多 worker 幂等：每次执行前用 Redis SET NX EX 抢占锁，仅一个 worker 真正执行。
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SYNC_LOCK_KEY = "sys:key_redis_sync:lock"


class RedisToMySQLSyncScheduler:
    """Redis → MySQL 上游 Key 状态同步调度器。"""

    def __init__(self, interval_minutes: int = 2):
        self._interval_seconds = max(int(interval_minutes) * 60, 30)
        self._task: asyncio.Task | None = None
        self._running = False

    async def _run_once(self) -> None:
        """执行一次 Redis → MySQL 同步，带多 worker 抢锁幂等。"""
        from service.redis_key_pool import get_key_pool_manager, KEY_POOL_PREFIX
        redis = get_key_pool_manager().redis

        lock_ttl = max(self._interval_seconds - 30, 30)
        acquired = redis.set(SYNC_LOCK_KEY, "1", nx=True, ex=lock_ttl)
        if not acquired:
            logger.debug("Redis→MySQL 同步已被其他 worker 执行，跳过")
            return

        from models.database import AsyncSessionLocal, UpstreamKey
        from sqlalchemy import select

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(UpstreamKey))
                db_keys = result.scalars().all()

                if not db_keys:
                    return

                pool_mgr = get_key_pool_manager()
                # 批量读取 Redis 状态
                pipe = redis.pipeline(transaction=False)
                for k in db_keys:
                    masked = pool_mgr._compute_key_prefix(k.key)
                    pipe.hgetall(f"{KEY_POOL_PREFIX}{masked}")
                redis_rows = pipe.execute()

                synced = 0
                for up_key, redis_data in zip(db_keys, redis_rows):
                    if not redis_data:
                        continue
                    redis_status = redis_data.get("status", "active")
                    # 以 Redis 为准
                    if redis_status != up_key.status:
                        up_key.status = redis_status
                        if redis_status == "disabled":
                            disabled_at_raw = redis_data.get("disabled_at")
                            if disabled_at_raw and str(disabled_at_raw).strip().isdigit():
                                up_key.disabled_at = datetime.fromtimestamp(
                                    int(disabled_at_raw), tz=timezone.utc
                                )
                            up_key.disabled_reason = redis_data.get("disabled_reason") or "自动禁用"
                        else:
                            up_key.disabled_at = None
                            up_key.disabled_reason = None
                        synced += 1

                if synced:
                    await db.commit()
                    logger.info(f"[Redis→MySQL 同步] 修正 {synced}/{len(db_keys)} 个 Key 状态")
                else:
                    logger.debug(f"[Redis→MySQL 同步] {len(db_keys)} 个 Key 状态一致，无需修正")
        except Exception as e:
            logger.error(f"Redis→MySQL 同步异常: {e}")
        finally:
            try:
                redis.delete(SYNC_LOCK_KEY)
            except Exception:
                pass

    async def _loop(self):
        logger.info(f"Redis→MySQL 状态同步调度器已启动，每 {self._interval_seconds // 60} 分钟执行一次")
        while self._running:
            try:
                await asyncio.sleep(self._interval_seconds)
                if not self._running:
                    break
                await self._run_once()
            except asyncio.CancelledError:
                logger.info("Redis→MySQL 状态同步调度器已取消")
                break
            except Exception as e:
                logger.error(f"Redis→MySQL 同步调度异常: {e}")
                await asyncio.sleep(60)

    def start(self):
        if self._running:
            logger.warning("Redis→MySQL 状态同步调度器已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Redis→MySQL 状态同步调度器已停止")
