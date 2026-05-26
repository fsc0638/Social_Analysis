"""根據趨勢摘要產出文章。"""
import json
from ..config import settings


def _fallback(keyword: str, trends: dict) -> tuple[str, str]:
    title = f"【{keyword}】社群輿情速覽(共 {trends.get('total', 0)} 則)"
    lines = [f"# {title}", ""]
    lines.append(f"平均情感分數: **{trends.get('avg_sentiment', 0):.2f}**\n")
    lines.append("## 情感分布")
    for k, v in trends.get("sentiment_dist", {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## 熱門主題")
    for t, c in trends.get("top_topics", []):
        lines.append(f"- {t} ({c})")
    lines.append("\n## 高互動貼文")
    for p in trends.get("top_posts", [])[:5]:
        lines.append(f"- [{p['platform']}] @{p['author']}: {p['content'][:60]}... ({p['engagement']} 互動)")
    return title, "\n".join(lines)


def generate_article(keyword: str, trends: dict) -> tuple[str, str]:
    if not settings.anthropic_api_key or trends.get("total", 0) == 0:
        return _fallback(keyword, trends)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=settings.anthropic_api_key)
    except Exception:
        return _fallback(keyword, trends)

    # 壓縮 trends 給 LLM
    digest = {
        "total": trends["total"],
        "avg_sentiment": trends["avg_sentiment"],
        "sentiment_dist": trends["sentiment_dist"],
        "platform_dist": trends["platform_dist"],
        "top_topics": trends["top_topics"],
        "top_posts_excerpt": [
            {"platform": p["platform"], "content": p["content"][:120],
             "engagement": p["engagement"], "sentiment": p["sentiment"]}
            for p in trends["top_posts"][:8]
        ],
    }

    prompt = (
        f"你是一位資深社群分析師。請根據以下關鍵字「{keyword}」的跨平台 (IG/Threads/X) 輿情資料,"
        "撰寫一篇 600~900 字的繁體中文分析文章。\n"
        "結構:\n"
        "1. 一句吸睛的標題(放在第一行,以 # 開頭)\n"
        "2. 開場:整體情緒與討論熱度概況\n"
        "3. 主題分析:熱門子議題與正反聲音\n"
        "4. 平台差異:不同平台討論調性\n"
        "5. 觀察與建議\n"
        "風格:客觀、有洞見,不誇大;可適度引用貼文摘錄。\n\n"
        f"資料:\n{json.dumps(digest, ensure_ascii=False, indent=2)}"
    )

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        body = resp.content[0].text.strip()
        # 取第一行為標題
        first_line = body.splitlines()[0].lstrip("#").strip()
        title = first_line or f"{keyword} 輿情分析"
        return title, body
    except Exception as e:
        print(f"[article] LLM 失敗,fallback: {e}")
        return _fallback(keyword, trends)
