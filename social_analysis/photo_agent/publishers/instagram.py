"""Instagram Feed + Story 發文 — 使用 instagrapi。"""
from pathlib import Path

from ..account_config import AccountConfig


class InstagramPublisher:
    def __init__(self, account: AccountConfig):
        self.account = account
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client

        try:
            from instagrapi import Client
        except ImportError:
            raise RuntimeError("請執行: python -m pip install instagrapi")

        cl = Client()
        session = self.account.session_file

        if session.exists():
            try:
                cl.load_settings(session)
                cl.login(self.account.ig_username, self.account.ig_password)
                self._client = cl
                return cl
            except Exception as e:
                print(f"[ig:{self.account.name}] 舊 session 失效，重新登入: {e}")

        print(f"[ig:{self.account.name}] 登入中 ({self.account.ig_username})...")
        cl.login(self.account.ig_username, self.account.ig_password)
        cl.dump_settings(session)
        print(f"[ig:{self.account.name}] 登入成功，session 已快取")
        self._client = cl
        return cl

    def post_feed(self, image_path: Path, caption: str) -> str:
        cl = self._get_client()
        media = cl.photo_upload(str(image_path), caption)
        return str(media.pk)

    def post_story(self, image_path: Path) -> str:
        cl = self._get_client()
        media = cl.photo_upload_to_story(str(image_path))
        return str(media.pk)
