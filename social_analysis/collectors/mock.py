import random
from datetime import datetime, timedelta
from .base import Collector
from ..models import Post

_TEMPLATES = [
    "最近很喜歡 {kw},真的太實用了!",
    "{kw} 讓我的生活完全改變,推薦給大家。",
    "說真的,{kw} 沒那麼神,炒作居多。",
    "今天試了 {kw},體驗普通,還行吧。",
    "{kw} 在台灣的討論度越來越高了 #趨勢",
    "對於 {kw} 我持保留態度,優缺點都有。",
    "剛買了跟 {kw} 相關的產品,期待開箱!",
    "工作上用 {kw} 提升效率超多,效率怪",
]
_AUTHORS = ["alice", "bob_tw", "charlie.lin", "dora_creates", "ethan_dev"]
_SENT_BIAS = [0.3, 0.4, -0.5, 0.0, 0.5, 0.1, 0.6, 0.7]


class MockCollector(Collector):
    platform = "mock"

    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        posts: list[Post] = []
        now = datetime.utcnow()
        for i in range(limit):
            idx = i % len(_TEMPLATES)
            posts.append(Post(
                platform=self.platform,
                post_id=f"mock-{keyword}-{i}",
                author=random.choice(_AUTHORS),
                content=_TEMPLATES[idx].format(kw=keyword),
                url=f"https://example.com/mock/{i}",
                created_at=now - timedelta(hours=random.randint(0, 168)),
                likes=random.randint(0, 5000),
                comments=random.randint(0, 200),
                shares=random.randint(0, 100),
                keyword=keyword,
                raw={"sentiment_hint": _SENT_BIAS[idx]},
            ))
        return posts
