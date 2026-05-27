"""用 GPT-4o Vision 分析照片，生成符合帳號風格的文案與 hashtag。"""
import base64
import json
from pathlib import Path

from ..config import settings

_MIME_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

_DEFAULT_STYLE = """\
- 語言：繁體中文
- 語氣：直接自然，不要詩情畫意
- 不用誇張形容詞"""

_PROMPT_TEMPLATE = """\
你是 Instagram 發文專家。依照下列步驟分析照片並輸出 JSON。

【此帳號風格】
{caption_style}

【Hashtag 四步驟】
1. 仔細觀察圖像：主體、場景、光線、細節
2. 列出 20 個候選 hashtag（中英皆可，貼合圖像內容）
3. 從 20 個中篩選出 5~10 個「受眾較集中」的 hashtag
   - 優先選有明確社群的（如 #MINI #jimny #台灣街拍）
   - 避免過於寬泛（如 #photo #life #beautiful 之類）
4. 從照片判斷出地點或攝影風格，若不重複則加入最終清單

【排版規則】
- 正文前空一行（caption 欄位開頭放 \\n）
- 每段不超過 2 句，段與段之間空行
- 正文結尾空一行（caption 欄位結尾放 \\n）
- 整體正文不超過 4 行

只輸出 JSON，不要其他文字：
{{
  "caption": "\\n正文內容\\n",
  "candidate_hashtags": ["20個候選..."],
  "hashtags": ["最終5~10個"]
}}"""


def generate_caption(image_path: Path, caption_style: str = "") -> tuple[str, list[str]]:
    from openai import OpenAI

    suffix = image_path.suffix.lower()
    mime = _MIME_MAP.get(suffix, "image/jpeg")
    style = caption_style.strip() if caption_style.strip() else _DEFAULT_STYLE
    prompt = _PROMPT_TEMPLATE.format(caption_style=style)

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"}},
            ],
        }],
    )

    raw = resp.choices[0].message.content.strip()

    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]

    if not raw:
        raise ValueError(f"GPT-4o 回傳空白或非 JSON: {resp.choices[0].message.content[:200]}")

    data = json.loads(raw)

    candidates = data.get("candidate_hashtags", [])
    if candidates:
        print(f"[caption] 候選 hashtag ({len(candidates)}): {' '.join(candidates)}")

    return data.get("caption", ""), data.get("hashtags", [])
