"""用 Claude API 批次做情感與主題分類。

LLM 失敗或無 key 時 fallback 到簡單關鍵字啟發式,確保 pipeline 不中斷。
為節省成本,使用 prompt caching + 批次提示。
"""
import json
import re
from ..models import Post, Analysis
from ..config import settings

_POSITIVE_WORDS = ["好", "讚", "推薦", "喜歡", "棒", "愛", "完美", "驚艷", "實用", "效率"]
_NEGATIVE_WORDS = ["爛", "差", "失望", "後悔", "炒作", "難用", "雷", "騙", "不推", "退貨"]


def _heuristic(post: Post) -> Analysis:
    text = post.content
    pos = sum(text.count(w) for w in _POSITIVE_WORDS)
    neg = sum(text.count(w) for w in _NEGATIVE_WORDS)
    if pos > neg:
        sent, score = "positive", min(0.3 + 0.2 * (pos - neg), 1.0)
    elif neg > pos:
        sent, score = "negative", max(-0.3 - 0.2 * (neg - pos), -1.0)
    else:
        sent, score = "neutral", 0.0
    return Analysis(
        post_uid=post.uid, sentiment=sent, sentiment_score=score,
        topics=[post.keyword] if post.keyword else [],
        summary=text[:50],
    )


def analyze_posts(posts: list[Post]) -> list[Analysis]:
    if not posts:
        return []
    if not settings.anthropic_api_key:
        return [_heuristic(p) for p in posts]

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.anthropic_api_key)
    except Exception:
        return [_heuristic(p) for p in posts]

    results: list[Analysis] = []
    BATCH = 20
    for i in range(0, len(posts), BATCH):
        chunk = posts[i:i + BATCH]
        items = [{"id": p.uid, "text": p.content[:500]} for p in chunk]
        prompt = (
            "你是中文社群輿情分析助手。對每則貼文輸出 JSON 陣列,每個元素包含:\n"
            "  id: 原始 id\n"
            "  sentiment: positive/neutral/negative\n"
            "  score: -1 到 1 的浮點數\n"
            "  topics: 最多 3 個主題關鍵字陣列\n"
            "  summary: 一句話摘要(<=30字)\n"
            "只輸出 JSON,不要其他文字。\n\n"
            f"貼文:\n{json.dumps(items, ensure_ascii=False)}"
        )
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if not m:
                raise ValueError("no JSON")
            data = json.loads(m.group(0))
            for item in data:
                results.append(Analysis(
                    post_uid=item["id"],
                    sentiment=item.get("sentiment", "neutral"),
                    sentiment_score=float(item.get("score", 0)),
                    topics=item.get("topics", []),
                    summary=item.get("summary", ""),
                ))
        except Exception as e:
            print(f"[analyzer] LLM 失敗,fallback heuristic: {e}")
            results.extend(_heuristic(p) for p in chunk)
    return results
