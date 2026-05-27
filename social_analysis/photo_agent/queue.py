"""照片佇列管理：掃描資料夾、追蹤狀態、移動檔案。"""
import shutil
from datetime import datetime
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


class PhotoQueue:
    def __init__(self, queue_dir: str, posted_dir: str, failed_dir: str):
        self.queue = Path(queue_dir)
        self.posted = Path(posted_dir)
        self.failed = Path(failed_dir)
        for d in (self.queue, self.posted, self.failed):
            d.mkdir(parents=True, exist_ok=True)

    def list_pending(self) -> list[Path]:
        files = [f for f in self.queue.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
        return sorted(files, key=lambda f: f.stat().st_mtime)

    def next(self) -> Path | None:
        pending = self.list_pending()
        return pending[0] if pending else None

    def mark_posted(self, path: Path) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.posted / f"{ts}_{path.name}"
        shutil.move(str(path), str(dest))
        print(f"[queue] 已移至 posted: {dest.name}")

    def mark_failed(self, path: Path) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.failed / f"{ts}_{path.name}"
        shutil.move(str(path), str(dest))
        print(f"[queue] 已移至 failed: {dest.name}")
