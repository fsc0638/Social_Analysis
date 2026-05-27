"""帳號設定：從 accounts/<name>/config.yaml 載入，每個帳號各自獨立。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AccountConfig:
    name: str

    # Instagram
    ig_username: str = ""
    ig_password: str = ""
    ig_session_id: str = ""
    ig_csrftoken: str = ""

    # Threads
    threads_sessionid: str = ""
    threads_csrftoken: str = ""
    threads_mid: str = ""
    threads_ds_user_id: str = ""

    # 發文開關
    ig_post_feed: bool = True
    ig_post_story: bool = True
    threads_post: bool = True

    # 排程（逗號分隔，如 "08:00,20:00"）
    schedule: str = "08:00,20:00"

    # 此帳號的額外文案風格備註（附加到 prompt 尾端）
    caption_style: str = ""

    # ── 互動增粉（engager）────────────────────────────
    engage_hashtags: list = field(default_factory=list)
    engage_max_per_session: int = 12
    engage_daily_max: int = 80

    # ── 智慧留言（commenter）──────────────────────────
    comment_enabled: bool = False
    comment_style: str = ""
    comment_max_per_session: int = 6
    comment_daily_max: int = 25
    comment_confidence_threshold: int = 75

    # ── 路徑 ──────────────────────────────────────────
    @property
    def base_dir(self) -> Path:
        return Path("accounts") / self.name

    @property
    def queue_dir(self) -> Path:
        return self.base_dir / "queue"

    @property
    def posted_dir(self) -> Path:
        return self.base_dir / "posted"

    @property
    def failed_dir(self) -> Path:
        return self.base_dir / "failed"

    @property
    def session_file(self) -> Path:
        return self.base_dir / "session.json"

    # ── 載入 / 建立 ───────────────────────────────────
    @classmethod
    def load(cls, account_name: str) -> AccountConfig:
        config_path = Path("accounts") / account_name / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"找不到帳號設定: {config_path}\n"
                f"請執行: python -m social_analysis.cli photo-init --account {account_name}"
            )
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # 相容舊欄位名稱
        if "caption_notes" in data:
            data["caption_style"] = data.pop("caption_notes")
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(name=account_name, **filtered)

    @classmethod
    def list_all(cls) -> list[str]:
        accounts_dir = Path("accounts")
        if not accounts_dir.exists():
            return []
        return sorted(
            d.name for d in accounts_dir.iterdir()
            if d.is_dir() and (d / "config.yaml").exists()
        )

    def init_dirs(self) -> None:
        for d in (self.queue_dir, self.posted_dir, self.failed_dir):
            d.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        config_path = self.base_dir / "config.yaml"
        data = {k: v for k, v in self.__dict__.items() if k != "name"}
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        print(f"[account] 設定已寫入: {config_path}")
