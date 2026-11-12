"""上游 Key 失败巡检调度器。

每 10 分钟对 disabled 的上游 Key 执行一次巡检：检验通过即恢复（DB+Redis，
恢复 Key 按 LRU 规则队尾重排），失败保持禁用。复用 service.key_validation.run_full_validation，
与手动「失败 Key 检验」端点走同一条逻辑路径，避免重复实现。

多 worker 幂等：每次执行前用 Redis SET NX EX 抢占锁，仅一个 worker 真正执行；
并把上次执行时间写入 Redis，供前端可选展示。
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 北京时间 UTC+8（无 DST，全年稳定）
BEIJING_TZ = timezone(timedelta(hours=8))
VALIDATION_LOCK_KEY = "sys:key_validation:lock"
LAST_RUN_TS_KEY = "sys:key_validation:last_run_ts"


class KeyValidationScheduler:
    """上游 Key 失败巡检后台调度器。"""

    def __init__(self, interval_minutes: int = 60, concurrency: int = 100):
        """Args:
            interval_minutes: 检验间隔（分钟），最小 1 分钟
            concurrency: 并发检验数
        """
        self._interval_seconds = max(int(interval_minutes) * 60, 60)
        self._concurrency = concurrency
        self._task: asyncio.Task | None = None
        self._running = False

    async def _run_once(self) -> None:
        """执行一次失败 Key 巡检，带多 worker 抢锁幂等。"""
        from service.redis_key_pool import get_key_pool_manager
        redis = get_key_pool_manager().redis

        # 抢锁：TTL 略小于间隔，既防死锁又保证同一窗口内仅一个 worker 执行
        lock_ttl = max(self._interval_seconds - 30, 60)
        acquired = redis.set(VALIDATION_LOCK_KEY, "1", nx=True, ex=lock_ttl)
        if not acquired:
            logger.debug("定时失败巡检已被其他 worker 执行，跳过")
            return

        from models.database import AsyncSessionLocal
        from service.key_validation import _write_state, run_full_validation

        # 与手动触发共用状态哈希：前端轮询能看到定时检验的进度
        now_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
        _write_state(
            redis,
            status="running", started_at=now_str, finished_at="",
            total=0, done=0, success=0, failed=0, message="", results="",
        )

        def _progress(done: int, total: int) -> None:
            _write_state(redis, done=done, total=total)

        try:
            async with AsyncSessionLocal() as session:
                data = await run_full_validation(session, concurrency=self._concurrency, progress_cb=_progress)
            summary = data.get("summary", {})
        except Exception as e:
            _write_state(
                redis,
                status="failed",
                finished_at=datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                message=str(e),
            )
            raise

        # 记录上次执行时间（北京时间），供前端可选展示
        last_run = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
        try:
            redis.set(LAST_RUN_TS_KEY, last_run)
        except Exception as e:
            logger.warning(f"记录定时检验时间失败: {e}")

        _write_state(
            redis,
            status="success", finished_at=last_run,
            total=summary.get("total", 0), done=summary.get("total", 0),
            success=summary.get("success", 0), failed=summary.get("failed", 0),
            results=json.dumps(data.get("results", []), ensure_ascii=False),
        )

        logger.info(
            f"[定时失败巡检] 完成: 总计 {summary.get('total', 0)} "
            f"通过 {summary.get('success', 0)} 失败 {summary.get('failed', 0)}"
        )

    async def _loop(self):
        logger.info(f"上游 Key 失败巡检调度器已启动，每 {self._interval_seconds // 60} 分钟执行一次")

        while self._running:
            try:
                # 首次执行在首个间隔后，避免开机尖峰
                await asyncio.sleep(self._interval_seconds)
                if not self._running:
                    break
                await self._run_once()
            except asyncio.CancelledError:
                logger.info("上游 Key 失败巡检调度器已取消")
                break
            except Exception as e:
                logger.error(f"定时失败巡检异常: {e}")
                # 出错后 60s 再试，避免空转
                await asyncio.sleep(60)

    def start(self):
        """启动后台调度任务。"""
        if self._running:
            logger.warning("上游 Key 失败巡检调度器已在运行中")
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
        logger.info("上游 Key 失败巡检调度器已停止")
