from typing import Optional
import pandas as pd
from sqlalchemy import select
from .db import get_session, PostRow, AnalysisRow, ArticleRow
from ..models import Post, Analysis


def save_posts(posts: list[Post]) -> int:
    if not posts:
        return 0
    n = 0
    with get_session() as s:
        for p in posts:
            existing = s.get(PostRow, p.uid)
            if existing:
                continue
            s.add(PostRow(
                uid=p.uid, platform=p.platform, post_id=p.post_id,
                author=p.author, content=p.content, url=p.url,
                created_at=p.created_at, likes=p.likes, comments=p.comments,
                shares=p.shares, keyword=p.keyword, raw=p.raw,
            ))
            n += 1
        s.commit()
    return n


def save_analyses(analyses: list[Analysis]) -> int:
    n = 0
    with get_session() as s:
        for a in analyses:
            existing = s.get(AnalysisRow, a.post_uid)
            if existing:
                existing.sentiment = a.sentiment
                existing.sentiment_score = a.sentiment_score
                existing.topics = a.topics
                existing.summary = a.summary
            else:
                s.add(AnalysisRow(
                    post_uid=a.post_uid, sentiment=a.sentiment,
                    sentiment_score=a.sentiment_score,
                    topics=a.topics, summary=a.summary,
                ))
            n += 1
        s.commit()
    return n


def save_article(keyword: str, title: str, body: str, published_to: str = "") -> int:
    with get_session() as s:
        row = ArticleRow(keyword=keyword, title=title, body=body, published_to=published_to)
        s.add(row)
        s.commit()
        return row.id


def fetch_posts(keyword: Optional[str] = None, limit: int = 500) -> list[Post]:
    with get_session() as s:
        q = select(PostRow).order_by(PostRow.created_at.desc()).limit(limit)
        if keyword:
            q = select(PostRow).where(PostRow.keyword == keyword).order_by(PostRow.created_at.desc()).limit(limit)
        rows = s.execute(q).scalars().all()
        return [Post(
            platform=r.platform, post_id=r.post_id, author=r.author,
            content=r.content, url=r.url, created_at=r.created_at,
            likes=r.likes, comments=r.comments, shares=r.shares,
            keyword=r.keyword, raw=r.raw or {},
        ) for r in rows]


def fetch_analyses_joined(keyword: Optional[str] = None) -> pd.DataFrame:
    with get_session() as s:
        q = (select(PostRow, AnalysisRow)
             .join(AnalysisRow, PostRow.uid == AnalysisRow.post_uid, isouter=True))
        if keyword:
            q = q.where(PostRow.keyword == keyword)
        rows = s.execute(q).all()
        data = []
        for post, ana in rows:
            data.append({
                "uid": post.uid,
                "platform": post.platform,
                "author": post.author,
                "content": post.content,
                "url": post.url,
                "created_at": post.created_at,
                "likes": post.likes,
                "comments": post.comments,
                "shares": post.shares,
                "keyword": post.keyword,
                "sentiment": ana.sentiment if ana else None,
                "sentiment_score": ana.sentiment_score if ana else None,
                "topics": ana.topics if ana else None,
                "summary": ana.summary if ana else None,
            })
        return pd.DataFrame(data)
