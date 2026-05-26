from datetime import datetime
import httpx
from .base import Collector
from ..models import Post
from ..config import settings


class XCollector(Collector):
    """X (Twitter) collector.

    兩種模式:
    1. 官方 API v2 (預設,需 X_BEARER_TOKEN,Basic tier 起 $200/月可關鍵字搜尋)
    2. twscrape 爬蟲 (X_USE_SCRAPER=true,需登入 cookies)
    """
    platform = "x"

    SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        if settings.x_use_scraper:
            return self._search_scraper(keyword, limit)
        return self._search_api(keyword, limit)

    def _search_api(self, keyword: str, limit: int) -> list[Post]:
        if not settings.x_bearer_token:
            print("[x] 未設定 X_BEARER_TOKEN,跳過。")
            return []
        headers = {"Authorization": f"Bearer {settings.x_bearer_token}"}
        params = {
            "query": f"{keyword} -is:retweet lang:zh",
            "max_results": min(max(limit, 10), 100),
            "tweet.fields": "created_at,public_metrics,author_id",
        }
        posts: list[Post] = []
        try:
            r = httpx.get(self.SEARCH_URL, headers=headers, params=params, timeout=20)
            if r.status_code != 200:
                print(f"[x] API 回應 {r.status_code}: {r.text[:200]}")
                return []
            for t in r.json().get("data", []):
                m = t.get("public_metrics", {})
                posts.append(Post(
                    platform=self.platform,
                    post_id=t["id"],
                    author=str(t.get("author_id", "")),
                    content=t.get("text", ""),
                    url=f"https://x.com/i/web/status/{t['id']}",
                    created_at=datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")),
                    likes=m.get("like_count", 0),
                    comments=m.get("reply_count", 0),
                    shares=m.get("retweet_count", 0),
                    keyword=keyword,
                    raw=t,
                ))
        except Exception as e:
            print(f"[x] API 失敗: {e}")
        return posts

    def _search_scraper(self, keyword: str, limit: int) -> list[Post]:
        try:
            import asyncio
            from twscrape import API  # type: ignore
        except ImportError:
            raise RuntimeError("未安裝 twscrape,執行: pip install twscrape")

        async def _run():
            api = API()
            out: list[Post] = []
            async for t in api.search(keyword, limit=limit):
                out.append(Post(
                    platform=self.platform,
                    post_id=str(t.id),
                    author=t.user.username if t.user else "",
                    content=t.rawContent or "",
                    url=t.url or "",
                    created_at=t.date or datetime.utcnow(),
                    likes=t.likeCount or 0,
                    comments=t.replyCount or 0,
                    shares=t.retweetCount or 0,
                    keyword=keyword,
                ))
            return out

        return asyncio.run(_run())
