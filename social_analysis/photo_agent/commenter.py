"""Instagram 智慧留言：三道過濾 + GPT-4o Vision 交叉分析，寧可不留也不亂留。"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import httpx
from instagrapi import Client
from instagrapi.exceptions import ClientError, MediaNotFound

from .account_config import AccountConfig
from ..config import settings

# ── 常數 ─────────────────────────────────────────────────────────────────────
_LOG_RETENTION_DAYS   = 7    # 留言紀錄保留天數
_COMMENT_INTERVAL_MIN = 45   # 留言最短間隔（秒）
_COMMENT_INTERVAL_MAX = 90   # 留言最長間隔（秒）
_POST_AGE_HOURS       = 36   # 只考慮最近幾小時的貼文
_MEDIAS_PER_HASHTAG   = 15   # 每個 hashtag 最多取幾篇
_HASHTAG_SAMPLE_MIN   = 2
_HASHTAG_SAMPLE_MAX   = 4
_CONFIDENCE_THRESHOLD = 75   # AI 信心分數門檻（0–100）

# 廣告關鍵字（caption 含任一則跳過）
_AD_KEYWORDS = {
    "#ad", "#sponsored", "#collab", "#partnership", "#gifted",
    "paid partnership", "贊助", "合作", "業配", "廣告",
    "link in bio", "shop now", "buy now", "discount code",
    "promo code", "use code", "官方帳號",
}

# 不適合留言的情境關鍵字
_SKIP_KEYWORDS = {
    "rip", "rest in peace", "安息", "離世", "逝世", "過世",
    "cancer", "病", "悲", "哀", "喪", "funeral",
}

_ANALYSIS_PROMPT = """\
你是 Instagram 留言品質審查員。請同時分析以下貼文的「文字 caption」與「圖片/影片縮圖」，
回答下列問題並輸出 JSON。

【帳號留言風格】
{comment_style}

【此貼文 caption】
{caption}

【分析任務】
1. 這則貼文的主要內容是什麼？（一句話描述）
2. 是否為廣告、業配或商業推廣？（true/false）
3. 圖片情境與 caption 傳達的訊息是否一致？
4. 這則貼文適合留言互動嗎？
5. 若適合，以帳號風格寫一句留言（5–15 字，自然口語，不帶推廣意味）
6. 留言信心分數（0–100，低於 {threshold} 表示不適合留言）

