"""上游 HTTP 客户端，统一封装请求和失败重试机制。"""
import json
import logging
import time
from typing import Optional, Any, Tuple

from httpx import Response
from utils.http_client import get_http_client
from service.redis_key_pool import get_key_pool_manager
from service.key_stats import get_key_stats_manager
from service.key_disable import check_and_disable_key_on_401
from service.errors import UpstreamAPIError

logger = logging.getLogger(__name__)

# 上游调用详细日志的截断阈值（防止 base64 图片等大字段打爆 console）
_MAX_STRING_FIELD_CHARS = 200   # 单个字符串字段最大显示长度
_MAX_PAYLOAD_CHARS = 2000       # payload 整体最大显示长度
_MAX_RESPONSE_BODY_CHARS = 2000  # 响应体最大显示长度


def truncate_string(value: str, limit: int = _MAX_STRING_FIELD_CHARS) -> str:
    """截断过长的字符串并标注原始长度。"""
    if len(value) <= limit:
        return value
    return value[:limit] + f"...[truncated {len(value)} chars]"


def truncate_payload(payload: Any) -> Any:
    """递归截断 payload 中过长的字符串字段（如 base64 图片数据）。"""
    if isinstance(payload, dict):
        return {k: truncate_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [truncate_payload(item) for item in payload]
    if isinstance(payload, str):
        return truncate_string(payload)
    return payload


def format_payload_for_log(payload: dict[str, Any]) -> str:
    """将 payload 序列化为可读的详细日志文本，自动截断大字段与超长整体。

    序列化失败时返回占位符，保证日志故障不阻断业务请求。
    """
    try:
        text = json.dumps(truncate_payload(payload), ensure_ascii=False)
        if len(text) > _MAX_PAYLOAD_CHARS:
            text = text[:_MAX_PAYLOAD_CHARS] + "...[truncated]"
        return text
    except Exception as e:
        logger.warning(f"payload 日志序列化失败: {e}")
        return f"<payload log failed: {e}>"


def format_response_body_for_log(resp: Response) -> str:
    """将响应体序列化为可读的详细日志文本，超长时截断。

    解码失败时返回占位符，保证日志故障不影响上游调用主流程。
    """
    try:
        text = resp.text
    except Exception as e:
        logger.warning(f"响应体日志解码失败: {e}")
        return f"<response body log failed: {e}>"
    if len(text) > _MAX_RESPONSE_BODY_CHARS:
        text = text[:_MAX_RESPONSE_BODY_CHARS] + f"...[truncated {len(resp.text)} chars]"
    return text

async def request_upstream_with_retry(
    method: str,
    path: str,
    model_type: str,
    payload: dict[str, Any],
    max_retries: int = 2,
    user_id: int = 0,
) -> Tuple[Response, str]:
    """使用带有自动换 Key 和重试机制的请求封装。

    Args:
        method: HTTP 方法 (如 "POST")
        path: URL 相对路径（例如 "/v1/chat/completions"）
        model_type: 统计用的模型类型 ("text", "image", "video")
        payload: 发送的 JSON 载荷
        max_retries: 失败自动换 Key 的最大重试次数，默认重试 2 次（最多 3 把 Key）

    Returns:
        (HTTP Response 对象, 最终成功的 full_key)
    """
    key_pool = get_key_pool_manager()
    stats_manager = get_key_stats_manager()
    http_client = get_http_client()
    from service.url_manager import get_url_manager
    url_manager = get_url_manager()

    last_exception = None
    tried_keys: set[str] = set()  # 本次请求已失败过的 Key，重试时排除
    request_ok = False  # 请求级最终结果（用户视角）
    final_key: Optional[str] = None  # 终局归属 Key：成功为实际成功的 Key，失败为最后尝试的 Key

    try:
        # 尝试次数 = 1 (首次) + max_retries
        for attempt in range(max_retries + 1):
            # 1. 获取一个可用的 Key（排除本轮已失败的 Key）
            full_key = await key_pool.get_key(exclude=tried_keys)
            if not full_key:
                raise UpstreamAPIError(status_code=503, detail="没有可用的上游 Key (全部耗尽或被降级)")
            tried_keys.add(full_key)
            final_key = full_key

            # 获取当前成功率最高的可用 URL
            base_url = url_manager.get_best_url()
            url = f"{base_url}{path}"

            headers = {
                "Authorization": f"Bearer {full_key}",
                "Content-Type": "application/json",
            }

            # 详细日志：记录发往 Agnes 上游的请求（method / url / model_type / payload）
            logger.debug(
                f"[Upstream] → {method} {url} model_type={model_type} "
                f"key={full_key[:8]}... payload={format_payload_for_log(payload)}"
            )

            # 2. 发起请求（网络异常单独捕获：节点级故障，不归咎 Key）
            try:
                t_http_start = time.monotonic()
                http_resp = await http_client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=payload
                )
                http_elapsed = (time.monotonic() - t_http_start) * 1000
            except UpstreamAPIError:
                raise
            except Exception as e:
                # 网络超时、连接被拒等算作该 URL 节点的失败，不累计 Key 连续失败
                url_manager.record_result(base_url, False)
                logger.error(f"上游请求异常 (Attempt {attempt+1}/{max_retries+1}): {e}")
                await key_pool.record_failure(full_key, reason="network", degradable=False)
                last_exception = UpstreamAPIError(status_code=502, detail=f"上游网关错误: {str(e)}")
                if attempt < max_retries:
                    continue
                raise last_exception

            # 记录 URL 成功或失败
            if http_resp.status_code >= 500:
                url_manager.record_result(base_url, False)
            else:
                url_manager.record_result(base_url, True)

            # 3. 检查状态码
            if http_resp.status_code >= 400:
                logger.warning(
                    f"[{http_elapsed:.0f}ms] 上游请求失败 (Attempt {attempt+1}/{max_retries+1}): "
                    f"status={http_resp.status_code}, key={full_key[:8]}..., "
                    f"body={format_response_body_for_log(http_resp)}"
                )

                try:
                    err_body = http_resp.json()
                except Exception:
                    err_body = {"error": {"message": http_resp.text}}

                status_code = http_resp.status_code

                # 客户端参数错误（400/404/422 等，排除 401/403/408/429）：
                # 与 Key 健康无关，不记 Key 失败、不换 Key 重试，直接返回
                is_client_fault = 400 <= status_code < 500 and status_code not in (401, 403, 408, 429)
                if is_client_fault:
                    logger.warning(
                        f"[{http_elapsed:.0f}ms] 客户端错误，不记 Key 失败、不换 Key 重试: "
                        f"status={status_code}, key={full_key[:8]}..."
                    )
                    raise UpstreamAPIError(status_code=status_code, detail=err_body)

                # Key 可归责失败：分类记录（429 立即降级 / 401·403 鉴权 / 408·5xx 服务端）
                if status_code == 429:
                    fail_reason = "rate_limit"
                elif status_code in (401, 403):
                    fail_reason = "auth"
                else:
                    fail_reason = "server"
                await key_pool.record_failure(full_key, reason=fail_reason)

                # 检测是否需要永久禁用 (401 令牌不可用)
                await check_and_disable_key_on_401(full_key, status_code, err_body)

                # 可重试错误：如果还有重试次数则换 Key 重试，否则抛出最后一次错误
                last_exception = UpstreamAPIError(status_code=status_code, detail=err_body)
                if attempt < max_retries:
                    logger.warning(
                        f"[{http_elapsed:.0f}ms] 可重试错误，切换 Key 重试: "
                        f"status={status_code}, key={full_key[:8]}..."
                    )
                    continue

                raise last_exception

            # 请求成功
            await key_pool.record_success(full_key)
            request_ok = True

            logger.info(f"[{http_elapsed:.0f}ms] 上游请求成功 (Attempt {attempt+1}): status={http_resp.status_code}")
            # 详细日志：记录 Agnes 上游返回的响应体（截断超长内容）
            logger.debug(
                f"[Upstream] ← status={http_resp.status_code} key={full_key[:8]}... "
                f"body={format_response_body_for_log(http_resp)}"
            )
            return http_resp, full_key
    finally:
        # 终局一次性记账：整个请求（含内部重试）只按最终结果记一次（用户视角成功率）。
        # 中间尝试不产生成功率计数；Key Pool 的 record_success/record_failure 已在
        # 各尝试点独立承担 Key 健康观测。final_key 为 None（未尝试任何 Key，如池耗尽）
        # 时只记请求级。
        try:
            stats_manager.record_final_outcome(model_type, request_ok, key=final_key, user_id=user_id)
        except Exception:
            pass  # 请求级统计失败不影响主流程
