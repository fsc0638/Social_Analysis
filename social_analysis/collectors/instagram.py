from datetime import datetime
from .base import Collector
from ..models import Post
from ..config import settings


class InstagramCollector(Collector):
    """用 instaloader 依 hashtag 抓取公開貼文。

    需先 `pip install instaloader`,並在 .env 設定 IG_USERNAME/IG_PASSWORD。
    注意:IG 對未登入請求限制嚴格,且 ToS 不鼓勵爬蟲。僅供研究。
    """
    platform = "instagram"

    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        try:
            import instaloader  # type: ignore
        except ImportError:
            raise RuntimeError(
                "未安裝 instaloader。執行: pip install instaloader\n"
                "或改用 --platforms mock 跑通 pipeline。"
            )

        L = instaloader.Instaloader(download_pictures=False, download_videos=False,
                                    download_video_thumbnails=False, save_metadata=False)
        if settings.ig_username and settings.ig_password:
            try:
                L.login(settings.ig_username, settings.ig_password)
            except Exception as e:
                print(f"[instagram] 登入失敗,改用匿名模式: {e}")

        tag = keyword.lstrip("#")
        posts: list[Post] = []
        try:
            hashtag = instaloader.Hashtag.from_name(L.context, tag)
            for i, p in enumerate(hashtag.get_posts()):
                if i >= limit:
                    break
                posts.append(Post(
                    platform=self.platform,
                    post_id=p.shortcode,
                    author=p.owner_username,
                    content=p.caption or "",
                    url=f"https://www.instagram.com/p/{p.shortcode}/",
                    created_at=p.date_utc or datetime.utcnow(),
                    likes=p.likes,
                    comments=p.comments,
                    keyword=keyword,
                ))
        except Exception as e:
            print(f"[instagram] 抓取失敗: {e}")
        return posts
