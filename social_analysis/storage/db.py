from datetime import datetime
from sqlalchemy import create_engine, String, Integer, Float, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from ..config import settings


class Base(DeclarativeBase):
    pass


class PostRow(Base):
    __tablename__ = "posts"
    uid: Mapped[str] = mapped_column(String, primary_key=True)
    platform: Mapped[str] = mapped_column(String, index=True)
    post_id: Mapped[str] = mapped_column(String)
    author: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    keyword: Mapped[str] = mapped_column(String, index=True, default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class AnalysisRow(Base):
    __tablename__ = "analyses"
    post_uid: Mapped[str] = mapped_column(String, primary_key=True)
    sentiment: Mapped[str] = mapped_column(String)
    sentiment_score: Mapped[float] = mapped_column(Float)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")


class ArticleRow(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_to: Mapped[str] = mapped_column(String, default="")


_engine = create_engine(settings.db_url, future=True)
_Session = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(_engine)


def get_session():
    return _Session()
