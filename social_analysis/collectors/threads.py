from datetime import datetime
import httpx
from .base import Collector
from ..models import Post
from ..config import settings


class ThreadsCollector(Collector):
    """Threads 沒有公開的關鍵字搜尋 API。

    這裡實作一個簡化的搜尋 endpoint 呼叫(www.threads.net 的 internal API),
    需要登入 cookie。若不可用會 fallback 回空陣列並印警告。

    生產環境建議改用第三方代理服務(Apify / RapidAPI 上的 Threads scraper)。
    """
    platform = "threads"

    SEARCH_URL = "https://www.threads.net/api/graphql"

    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        if not settings.threads_cookie:
            print("[threads] 未設定 THREADS_COOKIE,跳過。")
            return []

        # 注意:Threads 的內部 GraphQL doc_id 會頻繁更動,此處僅示意。
        # 實際使用前需從瀏覽器 devtools 抓取最新的 doc_id 與 variables。
        headers = {
            "Cookie": settings.threads_cookie,
            "User-Agent": "Mozilla/5.0",
            "X-IG-App-ID": "238260118697367",
        }
        posts: list[Post] = []
        try:
            with httpx.Client(timeout=20, headers=headers) as client:
                # 此處留空骨架,實際 payload 需依當下 Threads web 端逆向取得
                r = client.post(self.SEARCH_URL, data={
                    "q": keyword,
                    "count": limit,
                })
                if r.status_code != 200:
                    print(f"[threads] 回應 {r.status_code},關鍵字搜尋目前未實作完整。")
                    return []
                # TODO: parse response.json() into Post
        except Exception as e:
            print(f"[threads] 抓取失敗: {e}")
        return posts