只輸出 JSON，不要其他文字：
{{
  "summary": "一句話描述貼文內容",
  "is_ad": false,
  "image_caption_consistent": true,
  "suitable_for_comment": true,
  "comment": "留言內容（不適合時留空字串）",
  "confidence": 85,
  "skip_reason": "若跳過，說明原因；適合則留空"
}}"""


class CommentSession:
    """單次留言巡迴。"""

    def __init__(self, account: AccountConfig):
        self.account = account
        self._cl: Client | None = None
        self._log_path = Path("accounts") / account.name / "comment_log.json"
        self._log: dict[str, str] = {}
        self._self_user_id: str | None = None

    # ── 登入 ──────────────────────────────────────────────────────────────────

    def _login(self) -> Client:
        if self._cl is not None:
            return self._cl
        acc = self.account
        cl = Client()
        session_file = Path("accounts") / acc.name / "session.json"
        if session_file.exists():
            cl.load_settings(str(session_file))
        cl.login_by_sessionid(unquote(acc.ig_session_id))
        self._cl = cl
        self._self_user_id = str(cl.user_id)
        print(f"[{acc.name}/comment] 登入成功（user_id={self._self_user_id}）")
        return cl

    # ── 紀錄 ──────────────────────────────────────────────────────────────────

    def _load_log(self) -> None:
        if self._log_path.exists():
            with open(self._log_path, encoding="utf-8") as f:
                raw: dict = json.load(f)
        else:
            raw = {}
        cutoff = datetime.now(timezone.utc) - timedelta(days=_LOG_RETENTION_DAYS)
        self._log = {
            pid: ts for pid, ts in raw.items()
            if datetime.fromisoformat(ts) >= cutoff
        }

    def _save_log(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "w", encoding="utf-8") as f:
            json.dump(self._log, f, ensure_ascii=False, indent=2)

    def _already_commented(self, post_id: str) -> bool:
        return post_id in self._log

    def _mark_commented(self, post_id: str) -> None:
        self._log[post_id] = datetime.now(timezone.utc).isoformat()

    def _daily_count(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(1 for ts in self._log.values() if ts.startswith(today))

    # ── 第一道過濾：廣告偵測 ─────────────────────────────────────────────────

    def _is_ad(self, media) -> bool:
        caption = (media.caption_text or "").lower()
        # 廣告關鍵字
        for kw in _AD_KEYWORDS:
            if kw.lower() in caption:
                return True
        # 不適合留言的情境
        for kw in _SKIP_KEYWORDS:
            if kw.lower() in caption:
                return True
        # 商業帳號大號（追蹤者超過 10 萬且有 is_business 標記）
        try:
            if getattr(media.user, "is_business", False):
                follower_count = getattr(media.user, "follower_count", 0) or 0
                if follower_count > 100_000:
                    return True
        except Exception:
            pass
        return False

    def _should_skip_basic(self, media) -> bool:
        post_id = str(media.pk)
        if self._already_commented(post_id):
            return True
        if self._self_user_id and str(media.user.pk) == self._self_user_id:
            return True
        if getattr(media.user, "is_private", False):
            return True
        try:
            taken_at = media.taken_at
            if taken_at:
                if taken_at.tzinfo is None:
                    taken_at = taken_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - taken_at > timedelta(hours=_POST_AGE_HOURS):
                    return True
        except Exception:
            pass
        return False

    # ── 第二道過濾：取得圖片 URL ─────────────────────────────────────────────

    def _get_thumbnail_url(self, media) -> str | None:
        try:
            if media.thumbnail_url:
                return str(media.thumbnail_url)
            if media.resources:
                return str(media.resources[0].thumbnail_url)
        except Exception:
            pass
        return None

    # ── 第三道過濾：GPT-4o Vision 分析 ───────────────────────────────────────

    def _analyze(self, media) -> dict | None:
        from openai import OpenAI
        import base64

        caption = (media.caption_text or "").strip()
        thumbnail_url = self._get_thumbnail_url(media)
        acc = self.account

        prompt = _ANALYSIS_PROMPT.format(
            comment_style=acc.comment_style or "自然口語，簡短真誠",
            caption=caption[:500] if caption else "（無文字）",
            threshold=acc.comment_confidence_threshold,
        )

        content: list[dict] = [{"type": "text", "text": prompt}]

        # 嘗試下載圖片並以 base64 傳入（比 URL 穩定）
        if thumbnail_url:
            try:
                resp = httpx.get(thumbnail_url, timeout=10, follow_redirects=True)
                if resp.status_code == 200:
                    b64 = base64.b64encode(resp.content).decode()
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "low",   # 留言分析用 low 即可，省 token
                        },
                    })
            except Exception as e:
                print(f"[{acc.name}/comment] 圖片下載失敗，僅用 caption 分析: {e}")

        client = OpenAI(api_key=settings.openai_api_key)
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",    # 留言分析用 mini 省成本
                max_tokens=300,
                messages=[{"role": "user", "content": content}],
            )
            raw = resp.choices[0].message.content.strip()
            if "```" in raw:
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else parts[0]
                raw = raw.lstrip("json").strip()
            if not raw.startswith("{"):
                start, end = raw.find("{"), raw.rfind("}") + 1
                if start != -1:
                    raw = raw[start:end]
            return json.loads(raw)
        except Exception as e:
            print(f"[{acc.name}/comment] AI 分析失敗: {e}")
            return None

    # ── 核心巡迴 ─────────────────────────────────────────────────────────────

    def run(self) -> int:
        acc = self.account
        if not acc.comment_enabled:
            print(f"[{acc.name}/comment] 留言功能未啟用（comment_enabled: false）")
            return 0

        hashtags: list[str] = acc.engage_hashtags
        if not hashtags:
            print(f"[{acc.name}/comment] engage_hashtags 為空，略過")
            return 0

        self._load_log()
        remaining_daily = acc.comment_daily_max - self._daily_count()
        if remaining_daily <= 0:
            print(f"[{acc.name}/comment] 今日留言已達上限 ({acc.comment_daily_max})，略過")
            return 0

        session_budget = min(acc.comment_max_per_session, remaining_daily)
        cl = self._login()

        sample_size = min(
            random.randint(_HASHTAG_SAMPLE_MIN, _HASHTAG_SAMPLE_MAX),
            len(hashtags),
        )
        selected = random.sample(hashtags, sample_size)
        print(f"[{acc.name}/comment] 本次巡迴 hashtags: {selected}，預算={session_budget}")

        commented_count = 0
        analyzed_count = 0

        for tag in selected:
            if commented_count >= session_budget:
                break
            print(f"[{acc.name}/comment] 搜尋 #{tag}")
            try:
                medias = cl.hashtag_medias_recent_v1(tag, amount=_MEDIAS_PER_HASHTAG)
            except Exception as e:
                print(f"[{acc.name}/comment] #{tag} 搜尋失敗: {e}")
                continue

            for media in medias:
                if commented_count >= session_budget:
                    break

                post_id = str(media.pk)

                # 第一道：基本過濾
                if self._should_skip_basic(media):
                    continue

                # 第一道：廣告偵測
                if self._is_ad(media):
                    print(f"[{acc.name}/comment] 跳過（廣告/不適合）: {post_id}")
                    continue

                analyzed_count += 1
                print(f"[{acc.name}/comment] 分析第 {analyzed_count} 則 (user={media.user.username})")

                # 第二、三道：AI 分析
                result = self._analyze(media)
                if not result:
                    continue

                confidence = result.get("confidence", 0)
                is_ad = result.get("is_ad", False)
                suitable = result.get("suitable_for_comment", False)
                comment_text = (result.get("comment") or "").strip()
                skip_reason = result.get("skip_reason", "")

                if is_ad:
                    print(f"[{acc.name}/comment] AI 判斷為廣告，跳過")
                    continue

                if not suitable or confidence < acc.comment_confidence_threshold or not comment_text:
                    print(f"[{acc.name}/comment] 信心不足({confidence}) / 不適合，跳過: {skip_reason}")
                    continue

                # 留言
                try:
                    cl.media_comment(media.pk, comment_text)
                    self._mark_commented(post_id)
                    commented_count += 1
                    print(
                        f"[{acc.name}/comment] 留言 #{commented_count} "
                        f"(user={media.user.username}, 信心={confidence}): 「{comment_text}」"
                    )
                except (ClientError, MediaNotFound) as e:
                    print(f"[{acc.name}/comment] 留言失敗 {post_id}: {e}")
                except Exception as e:
                    print(f"[{acc.name}/comment] 未知錯誤 {post_id}: {e}")

                if commented_count < session_budget:
                    wait = random.randint(_COMMENT_INTERVAL_MIN, _COMMENT_INTERVAL_MAX)
                    print(f"[{acc.name}/comment] 等待 {wait} 秒...")
                    time.sleep(wait)

        self._save_log()
        print(
            f"[{acc.name}/comment] 巡迴結束，分析 {analyzed_count} 則，"
            f"實際留言 {commented_count} 則"
        )
        return commented_count


# ── 公開入口 ──────────────────────────────────────────────────────────────────

def run_comment_session(account: AccountConfig) -> int:
    """執行單一帳號的留言巡迴，回傳本次留言數。"""
    session = CommentSession(account)
    return session.run()
