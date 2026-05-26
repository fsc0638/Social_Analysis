from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Post(BaseModel):
    """跨平台統一貼文模型"""
    platform: str  # instagram | threads | x | mock
    post_id: str
    author: str
    content: str
    url: str = ""
    created_at: datetime
    likes: int = 0
    comments: int = 0
    shares: int = 0
    keyword: str = ""  # 觸發抓取的關鍵字
    raw: dict = Field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"{self.platform}:{self.post_id}"


class Analysis(BaseModel):
    post_uid: str
    sentiment: str  # positive | neutral | negative
    sentiment_score: float  # -1 ~ 1
    topics: list[str] = Field(default_factory=list)
    summary: str = ""
