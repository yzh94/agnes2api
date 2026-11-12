"""上游 Key 检验模块。

使用 agnes-2.5-flash 模型对 Key 进行轻量级健康检验。
支持单次检验和全量并发检验。
"""

import asyncio
import logging
from typing import Tuple

import httpx

from config import settings

logger = logging.getLogger(__name__)

TEST_MODEL = "agnes-2.5-flash"
TEST_TIMEOUT = 30.0


async def validate_key(full_key: str) -> Tuple[bool, str]:
    """对单个 Key 进行检验。

    判定规则：HTTP 200 为通过；其余任何情况（鉴权失败、限流、5xx、网络异常/超时等）
    均判为失败——检验失败即禁用。误禁的 Key 会由后续检验通过时自动恢复，
    或由服务启动时的"全部重置启用"兜底。

    Returns:
        (success: bool, message: str)
    """
    try:
        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            payload = {
                "model": TEST_MODEL,
                "messages": [{"role": "user", "content": "OK"}],
                "max_tokens": 5,
            }
            from service.url_manager import get_url_manager
            url_manager = get_url_manager()
            base_url = url_manager.get_best_url()
            resp = await client.post(
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {full_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code == 200:
                return True, "检验通过"
            else:
                err_body = {}
                try:
                    err_body = resp.json()
                except Exception:
                    pass
                error_msg = (
                    err_body.get("error", {}).get("message", resp.text[:200])
                    if isinstance(err_body, dict)
                    else resp.text[:200]
                )
                return False, f"检验失败: HTTP {resp.status_code} {error_msg}"
    except Exception as e:
        return False, f"检验异常: {str(e)}"


async def validate_all_keys(
    db_keys: list,
    concurrency: int = 100,
    progress_cb=None,
) -> list:
    """并发检验所有上游 Key。

    Args:
        db_keys: UpstreamKey ORM 对象列表
        concurrency: 最大并发数
        progress_cb: 可选进度回调，每检完一个 Key 调用一次 progress_cb(done, total)

    Returns:
        [{key_id, name, masked_key, user_id, success, message}]
    """
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    total = len(db_keys)
    done = 0

    async def _validate_one(key):
        nonlocal done
        masked = key.key[:8] + "***"
        async with semaphore:
            success, message = await validate_key(key.key)
            results.append({
                "key_id": key.id,
                "name": key.name,
                "masked_key": masked,
                "user_id": key.user_id,
                "success": success,
                "message": message,
            })
            done += 1
            if progress_cb:
                try:
                    progress_cb(done, total)
                except Exception:
                    pass  # 进度回调失败不影响检验
            status_str = "通过" if success else "失败"
            logger.info(f"[失败巡检] Key '{key.name}' ({masked}) {status_str}: {message}")

    tasks = [_validate_one(k) for k in db_keys]
    await asyncio.gather(*tasks)
    return results
