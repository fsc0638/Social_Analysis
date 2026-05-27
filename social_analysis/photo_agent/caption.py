"""用 GPT-4o Vision 分析照片，生成符合帳號風格的文案與 hashtag。"""
import base64
import json
from datetime import datetime
from pathlib import Path

from ..config import settings

_MIME_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

_DEFAULT_STYLE = """\
- 語言：繁體中文
- 語氣：直接自然，不要詩情畫意
- 不用誇張形容詞"""

_PROMPT_TEMPLATE = """\
你是 Instagram 發文專家。依照下列步驟分析照片並輸出 JSON。

【照片拍攝日期】
{photo_date}
請將此日期（格式 YYYYMMDD）作為文案的第一行，不要修改格式。

【此帳號風格】
{caption_style}

【圖像深度分析（寫文案前必做）】
請依序觀察以下四個面向，交叉判斷當下場景的語氣與情緒：
1. 情境：發生了什麼事？主體在做什麼動作？
2. 設備 / 道具：出現哪些物件或裝備？（車、相機、玩具、食物…）
3. 環境：室內 / 室外？光線？天氣？地點特徵？
4. 動物表情（若有動物請特別專注）：眼神、耳朵方向、嘴型、身體姿勢傳達出什麼情緒？
→ 根據以上四點綜合判斷，決定文案要用什麼語氣

【Hashtag 四步驟】
1. 根據圖像分析結果，列出 20 個候選 hashtag（中英皆可）
2. 從 20 個中篩選 5~10 個「受眾較集中」的 hashtag
   - 優先選有明確社群的（如 #英短藍白 #jimny #台灣街拍 #minicooper）
   - 避免過於寬泛（如 #photo #life #beautiful）
3. 從照片判斷地點或攝影風格，若不重複則加入最終清單

只輸出 JSON，不要其他文字：
{{
  "caption": "正文（含日期與分隔線，不含 hashtag）",
  "candidate_hashtags": ["20個候選..."],
  "hashtags": ["最終5~10個"]
}}"""


def generate_caption(image_path: Path, caption_style: str = "", photo_date: datetime | None = None) -> tuple[str, list[str]]:
    from openai import OpenAI

    suffix = image_path.suffix.lower()
    mime = _MIME_MAP.get(suffix, "image/jpeg")
    style = caption_style.strip() if caption_style.strip() else _DEFAULT_STYLE
    date_str = photo_date.strftime("%Y%m%d") if photo_date else datetime.now().strftime("%Y%m%d")
    prompt = _PROMPT_TEMPLATE.format(caption_style=style, photo_date=date_str)

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
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
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
