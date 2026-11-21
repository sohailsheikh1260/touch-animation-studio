"""Custom-painted timeline widget (ruler, tracks, clips, playhead)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from screens.project_details.clip import Clip
from screens.theme import MUTED


class _PlayheadOverlay(QWidget):
    """Transparent child widget drawing only the moving playhead line.

    Moving/resizing this widget repaints a ~10px vertical strip instead
    of the whole timeline surface each playback tick.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        x = self.width() // 2
        painter.setPen(QPen(QColor("#f43f5e"), 2))
        painter.drawLine(x, 0, x, self.height())
        painter.setBrush(QColor("#f43f5e"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(x - 4, 0, 8, 10, 2, 2)
        painter.end()


class TimelineWidget(QWidget):
    """Custom-painted timeline: ruler, two tracks, playhead and clip editing.

    Clips can be dragged left/right to reposition them (session-local),
    and their left/right edge can be grabbed to change the duration.
    """

    RULER_H = 22
    TRACK_H = 40
    PXS = 40  # pixels per second
    EDGE_GRAB_PX = 7  # grab zone at clip edges
    MIN_CLIP_SEC = 0.5

    def __init__(self, on_seek) -> None:
        super().__init__()
        self.on_seek = on_seek
        self.on_change = None  # optional callback while clips change
        self.on_selection = None  # callable(selected_uid): fires when the selected clip changes
        self.scene_clips: list[Clip] = []
        self.audio_clips: list[Clip] = []
        self.empty_tracks: set[int] = set()
        self.selected_uid: int | None = None
        self.selected_track: int | None = None  # scene track currently selected
        self.playhead = 0.0
        # Collapsed mode: show only the selected timeline row instead of
        # every track (ruler + one row). Wired by the project editor.
        self.show_selected_only = False

        # Drag state
        self._drag_mode: str | None = None  # "move" | "left" | "right"
        self._drag_clip: Clip | None = None
        self._press_x = 0.0
        self._orig_start = 0.0
        self._orig_duration = 0.0

        # Optional callbacks (wired by the project editor):
        self.on_play_toggle = None      # callable(): Space toggles playback
        self.on_remove_selected = None  # callable(): Delete removes the clip
        self.on_drag_end = None         # callable(): flush deferred work

        # Snap targets for drag operations (times in seconds, filled on press)
        self._snap_points: list[float] = []

        # Last hover state — mouse moves only repaint when it changes
        self._hover_key: tuple | None = None

        # Playhead drawn on a tiny transparent overlay widget so playback
        # doesn't repaint the whole timeline 30+ times a second.
        self._playhead_overlay = _PlayheadOverlay(self)
        self._playhead_overlay.show()

        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(self.desired_height())
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def desired_height(self) -> int:
        """Height needed for the ruler + the visible rows (+ small tail).

        With ``show_selected_only`` only the selected row is shown, so the
        collapsed timeline takes a single row height. The audio track only
        exists when there are audio clips; an empty audio lane takes no
        row at all.
        """
        return self.RULER_H + self.TRACK_H * len(self._visible_rows()) + 12

    def _all_rows(self) -> list[tuple[str, int | None]]:
        """Every timeline row as painted, in top-to-bottom order:
        [("scene", track_index), …, ("audio", None)] (audio row last,
        only when it has clips)."""
        rows = [("scene", i) for i in range(self.num_scene_tracks())]
        if self.audio_clips:
            rows.append(("audio", None))
        return rows

    def _selected_row_key(self, rows: list[tuple[str, int | None]]):
        """Which row the current selection points to (any row from ``rows``)."""
        if not rows:
            return None
        if self.selected_uid is not None:
            for clip in self.audio_clips:
                if clip.uid == self.selected_uid:
                    return ("audio", None)
            for clip in self.scene_clips:
                if clip.uid == self.selected_uid and ("scene", clip.track) in rows:
                    return ("scene", clip.track)
        if (
            self.selected_track is not None
            and ("scene", self.selected_track) in rows
        ):
            return ("scene", self.selected_track)
        return rows[0]

    def _visible_rows(self) -> list[tuple[str, int | None]]:
        """The rows currently shown (packed top-to-bottom). All rows in
        normal mode; just the selected row when ``show_selected_only``."""
        rows = self._all_rows()
        if not self.show_selected_only:
            return rows
        key = self._selected_row_key(rows)
        return [key] if key is not None else rows[:1]

    def content_width(self) -> int:
        end = max(
            [c.start + c.duration for c in self.scene_clips + self.audio_clips]
            + [self.playhead, 8]
        )
        # +4 s empty tail so the ruler always extends past the last clip
        return int((end + 4) * self.PXS) + 2

    def num_scene_tracks(self) -> int:
        n = 0
        if self.scene_clips:
            n = max(n, max(c.track for c in self.scene_clips) + 1)
        if getattr(self, "empty_tracks", None):
            n = max(n, max(self.empty_tracks) + 1)
        return n

    def add_clip(self, clip: Clip, track: int | None = None) -> None:
        if clip.kind == "audio":
            target = self.audio_clips
            end = max([c.start + c.duration for c in target] + [0.0])
            clip.start = end
            clip.track = -1
            target.append(clip)
        else:
            if track is None:
                # append to last scene track
                if not self.scene_clips:
                    track = 0
                else:
                    track = max(c.track for c in self.scene_clips)
            end = max([c.start + c.duration for c in self.scene_clips if c.track == track] + [0.0])
            clip.start = end
            clip.track = track
            self.scene_clips.append(clip)
        self.selected_uid = clip.uid
        self._refresh_size()
        if self.on_change:
            self.on_change()

    def delete_track(self, track_index: int) -> None:
        """Remove all clips on a scene track and reindex remaining tracks."""
        self.scene_clips = [c for c in self.scene_clips if c.track != track_index]
        self.empty_tracks.discard(track_index)
        # reindex tracks
        for c in self.scene_clips:
            if c.track > track_index:
                c.track -= 1
        new_empty = set()
        for t in self.empty_tracks:
            if t > track_index:
                new_empty.add(t - 1)
            else:
                new_empty.add(t)
        self.empty_tracks = new_empty
        self.selected_uid = None
        if self.selected_track == track_index:
            self.selected_track = None
        self._refresh_size()
        if self.on_change:
            self.on_change()

    def add_empty_track(self) -> int:
        """Create a new empty scene track row. Returns its index."""
        idx = self.num_scene_tracks()
        self.empty_tracks.add(idx)
        self._refresh_size()
        if self.on_change:
            self.on_change()
        return idx

    def assets_at(self, t: float):
        """Return (background_id, [character_ids], audio_clip) present at time t."""
        background_id = None
        character_ids = []
        audio_clip = None
        for clip in self.scene_clips:
            if clip.start <= t < clip.start + clip.duration:
                kind, asset_id = clip.data
                if kind == "background":
                    background_id = asset_id
                elif kind == "character":
                    character_ids.append(asset_id)
        for clip in self.audio_clips:
            if clip.start <= t < clip.start + clip.duration:
                audio_clip = clip
        return background_id, character_ids, audio_clip

    def total_duration(self) -> float:
        return max(
            [c.start + c.duration for c in self.scene_clips + self.audio_clips]
            + [self.playhead, 1.0]
        )

    # ------------------------------------------------------------ playhead
    def _update_playhead_overlay(self) -> None:
        """Position the overlay strip for the current playhead time."""
        rows = self._visible_rows()
        height = self.RULER_H + self.TRACK_H * len(rows)
        px = int(self.playhead * self.PXS)
        self._playhead_overlay.setGeometry(max(0, px - 5), 0, 10, height)
        self._playhead_overlay.raise_()

    def set_playhead(self, t: float) -> None:
        """Time-based playhead update — cheap overlay move, no full repaint.

        This must always move the overlay (callers may already have set
        ``self.playhead`` themselves — an equality check here would leave
        the cursor frozen onscreen).
        """
        self.playhead = max(0.0, float(t))
        self._update_playhead_overlay()

    # ------------------------------------------------------------ snapping
    def _collect_snap_points(self, exclude: Clip | None) -> list[float]:
        """All edges the queried drag positions may snap to (plus zero)."""
        points = {0.0}
        for clip in self.scene_clips + self.audio_clips:
            if clip is exclude:
                continue
            points.add(clip.start)
            points.add(clip.start + clip.duration)
        return sorted(points)

    def _snap(self, t_value: float) -> float:
        """Snap ``t_value`` to a nearby clip edge (8px tolerance)."""
        threshold = 8.0 / self.PXS
        best, best_d = t_value, threshold
        for point in self._snap_points:
            d = abs(t_value - point)
            if d < best_d:
                best, best_d = point, d
        return best

    # -------------------------------------------------------- keyboard
    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        key = event.key()
        if key == Qt.Key_Space and callable(self.on_play_toggle):
            self.on_play_toggle()
            event.accept()
            return
        if key in (Qt.Key_Delete, Qt.Key_Backspace) and callable(self.on_remove_selected):
            self.on_remove_selected()
            event.accept()
            return
        if key == Qt.Key_Home:
            self.on_seek(0.0)
            event.accept()
            return
        if key == Qt.Key_End:
            self.on_seek(self.total_duration())
            event.accept()
            return
        if key in (Qt.Key_Left, Qt.Key_Right):
            step = 1.0 if (event.modifiers() & Qt.ShiftModifier) else 0.25
            t = self.playhead - step if key == Qt.Key_Left else self.playhead + step
            self.on_seek(max(0.0, t))
            event.accept()
            return
        super().keyPressEvent(event)

    def _refresh_size(self) -> None:
        # At least as wide as the visible viewport (machine/window width),
        # and wider when clips extend past it. Height follows the track count,
        # so the widget shrinks/grows as tracks are added or deleted.
        viewport = self.parentWidget()
        visible_width = viewport.width() if viewport is not None else 0
        width = max(self.content_width(), visible_width)
        height = self.desired_height()
        self.setMinimumWidth(width)
        self.setMinimumHeight(height)
        self.resize(width, height)
        self._update_playhead_overlay()
        self.update()

    def select_by_kind(self, kind: str) -> int | None:
        """Uid of the last (rightmost) clip of a kind - used by 'add' defaults."""
        target = self.audio_clips if kind == "audio" else self.scene_clips
        return target[-1].uid if target else None

    def select_track(self, track_index: int) -> None:
        """Select a scene track (only one timeline row can be selected at a time)."""
        self.selected_track = track_index
        self.update()

    def remove_selected(self) -> bool:
        """Remove the currently selected clip (if any)."""
        if self.selected_uid is None:
            return False
        for track in (self.scene_clips, self.audio_clips):
            for clip in track:
                if clip.uid == self.selected_uid:
                    track.remove(clip)
                    self.selected_uid = None
                    self._refresh_size()
                    if self.on_selection is not None:
                        self.on_selection(None)
                    return True
        return False

    # ------------------------------------------------------------ events
    def _row_at_y(self, y: float):
        """The visible (kind, index) row under y — None beyond the last row."""
        rows = self._visible_rows()
        idx = int((y - self.RULER_H) // self.TRACK_H)
        if idx < 0 or idx >= len(rows):
            return None
        return rows[idx]

    def _clip_at(self, y: float, t: float) -> Clip | None:
        """The clip under (y, t), searching the relevant track first."""
        row = self._row_at_y(y)
        if row is None:
            return None
        kind, track_index = row
        if kind == "scene":
            for clip in self.scene_clips:
                if clip.track == track_index and clip.start <= t < clip.start + clip.duration:
                    return clip
            return None
        # audio row
        for clip in self.audio_clips:
            if clip.start <= t < clip.start + clip.duration:
                return clip
        return None

    def _edge_kind_at(self, clip: Clip, t: float) -> str | None:
        """'left' or 'right' if t is within the grab zone of a clip edge."""
        px_edge = self.EDGE_GRAB_PX / self.PXS
        if t <= clip.start + px_edge:
            return "left"
        if t >= clip.start + clip.duration - px_edge:
            return "right"
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        x, y = event.position().x(), event.position().y()
        prev_selection = self.selected_uid

        # Ruler clicks seek
        if 0 <= y <= self.RULER_H:
            self.playhead = max(0.0, x / self.PXS)
            self.selected_uid = None
            self._update_playhead_overlay()
            self.update()
            self.on_seek(self.playhead)
            self._emit_selection(prev_selection)
            return

        t = x / self.PXS
        clip = self._clip_at(y, t)
        self.setFocus(Qt.MouseFocusReason)
        if clip is not None:
            self.selected_uid = clip.uid
            edge = self._edge_kind_at(clip, t)
            self._drag_mode = edge or "move"
            self._drag_clip = clip
            self._press_x = x
            self._orig_start = clip.start
            self._orig_duration = clip.duration
            self._snap_points = self._collect_snap_points(clip)
            self.setCursor(
                Qt.SizeHorCursor if edge else Qt.ClosedHandCursor
            )
        else:
            self.selected_uid = None
        self.update()
        self._emit_selection(prev_selection)

    def _emit_selection(self, prev: int | None) -> None:
        """Notify on_selection when the selected clip changed."""
        if self.selected_uid != prev and self.on_selection is not None:
            self.on_selection(self.selected_uid)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        x, y = event.position().x(), event.position().y()

        # ---- Dragging in progress ----
        if self._drag_mode and self._drag_clip is not None:
            delta_t = (x - self._press_x) / self.PXS
            clip = self._drag_clip
            if self._drag_mode == "move":
                raw_start = max(0.0, self._orig_start + delta_t)
                # Snap whichever edge lands closest to a target
                snap_start = self._snap(raw_start)
                snap_end_start = min(raw_start, self._snap(raw_start + clip.duration) - clip.duration)
                candidates = [c for c in (snap_start, snap_end_start) if c >= 0.0]
                clip.start = min(candidates, key=lambda c: abs(c - raw_start)) if candidates else raw_start
            elif self._drag_mode == "left":
                end = self._orig_start + self._orig_duration
                new_start = min(max(0.0, self._snap(self._orig_start + delta_t)), end - self.MIN_CLIP_SEC)
                clip.start = new_start
                clip.duration = end - new_start
            else:  # right edge
                end = clip.start + max(
                    self.MIN_CLIP_SEC, self._orig_duration + delta_t
                )
                clip.duration = max(
                    self.MIN_CLIP_SEC, self._snap(end) - clip.start
                )
            self.update()
            if self.on_change:
                self.on_change()
            return

        # ---- Hover feedback (no drag) — repaint only when it changes ----
        if not self._drag_mode:
            t = x / self.PXS
            clip = self._clip_at(y, t)
            edge = self._edge_kind_at(clip, t) if clip is not None else None
            cursor_key: tuple | bool | None = (
                (clip.uid, edge) if clip is not None
                else (None if 0 <= y <= self.RULER_H else False)
            )
            if cursor_key == self._hover_key:
                return  # nothing changed — skip cursor churn & repaint
            self._hover_key = cursor_key
            if clip is not None:
                self.setCursor(Qt.SizeHorCursor if edge else Qt.OpenHandCursor)
            elif cursor_key is None:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._drag_mode:
            self._drag_mode = None
            self._press_x = 0.0
            self._snap_points = []
            self.setCursor(Qt.OpenHandCursor)
            self.update()
            if callable(self.on_drag_end):
                # Persist the final clip positions right away (not only
                # at the end of a debounce window).
                self.on_drag_end()
            return
        self._hover_key = None
        self.update()

    # ------------------------------------------------------------ paint
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        # Never paint more than the damaged rect asked for
        painter.setClipRect(event.rect())
        w = max(self.width(), self.content_width())

        # Background
        painter.fillRect(self.rect(), QColor("#111827"))

        # Ruler
        painter.fillRect(0, 0, w, self.RULER_H, QColor("#1f2937"))
        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(QFont("Segoe UI", 8))
        step = 1
        for sec in range(0, int(w / self.PXS) + 1, step):
            x = sec * self.PXS
            painter.drawLine(x, self.RULER_H - 6, x, self.RULER_H)
            painter.drawText(x + 3, 14, f"{sec}s")

        # Track lanes (packed visible rows)
        visible = self._visible_rows()
        for vidx, (_kind, _idx) in enumerate(visible):
            y0 = self.RULER_H + vidx * self.TRACK_H
            color = "#0b1220" if vidx % 2 == 0 else "#111827"
            painter.fillRect(0, y0, w, self.TRACK_H, QColor(color))

        painter.setFont(QFont("Segoe UI", 9))
        for vidx, (kind, ti) in enumerate(visible):
            lane_y = self.RULER_H + vidx * self.TRACK_H
            color = "#0b1220" if vidx % 2 == 0 else "#111827"
            painter.setPen(QPen(QColor("#334155")))
            painter.drawLine(0, lane_y + self.TRACK_H, w, lane_y + self.TRACK_H)
            if kind == "scene":
                painter.fillRect(
                    0, lane_y, w, self.TRACK_H,
                    QColor("#1e2a44" if ti == self.selected_track else color),
                )
                for clip in self.scene_clips:
                    if clip.track != ti:
                        continue
                    x = int(clip.start * self.PXS)
                    cw = int(clip.duration * self.PXS) - 2
                    selected = clip.uid == self.selected_uid
                    block = QColor("#0891b2")
                    if selected:
                        block = block.lighter(130)
                    painter.setBrush(block)
                    painter.setPen(
                        QPen(QColor("#fde047") if selected else QColor("#e2e8f0"), 2)
                    )
                    painter.drawRoundedRect(x + 1, lane_y + 5, cw, self.TRACK_H - 12, 6, 6)
                    painter.setPen(QPen(QColor("#e2e8f0")))
                    label = f"🎞 {clip.name}"
                    max_chars = max(4, cw // 9)
                    painter.drawText(x + 8, lane_y + 5 + 16, label[:max_chars])
                    if selected:
                        painter.setPen(QPen(QColor("#fde047"), 3))
                        painter.drawLine(x + 2, lane_y + 7, x + 2, lane_y + self.TRACK_H - 8)
                        painter.drawLine(
                            x + cw - 1, lane_y + 7, x + cw - 1, lane_y + self.TRACK_H - 8
                        )
            else:
                for clip in self.audio_clips:
                    x = int(clip.start * self.PXS)
                    cw = int(clip.duration * self.PXS) - 2
                    selected = clip.uid == self.selected_uid
                    block = QColor("#7c3aed")
                    if selected:
                        block = block.lighter(130)
                    painter.setBrush(block)
                    painter.setPen(
                        QPen(QColor("#fde047") if selected else QColor("#e2e8f0"), 2)
                    )
                    painter.drawRoundedRect(x + 1, lane_y + 5, cw, self.TRACK_H - 12, 6, 6)
                    painter.setPen(QPen(QColor("#e2e8f0")))
                    label = f"🎵 {clip.name}"
                    max_chars = max(4, cw // 9)
                    painter.drawText(x + 8, lane_y + 5 + 16, label[:max_chars])
                    if selected:
                        painter.setPen(QPen(QColor("#fde047"), 3))
                        painter.drawLine(x + 2, lane_y + 7, x + 2, lane_y + self.TRACK_H - 8)
                        painter.drawLine(
                            x + cw - 1, lane_y + 7, x + cw - 1, lane_y + self.TRACK_H - 8
                        )

        # (Playhead is drawn by _PlayheadOverlay — see __init__ / set_playhead)
        painter.end()
