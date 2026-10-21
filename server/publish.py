"""Publisher: build a release, commit to the DB, atomically swap `current`.

Every owner save goes through Publisher.apply(). The build runs first; only
if it succeeds are the changes committed and the symlink swapped.

build_site uses module-level globals and is not thread-safe, so every build
(including rebuild()) happens under the single Publisher lock.
"""
import os
import secrets
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from build import build_site
from content import default_content, merge

KEEP_RELEASES = 3
_EXT = {"image/jpeg": "jpg", "image/png": "png"}


class Publisher:
    def __init__(self, store, site_root):
        self.store = store
        self.site_root = Path(site_root)
        self._lock = threading.Lock()
        self._photo_cache: dict[str, bytes] = {}   # sha -> bytes
        self._content: dict | None = None

    # ── public API ──────────────────────────────────────────────────────────
    def current_dir(self) -> Path | None:
        link = self.site_root / "current"
        return link.resolve() if link.exists() else None

    def content(self) -> dict:
        """Merged content currently live, WITHOUT the private `_photos` key.

        Falls back to the stored content if nothing has been published yet.
        """
        c = self._content
        if c is None:
            c = merge(default_content(), self.store.load())
        return c

    def rebuild(self) -> None:
        self.apply(lambda view: {})

    def apply(self, mutate: Callable[[dict], dict]) -> None:
        with self._lock:
            stored = self.store.load()
            view = merge(default_content(), stored)
            changes = mutate(view)                       # may raise ValidationError
            candidate = merge(default_content(), {**stored, **changes})
            release = self._new_release_dir()
            try:
                files, photos = self._photo_files()
                candidate["_photos"] = photos
                build_site(candidate, release, extra_files=files)
                if changes:
                    self.store.save_sections(changes)
                self._swap(release)
            except Exception:
                shutil.rmtree(release, ignore_errors=True)
                raise
            candidate.pop("_photos", None)
            self._content = candidate
            self._prune()

    # ── internals ───────────────────────────────────────────────────────────
    def _new_release_dir(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        releases = self.site_root / "releases"
        releases.mkdir(parents=True, exist_ok=True)
        return releases / f"{stamp}-{secrets.token_hex(2)}"

    def _photo_files(self):
        """({"uploads/<sha12>.<ext>": bytes}, {photo_id: "uploads/..."})."""
        files, photos = {}, {}
        metas = [m for m in self.store.list_photos() if m["mime"] in _EXT]
        live = {m["sha"] for m in metas}
        self._photo_cache = {s: b for s, b in self._photo_cache.items() if s in live}
        for m in metas:
            if m["sha"] not in self._photo_cache:
                row = self.store.get_photo(m["id"])
                if row is None:
                    continue
                self._photo_cache[m["sha"]] = row["data"]
            rel = f"uploads/{m['sha'][:12]}.{_EXT[m['mime']]}"
            files[rel] = self._photo_cache[m["sha"]]
            photos[m["id"]] = rel
        return files, photos

    def _swap(self, release: Path) -> None:
        tmp = self.site_root / f".current-{secrets.token_hex(4)}"
        os.symlink(release, tmp)
        try:
            os.replace(tmp, self.site_root / "current")
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def _prune(self) -> None:
        live = self.current_dir()
        dirs = sorted(p for p in (self.site_root / "releases").iterdir() if p.is_dir())
        keep = set(dirs[-KEEP_RELEASES:])
        for p in dirs:
            if p not in keep and p.resolve() != live:
                shutil.rmtree(p, ignore_errors=True)
