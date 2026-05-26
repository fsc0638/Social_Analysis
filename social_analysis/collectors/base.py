from abc import ABC, abstractmethod
from ..models import Post


class Collector(ABC):
    platform: str = "base"

    @abstractmethod
    def search(self, keyword: str, limit: int = 50) -> list[Post]:
        """依關鍵字搜尋公開貼文"""
        ...
