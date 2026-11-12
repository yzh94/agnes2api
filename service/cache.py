"""请求缓存服务模块。

提供 LRU 缓存功能，支持：
- 基于请求参数的缓存键生成
- TTL 过期机制
- 线程安全的读写操作
- 支持文本模型和图片模型的缓存
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Optional
from collections import OrderedDict

from config import settings

logger = logging.getLogger(__name__)


class RequestCache:
    """请求缓存类，使用 LRU 策略和 TTL 过期机制。"""

    def __init__(
        self,
        max_size: Optional[int] = None,
        ttl: Optional[int] = None,
        key_prefix: Optional[str] = None,
    ):
        self.max_size = max_size or settings.cache_max_size
        self.ttl = ttl or settings.cache_ttl
        self.key_prefix = key_prefix or settings.cache_key_prefix
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = asyncio.Lock()  # 异步锁保护缓存读写

    def _make_key(self, *args, **kwargs) -> str:
        """生成缓存键。"""
        # 将参数序列化为字符串
        key_data = {
            "prefix": self.key_prefix,
            "args": args,
            "kwargs": kwargs,
        }
        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        # 使用 SHA256 生成固定长度的键
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:32]

    async def get(self, key: str) -> Optional[Any]:
        """从缓存中获取数据。

        Args:
            key: 缓存键

        Returns:
            缓存数据，如果不存在或已过期则返回 None
        """
        if not settings.enable_cache:
            return None

        async with self._lock:
            entry = self._cache.get(key)

        if not entry:
            return None

        # 检查是否过期
        if time.time() > entry["expires_at"]:
            async with self._lock:
                del self._cache[key]
            logger.debug(f"Cache expired: {key[:16]}...")
            return None

        # 移动到末尾（最近使用）
        async with self._lock:
            self._cache.move_to_end(key)
        logger.debug(f"Cache hit: {key[:16]}...")
        return entry["data"]

    async def set(self, key: str, data: Any) -> None:
        """将数据写入缓存。

        Args:
            key: 缓存键
            data: 要缓存的数据
        """
        if not settings.enable_cache:
            return

        async with self._lock:
            # 如果键已存在，先删除
            if key in self._cache:
                del self._cache[key]
            # 如果超出容量，淘汰最旧的
            elif len(self._cache) >= self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                logger.debug(f"Cache evicted (LRU): {oldest_key[:16]}...")

            self._cache[key] = {
                "data": data,
                "expires_at": time.time() + self.ttl,
                "created_at": time.time(),
            }
        logger.debug(f"Cache set: {key[:16]}...")

    async def invalidate(self, key: str) -> bool:
        """使指定缓存失效。

        Args:
            key: 缓存键

        Returns:
            是否成功失效
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache invalidated: {key[:16]}...")
                return True
        return False

    async def clear(self) -> None:
        """清空所有缓存。"""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
        logger.info(f"Cache cleared: {count} entries removed")

    def stats(self) -> dict:
        """获取缓存统计信息。"""
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
            "hit_rate": "N/A",  # 暂未实现命中率统计
        }


# 全局缓存实例
request_cache = RequestCache()


def generate_text_cache_key(model: str, messages: list, **kwargs) -> str:
    """为文本模型请求生成缓存键。

    使用完整的消息历史作为缓存键的一部分，以确保多轮对话场景下的缓存准确性。
    对于多轮对话，使用消息序列的哈希作为标识。

    Args:
        model: 模型名称
        messages: 消息列表
        **kwargs: 其他请求参数

    Returns:
        缓存键
    """
    # 提取所有消息内容，构建更精确的缓存键
    message_contents = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            message_contents.append(f"{role}:{content}")
        elif hasattr(msg, "role") and hasattr(msg, "content"):
            message_contents.append(f"{msg.role}:{msg.content}")
    
    # 使用完整消息序列作为缓存键的一部分
    return request_cache._make_key(
        "text", model, "|".join(message_contents),
        temperature=kwargs.get("temperature"),
        max_tokens=kwargs.get("max_tokens"),
        stream=False,  # 只缓存非流式响应
    )


def generate_image_cache_key(model: str, prompt: str, **kwargs) -> str:
    """为图片模型请求生成缓存键。

    Args:
        model: 模型名称
        prompt: 提示词
        **kwargs: 其他请求参数（size / n / return_base64 / response_format / image）

    Returns:
        缓存键
    """
    # 图生图输入图像（可能含大体积 Base64）单独哈希，既区分不同输入又避免键过长
    image = kwargs.get("image")
    image_hash = None
    if image:
        try:
            image_hash = hashlib.sha256(
                json.dumps(image, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()[:16]
        except Exception:
            image_hash = str(image)

    return request_cache._make_key(
        "image", model, prompt,
        size=kwargs.get("size"),
        n=kwargs.get("n", 1),
        return_base64=kwargs.get("return_base64"),
        response_format=kwargs.get("response_format"),
        image_hash=image_hash,
    )