import threading
import collections
from config import settings

class UrlManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(UrlManager, cls).__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        raw_urls = settings.agnes_base_url.split(',')
        self.urls = [url.strip().rstrip('/') for url in raw_urls if url.strip()]
        if not self.urls:
            self.urls = ["https://apihub.agnes-ai.com"]
        self.history = {url: collections.deque([True] * 100, maxlen=100) for url in self.urls}
        self._history_lock = threading.Lock()

    def get_best_url(self) -> str:
        best_url = None
        max_rate = -1.0
        
        with self._history_lock:
            for url in self.urls:
                hist = self.history[url]
                if not hist:
                    rate = 1.0
                else:
                    rate = sum(hist) / len(hist)
                
                if rate > max_rate:
                    max_rate = rate
                    best_url = url
                    
        return best_url or self.urls[0]

    def record_result(self, url: str, success: bool):
        if url in self.history:
            with self._history_lock:
                self.history[url].append(success)

    def reset_all(self):
        """每日重置：清空所有 URL 的滑动窗口并回填 100 次成功记录。

        重置后所有节点成功率恢复 100%（预热态），路由退化为配置顺序首选，
        与服务刚启动时的初始状态一致。纯内存操作，幂等且可在多 worker 中各自执行。
        """
        with self._history_lock:
            for url in self.urls:
                self.history[url] = collections.deque([True] * 100, maxlen=100)

    def get_health_stats(self) -> list[dict]:
        """获取所有 URL 的健康度统计（最近 100 次滑动窗口）。

        Returns:
            [{url, total, success, failure, success_rate, is_best}]
            success_rate 为百分比数值（0-100），窗口为空时视为 100%。
        """
        stats = []
        rates: list[float] = []
        with self._history_lock:
            for url in self.urls:
                hist = self.history[url]
                total = len(hist)
                success = sum(1 for r in hist if r)
                failure = total - success
                rate = (success / total * 100) if total > 0 else 100.0
                rates.append(rate)
                stats.append({
                    "url": url,
                    "total": total,
                    "success": success,
                    "failure": failure,
                    "success_rate": round(rate, 2),
                })
        # 锁外按选择算法（严格大于，同分取第一个）确定当前最优 URL
        best_url = self.urls[0] if self.urls else None
        max_rate = -1.0
        for url, rate in zip(self.urls, rates):
            if rate > max_rate:
                max_rate = rate
                best_url = url
        for item in stats:
            item["is_best"] = item["url"] == best_url
        return stats

def get_url_manager() -> UrlManager:
    return UrlManager()
