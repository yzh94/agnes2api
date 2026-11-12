"""上游 Key 失败巡检与热重载的可复用逻辑。

供管理端点（手动失败 Key 巡检）与定时调度器共用，避免逻辑重复。
"""
import asyncio
import logging
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import UpstreamKey

logger = logging.getLogger(__name__)


async def trigger_hot_reload(db: AsyncSession) -> None:
    """当上游 Key 发生变化时，热重载内存和 Redis 中的 Key 池。

    以 MySQL 全量 key（含 disabled）重建 Redis：active 参与选 Key，disabled
    标记跳过但保留在池中以便展示与巡检。disabled_reason/disabled_at 一并还原。
    """
    result = await db.execute(select(UpstreamKey))
    db_keys = result.scalars().all()
    all_keys = [k.key for k in db_keys]
    active_keys = [k.key for k in db_keys if k.status == "active"]

    from service.key_stats import get_key_stats_manager
    from service.redis_key_pool import get_key_pool_manager

    stats_manager = get_key_stats_manager()
    for k in active_keys:
        stats_manager.register_key(k)

    # 构建 masked -> 状态映射（来自 MySQL，作为 Redis 重建依据）
    key_pool = get_key_pool_manager()
    key_statuses: dict[str, dict] = {}
    for k in db_keys:
        masked = key_pool._compute_key_prefix(k.key)
        disabled_at_ts = ""
        if k.disabled_at:
            try:
                disabled_at_ts = str(int(k.disabled_at.timestamp()))
            except Exception:
                disabled_at_ts = ""
        key_statuses[masked] = {
            "status": k.status,
            "disabled_at": disabled_at_ts,
            "disabled_reason": k.disabled_reason or "",
        }

    await key_pool.initialize(all_keys, key_statuses=key_statuses)

    # 变更后对账：清扫 Redis 中 DB 已不存在的上游 Key 的孤儿数据
    from service.redis_reconcile import reconcile_upstream_keys_with_db
    try:
        await reconcile_upstream_keys_with_db(db)
    except Exception as e:
        logger.warning(f"变更后对账失败: {e}")


async def run_full_validation(
    db: AsyncSession,
    concurrency: int = 100,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> dict[str, Any]:
    """失败 Key 巡检：只检验 disabled 的 Key，通过即恢复，失败保持禁用。

    检验范围 = DB status=disabled ∪ Redis 池中 status=disabled（运行时禁用
    异步写 DB 存在延迟窗口，以两者并集为准）。active Key 不检验——真实流量
    即其健康检查，失败会即时禁用。

    恢复语义：DB 与 Redis 同步置 active，Redis last_used_at 更新为恢复时刻
    （UTC epoch），恢复 Key 按 LRU 规则从队尾重新排队，避免旧时间戳插队。

    Args:
        db: 数据库会话
        concurrency: 最大并发数
        progress_cb: 可选进度回调，每检完一个 Key 调用一次 progress_cb(done, total)

    Returns:
        {"results": [...], "summary": {"total", "success", "failed"}}
    """
    import time as _time

    from service.key_validator import validate_all_keys
    from service.key_disable import disable_key_and_check_user_rate

    # 获取所有 Key，筛选待巡检目标（DB disabled ∪ Redis disabled）
    result = await db.execute(select(UpstreamKey))
    all_keys: list[UpstreamKey] = result.scalars().all()

    if not all_keys:
        return {"results": [], "summary": {"total": 0, "success": 0, "failed": 0}}

    from service.redis_key_pool import get_key_pool_manager, KEY_POOL_PREFIX
    pool_manager = get_key_pool_manager()
    redis_pool = pool_manager.redis
    pipe = redis_pool.pipeline(transaction=False)
    for k in all_keys:
        pipe.hget(f"{KEY_POOL_PREFIX}{pool_manager._compute_key_prefix(k.key)}", "status")
    redis_statuses = pipe.execute()

    targets = [
        k for k, rs in zip(all_keys, redis_statuses)
        if k.status == "disabled" or rs == "disabled"
    ]
    if not targets:
        return {"results": [], "summary": {"total": 0, "success": 0, "failed": 0}}

    # 并发检验（仅失败 Key）
    results = await validate_all_keys(targets, concurrency=concurrency, progress_cb=progress_cb)

    # 处理结果：失败保持禁用，成功恢复（DB + Redis，恢复 Key 队尾重排）
    success_count = 0
    fail_count = 0
    users_to_refresh = set()
    restored = False

    for r in results:
        up_key = next((k for k in targets if k.id == r["key_id"]), None)
        if not up_key:
            continue

        if not r["success"]:
            # 检验失败 -> 保持禁用（若 DB 尚为 active，补一次禁用落库）
            if up_key.status != "disabled":
                await disable_key_and_check_user_rate(db, up_key, f"巡检失败: {r['message']}")
                if up_key.user_id:
                    users_to_refresh.add(up_key.user_id)
            # 同步更新 Redis 的 disabled_reason（Redis 已是 disabled 状态）
            try:
                redis_pool.hset(
                    f"{KEY_POOL_PREFIX}{pool_manager._compute_key_prefix(up_key.key)}",
                    mapping={
                        "status": "disabled",
                        "disabled_reason": f"巡检失败: {r['message']}",
                    },
                )
            except Exception as e:
                logger.warning(f"巡检失败写 Redis reason 失败: {pool_manager._compute_key_prefix(up_key.key)} | {e}")
            fail_count += 1
        else:
            # 检验成功 -> 恢复：DB 置 active，Redis 置 active 并更新 last_used_at
            if up_key.status == "disabled":
                up_key.status = "active"
                up_key.disabled_reason = None
                up_key.disabled_at = None
                users_to_refresh.add(up_key.user_id or 0)
            try:
                redis_pool.hset(
                    f"{KEY_POOL_PREFIX}{pool_manager._compute_key_prefix(up_key.key)}",
                    mapping={
                        "status": "active",
                        "disabled_at": "",
                        "disabled_reason": "",
                        "last_used_at": str(int(_time.time())),
                    },
                )
            except Exception as e:
                logger.warning(f"巡检恢复写 Redis 失败: {pool_manager._compute_key_prefix(up_key.key)} | {e}")
            restored = True
            success_count += 1

    # 提交未提交的状态变更（如检验成功的 disabled key 恢复）
    try:
        await db.commit()
    except Exception:
        await db.rollback()

    # 有恢复时热重载一次
    if restored:
        await trigger_hot_reload(db)

    # 刷新受影响用户的速率
    from service.rate_limit import refresh_user_tier
    for uid in users_to_refresh:
        refresh_user_tier(uid)

    return {
        "results": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": fail_count,
        },
    }


