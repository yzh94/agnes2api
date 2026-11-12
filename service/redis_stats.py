"""Redis 分布式统计管理器。

功能：
- 使用 Redis Connection String 连接
- 提供原子 HINCRBY 操作写入统计
- 提供 HGETALL 操作读取统计
- 自动计算成功率等衍生数据

线程安全：是（Redis 操作本身是原子的）
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

logger = logging.getLogger(__name__)

# 北京时间 UTC+8。时间序列标签按此时区生成，与每日重置调度器（stats_scheduler）
# 的口径一致，不依赖容器 TZ 环境变量，确保"凌晨 0 点重置"边界在图表上正确呈现。
BEIJING_TZ = timezone(timedelta(hours=8))

# P1-8: 维护活跃 Key 前缀集合，供 get_all_stats() 使用，避免全量 SCAN
ACTIVE_PREFIXES_KEY = "stats:active_prefixes"

# 请求级统计 key 前缀（stats:reqlevel:{model_type}）。
# 与 Key 维度统计（stats:{key_prefix}:{model_type}，按终局归属 Key 记账）不同，
# 请求级是全局口径：每个用户请求按最终结果只记一次（内部重试后成功即成功），
# 用于衡量用户真实感知成功率。
# 命名落在 stats:*:* 扫描范围内，每日重置自动覆盖。
REQ_LEVEL_KEY_PREFIX = "stats:reqlevel:"


class RedisStatsManager:
    """基于 Redis 的分布式统计管理器。
    
    使用 Redis Hash 存储每个 API Key 的统计数据：
    - stats:{key_prefix}:text → Hash{total, success, failure, last_updated}
    - stats:{key_prefix}:image → Hash{total, success, failure, last_updated}
    
    示例数据结构：
        HSET stats:abcd****:text total 100 success 95 failure 5
        HSET stats:abcd****:text last_updated 1720000000
    """
    
    def __init__(self, redis_conn_string: str):
        """初始化 Redis 统计管理器。
        
        Args:
            redis_conn_string: Redis 连接字符串
                             格式: redis://[:password@]host:port/db
                             示例: redis://default:PASSWORD@HOST:PORT/1
        """
        import redis as redis_lib
        self._redis_lib = redis_lib
        self._redis_conn_string = redis_conn_string
        self._redis: Optional[redis_lib.Redis] = None
        self._initialize()
    
    def _initialize(self):
        """建立 Redis 连接。"""
        try:
            self._redis = self._redis_lib.from_url(
                self._redis_conn_string,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # 测试连接
            self._redis.ping()
            logger.info("Redis 统计管理器连接成功")
        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            raise
    
    @property
    def redis(self) -> Any:
        """获取 Redis 连接，如果断开则尝试重连。"""
        if self._redis is None:
            self._initialize()
        try:
            if self._redis:
                self._redis.ping()
        except Exception:
            logger.warning("Redis 连接断开，尝试重连...")
            self._initialize()
        return self._redis
    
    def _make_stat_key(self, key_prefix: str, model_type: str) -> str:
        """构建 Redis Hash 的 key。
        
        Args:
            key_prefix: API Key 前缀（如 "abcd****"）
            model_type: 模型类型（"text" 或 "image"）
            
        Returns:
            Redis key，如 "stats:abcd****:text"
        """
        return f"stats:{key_prefix}:{model_type}"
    
    def init_key_stats(self, key_prefix: str):
        """初始化 Key 的统计 Hash（用于页面展示所有 Key）。
        
        如果 Hash 已存在则不覆盖，只在首次初始化时创建。
        
        Args:
            key_prefix: API Key 前缀
        """
        stat_key_text = self._make_stat_key(key_prefix, "text")
        stat_key_image = self._make_stat_key(key_prefix, "image")
        stat_key_video = self._make_stat_key(key_prefix, "video")
        
        # 使用 HSETNX 确保不覆盖已有数据
        pipe = self.redis.pipeline(transaction=True)
        pipe.hsetnx(stat_key_text, "total", 0)
        pipe.hsetnx(stat_key_text, "success", 0)
        pipe.hsetnx(stat_key_text, "failure", 0)
        pipe.hsetnx(stat_key_image, "total", 0)
        pipe.hsetnx(stat_key_image, "success", 0)
        pipe.hsetnx(stat_key_image, "failure", 0)
        pipe.hsetnx(stat_key_video, "total", 0)
        pipe.hsetnx(stat_key_video, "success", 0)
        pipe.hsetnx(stat_key_video, "failure", 0)
        pipe.execute()
        logger.info(f"初始化 Key 统计: {key_prefix}")
    
    def incr_stats(self, key_prefix: str, model_type: str, success: bool):
        """原子性地增加统计计数。

        使用 Redis HINCRBY 命令，保证原子性。
        同时写入当前小时桶用于时间序列图表。

        Args:
            key_prefix: API Key 前缀（如 "abcd****"）
            model_type: 模型类型（"text"、"image" 或 "video"）
            success: 请求是否成功
        """
        stat_key = self._make_stat_key(key_prefix, model_type)
        now = str(int(time.time()))

        pipe = self.redis.pipeline(transaction=True)
        pipe.hincrby(stat_key, "total", 1)
        if success:
            pipe.hincrby(stat_key, "success", 1)
        else:
            pipe.hincrby(stat_key, "failure", 1)
        pipe.hset(stat_key, "last_updated", now)
        pipe.sadd(ACTIVE_PREFIXES_KEY, key_prefix)  # P1-8: 维护活跃前缀集合
        pipe.execute()

        # 写入时间序列桶
        self._incr_ts(model_type, success)

    def _incr_ts(self, model_type: str, success: bool):
        """写入时间序列桶：小时桶（7 天回看）+ 30 秒桶（最近 30 分钟趋势图，1 小时过期自清理）。"""
        now = int(time.time())
        hour_key = f"stats_ts:{model_type}:{now // 3600}"
        sub_key = f"stats_ts_min:{model_type}:{now // 30}"
        pipe = self.redis.pipeline(transaction=True)
        pipe.hincrby(hour_key, "total", 1)
        if success:
            pipe.hincrby(hour_key, "success", 1)
        else:
            pipe.hincrby(hour_key, "failure", 1)
        pipe.expire(hour_key, 86400 * 7)
        pipe.hincrby(sub_key, "total", 1)
        if success:
            pipe.hincrby(sub_key, "success", 1)
        else:
            pipe.hincrby(sub_key, "failure", 1)
        pipe.expire(sub_key, 3600)
        pipe.execute()

    def incr_request_level(self, model_type: str, success: bool):
        """请求级统计：每个用户请求只记一次最终结果（重试后成功即成功）。

        Args:
            model_type: 模型类型（"text"、"image" 或 "video"）
            success: 请求最终结果是否成功
        """
        stat_key = f"{REQ_LEVEL_KEY_PREFIX}{model_type}"
        pipe = self.redis.pipeline(transaction=True)
        pipe.hincrby(stat_key, "total", 1)
        if success:
            pipe.hincrby(stat_key, "success", 1)
        else:
            pipe.hincrby(stat_key, "failure", 1)
        pipe.execute()

    def get_request_level_stats(self) -> dict:
        """获取请求级成功率统计（按模型类型 + 汇总）。"""
        def calc_rate(total, success):
            return round((success / total * 100), 2) if total > 0 else 0.0

        result = {}
        total_all = success_all = failure_all = 0
        for mt in ("text", "image", "video"):
            data = self.redis.hgetall(f"{REQ_LEVEL_KEY_PREFIX}{mt}")
            total = int(data.get("total", 0) or 0)
            success = int(data.get("success", 0) or 0)
            failure = int(data.get("failure", 0) or 0)
            result[mt] = {
                "total": total,
                "success": success,
                "failure": failure,
                "success_rate": calc_rate(total, success),
            }
            total_all += total
            success_all += success
            failure_all += failure
        result["summary"] = {
            "total": total_all,
            "success": success_all,
            "failure": failure_all,
            "success_rate": calc_rate(total_all, success_all),
        }
        return result
    
    def get_stat(self, key_prefix: str, model_type: str) -> dict[str, int]:
        """获取单个 Key + 模型类型的统计数据。
        
        Args:
            key_prefix: API Key 前缀
            model_type: 模型类型（"text"、"image" 或 "video"）
            
        Returns:
            {total: 0, success: 0, failure: 0, last_updated: 0}
        """
        stat_key = self._make_stat_key(key_prefix, model_type)
        data = self.redis.hgetall(stat_key)
        
        return {
            "total": int(data.get("total", 0)),
            "success": int(data.get("success", 0)),
            "failure": int(data.get("failure", 0)),
            "last_updated": int(data.get("last_updated", 0)),
        }
    
    def get_key_stats(self, key_prefix: str) -> dict | None:
        """获取单个 API Key 的完整统计（聚合 text + image + video）。
        
        Args:
            key_prefix: API Key 前缀
            
        Returns:
            {
                "key_prefix": "abcd****",
                "text": {total, success, failure, success_rate},
                "image": {total, success, failure, success_rate},
                "video": {total, success, failure, success_rate},
                "summary": {total, success, failure, success_rate}
            } 或 None（如果 Key 未初始化）
        
        注意：如果后端返回的数据中没有 video 字段（旧数据），
        renderModelStats 会默认使用 {total: 0, success: 0, failure: 0, success_rate: 0}
        """
        text_data = self.get_stat(key_prefix, "text")
        image_data = self.get_stat(key_prefix, "image")
        video_data = self.get_stat(key_prefix, "video")
        
        # 检查 Key 是否在 Redis 中存在（通过检查 Hash 是否有字段）
        stat_key_text = self._make_stat_key(key_prefix, "text")
        if self.redis.exists(stat_key_text) == 0:
            return None
        
        text_success_rate = (
            round((text_data["success"] / text_data["total"] * 100), 2)
            if text_data["total"] > 0 else 0.0
        )
        image_success_rate = (
            round((image_data["success"] / image_data["total"] * 100), 2)
            if image_data["total"] > 0 else 0.0
        )
        video_success_rate = (
            round((video_data["success"] / video_data["total"] * 100), 2)
            if video_data["total"] > 0 else 0.0
        )
        
        total_all = text_data["total"] + image_data["total"] + video_data["total"]
        success_all = text_data["success"] + image_data["success"] + video_data["success"]
        failure_all = text_data["failure"] + image_data["failure"] + video_data["failure"]
        success_rate_all = (
            round((success_all / total_all * 100), 2) if total_all > 0 else 0.0
        )
        
        return {
            "key_prefix": key_prefix,
            "text": {
                "total": text_data["total"],
                "success": text_data["success"],
                "failure": text_data["failure"],
                "success_rate": text_success_rate,
            },
            "image": {
                "total": image_data["total"],
                "success": image_data["success"],
                "failure": image_data["failure"],
                "success_rate": image_success_rate,
            },
            "video": {
                "total": video_data["total"],
                "success": video_data["success"],
                "failure": video_data["failure"],
                "success_rate": video_success_rate,
            },
            "summary": {
                "total": total_all,
                "success": success_all,
                "failure": failure_all,
                "success_rate": success_rate_all,
            },
        }
    
    def get_all_stats(self) -> list[dict]:
        """获取所有 API Key 的统计信息。

        使用活跃前缀集合（stats:active_prefixes）迭代，避免全量 SCAN。
        集合在每次 incr_stats 时自动维护，reset_stats 时清空。

        Returns:
            所有 Key 的统计列表
        """
        raw = self.redis.smembers(ACTIVE_PREFIXES_KEY)
        # smembers 返回 bytes 或 str，视 decode_responses 而定
        keys_prefixes = {
            p.decode("utf-8") if isinstance(p, bytes) else p
            for p in raw
        }

        result = []
        for prefix in sorted(keys_prefixes):
            stats = self.get_key_stats(prefix)
            if stats:
                result.append(stats)

        return result
    
    def get_total_stats(self) -> dict:
        """获取全局汇总统计。
        
        Returns:
            {
                "text": {total, success, failure, success_rate},
                "image": {total, success, failure, success_rate},
                "video": {total, success, failure, success_rate},
                "summary": {total, success, failure, success_rate}
            }
        """
        total_text = {"total": 0, "success": 0, "failure": 0}
        total_image = {"total": 0, "success": 0, "failure": 0}
        total_video = {"total": 0, "success": 0, "failure": 0}
        
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="stats:*:*", count=100)
            for key in keys:
                model_type = key.split(":")[-1]  # "text", "image" 或 "video"
                if model_type not in {"text", "image", "video"}:
                    continue

                data = self.redis.hgetall(key)

                t = int(data.get("total", 0))
                s = int(data.get("success", 0))
                f = int(data.get("failure", 0))
                
                if model_type == "text":
                    total_text["total"] += t
                    total_text["success"] += s
                    total_text["failure"] += f
                elif model_type == "image":
                    total_image["total"] += t
                    total_image["success"] += s
                    total_image["failure"] += f
                elif model_type == "video":
                    total_video["total"] += t
                    total_video["success"] += s
                    total_video["failure"] += f
            
            if cursor == 0:
                break
        
        text_success_rate = (
            round((total_text["success"] / total_text["total"] * 100), 2)
            if total_text["total"] > 0 else 0.0
        )
        image_success_rate = (
            round((total_image["success"] / total_image["total"] * 100), 2)
            if total_image["total"] > 0 else 0.0
        )
        video_success_rate = (
            round((total_video["success"] / total_video["total"] * 100), 2)
            if total_video["total"] > 0 else 0.0
        )
        
        total_all = total_text["total"] + total_image["total"] + total_video["total"]
        success_all = total_text["success"] + total_image["success"] + total_video["success"]
        failure_all = total_text["failure"] + total_image["failure"] + total_video["failure"]
        success_rate_all = (
            round((success_all / total_all * 100), 2) if total_all > 0 else 0.0
        )
        
        return {
            "text": {
                "total": total_text["total"],
                "success": total_text["success"],
                "failure": total_text["failure"],
                "success_rate": text_success_rate,
            },
            "image": {
                "total": total_image["total"],
                "success": total_image["success"],
                "failure": total_image["failure"],
                "success_rate": image_success_rate,
            },
            "video": {
                "total": total_video["total"],
                "success": total_video["success"],
                "failure": total_video["failure"],
                "success_rate": video_success_rate,
            },
            "summary": {
                "total": total_all,
                "success": success_all,
                "failure": failure_all,
                "success_rate": success_rate_all,
            },
        }
    
    def reset_stats(self, key_prefix: Optional[str] = None, model_type: Optional[str] = None):
        """重置统计数据。

        使用 SCAN（非阻塞）遍历匹配的 key 并删除，避免 KEYS 在 key 数量
        增长时阻塞 Redis。

        Args:
            key_prefix: 如果指定，只重置该 Key 的数据
            model_type: 如果指定，只重置该模型类型的数据
        """
        if key_prefix:
            if model_type:
                stat_key = self._make_stat_key(key_prefix, model_type)
                self.redis.delete(stat_key)
                self.redis.srem(ACTIVE_PREFIXES_KEY, key_prefix)  # P1-8: 清理活跃前缀
                logger.info(f"重置统计: {stat_key}")
            else:
                pattern = f"stats:{key_prefix}:*"
                deleted = self._scan_delete(pattern)
                self.redis.srem(ACTIVE_PREFIXES_KEY, key_prefix)  # P1-8: 清理活跃前缀
                logger.info(f"重置统计: {pattern} (删除 {deleted} 个)")
        else:
            deleted = self._scan_delete("stats:*:*")
            logger.info(f"重置所有统计: stats:*:* (删除 {deleted} 个)")
            self.redis.delete(ACTIVE_PREFIXES_KEY)  # P1-8: 清空活跃前缀集合

    def _scan_delete(self, pattern: str) -> int:
        """SCAN 遍历 pattern 并删除所有匹配的 key，返回删除数量。

        用 SCAN（非阻塞）而非 KEYS，避免 key 量增长时阻塞 Redis；
        删除用 UNLINK（Redis 4.0+）在后台线程释放内存，避免每日重置清空
        大批 stats:* / user_stats:* 时阻塞主线程。
        """
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                self.redis.unlink(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted

    def _make_user_stat_key(self, user_id: int, model_type: str) -> str:
        """构建用户统计 Hash 的 key。

        Args:
            user_id: 用户 ID
            model_type: 模型类型

        Returns:
            Redis key，如 "user_stats:1:text"
        """
        return f"user_stats:{user_id}:{model_type}"

    def incr_user_stats(self, user_id: int, model_type: str, success: bool):
        """原子性地增加用户维度的统计计数。

        Args:
            user_id: 用户 ID
            model_type: 模型类型
            success: 请求是否成功
        """
        stat_key = self._make_user_stat_key(user_id, model_type)
        pipe = self.redis.pipeline(transaction=True)
        pipe.hincrby(stat_key, "total", 1)
        if success:
            pipe.hincrby(stat_key, "success", 1)
        else:
            pipe.hincrby(stat_key, "failure", 1)
        pipe.execute()

    def get_user_stats(self, user_id: int) -> dict:
        """获取单个用户的完整统计（聚合 text + image + video）。

        Args:
            user_id: 用户 ID

        Returns:
            {
                "user_id": 1,
                "text": {total, success, failure, success_rate},
                "image": {total, success, failure, success_rate},
                "video": {total, success, failure, success_rate},
                "summary": {total, success, failure, success_rate}
            }
        """
        text_data = self._get_user_model_stat(user_id, "text")
        image_data = self._get_user_model_stat(user_id, "image")
        video_data = self._get_user_model_stat(user_id, "video")

        def calc_rate(total, success):
            return round((success / total * 100), 2) if total > 0 else 0.0

        total_all = text_data["total"] + image_data["total"] + video_data["total"]
        success_all = text_data["success"] + image_data["success"] + video_data["success"]
        failure_all = text_data["failure"] + image_data["failure"] + video_data["failure"]

        return {
            "user_id": user_id,
            "text": {**text_data, "success_rate": calc_rate(text_data["total"], text_data["success"])},
            "image": {**image_data, "success_rate": calc_rate(image_data["total"], image_data["success"])},
            "video": {**video_data, "success_rate": calc_rate(video_data["total"], video_data["success"])},
            "summary": {
                "total": total_all,
                "success": success_all,
                "failure": failure_all,
                "success_rate": calc_rate(total_all, success_all),
            },
        }

    def _get_user_model_stat(self, user_id: int, model_type: str) -> dict[str, int]:
        """获取单个用户 + 模型类型的统计数据。"""
        stat_key = self._make_user_stat_key(user_id, model_type)
        data = self.redis.hgetall(stat_key)
        return {
            "total": int(data.get("total", 0)),
            "success": int(data.get("success", 0)),
            "failure": int(data.get("failure", 0)),
        }

    def get_all_user_stats(self) -> list[dict]:
        """获取所有用户的统计列表。

        使用 SCAN 遍历所有 user_stats:*:* 键（覆盖 text/image/video 三类），
        提取 user_id 并去重，聚合每个用户的三个模型。

        注意：不能只扫 user_stats:*:text，否则只调用过 image/video 模型、
        从未产生 text 统计的用户（例如重置后新注册、且只发图像/视频请求的用户）
        会被漏掉，导致管理员“用户请求次数排名”缺失该用户。
        """
        user_ids = set()
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="user_stats:*:*", count=100)
            for key in keys:
                parts = key.split(":")
                if len(parts) >= 3:
                    try:
                        user_ids.add(int(parts[1]))
                    except ValueError:
                        pass
            if cursor == 0:
                break

        result = []
        for uid in sorted(user_ids):
            stats = self.get_user_stats(uid)
            if stats["summary"]["total"] > 0:
                result.append(stats)
        return result

    def reset_user_stats(self, user_id: Optional[int] = None):
        """重置用户统计。

        Args:
            user_id: 如果指定，只重置该用户的统计；否则重置全部
        """
        if user_id is not None:
            pattern = f"user_stats:{user_id}:*"
            deleted = self._scan_delete(pattern)
            logger.info(f"重置用户统计: user_id={user_id} (删除 {deleted} 个)")
        else:
            deleted = self._scan_delete("user_stats:*")
            logger.info(f"重置所有用户统计: user_stats:* (删除 {deleted} 个)")

    def get_model_timeline(self, minutes: int = 30) -> list[dict]:
        """获取最近 N 分钟的模型调用时间序列（30 秒粒度）。

        供前端"最近 30 分钟"成功率趋势图使用：30 秒桶 × N 分钟窗口 = N*2 个数据点，
        一次 pipeline 批量读取（stats_ts_min:{type}:{epoch//30}，由 _incr_ts 写入，
        1 小时过期）。

        空数据桶的处理：某桶无请求（total==0）时 success_rate 返回 None，
        前端对该点断开连线，避免把"无请求"误读为 100% 或 0%；
        total/success/failure 仍按真实计数返回（0）。

        Args:
            minutes: 回溯的分钟数，默认 30

        Returns:
            [{timestamp: "2026-07-21T10:05:30", text: {...}, image: {...}, video: {...}}, ...]
        """
        now_sub = int(time.time()) // 30
        points = minutes * 2
        types = ("text", "image", "video")

        pipe = self.redis.pipeline(transaction=False)
        for p in range(points - 1, -1, -1):
            bucket = now_sub - p
            for mt in types:
                pipe.hgetall(f"stats_ts_min:{mt}:{bucket}")
        results = pipe.execute()

        result = []
        idx = 0
        for p in range(points - 1, -1, -1):
            bucket = now_sub - p
            data = {}
            for mt in types:
                d = results[idx] or {}
                idx += 1
                total = int(d.get("total", 0))
                success = int(d.get("success", 0))
                failure = int(d.get("failure", 0))
                rate = round((success / total * 100), 2) if total > 0 else None
                data[mt] = {"total": total, "success": success, "failure": failure, "success_rate": rate}

            ts_dt = datetime.fromtimestamp(bucket * 30, tz=BEIJING_TZ)
            result.append({
                "timestamp": ts_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "text": data["text"],
                "image": data["image"],
                "video": data["video"],
            })

        return result