"""上游 HTTP 客户端，统一封装请求和失败重试机制。

简化版：移除 Redis 依赖，使用 simple_key_pool。
"""
import logging
import time
from typing import Optional, Dict, Any, Tuple

from httpx import Response
from utils.http_client import get_http_client
from service.simple_key_pool import get_key_pool_manager
from service.key_stats import get_key_stats_manager
from service.key_disable import check_and_disable_key_on_401
from service.errors import UpstreamAPIError

logger = logging.getLogger(__name__)


async def request_upstream_with_retry(
    method: str,
    url_template: str,
    model_type: str,
    payload: Dict[str, Any],
    max_retries: int = 1,
    user_id: int = 0,
) -> Tuple[Response, str]:
    """使用带有自动换 Key 和重试机制的请求封装。

    Args:
        method: HTTP 方法 (如 "POST")
        url_template: URL 模板（不用包含具体的 host）
        model_type: 统计用的模型类型 ("text", "image", "video")
        payload: 发送的 JSON 载荷
        max_retries: 失败自动换 Key 的最大重试次数，默认重试 1 次
        user_id: 用户 ID（单用户模式忽略）

    Returns:
        (HTTP Response 对象, 最终成功的 full_key)
    """
    key_pool = get_key_pool_manager()
    stats_manager = get_key_stats_manager()
    http_client = get_http_client()

    last_exception = None

    for attempt in range(max_retries + 1):
        # 1. 获取一个可用的 Key
        full_key = await key_pool.get_key()
        if not full_key:
            raise UpstreamAPIError(status_code=503, detail="没有可用的上游 Key (全部耗尽或被禁用)")

        headers = {
            "Authorization": f"Bearer {full_key}",
            "Content-Type": "application/json",
        }

        try:
            # 2. 发起请求
            t_http_start = time.monotonic()
            http_resp = await http_client.request(
                method=method,
                url=url_template,
                headers=headers,
                json=payload
            )
            http_elapsed = (time.monotonic() - t_http_start) * 1000

            # 3. 检查状态码
            if http_resp.status_code >= 400:
                logger.warning(
                    f"[{http_elapsed:.0f}ms] 上游请求失败 (Attempt {attempt+1}/{max_retries+1}): "
                    f"status={http_resp.status_code}, key={full_key[:8]}..."
                )

                try:
                    err_body = http_resp.json()
                except Exception:
                    err_body = {"error": {"message": http_resp.text}}

                # 记录失败状态
                await key_pool.record_failure(full_key)
                stats_manager.record_request(full_key, model_type, False, user_id=user_id)

                # 检测是否需要永久禁用 (401 令牌不可用)
                await check_and_disable_key_on_401(full_key, http_resp.status_code, err_body)

                # 判定是否可换 Key 重试
                status_code = http_resp.status_code
                retryable = status_code in (401, 408, 429) or status_code >= 500

                last_exception = UpstreamAPIError(status_code=status_code, detail=err_body)
                if not retryable:
                    logger.warning(
                        f"[{http_elapsed:.0f}ms] 客户端错误，不换 Key 重试: "
                        f"status={status_code}, key={full_key[:8]}..."
                    )
                    raise last_exception

                if attempt < max_retries:
                    logger.warning(
                        f"[{http_elapsed:.0f}ms] 可重试错误，切换 Key 重试: "
                        f"status={status_code}, key={full_key[:8]}..."
                    )
                    continue

                raise last_exception

            # 请求成功
            await key_pool.record_success(full_key)
            stats_manager.record_request(full_key, model_type, True, user_id=user_id)

            logger.info(f"[{http_elapsed:.0f}ms] 上游请求成功 (Attempt {attempt+1}): status={http_resp.status_code}")
            return http_resp, full_key

        except UpstreamAPIError:
            raise
        except Exception as e:
            logger.error(f"上游请求异常 (Attempt {attempt+1}/{max_retries+1}): {e}")
            await key_pool.record_failure(full_key)
            stats_manager.record_request(full_key, model_type, False, user_id=user_id)
            last_exception = UpstreamAPIError(status_code=502, detail=f"上游网关错误: {str(e)}")
            if attempt < max_retries:
                continue
            raise last_exception