# --- 失败巡检后台任务（异步任务化：避免同步 HTTP 请求撑爆前端/网关超时） ---

# 检验状态 Hash：status/started_at/finished_at/total/done/success/failed/message/results
VALIDATION_STATE_KEY = "sys:key_validation:state"
# 手动触发的锁 TTL（秒）：worker 崩溃时自愈上限；正常结束会主动删锁
MANUAL_LOCK_TTL = 900
# 持有后台任务引用，避免事件循环仅弱引用导致任务被 GC
_BG_TASKS: set[asyncio.Task] = set()


def _write_state(redis, **fields) -> None:
    """写失败巡检状态（异常仅告警，不影响检验主流程）。"""
    try:
        if fields:
            redis.hset(VALIDATION_STATE_KEY, mapping={k: str(v) for k, v in fields.items()})
    except Exception as e:
        logger.warning(f"写失败巡检状态失败: {e}")


def get_validation_state() -> dict[str, Any]:
    """读取失败巡检当前状态，供状态轮询接口返回。"""
    import json as _json

    from service.redis_key_pool import get_key_pool_manager

    try:
        data = get_key_pool_manager().redis.hgetall(VALIDATION_STATE_KEY)
    except Exception as e:
        return {"status": "unknown", "message": str(e)}
    if not data:
        return {"status": "idle"}

    state: dict[str, Any] = dict(data)
    for f in ("total", "done", "success", "failed"):
        try:
            state[f] = int(state.get(f, 0) or 0)
        except (ValueError, TypeError):
            state[f] = 0
    results_raw = state.get("results")
    if results_raw:
        try:
            state["results"] = _json.loads(results_raw)
        except Exception:
            state["results"] = []
    return state


def start_full_validation_background(concurrency: int = 100) -> dict[str, Any]:
    """后台启动失败巡检并立即返回，进度写 Redis 供前端轮询。

    与定时调度器共用同一把 Redis 锁（VALIDATION_LOCK_KEY），手动/定时互斥；
    正常结束主动删锁，异常崩溃由锁 TTL 自愈。
    """
    import json as _json
    from datetime import datetime as _dt

    from service.redis_key_pool import get_key_pool_manager
    from service.key_validation_scheduler import (
        BEIJING_TZ,
        LAST_RUN_TS_KEY,
        VALIDATION_LOCK_KEY,
    )

    redis = get_key_pool_manager().redis
    acquired = redis.set(VALIDATION_LOCK_KEY, "manual", nx=True, ex=MANUAL_LOCK_TTL)
    if not acquired:
        return {"status": "already_running", "state": get_validation_state()}

    now_str = _dt.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    _write_state(
        redis,
        status="running", started_at=now_str, finished_at="",
        total=0, done=0, success=0, failed=0, message="", results="",
    )

    def _progress(done: int, total: int) -> None:
        _write_state(redis, done=done, total=total)

    async def _bg() -> None:
        from models.database import AsyncSessionLocal

        try:
            # 后台任务自建会话：请求级 db 会话随响应结束即关闭，不能跨请求复用
            async with AsyncSessionLocal() as session:
                data = await run_full_validation(session, concurrency=concurrency, progress_cb=_progress)
            summary = data.get("summary", {})
            finished_str = _dt.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
            _write_state(
                redis,
                status="success", finished_at=finished_str,
                total=summary.get("total", 0), done=summary.get("total", 0),
                success=summary.get("success", 0), failed=summary.get("failed", 0),
                results=_json.dumps(data.get("results", []), ensure_ascii=False),
            )
            try:
                redis.set(LAST_RUN_TS_KEY, finished_str)
            except Exception:
                pass
            logger.info(
                f"[手动失败巡检] 完成: 总计 {summary.get('total', 0)} "
                f"通过 {summary.get('success', 0)} 失败 {summary.get('failed', 0)}"
            )
        except Exception as e:
            logger.error(f"[手动失败巡检] 异常: {e}")
            _write_state(
                redis,
                status="failed",
                finished_at=_dt.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S"),
                message=str(e),
            )
        finally:
            try:
                redis.delete(VALIDATION_LOCK_KEY)
            except Exception:
                pass

    task = asyncio.create_task(_bg())
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return {"status": "started", "state": get_validation_state()}
