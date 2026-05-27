import json
import re
from datetime import datetime
from urllib.parse import unquote

import httpx

from .base import Collector
from ..models import Post
from ..config import settings


class ThreadsCollector(Collector):
    """Threads 搜尋 — 解析 SSR HTML 中的 thread_items JSON。

    認證方式：在 .env 設定下列 Threads cookie（從 threads.com DevTools 複製）：
      THREADS_SESSIONID   — sessionid (threads.com domain)
      THREADS_CSRFTOKEN   — csrftoken
      THREADS_MID         — mid
      THREADS_DS_USER_ID  — ds_user_id

    每次請求約可取得 20 篇貼文（SSR 所帶的數量）。
    """

    platform = "threads"
    _BASE = "https://www.threads.com"
    _SEARCH_PATH = "/search"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def _make_client(self) -> httpx.Client:
        if not settings.threads_sessionid:
            raise RuntimeError(
                "未設定 THREADS_SESSIONID。\n"
                "請在 Chrome 開啟 threads.com，按 F12 > Application > Cookies，\n"
                "複製 sessionid 的值並填入 .env: THREADS_SESSIONID=<值>"
            )
        cookies = {
            "sessionid": unquote(settings.threads_sessionid),
        }
        if settings.threads_csrftoken:
            cookies["csrftoken"] = settings.threads_csrftoken
        if settings.threads_mid:
            cookies["mid"] = settings.threads_mid
        if settings.threads_ds_user_id:
            cookies["ds_user_id"] = settings.threads_ds_user_id

        return httpx.Client(
            base_url=self._BASE,
            cookies=cookies,
            headers={
                "User-Agent": self._UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
                "Referer": "https://www.threads.com/",
            },
            follow_redirects=True,
            timeout=20,
        )

    @staticmethod
    def _find_thread_items(obj: object, results: list | None = None) -> list:
        """Recursively collect all thread_items arrays from a nested JSON object."""
        if results is None:
            results = []
        if isinstance(obj, dict):
            if "thread_items" in obj:
                results.append(obj["thread_items"])
            for v in obj.values():
                ThreadsCollector._find_thread_items(v, results)
        elif isinstance(obj, list):
            for item in obj:
                ThreadsCollector._find_thread_items(item, results)
        return results

    @staticmethod
    def _extract_from_html(html: str, keyword: str) -> list[Post]:
        # Find the application/json script that contains thread data
        scripts = re.findall(
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )
        target = next((s for s in scripts if "thread_items" in s), None)
        if not target:
            return []

        try:
            data = json.loads(target)
        except Exception:
            return []

        posts: list[Post] = []
        seen_ids: set[str] = set()

        for items_array in ThreadsCollector._find_thread_items(data):
            for item in items_array:
                post_data = item.get("post", {})
                pk = str(post_data.get("pk", ""))
                if not pk or pk in seen_ids:
                    continue
                seen_ids.add(pk)

                user = post_data.get("user", {})
                username = user.get("username", "")
                cap_obj = post_data.get("caption") or {}
                text = cap_obj.get("text", "") if isinstance(cap_obj, dict) else ""
                code = post_data.get("code", "")
                taken_at = post_data.get("taken_at")
                likes = post_data.get("like_count", 0)
                reply_count = (
                    post_data.get("text_post_app_info", {})
                    .get("direct_reply_count", 0)
                )

                posts.append(Post(
                    platform="threads",
                    post_id=pk,
                    author=username,
                    content=text,
                    url=f"https://www.threads.com/@{username}/post/{code}" if code else "",
                    created_at=(
                        datetime.utcfromtimestamp(taken_at)
                        if taken_at
                        else datetime.utcnow()
                    ),
                    likes=likes,
                    comments=reply_count,
                    keyword=keyword,
                ))

        return posts

    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        if not settings.threads_sessionid:
            print("[threads] 未設定 THREADS_SESSIONID，跳過。\n"
                  "請從 Chrome DevTools (threads.com) 複製 sessionid 填入 .env。")
            return []

        posts: list[Post] = []
        try:
            with self._make_client() as client:
                params = {"q": keyword, "serp_type": "default"}
                r = client.get(self._SEARCH_PATH, params=params)
                r.raise_for_status()

                if "thread_items" not in r.text:
                    print(f"[threads] 頁面未包含 thread_items，"
                          f"狀態: {r.status_code}，大小: {len(r.text)}")
                    return []

                posts = self._extract_from_html(r.text, keyword)
                if not posts:
                    print(f"[threads] 解析到 0 篇貼文（HTML 大小: {len(r.text)}）")

        except Exception as e:
            print(f"[threads] 抓取失敗: {e}")

        return posts[:limit]
