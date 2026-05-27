"""Threads 圖片發文 — 透過 Instagram 共用後端的非官方 API。"""
import json
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlencode

import httpx

from ..account_config import AccountConfig

_THREADS_APP_ID = "238260118697367"
_IG_API = "https://i.instagram.com"
_UA = (
    "Barcelona 289.0.0.77.109 Android "
    "(26/8.0.0; 480dpi; 1080x1920; samsung; SM-G988B; t2s; exynos990; en_US; 458229258)"
)


class ThreadsPublisher:
    def __init__(self, account: AccountConfig):
        self.account = account

    def _make_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=_IG_API,
            cookies={
                "sessionid": unquote(self.account.threads_sessionid),
                "csrftoken": self.account.threads_csrftoken,
                "ds_user_id": self.account.threads_ds_user_id,
            },
            headers={
                "User-Agent": _UA,
                "X-IG-App-ID": _THREADS_APP_ID,
                "X-CSRFToken": self.account.threads_csrftoken,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=60,
        )

    def _upload_image(self, client: httpx.Client, image_path: Path) -> str:
        upload_id = str(int(time.time() * 1000))
        image_data = image_path.read_bytes()

        rupload_params = json.dumps({
            "upload_id": upload_id,
            "media_type": "1",
            "retry_context": '{"num_step_auto_retry":0,"num_reupload":0,"num_step_manual_retry":0}',
            "image_compression": json.dumps({"lib_name": "moz", "lib_version": "3.1.m", "quality": "80"}),
        })

        r = client.post(
            f"/rupload_igphoto/fb_uploader_{upload_id}",
            content=image_data,
            headers={
                "X_FB_PHOTO_WATERFALL_ID": str(uuid.uuid4()),
                "X-Entity-Type": "image/jpeg",
                "Offset": "0",
                "X-Instagram-Rupload-Params": rupload_params,
                "X-Entity-Name": f"fb_uploader_{upload_id}",
                "X-Entity-Length": str(len(image_data)),
                "Content-Type": "application/octet-stream",
            },
        )
        r.raise_for_status()
        return upload_id

    def post_image(self, image_path: Path, caption: str) -> bool:
        acc = self.account
        if not acc.threads_sessionid:
            print(f"[threads:{acc.name}] 未設定 threads_sessionid，跳過")
            return False

        with self._make_client() as client:
            print(f"[threads:{acc.name}] 上傳圖片...")
            upload_id = self._upload_image(client, image_path)

            body = urlencode({
                "upload_id": upload_id,
                "caption": caption,
                "source_type": "4",
                "publish_mode": "text_post",
                "text_post_app_info": json.dumps({"reply_control": 0}),
                "device_id": f"android-{uuid.uuid4().hex[:16]}",
            })

            r = client.post(
                "/api/v1/media/configure_to_text_post_app_feed/",
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            )
            r.raise_for_status()
            return r.json().get("status") == "ok"
