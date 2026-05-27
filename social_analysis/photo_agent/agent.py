"""Photo Agent：從帳號佇列取圖 → AI 文案 → 多平台發文。"""
from .account_config import AccountConfig
from .queue import PhotoQueue
from .caption import generate_caption
from .publishers.instagram import InstagramPublisher
from .publishers.threads import ThreadsPublisher


class PhotoAgent:
    def __init__(self, account: AccountConfig):
        self.account = account
        account.init_dirs()
        self.queue = PhotoQueue(
            str(account.queue_dir),
            str(account.posted_dir),
            str(account.failed_dir),
        )
        self._ig = InstagramPublisher(account)
        self._threads = ThreadsPublisher(account)

    def run_once(self, dry_run: bool = False) -> bool:
        acc = self.account
        photo = self.queue.next()
        if not photo:
            print(f"[{acc.name}] 佇列為空，跳過")
            return False

        print(f"[{acc.name}] 處理: {photo.name}")

        try:
            caption_text, hashtags = generate_caption(photo, acc.caption_style)
            full_caption = f"{caption_text}\n{' '.join(hashtags)}"
        except Exception as e:
            print(f"[{acc.name}] 文案生成失敗，使用檔名: {e}")
            full_caption = photo.stem

        print(f"[{acc.name}] 文案預覽:\n{'─'*40}\n{full_caption}\n{'─'*40}")

        if dry_run:
            print(f"[{acc.name}] dry-run 模式，不實際發文")
            return True

        any_success = False
        errors = []

        if acc.ig_post_feed:
            try:
                pk = self._ig.post_feed(photo, full_caption)
                print(f"[{acc.name}] IG Feed 成功 (pk={pk})")
                any_success = True
            except Exception as e:
                errors.append(f"IG Feed: {e}")
                print(f"[{acc.name}] IG Feed 失敗: {e}")

        if acc.ig_post_story:
            try:
                pk = self._ig.post_story(photo)
                print(f"[{acc.name}] IG Story 成功 (pk={pk})")
            except Exception as e:
                errors.append(f"IG Story: {e}")
                print(f"[{acc.name}] IG Story 失敗: {e}")

        if acc.threads_post:
            try:
                ok = self._threads.post_image(photo, full_caption)
                print(f"[{acc.name}] Threads {'成功' if ok else '回傳非 ok'}")
                any_success = any_success or ok
            except Exception as e:
                errors.append(f"Threads: {e}")
                print(f"[{acc.name}] Threads 失敗: {e}")

        if any_success:
            self.queue.mark_posted(photo)
        else:
            self.queue.mark_failed(photo)
            print(f"[{acc.name}] 所有平台均失敗: {errors}")

        return any_success
