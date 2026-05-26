from .base import Collector
from .mock import MockCollector
from .instagram import InstagramCollector
from .threads import ThreadsCollector
from .x_twitter import XCollector


def get_collector(platform: str) -> Collector:
    mapping = {
        "mock": MockCollector,
        "instagram": InstagramCollector,
        "threads": ThreadsCollector,
        "x": XCollector,
    }
    if platform not in mapping:
        raise ValueError(f"Unknown platform: {platform}")
    return mapping[platform]()


__all__ = ["Collector", "get_collector"]
