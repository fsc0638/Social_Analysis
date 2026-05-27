"""Instagram 互動巡迴：依帳號風格 hashtag 巡迴按愛心，增加曝光與粉絲。"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

from instagrapi import Client
from instagrapi.exceptions import ClientError, MediaNotFound

from .account_config import AccountConfig

# ── 常數 ─────────────────────────────────────────────────────────────────────
_LOG_RETENTION_DAYS = 7          # 已按紀錄保留天數
_LIKE_INTERVAL_MIN = 10          # 按愛心最短間隔（秒）
_LIKE_INTERVAL_MAX = 25          # 按愛心最長間隔（秒）
_POST_AGE_HOURS = 24             # 只考慮最近幾小時內的貼文
_HASHTAG_SAMPLE_MIN = 3          # 每次巡迴最少抽幾個 hashtag
_HASHTAG_SAMPLE_MAX = 5          # 每次巡迴最多抽幾個 hashtag
_MEDIAS_PER_HASHTAG = 20         # 每個 hashtag 最多取幾篇貼文


class EngageSession:
    """單次互動巡迴。"""

    def __init__(self, account: AccountConfig):
        self.account = account
        self._cl: Client | None = None
        self._log_path = (
            Path("accounts") / account.name / "engaged_log.json"
        )
        self._log: dict[str, str] = {}   # post_id -> ISO date string
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
        cl.dump_settings(str(session_file))
        self._cl = cl
        self._self_user_id = str(cl.user_id)
        print(f"[{acc.name}] 登入成功（user_id={self._self_user_id}）")
        return cl

    # ── 紀錄 ──────────────────────────────────────────────────────────────────

    def _load_log(self) -> None:
        if self._log_path.exists():
            with open(self._log_path, encoding="utf-8") as f:
                raw: dict = json.load(f)
        else:
            raw = {}

        # 清除超過保留期限的紀錄
        cutoff = datetime.now(timezone.utc) - timedelta(days=_LOG_RETENTION_DAYS)
        self._log = {
            pid: ts
            for pid, ts in raw.items()
            if datetime.fromisoformat(ts) >= cutoff
        }

    def _save_log(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "w", encoding="utf-8") as f:
            json.dump(self._log, f, ensure_ascii=False, indent=2)

    def _already_liked(self, post_id: str) -> bool:
        return post_id in self._log

    def _mark_liked(self, post_id: str) -> None:
        self._log[post_id] = datetime.now(timezone.utc).isoformat()

    def _daily_count(self) -> int:
        """計算今日（UTC）已按愛心數。"""
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(1 for ts in self._log.values() if ts.startswith(today))

    # ── 過濾 ──────────────────────────────────────────────────────────────────

    def _is_recent(self, media) -> bool:
        """貼文是否在指定時數內。"""
        try:
            taken_at = media.taken_at
            if taken_at is None:
                return False
            if taken_at.tzinfo is None:
                taken_at = taken_at.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - taken_at
            return age <= timedelta(hours=_POST_AGE_HOURS)
        except Exception:
            return False

    def _should_skip(self, media) -> bool:
        """回傳 True 表示應該跳過這篇貼文。"""
        post_id = str(media.pk)
        if self._already_liked(post_id):
            return True
        # 跳過自己的貼文
        if self._self_user_id and str(media.user.pk) == self._self_user_id:
            return True
        # 跳過私人帳號（user.is_private 不一定有，用 getattr 保護）
        if getattr(media.user, "is_private", False):
            return True
        return False

    # ── 核心巡迴 ─────────────────────────────────────────────────────────────

    def run(self) -> int:
        """執行一次互動巡迴，回傳本次實際按愛心數。"""
        acc = self.account
        hashtags: list[str] = acc.engage_hashtags
        if not hashtags:
            print(f"[{acc.name}] engage_hashtags 為空，略過")
            return 0

        self._load_log()

        remaining_daily = acc.engage_daily_max - self._daily_count()
        if remaining_daily <= 0:
            print(f"[{acc.name}] 今日已達上限 ({acc.engage_daily_max})，略過")
            return 0

        session_budget = min(acc.engage_max_per_session, remaining_daily)
        cl = self._login()

        sample_size = min(
            random.randint(_HASHTAG_SAMPLE_MIN, _HASHTAG_SAMPLE_MAX),
            len(hashtags),
        )
        selected = random.sample(hashtags, sample_size)
        print(f"[{acc.name}] 本次巡迴 hashtags: {selected}，預算={session_budget}")

        liked_count = 0

        for tag in selected:
            if liked_count >= session_budget:
                break
            print(f"[{acc.name}] 搜尋 #{tag}")
            try:
                medias = cl.hashtag_medias_recent_v1(tag, amount=_MEDIAS_PER_HASHTAG)
            except Exception as e:
                print(f"[{acc.name}] #{tag} 搜尋失敗: {e}")
                continue

            for media in medias:
                if liked_count >= session_budget:
                    break
                if not self._is_recent(media):
                    continue
                if self._should_skip(media):
                    continue

                try:
                    cl.media_like(media.pk)
                    self._mark_liked(str(media.pk))
                    liked_count += 1
                    print(
                        f"[{acc.name}] 愛心 #{liked_count} "
                        f"(media_pk={media.pk}, user={media.user.username})"
                    )
                except (ClientError, MediaNotFound) as e:
                    print(f"[{acc.name}] 按愛心失敗 {media.pk}: {e}")
                except Exception as e:
                    print(f"[{acc.name}] 未知錯誤 {media.pk}: {e}")

                if liked_count < session_budget:
                    wait = random.randint(_LIKE_INTERVAL_MIN, _LIKE_INTERVAL_MAX)
                    time.sleep(wait)

        self._save_log()
        print(f"[{acc.name}] 巡迴結束，本次按愛心 {liked_count} 個")
        return liked_count


# ── 公開入口 ──────────────────────────────────────────────────────────────────

def run_session(account: AccountConfig) -> int:
    """執行單一帳號的互動巡迴，回傳本次按愛心數。"""
    session = EngageSession(account)
    return session.run()
