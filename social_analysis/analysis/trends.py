from collections import Counter
import pandas as pd


def compute_trends(df: pd.DataFrame) -> dict:
    """產出趨勢摘要:時序熱度、情感分布、熱門主題、平台分布。"""
    if df.empty:
        return {"total": 0}

    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["engagement"] = df["likes"].fillna(0) + df["comments"].fillna(0) + df["shares"].fillna(0)

    by_day = (df.set_index("created_at")
                .resample("D")
                .agg(posts=("uid", "count"), engagement=("engagement", "sum"))
                .reset_index())

    sentiment_dist = df["sentiment"].value_counts(dropna=False).to_dict()
    platform_dist = df["platform"].value_counts().to_dict()

    topics_counter: Counter = Counter()
    for t in df["topics"].dropna():
        if isinstance(t, list):
            topics_counter.update(t)
    top_topics = topics_counter.most_common(10)

    top_posts = (df.sort_values("engagement", ascending=False)
                   .head(10)[["uid", "platform", "author", "content", "engagement",
                              "sentiment", "url"]]
                   .to_dict(orient="records"))

    return {
        "total": len(df),
        "by_day": by_day.to_dict(orient="records"),
        "sentiment_dist": sentiment_dist,
        "platform_dist": platform_dist,
        "top_topics": top_topics,
        "top_posts": top_posts,
        "avg_sentiment": float(df["sentiment_score"].dropna().mean() or 0),
    }
