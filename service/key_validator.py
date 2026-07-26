"""上游 Key 检验模块。

使用 agnes-2.0-flash 模型对 Key 进行轻量级健康检验。
支持单次检验和全量并发检验。
"""

import asyncio
import logging
from typing import List, Dict, Tuple

import httpx

from config import settings

logger = logging.getLogger(__name__)

TEST_MODEL = "agnes-2.0-flash"
TEST_TIMEOUT = 30.0


async def validate_key(full_key: str) -> Tuple[bool, str]:
    """对单个 Key 进行检验。

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
            resp = await client.post(
                f"{settings.agnes_base_url}/v1/chat/completions",
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
                return False, f"检验失败: {error_msg}"
    except Exception as e:
        return False, f"检验异常: {str(e)}"


async def validate_all_keys(
    db_keys: List,
    concurrency: int = 100,
) -> List[Dict]:
    """并发检验所有上游 Key。

    Args:
        db_keys: UpstreamKey ORM 对象列表
        concurrency: 最大并发数

    Returns:
        [{key_id, name, masked_key, user_id, success, message}]
    """
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async def _validate_one(key):
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
            status_str = "通过" if success else "失败"
            logger.info(f"[全量检验] Key '{key.name}' ({masked}) {status_str}: {message}")

    tasks = [_validate_one(k) for k in db_keys]
    await asyncio.gather(*tasks)
    return results
