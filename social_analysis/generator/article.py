"""根據趨勢摘要產出文章。

設計重點:
- system prompt 走 Anthropic prompt caching,長期 system 部分一次定價
- 從 trends 抽真實貼文引述(正反各取)讓 LLM 有「素材」可引用
- 三種格式 analysis / brief / social
- 可選 self-critique 二次潤稿
- 無 API key 或 LLM 失敗時 fallback 到結構化模板
"""
import json
from typing import Literal
from ..config import settings
from . import prompts as P

ArticleFormat = Literal["analysis", "brief", "social"]


# ---------- Fallback (無 LLM 時) ----------
def _fallback(keyword: str, trends: dict, fmt: ArticleFormat) -> tuple[str, str]:
    title = f"【{keyword}】社群輿情速覽(共 {trends.get('total', 0)} 則)"
    lines = [f"# {title}", ""]
    lines.append(f"平均情感分數: **{trends.get('avg_sentiment', 0):.2f}**\n")
    sd = trends.get("sentiment_dist", {})
    total = max(trends.get("total", 0), 1)
    lines.append("## 情感分布")
    for k, v in sd.items():
        lines.append(f"- {k}: {v} ({v/total:.0%})")
    lines.append("\n## 熱門主題")
    for t, c in trends.get("top_topics", [])[:8]:
        lines.append(f"- {t} ({c})")
    lines.append("\n## 高互動貼文")
    for p in trends.get("top_posts", [])[:5]:
        lines.append(f"- [{p['platform']}] @{p['author']}: {p['content'][:60]}... "
                     f"({p['engagement']} 互動, {p.get('sentiment', '?')})")
    lines.append("\n_說明: LLM 未啟用,本文為結構化模板輸出。設定 ANTHROPIC_API_KEY 可得到分析文章。_")
    return title, "\n".join(lines)


# ---------- 從 trends 抽引述素材 ----------
def _format_quote(p: dict, max_len: int = 60) -> str:
    text = (p.get("content") or "").replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return (f"- [{p['platform']}] @{p.get('author', 'unknown')}"
            f"「{text}」({p.get('engagement', 0)} 互動, {p.get('sentiment', '?')})")


def _extract_quote_blocks(trends: dict) -> tuple[str, str, str]:
    top = trends.get("top_posts", [])
    quotes = "\n".join(_format_quote(p) for p in top[:8]) or "(無)"
    positive = [p for p in top if p.get("sentiment") == "positive"][:4]
    negative = [p for p in top if p.get("sentiment") == "negative"][:4]
    pos_block = "\n".join(_format_quote(p) for p in positive) or "(無明顯正面代表)"
    neg_block = "\n".join(_format_quote(p) for p in negative) or "(無明顯負面代表)"
    return quotes, pos_block, neg_block


# ---------- OpenAI 流程 ----------
def _generate_openai(client, keyword, trends, fmt, critique, model):
    oai_model = model if not model.startswith("claude") else "gpt-4o-mini"
    quotes, pos_quotes, neg_quotes = _extract_quote_blocks(trends)
    system_text = P.SYSTEM_PROMPT + "\n\n# 本次格式要求\n" + P.FORMAT_HINTS[fmt]
    user_text = P.USER_TEMPLATE.format(
        keyword=keyword,
        total=trends.get("total", 0),
        sentiment_dist=__import__("json").dumps(trends.get("sentiment_dist", {}), ensure_ascii=False),
        avg_sentiment=trends.get("avg_sentiment", 0),
        platform_dist=__import__("json").dumps(trends.get("platform_dist", {}), ensure_ascii=False),
        top_topics=__import__("json").dumps(trends.get("top_topics", []), ensure_ascii=False),
        quotes_block=quotes,
        positive_quotes=pos_quotes,
        negative_quotes=neg_quotes,
        fmt=fmt,
    )
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": P.FEWSHOT_USER},
        {"role": "assistant", "content": P.FEWSHOT_ASSISTANT},
        {"role": "user", "content": user_text},
    ]
    try:
        resp = client.chat.completions.create(model=oai_model, max_tokens=2048, messages=messages)
        draft = resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[article] OpenAI 失敗,fallback: {e}")
        return _fallback(keyword, trends, fmt)

    if critique:
        try:
            resp2 = client.chat.completions.create(
                model=oai_model, max_tokens=2048,
                messages=[{"role": "system", "content": system_text},
                           {"role": "user", "content": P.CRITIQUE_PROMPT.format(draft=draft)}],
            )
            draft = resp2.choices[0].message.content.strip()
        except Exception as e:
            print(f"[article] critique 失敗,保留第一稿: {e}")

    first_line = next((ln for ln in draft.splitlines() if ln.strip()), "")
    title = first_line.lstrip("#").strip() or f"{keyword} 輿情分析"
    return title, draft


