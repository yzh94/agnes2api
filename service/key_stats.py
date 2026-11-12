"""API Key 请求统计管理器 - 基于 Redis 的分布式统计。

功能：
- 跟踪文本(text)、图片(image)模型的成功/失败计数
- 支持按模型类型查询统计信息
- 所有数据存储在 Redis，支持多 Worker 分布式部署

工作流程：
  1. 程序启动 → 初始化 Redis 连接
  2. 运行时 → 所有统计更新通过 HINCRBY 写入 Redis
  3. 前端读取 → 从 Redis 实时读取最新数据
"""

import logging
from typing import Optional

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
        # 按模型类型分类的统计
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
            # 短 key 显示完整内容并添加后缀以作区分
            return key + "***"


class KeyStatsManager:
    """API Key 统计管理器 - 基于 Redis。

    所有统计操作通过 Redis 完成，支持多 Worker 分布式部署。

    属性：
        redis_stats: RedisStatsManager 实例
    """

    def __init__(self, redis_stats=None):
        """初始化统计管理器。

        Args:
            redis_stats: RedisStatsManager 实例，如果为 None 则从配置创建
        """
        self._redis_stats = redis_stats
        self._registered_keys: list[str] = []
        self._fallback_stats: dict[str, dict[str, ModelTypeStats]] = {}  # key_prefix -> {model_type -> ModelTypeStats}

        if self._redis_stats is None:
            from config import settings
            redis_conn_string = settings.redis_conn_string
            if redis_conn_string:
                from service.redis_stats import RedisStatsManager
                self._redis_stats = RedisStatsManager(redis_conn_string)
                logger.info("Redis 统计管理器已初始化")
            else:
                logger.warning("Redis 连接字符串未配置，统计功能将不可用，使用内存降级方案")
    
    def register_key(self, key: str):
        """注册一个新的 API Key 统计。

        在 Redis 中初始化该 Key 的统计 Hash（如果不存在），
        确保页面启动时就能展示所有 Key。

        Args:
            key: API Key
        """
        if key not in self._registered_keys:
            self._registered_keys.append(key)
            key_prefix = APIKeyStats._compute_key_prefix(key)
            logger.info(f"注册 API Key 统计: {key_prefix}")

            # 在 Redis 中初始化该 Key 的统计 Hash
            if self._redis_stats is not None:
                try:
                    self._redis_stats.init_key_stats(key_prefix)
                except Exception as e:
                    logger.warning(f"初始化 Key 统计失败: {key_prefix} | {e}")
            else:
                # 降级：在内存中初始化
                if key_prefix not in self._fallback_stats:
                    self._fallback_stats[key_prefix] = {
                        "text": ModelTypeStats(),
                        "image": ModelTypeStats(),
                        "video": ModelTypeStats(),
                    }

    def unregister_key(self, key: str):
        """注销一个 API Key，清理其内存注册表、降级统计与 Redis 统计哈希。

        用于上游 Key 被硬删除时，避免看板残留"未知/已删除渠道"的统计行。
        软禁用不应调用此方法（需保留统计，看板显示 disabled 状态）。

        注意：统计按 key[:8]+"***" 脱敏前缀聚合，若两个 Key 前 8 字符相同，
        会连带清理另一个 Key 的统计（既有前缀碰撞限制）。

        Args:
            key: API Key
        """
        key_prefix = APIKeyStats._compute_key_prefix(key)
        if key in self._registered_keys:
            self._registered_keys.remove(key)
        self._fallback_stats.pop(key_prefix, None)

        if self._redis_stats is not None:
            try:
                self._redis_stats.reset_stats(key_prefix=key_prefix)
            except Exception as e:
                logger.warning(f"清理 Key 统计失败: {key_prefix} | {e}")
        logger.info(f"注销 API Key 统计: {key_prefix}")
    
    def record_request(self, key: str, model_type: str, success: bool, client_key_id: int = None, tokens: int = 0, cost: float = 0.0, user_id: int = 0):
        """按归属 Key 记录一次终局结果（Key 维度 + 用户维度），并异步写 UsageLog。

        请求链路应通过 record_final_outcome 调用本方法（一次请求仅落账一次），
        中间重试尝试不得直接调用，否则会重新引入多次计数。

        Args:
            key: API Key
            model_type: 模型类型 ("text", "image", "video")
            success: 请求是否成功
            client_key_id: 客户端密钥 ID
            tokens: token 数
            cost: 费用
            user_id: 用户 ID（0 = master key，不计入用户统计）
        """
        key_prefix = APIKeyStats._compute_key_prefix(key)

        # 降级：Redis 不可用时使用内存统计
        if self._redis_stats is None:
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
            return

        self._redis_stats.incr_stats(key_prefix, model_type, success)

        # 用户维度统计（user_id=0 为 master key，跳过）
        if user_id and user_id > 0:
            try:
                self._redis_stats.incr_user_stats(user_id, model_type, success)
            except Exception:
                pass  # 用户统计失败不影响主流程

        # 异步写入数据库使用日志
        if client_key_id is not None:
            import asyncio
            from models.database import AsyncSessionLocal, UsageLog, ClientKey
            from sqlalchemy import select, update

            effective_user_id = user_id if user_id > 0 else 1

            async def _write_usage_log():
                try:
                    async with AsyncSessionLocal() as session:
                        # 插入日志
                        usage = UsageLog(
                            client_key_id=client_key_id,
                            user_id=effective_user_id,
                            upstream_key=key_prefix,
                            model=model_type,
                            tokens=tokens,
                            cost=cost
                        )
                        session.add(usage)
                        
                        # 扣减配额 (if quota > 0)
                        if cost > 0:
                            result = await session.execute(select(ClientKey).where(ClientKey.id == client_key_id))
                            ck = result.scalars().first()
                            if ck:
                                ck.used_quota += cost
                        await session.commit()
                except Exception as e:
                    logger.error(f"Failed to write usage log to db: {e}")
            
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_write_usage_log())
            except RuntimeError:
                pass # not running in async loop

    
    def record_final_outcome(self, model_type: str, success: bool, key: Optional[str] = None, user_id: int = 0, client_key_id: int = None, tokens: int = 0, cost: float = 0.0):
        """终局一次性记账：一次用户请求只按最终结果记一条成功率数据。

        无论内部换 Key 重试多少次，中间尝试均不产生成功率计数：
        - 最终成功 → 只记一次成功，归属实际成功的 Key
        - 最终失败 → 只记一次失败，归属最后一次尝试的 Key
        - key 为 None（未尝试任何 Key 即失败，如 Key 池耗尽）→ 只记请求级

        同时写入：Key 维度统计（含时间线）、请求级统计、用户维度统计。
        中间失败的观测由 Key Pool 滑动窗口与失败原因分类计数独立承担。

        Args:
            model_type: 模型类型 ("text", "image", "video")
            success: 请求最终结果是否成功
            key: 归属的 API Key；None 表示未尝试任何 Key
            user_id: 用户 ID（0 = master key，不计入用户统计）
            client_key_id: 客户端密钥 ID
            tokens: token 数
            cost: 费用
        """
        if key is not None:
            self.record_request(key, model_type, success, client_key_id=client_key_id, tokens=tokens, cost=cost, user_id=user_id)
        self.record_request_level(model_type, success)

    def record_request_level(self, model_type: str, success: bool):
        """请求级统计：每个用户请求只记一次最终结果（重试后成功即成功）。

        Args:
            model_type: 模型类型 ("text", "image", "video")
            success: 请求最终结果是否成功
        """
        if self._redis_stats is None:
            # 降级：内存统计
            if not hasattr(self, "_req_level_fallback"):
                self._req_level_fallback = {}
            if model_type not in self._req_level_fallback:
                self._req_level_fallback[model_type] = ModelTypeStats()
            stats = self._req_level_fallback[model_type]
            stats.total_requests += 1
            if success:
                stats.success_count += 1
            else:
                stats.failure_count += 1
            return
        self._redis_stats.incr_request_level(model_type, success)

    def get_request_level_stats(self) -> dict:
        """获取请求级成功率统计（按模型类型 + 汇总）。"""
        if self._redis_stats is not None:
            return self._redis_stats.get_request_level_stats()

        # 降级：从内存中读取
        fallback = getattr(self, "_req_level_fallback", {})
        result = {}
        total_all = success_all = failure_all = 0
        for mt in ("text", "image", "video"):
            s = fallback.get(mt, ModelTypeStats())
            result[mt] = s.to_dict()
            total_all += s.total_requests
            success_all += s.success_count
            failure_all += s.failure_count
        result["summary"] = {
            "total": total_all,
            "success": success_all,
            "failure": failure_all,
            "success_rate": round((success_all / total_all * 100), 2) if total_all > 0 else 0.0,
        }
        return result

    def get_all_stats(self) -> list[dict]:
        """获取所有 API Key 的统计信息。

        Returns:
            所有 Key 的统计列表
        """
        if self._redis_stats is not None:
            return self._redis_stats.get_all_stats()

        # 降级：从内存中读取
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

    def get_user_stats(self, user_id: int) -> dict:
        """获取单个用户的统计信息。"""
        if self._redis_stats is not None:
            return self._redis_stats.get_user_stats(user_id)

        # 降级：从内存中读取
        stats_dict = self._fallback_stats.get(APIKeyStats._compute_key_prefix(""))
        if not stats_dict:
            return {"user_id": user_id, "text": {}, "image": {}, "video": {}, "summary": {}}
        text_s = stats_dict.get("text", ModelTypeStats())
        image_s = stats_dict.get("image", ModelTypeStats())
        video_s = stats_dict.get("video", ModelTypeStats())
        total_all = text_s.total_requests + image_s.total_requests + video_s.total_requests
        success_all = text_s.success_count + image_s.success_count + video_s.success_count
        failure_all = text_s.failure_count + image_s.failure_count + video_s.failure_count
        return {
            "user_id": user_id,
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

    def get_all_user_stats(self) -> list[dict]:
        """获取所有用户的统计列表。"""
        if self._redis_stats is not None:
            return self._redis_stats.get_all_user_stats()
        return []
    
    def get_key_stats(self, key: str) -> Optional[dict]:
        """获取指定 API Key 的统计信息。

        Args:
            key: API Key

        Returns:
            统计摘要或 None
        """
        key_prefix = APIKeyStats._compute_key_prefix(key)

        if self._redis_stats is not None:
            return self._redis_stats.get_key_stats(key_prefix)

        # 降级：从内存中读取
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
        """获取所有 Key 的总体统计。

        Returns:
            全局汇总统计
        """
        if self._redis_stats is not None:
            return self._redis_stats.get_total_stats()

        # 降级：从内存中汇总
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
        summary_total = total_text.total_requests + total_image.total_requests + total_video.total_requests
        summary_success = total_text.success_count + total_image.success_count + total_video.success_count
        summary_failure = total_text.failure_count + total_image.failure_count + total_video.failure_count
        return {
            "text": total_text.to_dict(),
            "image": total_image.to_dict(),
            "video": total_video.to_dict(),
            "summary": {
                "total": summary_total,
                "success": summary_success,
                "failure": summary_failure,
                "success_rate": round((summary_success / summary_total * 100), 2) if summary_total > 0 else 0.0,
            }
        }

    def get_model_timeline(self, minutes: int = 30) -> list[dict]:
        """获取最近 N 分钟的模型调用时间序列。"""
        if self._redis_stats is not None:
            return self._redis_stats.get_model_timeline(minutes)
        return []
    
    def reset_stats(self, key_prefix: Optional[str] = None, model_type: Optional[str] = None, user_id: Optional[int] = None):
        """重置统计数据。

        Args:
            key_prefix: 如果指定，只重置该 Key 的数据
            model_type: 如果指定，只重置该模型类型的数据
            user_id: 如果指定，只重置该用户的统计
        """
        if self._redis_stats is None:
            return
        if user_id is not None:
            self._redis_stats.reset_user_stats(user_id)
        else:
            self._redis_stats.reset_stats(key_prefix, model_type)


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
    
    Args:
        model: 模型名称
        
    Returns:
        "text", "image" 或 "video"
    """
    model_lower = model.lower()
    
    # 优先检测视频模型
    for keyword in _VIDEO_MODEL_KEYWORDS:
        if keyword in model_lower:
            return "video"
    
    # 检测图片模型
    for keyword in _IMAGE_MODEL_KEYWORDS:
        if keyword in model_lower:
            return "image"
    
    # 默认为文本模型
    return "text"
