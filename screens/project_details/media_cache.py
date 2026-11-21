"""Caches so the project-editor preview never repeats heavy work per frame.

The old render path re-decoded PNGs from disk, re-scaled full-resolution
images and opened fresh SQLite connections on every animation tick (the
``database.*`` helpers each call ``sqlite3.connect``). That made editor
playback/scrubbing feel heavy. This module keeps:

- decoded pixmaps by (asset identity, file mtime) — invalidates when the
  file on disk changes;
- scaled pixmap variants by (source key, target size, aspect, mode);
- a small LRU for assembled character canvases;
- database rows cached for a short TTL, so repeated per-frame lookups
  don't open a new SQLite connection each time (and missing new rows
  written elsewhere self-heals within a couple of seconds).
"""

import os
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

# SQLite row objects wrap a live connection, so they must be converted
# to plain dict values before being stored in the TTL cache.
_DB_TTL_SECONDS = 2.5


def _mtime(path) -> float:
    try:
        return os.stat(str(path)).st_mtime
    except OSError:
        return -1.0


# Public alias (used for cache keys in the project editor).
file_mtime = _mtime


class _LRU:
    """Minimal insertion-order LRU built on a dict (Python 3.7+ order)."""

    def __init__(self, max_entries: int) -> None:
        self.max_entries = max(1, max_entries)
        self.data: dict = {}

    def get(self, key):
        value = self.data.get(key)
        if value is not None:  # refresh recency
            self.data[key] = self.data.pop(key)
        return value

    def put(self, key, value) -> None:
        if key in self.data:
            self.data.pop(key)
        self.data[key] = value
        while len(self.data) > self.max_entries:
            self.data.pop(next(iter(self.data)), None)


def row_to_dict(row) -> dict | None:
    """sqlite3.Row -> plain dict (safe to keep across connections)."""
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


class AssetCache:
    """Per-editor caching of pixmaps and short-lived DB query results."""

    def __init__(self) -> None:
        self._pixmaps = _LRU(24)     # full decodes (few MB each)
        self._scaled = _LRU(64)      # display-size variants (small)
        self._canvases = _LRU(8)     # assembled character canvases
        self._db: dict = {}

    # ------------------------------------------------------------ pixmaps
    def pixmap(self, key, path) -> QPixmap:
        """Decode ``path`` once; re-decode only when the file changes."""
        p = str(path) if path else ""
        if not p:
            return QPixmap()
        mt = _mtime(p)
        if mt < 0:
            return QPixmap()
        cache_key = (key, round(mt, 3))
        pix = self._pixmaps.get(cache_key)
        if pix is None:
            pix = QPixmap(p)
            self._pixmaps.put(cache_key, pix)
        return pix

    def scaled(
        self,
        key,
        source: QPixmap,
        width: int,
        height: int,
        aspect: Qt.AspectRatioMode = Qt.KeepAspectRatio,
        mode=Qt.SmoothTransformation,
    ) -> QPixmap:
        """Cached ``source.scaled(...)`` for repeated identical targets."""
        if source.isNull() or width <= 0 or height <= 0:
            return QPixmap()
        cache_key = (key, width, height, str(aspect), str(mode))
        pix = self._scaled.get(cache_key)
        if pix is None:
            pix = source.scaled(width, height, aspect, mode)
            self._scaled.put(cache_key, pix)
        return pix

    # ---------------------------------------------------------- canvases
    def canvas(self, key, factory):
        """Cache a composed (larger) pixmap built by ``factory()``."""
        pix = self._canvases.get(key)
        if pix is None:
            pix = factory()
            self._canvases.put(key, pix)
        return pix

    # ------------------------------------------------------- db lookup
    def db(self, key, loader, ttl: float = _DB_TTL_SECONDS):
        """Query ``loader()`` at most once per ``ttl`` seconds per key.

        sqlite3.Row results are converted to plain dicts so they survive
        after the short-lived connections close.
        """
        entry = self._db.get(key)
        now = time.monotonic()
        if entry is not None and now - entry[0] < ttl:
            return entry[1]
        value = loader()
        if isinstance(value, tuple):
            self._db[key] = (now, tuple(row_to_dict(v) for v in value))
        elif hasattr(value, "keys"):  # sqlite3.Row
            self._db[key] = (now, row_to_dict(value))
        elif isinstance(value, list):
            self._db[key] = (now, [row_to_dict(v) for v in value])
        else:
            self._db[key] = (now, value)
        return self._db[key][1]

    # ------------------------------------------------------------ reset
    def clear_db(self) -> None:
        self._db.clear()