# ---------- 主流程 ----------
def generate_article(
    keyword: str,
    trends: dict,
    fmt: ArticleFormat = "analysis",
    critique: bool = False,
    model: str = "claude-sonnet-4-5",
) -> tuple[str, str]:
    if trends.get("total", 0) == 0:
        return _fallback(keyword, trends, fmt)
    provider = settings.llm_provider

    if provider == "openai":
        if not settings.openai_api_key:
            return _fallback(keyword, trends, fmt)
        try:
            from openai import OpenAI
            oai_client = OpenAI(api_key=settings.openai_api_key)
        except Exception:
            return _fallback(keyword, trends, fmt)
        return _generate_openai(oai_client, keyword, trends, fmt, critique, model)
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            return _fallback(keyword, trends, fmt)
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings.anthropic_api_key)
        except Exception:
            return _fallback(keyword, trends, fmt)
    else:
        return _fallback(keyword, trends, fmt)

    quotes, pos_quotes, neg_quotes = _extract_quote_blocks(trends)

    user_text = P.USER_TEMPLATE.format(
        keyword=keyword,
        total=trends.get("total", 0),
        sentiment_dist=json.dumps(trends.get("sentiment_dist", {}), ensure_ascii=False),
        avg_sentiment=trends.get("avg_sentiment", 0),
        platform_dist=json.dumps(trends.get("platform_dist", {}), ensure_ascii=False),
        top_topics=json.dumps(trends.get("top_topics", []), ensure_ascii=False),
        quotes_block=quotes,
        positive_quotes=pos_quotes,
        negative_quotes=neg_quotes,
        fmt=fmt,
    )

    # System prompt 含格式提示,走 cache
    system_blocks = [
        {
            "type": "text",
            "text": P.SYSTEM_PROMPT + "\n\n# 本次格式要求\n" + P.FORMAT_HINTS[fmt],
            "cache_control": {"type": "ephemeral"},
        }
    ]

    messages = [
        {"role": "user", "content": P.FEWSHOT_USER},
        {"role": "assistant", "content": P.FEWSHOT_ASSISTANT},
        {"role": "user", "content": user_text},
    ]

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_blocks,
            messages=messages,
        )
        draft = resp.content[0].text.strip()
    except Exception as e:
        print(f"[article] LLM 第一輪失敗,fallback: {e}")
        return _fallback(keyword, trends, fmt)

    # 可選的 self-critique 二次潤稿
    if critique:
        try:
            resp2 = client.messages.create(
                model=model,
                max_tokens=2048,
                system=system_blocks,  # 同 system,延續 cache
                messages=[{"role": "user", "content": P.CRITIQUE_PROMPT.format(draft=draft)}],
            )
            draft = resp2.content[0].text.strip()
        except Exception as e:
            print(f"[article] critique 失敗,保留第一稿: {e}")

    # 取第一行為標題
    first_line = next((ln for ln in draft.splitlines() if ln.strip()), "")
    title = first_line.lstrip("#").strip() or f"{keyword} 輿情分析"
    return title, draft
