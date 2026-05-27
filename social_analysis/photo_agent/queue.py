"""照片佇列管理：掃描資料夾、追蹤狀態、移動檔案。"""
import shutil
from datetime import datetime
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def _photo_datetime(path: Path) -> datetime:
    """取得照片的拍攝時間（優先順序：EXIF DateTimeOriginal → 檔案建立時間 → 修改時間）。"""
    # 1. 嘗試從 EXIF 讀取拍攝時間
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        with Image.open(path) as img:
            exif = img._getexif()
            if exif:
                tag_map = {v: k for k, v in TAGS.items()}
                for tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                    tag_id = tag_map.get(tag_name)
                    if tag_id and tag_id in exif:
                        return datetime.strptime(exif[tag_id], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    # 2. 檔案建立時間（macOS st_birthtime，Windows/Linux fallback 到 st_mtime）
    stat = path.stat()
    birthtime = getattr(stat, "st_birthtime", None)
    if birthtime:
        return datetime.fromtimestamp(birthtime)

    # 3. 修改時間
    return datetime.fromtimestamp(stat.st_mtime)


class PhotoQueue:
    def __init__(self, queue_dir: str, posted_dir: str, failed_dir: str):
        self.queue = Path(queue_dir)
        self.posted = Path(posted_dir)
        self.failed = Path(failed_dir)
        for d in (self.queue, self.posted, self.failed):
            d.mkdir(parents=True, exist_ok=True)

    def list_pending(self) -> list[Path]:
        """回傳佇列中的照片，依拍攝日期由早到晚排序。"""
        files = [f for f in self.queue.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
        return sorted(files, key=_photo_datetime)

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
