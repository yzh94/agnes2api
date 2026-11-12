"""统计每日重置调度器。

每天在指定时刻（北京时间 UTC+8，默认 00:00）清空 Redis 中所有 stats:* 和 user_stats:* 统计哈希，
开始当日重新统计。清空后重新注册活跃 Key 和活跃用户，重建零值哈希，确保看板在当日
零请求时仍展示全部活跃通道和活跃用户（值为 0）。

注意：
- 仅清 stats:* 和 user_stats:*，不动 timeline 使用的 stats_ts:*，因此“近24小时全局模型成功率趋势”
  保持滚动 24 小时语义，不在午夜归零。
- 不动 KEY:POOL:{masked} 的 consecutive_failures 等运行时计数，避免影响降级与健康检查逻辑。
- 使用 Redis 记录 last_daily_reset_date，支持多 worker 幂等与服务启动补跑。
- 同时每日重置上游 URL 成功率滑动窗口（service/url_manager.py 的进程内存态，
  各 worker 在自己的调度循环中独立重置，无需 Redis 哨兵协调）。
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from config import settings

logger = logging.getLogger(__name__)

# 北京时间 UTC+8（无 DST，全年稳定）。调度器按此时区计算每日重置时刻，
# 不依赖容器 TZ 环境变量，确保 "00:00" 始终为北京时间 0 点。
BEIJING_TZ = timezone(timedelta(hours=8))
# 注意：不能放在 stats:* 命名空间下，否则会被统计扫描/重置逻辑误当成 hash 统计键
LAST_RESET_DATE_KEY = "sys:stats:last_daily_reset_date"
LEGACY_LAST_RESET_DATE_KEY = "stats:last_daily_reset_date"


class StatsDailyResetScheduler:
    """统计每日重置后台调度器。"""

    def __init__(self, reset_time: str = "00:00"):
        """Args:
            reset_time: 每日重置时刻，格式 "HH:MM"（北京时间 UTC+8）
        """
        self._reset_time = reset_time
        self._task: asyncio.Task | None = None
        self._running = False

    def _seconds_until_next(self) -> float:
        """计算距离下一次重置时刻（北京时间）的秒数。"""
        now = datetime.now(BEIJING_TZ)
        hh, mm = map(int, self._reset_time.split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return (target - now).total_seconds()

    @staticmethod
    def _today_beijing_date() -> str:
        """返回当前北京时间日期，格式 YYYY-MM-DD。"""
        return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")

    async def _perform_reset(self, reason: str) -> None:
        """执行一次每日统计重置。

        幂等保护：用 Redis 记录当天是否已重置，多 worker 并发时只会有一个进程真正执行。
        """
        from service.key_stats import get_key_stats_manager
        from models.database import AsyncSessionLocal, UpstreamKey, User
        from sqlalchemy import select
        from service.redis_key_pool import get_key_pool_manager

        today = self._today_beijing_date()
        redis = get_key_pool_manager().redis
        last_reset_date = redis.get(LAST_RESET_DATE_KEY) or redis.get(LEGACY_LAST_RESET_DATE_KEY)
        if last_reset_date == today:
            logger.info(f"每日统计重置已完成，跳过重复执行 | reason={reason} date={today}")
            return

        # 清理历史遗留的错误命名 key，避免被 stats:* 扫描误伤
        redis.delete(LEGACY_LAST_RESET_DATE_KEY)

        # 先写入当天日期，作为多 worker 幂等哨兵；重置流程可重复执行，因此这里先占位是安全的。
        # 若清理/重建失败，下方 except 会回退哨兵，使同日重启补跑或调度重试能再次执行，
        # 避免确定性故障被掩藏一整天（曾因 _scan_delete 缺失导致整月未真正重置）。
        redis.set(LAST_RESET_DATE_KEY, today)
        try:
            logger.info(f"开始执行每日统计重置 | reason={reason} date={today}")

            # 1. 清空全部 stats:* 与 user_stats:*（保留 timeline 的 stats_ts:* 不动）
            stats_mgr = get_key_stats_manager()
            stats_mgr.reset_stats()  # 清空 key stats
            if stats_mgr._redis_stats is not None:
                stats_mgr._redis_stats.reset_user_stats(None)  # 清空所有用户统计

            # 2. 重新注册活跃 Key，HSETNX 重建零值哈希，确保看板仍展示全部活跃通道
            async with AsyncSessionLocal() as session:
                rows = (
                    await session.execute(
                        select(UpstreamKey).where(UpstreamKey.status == "active")
                    )
                ).scalars().all()
                for k in rows:
                    stats_mgr.register_key(k.key)

                # 同时重建活跃用户零值统计
                user_rows = (
                    await session.execute(
                        select(User).where(User.is_active == True)
                    )
                ).scalars().all()
                for u in user_rows:
                    if stats_mgr._redis_stats is not None:
                        for mt in ("text", "image", "video"):
                            key = f"user_stats:{u.id}:{mt}"
                            stats_mgr._redis_stats.redis.hsetnx(key, "total", 0)
                            stats_mgr._redis_stats.redis.hsetnx(key, "success", 0)
                            stats_mgr._redis_stats.redis.hsetnx(key, "failure", 0)

            logger.info(f"每日统计已重置，开始新一天统计 | reason={reason} date={today}")
        except Exception:
            # 重置失败：回退哨兵，避免「哨兵已占位但实际未完成」导致当天不再重试。
            # 重置流程幂等，重试/补跑重复执行无副作用。回退本身用 try 包裹，确保
            # 即便 Redis 此刻不可用也不会掩盖原始异常。
            try:
                redis.delete(LAST_RESET_DATE_KEY)
            except Exception:
                logger.warning("回退每日重置哨兵失败，下次重试可能被跳过", exc_info=True)
            raise

    async def _perform_reset_with_retry(self, reason: str, max_attempts: int = 3) -> None:
        """带退避重试的每日重置。

        瞬时故障（Redis 抖动、DB 短暂不可用）不应让当天统计一整天不归零。失败时
        _perform_reset 已回退哨兵，故重试会重新进入完整流程。CancelledError 不吞，
        确保调度器能被干净停止；连续 max_attempts 次失败则记 ERROR 并等待下次调度。
        """
        for attempt in range(1, max_attempts + 1):
            try:
                await self._perform_reset(reason)
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if attempt < max_attempts:
                    backoff = 30 * attempt
                    logger.warning(
                        f"每日重置失败，{backoff}s 后重试 ({attempt}/{max_attempts}) | {e}"
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"每日重置连续 {max_attempts} 次失败，等待下次调度 | {e}")

    async def _catch_up_if_needed(self) -> None:
        """服务启动时检查是否跨日漏跑；若漏跑则立即补跑一次。"""
        from service.redis_key_pool import get_key_pool_manager

        today = self._today_beijing_date()
        redis = get_key_pool_manager().redis
        last_reset_date = redis.get(LAST_RESET_DATE_KEY) or redis.get(LEGACY_LAST_RESET_DATE_KEY)
        if last_reset_date != today:
            await self._perform_reset_with_retry("startup_catchup")

    async def _loop(self):
        logger.info(f"统计每日重置调度器已启动，每日 {self._reset_time} 重置")

        # 启动补跑：若当前北京时间日期尚未执行过 reset，则立即执行一次
        await self._catch_up_if_needed()

        while self._running:
            try:
                await asyncio.sleep(self._seconds_until_next())
                if not self._running:
                    break

                # 每日重置上游 URL 成功率滑动窗口（进程内存态，各 worker 独立执行，
                # 幂等无副作用）。与统计重置相互独立：URL 重置失败不影响统计重置。
                try:
                    from service.url_manager import get_url_manager
                    get_url_manager().reset_all()
                    logger.info("上游 URL 成功率滑动窗口已每日重置")
                except Exception as e:
                    logger.warning(f"URL 滑动窗口每日重置失败: {e}")

                await self._perform_reset_with_retry("scheduled")

            except asyncio.CancelledError:
                logger.info("统计每日重置调度器已取消")
                break
            except Exception as e:
                logger.error(f"每日重置异常: {e}")
                # 出错后 60s 再试，避免空转
                await asyncio.sleep(60)

    def start(self):
        """启动后台调度任务。"""
        if self._running:
            logger.warning("统计每日重置调度器已在运行中")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        """停止后台调度任务。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("统计每日重置调度器已停止")
