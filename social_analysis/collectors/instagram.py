from datetime import datetime
from urllib.parse import unquote
from .base import Collector
from ..models import Post
from ..config import settings


class InstagramCollector(Collector):
    """用 Instagram Mobile API v1 依 hashtag 抓取公開貼文。

    認證方式：在 .env 設定 IG_SESSION_ID（從瀏覽器 DevTools 複製）。
    舊的 instaloader hashtag GraphQL endpoint 已於 2024 年後失效。
    """
    platform = "instagram"

    _API_BASE = "https://i.instagram.com/api/v1"
    _APP_ID = "936619743392459"
    _UA = (
        "Instagram 269.0.0.18.75 Android "
        "(26/8.0.0; 480dpi; 1080x1920; OnePlus; 6T Dev; devitron; qcom; en_US; 314665256)"
    )

    def _make_session(self):
        try:
            import requests
        except ImportError:
            raise RuntimeError("未安裝 requests。執行: pip install requests")

        session_id = settings.ig_session_id
        csrf = settings.ig_csrftoken
        if not session_id:
            raise RuntimeError(
                "未設定 IG_SESSION_ID。\n"
                "請在 Chrome 開啟 instagram.com，按 F12 > Application > Cookies，\n"
                "複製 sessionid 的值並填入 .env: IG_SESSION_ID=<值>"
            )

        s = requests.Session()
        s.cookies.set("sessionid", unquote(session_id), domain=".instagram.com")
        if csrf:
            s.cookies.set("csrftoken", csrf, domain=".instagram.com")
        s.headers.update({
            "User-Agent": self._UA,
            "X-IG-App-ID": self._APP_ID,
            "X-CSRFToken": csrf or "",
        })
        return s

    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        tag = keyword.lstrip("#")
        s = self._make_session()
        posts: list[Post] = []
        next_max_id = None

        while len(posts) < limit:
            payload: dict = {"count": min(limit - len(posts), 48), "tab": "recent", "surface": "grid"}
            if next_max_id:
                payload["max_id"] = next_max_id

            try:
                r = s.post(f"{self._API_BASE}/tags/{tag}/sections/", data=payload, timeout=15)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"[instagram] API 請求失敗: {e}")
                break

            for section in data.get("sections", []):
                for m in section.get("layout_content", {}).get("medias", []):
                    media = m.get("media", {})
                    user = media.get("user", {})
                    cap_obj = media.get("caption") or {}
                    caption = cap_obj.get("text", "") if isinstance(cap_obj, dict) else ""
                    taken_at = media.get("taken_at")
                    posts.append(Post(
                        platform=self.platform,
                        post_id=str(media.get("pk", "")),
                        author=user.get("username", ""),
                        content=caption,
                        url=f"https://www.instagram.com/p/{media.get('code', '')}/",
                        created_at=datetime.utcfromtimestamp(taken_at) if taken_at else datetime.utcnow(),
                        likes=media.get("like_count", 0),
                        comments=media.get("comment_count", 0),
                        keyword=keyword,
                    ))
                    if len(posts) >= limit:
                        break
                if len(posts) >= limit:
                    break

            if not data.get("more_available") or not data.get("next_max_id"):
                break
            next_max_id = data["next_max_id"]

        return posts
