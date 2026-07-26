"""API Key 请求统计管理器 - 纯内存实现。

移除 Redis 依赖，适用于单用户/单进程场景。

功能：
- 跟踪文本(text)、图片(image)模型的成功/失败计数
- 支持按模型类型查询统计信息
- 所有数据存储在内存中，重启后归零
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelTypeStats:
    """单个模型类型的统计信息。"""

    def __init__(self, total_requests: int = 0, success_count: int = 0, failure_count: int = 0):
        self.total_requests = total_requests
        self.success_count = success_count
        self.failure_count = failure_count

    @property
    def success_rate(self) -> float:
        """计算成功率 (0-100)。"""
        if self.total_requests == 0:
            return 0.0
        return round((self.success_count / self.total_requests) * 100, 2)

    def to_dict(self) -> dict:
        return {
            "total": self.total_requests,
            "success": self.success_count,
            "failure": self.failure_count,
            "success_rate": self.success_rate,
        }


class APIKeyStats:
    """单个 API Key 的完整统计信息（用于本地聚合）。"""

    def __init__(self, key_prefix: str):
        self.key_prefix = key_prefix
        self.text_stats = ModelTypeStats()
        self.image_stats = ModelTypeStats()
        self.video_stats = ModelTypeStats()

    def get_summary(self) -> dict:
        """获取统计摘要。"""
        total_all = (self.text_stats.total_requests +
                     self.image_stats.total_requests +
                     self.video_stats.total_requests)
        success_all = (self.text_stats.success_count +
                       self.image_stats.success_count +
                       self.video_stats.success_count)
        failure_all = (self.text_stats.failure_count +
                       self.image_stats.failure_count +
                       self.video_stats.failure_count)

        return {
            "key_prefix": self.key_prefix,
            "text": self.text_stats.to_dict(),
            "image": self.image_stats.to_dict(),
            "video": self.video_stats.to_dict(),
            "summary": {
                "total": total_all,
                "success": success_all,
                "failure": failure_all,
                "success_rate": round((success_all / total_all * 100), 2) if total_all > 0 else 0.0,
            }
        }

    @staticmethod
    def _compute_key_prefix(key: str) -> str:
        """计算 API Key 的前缀显示。"""
        if len(key) > 8:
            return key[:8] + "***"
        else:
            return key + "***"


class KeyStatsManager:
    """API Key 统计管理器 - 纯内存。

    属性：
        fallback_stats: Dict[key_prefix, Dict[model_type, ModelTypeStats]]
    """

    def __init__(self):
        self._fallback_stats: Dict[str, Dict[str, ModelTypeStats]] = {}
        self._registered_keys: List[str] = []

    def register_key(self, key: str):
        """注册一个新的 API Key 统计。

        Args:
            key: API Key
        """
        if key not in self._registered_keys:
            self._registered_keys.append(key)
            key_prefix = APIKeyStats._compute_key_prefix(key)
            logger.info(f"注册 API Key 统计: {key_prefix}")
            if key_prefix not in self._fallback_stats:
                self._fallback_stats[key_prefix] = {
                    "text": ModelTypeStats(),
                    "image": ModelTypeStats(),
                    "video": ModelTypeStats(),
                }

    def unregister_key(self, key: str):
        """注销一个 API Key，清理其内存注册表。"""
        key_prefix = APIKeyStats._compute_key_prefix(key)
        if key in self._registered_keys:
            self._registered_keys.remove(key)
        self._fallback_stats.pop(key_prefix, None)
        logger.info(f"注销 API Key 统计: {key_prefix}")

    def record_request(self, key: str, model_type: str, success: bool, client_key_id: int = None, tokens: int = 0, cost: float = 0.0, user_id: int = 0):
        """记录一次请求结果。

        Args:
            key: API Key
            model_type: 模型类型 ("text", "image", "video")
            success: 请求是否成功
            client_key_id: 客户端密钥 ID（不再写入 DB）
            tokens: token 数（不再写入 DB）
            cost: 费用（不再写入 DB）
            user_id: 用户 ID（单用户模式忽略）
        """
        key_prefix = APIKeyStats._compute_key_prefix(key)

        if key_prefix not in self._fallback_stats:
            self._fallback_stats[key_prefix] = {
                "text": ModelTypeStats(),
                "image": ModelTypeStats(),
                "video": ModelTypeStats(),
            }

        stats_dict = self._fallback_stats[key_prefix]
        if model_type not in stats_dict:
            stats_dict[model_type] = ModelTypeStats()

        stats_dict[model_type].total_requests += 1
        if success:
            stats_dict[model_type].success_count += 1
        else:
            stats_dict[model_type].failure_count += 1

    def get_all_stats(self) -> list[dict]:
        """获取所有 API Key 的统计信息。"""
        result = []
        for prefix, stats_dict in self._fallback_stats.items():
            text_s = stats_dict.get("text", ModelTypeStats())
            image_s = stats_dict.get("image", ModelTypeStats())
            video_s = stats_dict.get("video", ModelTypeStats())
            total_all = text_s.total_requests + image_s.total_requests + video_s.total_requests
            success_all = text_s.success_count + image_s.success_count + video_s.success_count
            failure_all = text_s.failure_count + image_s.failure_count + video_s.failure_count
            result.append({
                "key_prefix": prefix,
                "text": text_s.to_dict(),
                "image": image_s.to_dict(),
                "video": video_s.to_dict(),
                "summary": {
                    "total": total_all,
                    "success": success_all,
                    "failure": failure_all,
                    "success_rate": round((success_all / total_all * 100), 2) if total_all > 0 else 0.0,
                }
            })
        return result

    def get_key_stats(self, key: str) -> Optional[dict]:
        """获取指定 API Key 的统计信息。"""
        key_prefix = APIKeyStats._compute_key_prefix(key)
        stats_dict = self._fallback_stats.get(key_prefix)
        if not stats_dict:
            return None
        text_s = stats_dict.get("text", ModelTypeStats())
        image_s = stats_dict.get("image", ModelTypeStats())
        video_s = stats_dict.get("video", ModelTypeStats())
        total_all = text_s.total_requests + image_s.total_requests + video_s.total_requests
        success_all = text_s.success_count + image_s.success_count + video_s.success_count
        failure_all = text_s.failure_count + image_s.failure_count + video_s.failure_count
        return {
            "key_prefix": key_prefix,
            "text": text_s.to_dict(),
            "image": image_s.to_dict(),
            "video": video_s.to_dict(),
            "summary": {
                "total": total_all,
                "success": success_all,
                "failure": failure_all,
                "success_rate": round((success_all / total_all * 100), 2) if total_all > 0 else 0.0,
            }
        }

    def get_total_stats(self) -> dict:
        """获取所有 Key 的总体统计。"""
        total_text = ModelTypeStats()
        total_image = ModelTypeStats()
        total_video = ModelTypeStats()
        for stats_dict in self._fallback_stats.values():
            total_text.total_requests += stats_dict.get("text", ModelTypeStats()).total_requests
            total_text.success_count += stats_dict.get("text", ModelTypeStats()).success_count
            total_text.failure_count += stats_dict.get("text", ModelTypeStats()).failure_count
            total_image.total_requests += stats_dict.get("image", ModelTypeStats()).total_requests
            total_image.success_count += stats_dict.get("image", ModelTypeStats()).success_count
            total_image.failure_count += stats_dict.get("image", ModelTypeStats()).failure_count
            total_video.total_requests += stats_dict.get("video", ModelTypeStats()).total_requests
            total_video.success_count += stats_dict.get("video", ModelTypeStats()).success_count
            total_video.failure_count += stats_dict.get("video", ModelTypeStats()).failure_count
        return {
            "text": total_text.to_dict(),
            "image": total_image.to_dict(),
            "video": total_video.to_dict(),
            "summary": {
                "total": total_text.total_requests + total_image.total_requests + total_video.total_requests,
                "success": total_text.success_count + total_image.success_count + total_video.success_count,
                "failure": total_text.failure_count + total_image.failure_count + total_video.failure_count,
                "success_rate": 0.0,
            }
        }

    def get_model_timeline(self, hours: int = 24) -> list[dict]:
        """获取最近 N 小时的模型调用时间序列。

        纯内存实现下，不提供历史时间序列（返回空列表或基于内存实时生成）。
        这里返回近 N 条请求的时间戳（仅当有统计时可用）。
        """
        # 简化：返回总统计摘要
        total = self.get_total_stats()
        return [{
            "timestamp": "",
            "text": total["text"],
            "image": total["image"],
            "video": total["video"],
        }]


# 全局单例
_key_stats_manager: Optional[KeyStatsManager] = None
_stats_lock = __import__('threading').Lock()


def get_key_stats_manager() -> KeyStatsManager:
    """获取全局统计管理器实例。"""
    global _key_stats_manager
    if _key_stats_manager is None:
        with _stats_lock:
            if _key_stats_manager is None:
                _key_stats_manager = KeyStatsManager()
    return _key_stats_manager


# 图片模型名称关键字列表
_IMAGE_MODEL_KEYWORDS = ["image", "img", "dall", "stable", "flux", "midjourney", "mj"]

# 视频模型名称关键字列表
_VIDEO_MODEL_KEYWORDS = ["video", "gen-2", "sora", "kling", "hunyuan", "runway", "luma", "agnes-video"]


def detect_model_type(model: str) -> str:
    """根据模型名称检测模型类型。

    支持的模型类型：
    - 文本模型: agnes-2.0-flash 等
    - 图片模型: agnes-image-2.1-flash, dall-e-3 等
    - 视频模型: agnes-video, sora, kling 等

    通过检查模型名称是否包含预定义的关键字来判断模型类型。
    优先级：video > image > text（默认）
    """
    model_lower = model.lower()

    for keyword in _VIDEO_MODEL_KEYWORDS:
        if keyword in model_lower:
            return "video"

    for keyword in _IMAGE_MODEL_KEYWORDS:
        if keyword in model_lower:
            return "image"

    return "text"
