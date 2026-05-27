"""批次情感與主題分類。

優先順序：
  1. Anthropic (claude-haiku)  — ANTHROPIC_API_KEY 有值時
  2. OpenAI  (gpt-4o-mini)     — LLM_PROVIDER=openai 且 OPENAI_API_KEY 有值時
  3. Heuristic fallback         — 無 API key 時
"""
import json
import re
from ..models import Post, Analysis
from ..config import settings

_POSITIVE_WORDS = ["好", "讚", "推薦", "喜歡", "棒", "愛", "完美", "驚艷", "實用", "效率"]
_NEGATIVE_WORDS = ["爛", "差", "失望", "後悔", "炒作", "難用", "雷", "騙", "不推", "退貨"]

_PROMPT_SYSTEM = (
    "你是中文社群輿情分析助手。對每則貼文輸出 JSON 陣列，每個元素包含：\n"
    "  id: 原始 id\n"
    "  sentiment: positive/neutral/negative\n"
    "  score: -1 到 1 的浮點數\n"
    "  topics: 最多 3 個主題關鍵字陣列\n"
    "  summary: 一句話摘要(<=30字)\n"
    "只輸出 JSON，不要其他文字。"
)


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


def _parse_llm_response(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("LLM 回應中找不到 JSON 陣列")
    return json.loads(m.group(0))


def _call_anthropic(items: list[dict]) -> list[dict]:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = f"{_PROMPT_SYSTEM}\n\n貼文:\n{json.dumps(items, ensure_ascii=False)}"
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_llm_response(resp.content[0].text)


def _call_openai(items: list[dict]) -> list[dict]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _PROMPT_SYSTEM},
            {"role": "user", "content": f"貼文:\n{json.dumps(items, ensure_ascii=False)}"},
        ],
    )
    return _parse_llm_response(resp.choices[0].message.content)


def _llm_call(items: list[dict]) -> list[dict]:
    """依 LLM_PROVIDER 設定選擇後端。"""
    provider = settings.llm_provider.lower()
    if provider == "anthropic" and settings.anthropic_api_key:
        return _call_anthropic(items)
    if provider == "openai" and settings.openai_api_key:
        return _call_openai(items)
    # 自動降級：任一可用的 key
    if settings.anthropic_api_key:
        return _call_anthropic(items)
    if settings.openai_api_key:
        return _call_openai(items)
    raise RuntimeError("沒有可用的 LLM API key")


def analyze_posts(posts: list[Post]) -> list[Analysis]:
    if not posts:
        return []

    has_key = settings.anthropic_api_key or settings.openai_api_key
    if not has_key:
        print("[analyzer] 無 API key，使用 heuristic fallback")
        return [_heuristic(p) for p in posts]

    results: list[Analysis] = []
    BATCH = 20
    for i in range(0, len(posts), BATCH):
        chunk = posts[i:i + BATCH]
        items = [{"id": p.uid, "text": p.content[:500]} for p in chunk]
        try:
            data = _llm_call(items)
            for item in data:
                results.append(Analysis(
                    post_uid=item["id"],
                    sentiment=item.get("sentiment", "neutral"),
                    sentiment_score=float(item.get("score", 0)),
                    topics=item.get("topics", []),
                    summary=item.get("summary", ""),
                ))
        except Exception as e:
            print(f"[analyzer] LLM 失敗，fallback heuristic: {e}")
            results.extend(_heuristic(p) for p in chunk)
    return results
