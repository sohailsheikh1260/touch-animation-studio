"""Project editor page - a video-editor style view for a project's details.

Layout:
- Top bar: back button, project name, Edit/Delete project buttons.
- Left: media library (characters, backgrounds, audios from the database).
- Center: live preview canvas (background + character composite).
- Bottom: timeline with a scene track + audio track, ruler, playhead and
  transport controls.

Timeline clips are session-local (not saved to SQLite yet).
"""

from PySide6.QtCore import QElapsedTimer, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import database
import json
import math
from screens.background import image_store as background_store
from screens.character import image_store as character_store
from screens.character.character_screen import CharacterScreen
from screens.project_details.audio_editor import AudioEditorMixin
from screens.project_details.clip import (
    MAX_CHARACTER_SIZE_PCT,
    MIN_CHARACTER_SIZE_PCT,
    Clip,
)
from screens.project_details.media_cache import AssetCache, file_mtime
from screens.project_details.preview_editor import (
    STAGE_MAX_H,
    STAGE_MAX_W,
    PreviewEditorMixin,
    SelectablePreviewLabel,  # re-exported for existing importers
)
from screens.project_details.editor_leftsidebar import (
    BUTTON_STYLE,
    EditorLeftSidebar,
    LIST_STYLE,
    PANEL_LABEL_STYLE,
    PANEL_STYLE,
)
from screens.project_details.screen_presets import DEFAULT_PRESET_ID, preset_by_id
from screens.project_details.timeline_scroll import TimelineScroll
from screens.project_details.timeline_widget import TimelineWidget
from screens.project_details import character_animator
from screens.project_details.video_exporter import ExportWorker
from screens.theme import MUTED, TEXT

ICON = "🎬"

EDIT_BUTTON_STYLE = (
    "QPushButton { background-color: #1d4ed8; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 8px 18px;"
    "  font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #2563eb; }"
)
DELETE_BUTTON_STYLE = (
    "QPushButton { background-color: #7f1d1d; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 8px 18px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
)

DEFAULT_SCENE_SEC = 3
TICK_MS = 16  # ~60 Hz playback clock (time-based, see _tick)
RENDER_MS = 33  # preview re-render throttle (~30 FPS is plenty)
RULER_SNAP_PX = 8  # timeline drag snapping tolerance


class ProjectEditorPage(AudioEditorMixin, PreviewEditorMixin, QWidget):
    """Video-editor styled page for a project."""

    def __init__(self, screen, parent: QWidget | None = None) -> None:
        """`screen` is the owning ProjectScreen (for drawer/back handlers)."""
        super().__init__(parent)
        self.screen = screen
        self.project_id: int | None = None
        self._export_worker: ExportWorker | None = None
        self._retired_workers: list[ExportWorker] = []

        # Preview stage defaults (overridden by _load_stage)
        self.stage_width, self.stage_height = 1280, 720
        self.stage_preset_id = DEFAULT_PRESET_ID
        self._render_w, self._render_h = STAGE_MAX_W, STAGE_MAX_H

        self._init_audio()

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.playing = False
        self._loop_enabled = False

        # Asset caches (decoded pixmaps, scaled variants, short-TTL DB rows)
        self._cache = AssetCache()

        # Playback clock: playhead derived from real elapsed time so the
        # preview stays smooth even if timer ticks jitter.
        self._play_clock = QElapsedTimer()
        self._play_start = 0.0  # playhead position when playback started
        self._render_clock = QElapsedTimer()
        self._render_clock.restart()

        # Preview coalescing: several change callbacks in one event burst
        # produce a single re-render.
        self._preview_dirty = False
        self._preview_coalescer = QTimer(self)
        self._preview_coalescer.setSingleShot(True)
        self._preview_coalescer.setInterval(0)
        self._preview_coalescer.timeout.connect(self._do_preview_render)

        # Persist + track-button rebuilds are debounced: dragging a clip
        # fires dozens of change callbacks per second and rewriting the
        # SQLite table / recreating buttons on each one made drag feel
        # heavy. The mouse release (on_drag_end) flushes immediately.
        self._persist_dirty = False
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(350)
        self._persist_timer.timeout.connect(self._flush_deferred)

        self.left_sidebar = EditorLeftSidebar()
        self.left_sidebar.on_add_timeline_row = self._on_add_empty_track
        self.left_sidebar.on_remove_selected = self._on_remove_selected
        self.left_sidebar.on_add_asset_to_timeline = self._on_add_asset_to_timeline
        # Text tool in the Tools tab: add a text overlay clip.
        self.left_sidebar.on_add_text = self._on_add_text
        # Audio tab: open the existing Add Audio drawer.
        self.left_sidebar.on_add_audio = self._open_add_audio
        # "✎" on a character row: leave the editor, open Character Details
        self.left_sidebar.on_edit_character = self._open_character_details
        self.left_sidebar.on_scale_changed = self._on_scale_changed
        self.left_sidebar.on_scale_commit = self._on_scale_commit
        self.left_sidebar.on_position_changed = self._on_position_changed
        self.left_sidebar.on_position_commit = self._on_position_commit
        self.left_sidebar.on_flip_h = self._on_flip_h
        self.left_sidebar.on_flip_v = self._on_flip_v
        self.left_sidebar.on_speed_changed = self._on_speed_changed
        self.left_sidebar.on_speed_commit = self._on_speed_commit
        self.left_sidebar.on_zoom_changed = self._on_zoom_changed
        self.left_sidebar.on_zoom_commit = self._on_zoom_commit
        self.left_sidebar.on_nudge = self._on_nudge

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        root.addWidget(self._build_top_bar())
        center = QHBoxLayout()
        center.setSpacing(12)
        center.addWidget(self.left_sidebar, 0)
        center.addWidget(self._build_preview_panel(), 1)
        root.addLayout(center, 1)
        root.addWidget(self._build_timeline_panel())

        # Add Audio slider, embedded in this page so the editor stays visible.
        self._setup_audio_drawer()

        self._stop_playback()

    # The timeline track bases must follow the machine's window width
    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if hasattr(self, "timeline"):
            self.timeline._refresh_size()
        self._resize_audio_drawer()

    # ------------------------------------------------------------ building
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(PANEL_STYLE)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        back_btn = QPushButton("← Back to Projects")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(BUTTON_STYLE)
        back_btn.clicked.connect(self.screen.show_projects)

        self.project_label = QLabel("Project")
        self.project_label.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: bold; {PANEL_LABEL_STYLE}"
        )
        self.project_desc = QLabel("")
        self.project_desc.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )

        edit_btn = QPushButton("✏ Edit")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet(EDIT_BUTTON_STYLE)
        edit_btn.clicked.connect(lambda: self.screen.open_drawer(self.project_id))

        delete_btn = QPushButton("🗑 Delete")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(DELETE_BUTTON_STYLE)
        delete_btn.clicked.connect(self.screen.delete_current_project)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; {PANEL_LABEL_STYLE}"
        )

        layout.addWidget(back_btn)
        layout.addSpacing(8)
        label_col = QVBoxLayout()
        label_col.setSpacing(0)
        label_col.addWidget(self.project_label)
        label_col.addWidget(self.project_desc)
        layout.addLayout(label_col)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        return bar

    # ------------------------------------------------------- screen size
    def _set_custom_row_visible(self, visible: bool) -> None:
        for widget in self._custom_widgets:
            widget.setVisible(visible)

    def _current_preset(self) -> dict:
        preset_id = self.stage_combo.currentData()
        return preset_by_id(preset_id) or preset_by_id(DEFAULT_PRESET_ID)

    def _on_preset_changed(self, _index: int) -> None:
        preset = self._current_preset()
        is_custom = preset["id"] == "custom"
        self._set_custom_row_visible(is_custom)
        if is_custom:
            # Seed the boxes with the previous stage size
            self.width_spin.blockSignals(True)
            self.height_spin.blockSignals(True)
            self.width_spin.setValue(self.stage_width)
            self.height_spin.setValue(self.stage_height)
            self.width_spin.blockSignals(False)
            self.height_spin.blockSignals(False)
        self._apply_stage(preset["width"], preset["height"], preset["id"])
        self._save_stage()

    def _on_custom_size_changed(self) -> None:
        preset = self._current_preset()
        if preset["id"] != "custom":
            return
        self._apply_stage(
            self.width_spin.value(), self.height_spin.value(), "custom"
        )
        self._save_stage()

    def _apply_stage(self, width: int, height: int, preset_id: str) -> None:
        """Resize the preview canvas to the stage aspect (fit into the box)."""
        self.stage_width, self.stage_height = width, height
        self.stage_preset_id = preset_id

        scale = min(
            STAGE_MAX_W / max(1, width), STAGE_MAX_H / max(1, height)
        )
        render_w = max(120, int(width * scale))
        render_h = max(90, int(height * scale))
        self._render_w, self._render_h = render_w, render_h
        self.preview.setText("")
        self.preview.setPixmap(QPixmap())  # clear before resize
        self.preview.setFixedSize(render_w, render_h)
        if not self.timeline.scene_clips and not self.timeline.audio_clips:
            self._render_preview()  # re-render the placeholder

    def _save_stage(self) -> None:
        if self.project_id is not None:
            database.update_project_screen_size(
                self.project_id, self.stage_preset_id, self.stage_width, self.stage_height
            )
            self.status_label.setText(
                f"Screen size: {self.stage_width}×{self.stage_height}"
            )

    def _load_stage(self) -> None:
        """Apply the stage saved for the loaded project."""
        project = database.get_project(self.project_id) if self.project_id else None
        preset_id = project["screen_preset"] if project else DEFAULT_PRESET_ID
        if not preset_by_id(preset_id):
            preset_id = DEFAULT_PRESET_ID
        preset = preset_by_id(preset_id)

        self.stage_combo.blockSignals(True)
        index = self.stage_combo.findData(preset_id)
        if index >= 0:
            self.stage_combo.setCurrentIndex(index)
        self.stage_combo.blockSignals(False)

        is_custom = preset_id == "custom"
        self._set_custom_row_visible(is_custom)
        custom_w = project["screen_width"] if is_custom and project else preset["width"]
        custom_h = project["screen_height"] if is_custom and project else preset["height"]

        self._apply_stage(custom_w, custom_h, preset_id)

    def _build_timeline_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(6)
        caption = QLabel("🎞 Timeline")
        caption.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; font-weight: bold; {PANEL_LABEL_STYLE}"
        )
        header.addWidget(caption)
        header.addStretch()
        self._timeline_toggle_btn = QPushButton("▾ Collapse")
        self._timeline_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._timeline_toggle_btn.setToolTip(
            "Collapse the timeline to give more space to the preview"
        )
        self._timeline_toggle_btn.setStyleSheet(
            "QPushButton { background-color: #334155; color: #e2e8f0;"
            "  border: none; border-radius: 6px; padding: 3px 10px;"
            "  font-size: 11px; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self._timeline_toggle_btn.clicked.connect(self._on_toggle_timeline)
        self._timeline_collapsed = False
        header.addWidget(self._timeline_toggle_btn)
        layout.addLayout(header)

        # Collapsible timeline body: tracks + ruler + the Add button. The
        # transport bar below stays visible so play/export remain usable
        # while the timeline is collapsed.
        self._timeline_body = QWidget()
        body_layout = QVBoxLayout(self._timeline_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        layout.addWidget(self._timeline_body)

        self.timeline = TimelineWidget(self._on_seek)
        # Live preview while clips are moved/resized + persist to SQLite
        self.timeline.on_change = self._on_timeline_change
        self.timeline.on_selection = self._on_timeline_selection_changed
        # Timeline keyboard + drag-end hooks
        self.timeline.on_play_toggle = self._on_play_toggle
        self.timeline.on_remove_selected = self._on_remove_selected
        self.timeline.on_drag_end = self._flush_deferred
        scroll = TimelineScroll(self.timeline)
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self.timeline)
        self._timeline_scroll = scroll
        self._fit_timeline_height()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ---- Delete-track column on the LEFT of the timeline ----
        self._track_btn_col = QVBoxLayout()
        self._track_btn_col.setContentsMargins(0, 0, 0, 0)
        self._track_btn_col.setSpacing(0)
        track_col_widget = QWidget()
        track_col_widget.setLayout(self._track_btn_col)
        track_col_widget.setFixedWidth(48)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        row_layout.addWidget(track_col_widget)
        row_layout.addWidget(scroll)
        body_layout.addLayout(row_layout)

        add_empty_btn = QPushButton("＋ Add")
        add_empty_btn.setCursor(Qt.PointingHandCursor)
        add_empty_btn.setStyleSheet(BUTTON_STYLE)
        add_empty_btn.clicked.connect(self._on_add_empty_track)
        body_layout.addWidget(add_empty_btn)

        self._rebuild_track_buttons()

        # ---- Transport bar ----
        transport = QHBoxLayout()
        transport.setSpacing(8)
        self.export_btn = QPushButton("⬇ Export Video")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setStyleSheet(
            "QPushButton { background-color: #b45309; color: #e2e8f0;"
            "  border: none; border-radius: 8px; padding: 8px 16px;"
            "  font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #d97706; }"
            "QPushButton:disabled { color: #64748b; background-color: #334155; }"
        )
        self.export_btn.clicked.connect(self._on_export)
        transport.addWidget(self.export_btn)
        # Export progress bar: only visible while an export runs.
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_progress.setFixedSize(180, 22)
        self.export_progress.setVisible(False)
        self.export_progress.setStyleSheet(
            "QProgressBar { background-color: #1e293b; color: #e2e8f0;"
            "  border: 1px solid #334155; border-radius: 8px;"
            "  text-align: center; font-size: 11px; font-weight: bold; }"
            "QProgressBar::chunk { background-color: #d97706;"
            "  border-radius: 7px; }"
        )
        transport.addWidget(self.export_progress)
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setFixedSize(96, 36)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: #e2e8f0;"
            "  border: none; border-radius: 8px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #22c55e; }"
        )
        self.play_btn.clicked.connect(self._on_play_toggle)
        self.loop_btn = QPushButton("↻ Loop")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setFixedSize(96, 36)
        self.loop_btn.setCursor(Qt.PointingHandCursor)
        self.loop_btn.setToolTip("Restart from the beginning when playback reaches the end")
        self.loop_btn.setStyleSheet(
            "QPushButton { background-color: #334155; color: #e2e8f0;"
            "  border: none; border-radius: 8px; font-size: 14px; }"
            "QPushButton:hover { background-color: #475569; }"
            "QPushButton:checked { background-color: #0e7490; color: #ecfeff; }"
        )
        self.loop_btn.toggled.connect(self._on_loop_toggled)
        from_btn = QPushButton("⏮ Start")
        from_btn.setCursor(Qt.PointingHandCursor)
        from_btn.setStyleSheet(BUTTON_STYLE)
        from_btn.clicked.connect(lambda: self._on_seek(0.0))
        self.time_label = QLabel("00:00.0")
        self.time_label.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; font-weight: bold; {PANEL_LABEL_STYLE}"
        )
        hint = QLabel(
            "Drag a clip to move it · grab its edges (yellow handles) to change duration · "
            "click the ruler to scrub · Space = play/pause · Delete = remove clip · "
            "←/→ = step 0.25s (Shift = 1s) · Home/End"
        )
        hint.setStyleSheet(f"color: {MUTED}; font-size: 11px; {PANEL_LABEL_STYLE}")

        transport.addWidget(self.play_btn)
        transport.addWidget(self.loop_btn)
        transport.addWidget(from_btn)
        transport.addSpacing(10)
        transport.addWidget(self.time_label)
        transport.addStretch()
        transport.addWidget(hint)
        layout.addLayout(transport)
        return panel

    def _on_toggle_timeline(self) -> None:
        """Show/hide the timeline tracks (transport bar stays visible)."""
        self._timeline_collapsed = not self._timeline_collapsed
        self._timeline_body.setVisible(not self._timeline_collapsed)
        # Collapsed: show only the selected timeline row (ruler + one row);
        # Expanding: bring back every track row.
        self.timeline.show_selected_only = self._timeline_collapsed
        self.timeline._refresh_size()
        self._fit_timeline_height()
        self._timeline_toggle_btn.setText(
            "▸ Expand" if self._timeline_collapsed else "▾ Collapse"
        )

    def _rebuild_track_buttons(self) -> None:
        """Rebuild per-track select/delete buttons on the left of the timeline."""
        while self._track_btn_col.count():
            item = self._track_btn_col.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        spacer = QWidget()
        spacer.setFixedHeight(self.timeline.RULER_H)
        self._track_btn_col.addWidget(spacer)
        num_scene = self.timeline.num_scene_tracks()
        for ti in range(num_scene):
            row = QWidget()
            row.setFixedHeight(self.timeline.TRACK_H - 4)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            sel_btn = QPushButton("✓")
            sel_btn.setFixedSize(18, 18)
            sel_btn.setCursor(Qt.PointingHandCursor)
            sel_btn.setStyleSheet(
                "QPushButton { background-color: #14532d; color: #86efac; border: none; "
                "border-radius: 4px; padding: 0; font-size: 11px; font-weight: bold; }"
                "QPushButton:hover { background-color: #166534; }"
            )
            sel_btn.clicked.connect(lambda checked=False, t=ti: self.timeline.select_track(t))
            row_layout.addWidget(sel_btn)
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(24, self.timeline.TRACK_H - 4)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton { background-color: #7f1d1d; color: #ffffff; border: none; "
                "border-radius: 4px; padding: 0; font-size: 12px; font-weight: bold; }"
                "QPushButton:hover { background-color: #991b1b; }"
            )
            del_btn.clicked.connect(lambda checked=False, t=ti: self._delete_track(t))
            row_layout.addWidget(del_btn)
            self._track_btn_col.addWidget(row)
        audio_row = self._build_audio_track_delete_row()
        if audio_row is not None:
            self._track_btn_col.addWidget(audio_row)
        self._track_btn_col.addStretch()

    def _delete_track(self, track_index: int) -> None:
        self.timeline.delete_track(track_index)
        self._rebuild_track_buttons()
        self._on_timeline_change()
        self._render_preview()

    # ------------------------------------------------------------- public
    def load(self, project_id: int) -> None:
        # Flush pending clip edits for the previous project before switching.
        self._flush_deferred()
        self._hide_audio_drawer()
        self._preview_coalescer.stop()
        self._preview_dirty = False
        self._cache.clear_db()
        self._last_frame_sig = None
        self.project_id = project_id
        self.timeline.scene_clips.clear()
        self.timeline.audio_clips.clear()
        self.timeline.selected_uid = None
        self.timeline.selected_track = None
        self.timeline.playhead = 0.0
        self._stop_playback()
        self.left_sidebar.set_project(project_id)
        self.left_sidebar._refresh_media()
        self._refresh_header()
        self._load_stage()
        # Restore saved timeline clips from SQLite
        for row in database.list_clips(project_id):
            kind = "scene" if row["kind"] == "scene" else "audio"
            track = row["track"] if "track" in row.keys() else 0
            anim = row["animation"] if "animation" in row.keys() else "idle"
            x_off = float(row["x_offset"]) if "x_offset" in row.keys() else 0.0
            y_off = float(row["y_offset"]) if "y_offset" in row.keys() else 0.0
            size_off = float(row["size_scale"]) if "size_scale" in row.keys() else 1.0
            x_end = float(row["x_end"]) if "x_end" in row.keys() and row["x_end"] is not None else None
            y_end = float(row["y_end"]) if "y_end" in row.keys() and row["y_end"] is not None else None
            spd = float(row["anim_speed"]) if "anim_speed" in row.keys() else 1.0
            z_start = float(row["zoom_start"]) if "zoom_start" in row.keys() else 1.0
            z_end = float(row["zoom_end"]) if "zoom_end" in row.keys() and row["zoom_end"] is not None else None
            clip = Clip(
                float(row["start"]),
                float(row["duration"]),
                f"{kind}-{row['asset_kind']}-{row['asset_id']}",
                kind,
                (row["asset_kind"], int(row["asset_id"])),
                track=int(track) if kind == "scene" else -1,
                animation=str(anim or "idle"),
                x_offset=x_off,
                y_offset=y_off,
                size_scale=size_off,
                x_end=x_end,
                y_end=y_end,
                anim_speed=spd if spd > 0 else 1.0,
                zoom_start=z_start if z_start > 0 else 1.0,
                zoom_end=z_end if z_end is None or z_end > 0 else None,
                text=str(row["text"]) if "text" in row.keys() else "",
                flip_h=bool(row["flip_h"]) if "flip_h" in row.keys() else False,
                flip_v=bool(row["flip_v"]) if "flip_v" in row.keys() else False,
            )
            if kind == "audio":
                self.timeline.audio_clips.append(clip)
            else:
                self.timeline.scene_clips.append(clip)
        self.timeline._refresh_size()
        self._fit_timeline_height()
        self._rebuild_track_buttons()
        self._render_preview()

    def _refresh_header(self) -> None:
        project = database.get_project(self.project_id) if self.project_id else None
        if project is None:
            return
        self.project_label.setText(f"{ICON} {project['name']}")
        self.project_desc.setText(
            project["description"] or "No description"
        )

    def _fit_timeline_height(self) -> None:
        """Resize the scroll area to fit the timeline's current track count."""
        if getattr(self, "_timeline_scroll", None) is not None:
            self._timeline_scroll.setFixedHeight(self.timeline.desired_height() + 12)

    def _request_preview(self) -> None:
        """Coalesce preview re-renders (one per event-loop burst)."""
        if not self._preview_dirty:
            self._preview_dirty = True
            self._preview_coalescer.start()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Refresh short-TTL DB rows when the editor becomes visible.

        Body parts, attachments, hide/show flags etc. may have been edited
        in the character details tabs since the last visit; dropping the
        cached rows makes those changes show up immediately instead of
        after the cache TTL.
        """
        super().showEvent(event)
        character_animator._row_cache.clear_db()

    def _do_preview_render(self) -> None:
        self._preview_dirty = False
        self._render_preview()

    def _schedule_persist(self) -> None:
        """Defer the SQLite rewrite until the change stream settles."""
        self._persist_dirty = True
        self._persist_timer.start()

    def _flush_deferred(self) -> None:
        """Persist debounced state now (used on drag end / leave / export)."""
        self._persist_timer.stop()
        if not self._persist_dirty:
            return
        self._persist_dirty = False
        self._persist_clips()
        self._rebuild_track_buttons()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # Leaving the editor: persist pending edits before the page hides.
        self._hide_audio_drawer()
        self._stop_playback()
        self._flush_deferred()
        super().hideEvent(event)

    def _on_timeline_change(self) -> None:
        """Live preview render + debounced persist of timeline state."""
        self._fit_timeline_height()
        self._schedule_persist()
        self._request_preview()

    def _persist_clips(self) -> None:
        """Save current timeline clips to the project's DB row (full replace)."""
        if self.project_id is None:
            return
        clips: list[tuple] = []
        for clip in self.timeline.scene_clips:
            asset_kind, asset_id = clip.data[:2]
            x_off = getattr(clip, "x_offset", 0.0)
            y_off = getattr(clip, "y_offset", 0.0)
            x_end = getattr(clip, "x_end", None)
            y_end = getattr(clip, "y_end", None)
            ex = x_off if x_end is None else float(x_end)
            ey = y_off if y_end is None else float(y_end)
            # Endpoint equal to startpoint -> no motion; store NULL so the
            # saved clip has no movement (matches legacy rows).
            if abs(ex - x_off) < 0.01 and abs(ey - y_off) < 0.01:
                ex = None
                ey = None
            clips.append(("scene", asset_kind, asset_id, clip.start, clip.duration, getattr(clip, "track", 0), getattr(clip, "animation", "idle"), x_off, y_off, getattr(clip, "size_scale", 1.0), ex, ey, getattr(clip, "anim_speed", 1.0), getattr(clip, "zoom_start", 1.0), getattr(clip, "zoom_end", None), getattr(clip, "text", ""),
                              getattr(clip, "flip_h", False), getattr(clip, "flip_v", False)))
        clips.extend(self._audio_clip_rows())
        database.save_clips(self.project_id, clips)

    def _on_remove_selected(self) -> None:
        if self.timeline.remove_selected():
            self.status_label.setText("Clip removed.")
        else:
            self.status_label.setText("Select a clip on the timeline first.")
        self.timeline._refresh_size()
        self._on_timeline_change()
        self._render_preview()

    def _on_add_empty_track(self) -> None:
        self.timeline.add_empty_track()
        self._rebuild_track_buttons()
        self.status_label.setText("Added an empty timeline row.")

    def _on_add_character_to_timeline(self, character_id: int) -> None:
        """Backwards-compatible wrapper: add a character to the timeline."""
        self._on_add_asset_to_timeline("character", character_id)

    def _on_add_text(self, text: str) -> None:
        """Add a text overlay clip to the selected timeline row."""
        text = (text or "").strip()
        if not text:
            self.status_label.setText("Type some text first.")
            return
        track = self.timeline.selected_track
        if track is None:
            track = self.timeline.add_empty_track()
            self.timeline.selected_track = track
        clip = Clip(
            0.0,
            float(DEFAULT_SCENE_SEC),
            f"🅣 {text[:24]}",
            "scene",
            ("text", 0),
            track=track,
            text=text,
        )
        self.timeline.add_clip(clip, track=track)
        self.status_label.setText(f"Added text: {text[:40]}")

    def _open_character_details(self, character_id: int) -> None:
        """"✎" on a character row: close this editor and open Character Details.

        Steps: stop playback + persist pending edits, return to the projects
        grid, then switch the main-window stack to the Character module and
        show that character on its details page.
        """
        self._flush_deferred()          # never lose clip edits on the way out
        self.screen.show_projects()     # closes the editor (like ← Back)

        window = self.window()
        stack = getattr(window, "stack", None)
        if stack is None:
            return
        for index in range(stack.count()):
            widget = stack.widget(index)
            if not isinstance(widget, CharacterScreen):
                continue
            stack.setCurrentIndex(index)
            widget.show_details(character_id)
            return
        # CharacterScreen not found in the stack (unexpected): stay on projects.

    def _on_add_asset_to_timeline(self, kind: str, asset_id: int) -> None:
        """Add a media asset (character/background/animation/audio) to the timeline.

        Scene assets (character/background/animation) go on the selected
        timeline row (a new empty row is created if none is selected).
        Audio always goes on the audio track.
        """
        if kind == "audio":
            self._add_audio_clip_to_timeline(asset_id)
            return
        if kind == "animation":
            # Animations are not separate clips: they are applied to the
            # character clip currently selected on the timeline.
            self._apply_animation_to_selected_character(asset_id)
            return
        track = self.timeline.selected_track
        if track is None:
            # No row selected yet: create a new empty row and place it there.
            track = self.timeline.add_empty_track()
            self.timeline.selected_track = track
        name = self._asset_display_name(kind, asset_id)
        emoji = {"character": "🧍", "background": "🌄"}.get(kind, "")
        clip = Clip(
            0.0,
            float(DEFAULT_SCENE_SEC),
            f"{emoji} {name}",
            "scene",
            (kind, asset_id),
            track=track,
        )
        self.timeline.add_clip(clip, track=track)
        if kind == "character":
            # Selecting the new clip filters the Anim tab to this characterId
            self._sync_character_tools(clip)
        self.status_label.setText(f"Added '{name}' to timeline row {track + 1}.")

    def _asset_display_name(self, kind: str, asset_id: int) -> str:
        """Human-readable name of an asset for clip labels/status messages."""
        try:
            if kind == "character":
                return database.get_character(asset_id)["name"]
            if kind == "background":
                return database.get_background(asset_id)["name"]
            if kind == "audio":
                return self._audio_display_name(asset_id)
            if kind == "animation":
                ik = database.get_character_ik_animation(asset_id)
                anim = ik if ik is not None else database.get_character_animation(asset_id)
                return anim["name"] if anim is not None else f"Animation {asset_id}"
        except Exception:
            pass
        return f"{kind.title()} {asset_id}"

    def _on_play_toggle(self) -> None:
        if self.playing:
            self._stop_playback()
            self.status_label.setText("Playback stopped.")
        else:
            if not (self.timeline.scene_clips or self.timeline.audio_clips):
                self.status_label.setText("The timeline is empty — add clips first.")
                return
            self.playing = True
            self.play_btn.setText("⏸ Pause")
            self._play_start = self.timeline.playhead
            self._play_clock.restart()
            self._render_clock.restart()
            self._timer.start()
            self.status_label.setText("Playing...")

    def _on_loop_toggled(self, checked: bool) -> None:
        self._loop_enabled = bool(checked)
        if self._loop_enabled and not self.playing:
            self.status_label.setText("Loop enabled — playback restarts from the beginning.")

    def _stop_playback(self) -> None:
        self.playing = False
        self._stop_audio_playback()
        if hasattr(self, "play_btn"):
            try:
                self.play_btn.setText("▶ Play")
            except RuntimeError:
                pass
        self._timer.stop()

    def _on_seek(self, t: float) -> None:
        self._pause_audio()
        if self.playing:
            # Keep the real-time clock consistent after a scrub.
            self._play_start = max(0.0, t)
            self._play_clock.restart()
        self.timeline.set_playhead(max(0.0, t))
        self._update_time_label()
        if not self.playing:
            self.timeline.update()
            self._render_preview()

    def _tick(self) -> None:
        """Playback clock: playhead = start + real elapsed time.

        The timer runs at 60 Hz while the preview render is throttled to
        ~30 FPS — the playhead stays smooth but the expensive re-render
        only happens every other tick.
        """
        if not self.playing:
            self._timer.stop()
            return
        total = self.timeline.total_duration()
        t = self._play_start + self._play_clock.elapsed() / 1000.0
        if t >= total:
            if self._loop_enabled:
                self._play_start = 0.0
                self._play_clock.restart()
                t = 0.0
            else:
                self.timeline.playhead = total
                self._stop_playback()
                self.status_label.setText("Playback finished.")
                self._update_time_label()
                self.timeline.set_playhead(total)
                self._render_preview()
                return
        self.timeline.set_playhead(t)  # sets playhead + moves the cursor overlay

        background_id, character_ids, audio_clip = self.timeline.assets_at(t)
        self._sync_audio_playback(audio_clip)

        if self._render_clock.elapsed() >= RENDER_MS:
            self._render_clock.restart()
            self._render_preview(background_id, character_ids)

        # Keep the playhead visible once it runs past the viewport edge.
        scroll = getattr(self, "_timeline_scroll", None)
        if scroll is not None:
            scroll.ensureVisible(
                int(t * self.timeline.PXS),
                self.timeline.RULER_H,
                64,
                0,
            )
        self._update_time_label()

    def _update_time_label(self) -> None:
        t = self.timeline.playhead
        minutes = int(t // 60)
        seconds = t - minutes * 60
        self.time_label.setText(f"{minutes:02d}:{seconds:04.1f}")

    def stop_export(self) -> None:
        """Cancel a running export and wait briefly for it (clean shutdown)."""
        worker = self._export_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(10000)  # cancel flag + ffmpeg kill settle quickly
            if worker.isRunning():
                worker.kill_process()
                worker.wait(5000)
                if worker.isRunning():
                    # Last resort before Qt destroys the thread mid-run
                    worker.terminate()
                    worker.wait(3000)
        self.export_progress.hide()
        self._retire_export_worker()

    def stop_playback(self) -> None:
        self._stop_playback()
        self._stop_audio_drawer_playback()

    # ---------------------------------------------------------------- export
    def _on_export(self) -> None:
        timeline = self.timeline
        if not (timeline.scene_clips or timeline.audio_clips):
            self.status_label.setText("The timeline is empty — add clips before exporting.")
            return
        if self._export_worker is not None and self._export_worker.isRunning():
            return  # already exporting

        self._stop_playback()
        self._flush_deferred()  # persist any pending clip edits first

        default_name = "export.mp4"
        if self.project_id is not None:
            project = database.get_project(self.project_id)
            if project is not None:
                safe_name = "".join(
                    ch if ch not in '\\/:*?"<>|' else "_" for ch in project["name"]
                ).strip() or "export"
                default_name = f"{safe_name}.mp4"
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export video", default_name, "MP4 video (*.mp4)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"
        self._start_export(out_path)

    def _start_export(self, out_path: str) -> ExportWorker:
        """Build the export payload (all asset data resolved on the GUI
        thread) and launch the export worker for ``out_path``."""
        timeline = self.timeline

        def asset_row(kind: str, asset_id: int):
            return (
                database.get_character(asset_id)
                if kind == "character"
                else database.get_background(asset_id)
                if kind == "background"
                else None
            )

        def asset_path(kind: str, asset_id: int):
            row = asset_row(kind, asset_id)
            if row is None or not row["image_path"]:
                return None
            path = (
                character_store.absolute_path(row["image_path"])
                if kind == "character"
                else background_store.absolute_path(row["image_path"])
            )
            return path if path.is_file() else None

        scene_data = []
        for c in timeline.scene_clips:
            kind = c.data[0] if c.data else "background"
            asset_id = c.data[1] if c.data and len(c.data) >= 2 else None
            path = (
                asset_path(kind, asset_id)
                if asset_id is not None and kind in ("character", "background")
                else None
            )
            entry: dict = {
                "start": c.start,
                "duration": c.duration,
                "kind": kind,
                "path": str(path) if path else "",
                "name": c.name,
                "text": getattr(c, "text", ""),
                "x_offset": getattr(c, "x_offset", 0.0),
                "y_offset": getattr(c, "y_offset", 0.0),
                "x_end": getattr(c, "x_end", None),
                "y_end": getattr(c, "y_end", None),
                "size_scale": getattr(c, "size_scale", 1.0),
                "anim_speed": getattr(c, "anim_speed", 1.0),
                "zoom_start": getattr(c, "zoom_start", 1.0),
                "zoom_end": getattr(c, "zoom_end", None),
                "flip_h": getattr(c, "flip_h", False),
                "flip_v": getattr(c, "flip_v", False),
            }
            if kind == "character" and asset_id is not None:
                # Everything the export compositor needs, resolved here on
                # the GUI thread: stage image path, animation rows and the
                # parsed body-part rects.
                entry["cid"] = asset_id
                character = database.get_character(asset_id)
                if character is not None and character["image_path"]:
                    stage_path = character_store.absolute_path(character["image_path"])
                    if stage_path.is_file():
                        entry["stage_path"] = str(stage_path)
                entry["animation"] = getattr(c, "animation", "idle") or "idle"
                # Animation rows for the character: saved IK keyframe
                # animations first (the Character Details Animation tab),
                # procedural walk-cycle presets as fallback - so exported
                # frames play the character's own animation.
                entry["anims"] = []
                try:
                    for a in database.list_character_ik_animations(asset_id):
                        entry["anims"].append(
                            {
                                "id": a["id"],
                                "name": a["name"],
                                "speed": float(a["speed"]),
                                "leg_amplitude": 0.0,
                                "arm_amplitude": 0.0,
                                "bob_amount": 0.0,
                                "bob_frequency": 1.0,
                                "anim_type": a["anim_type"],
                                "duration": float(a["duration"]),
                                "loop": bool(a["loop"]),
                                "payload": a["payload"],
                            }
                        )
                except Exception:
                    entry["anims"] = []
                if not entry["anims"]:
                    try:
                        entry["anims"] = [
                            {
                                "id": a["id"],
                                "name": a["name"],
                                "speed": float(a["speed"]),
                                "leg_amplitude": float(a["leg_amplitude"]),
                                "arm_amplitude": float(a["arm_amplitude"]),
                                "bob_amount": float(a["bob_amount"]),
                                "bob_frequency": float(a["bob_frequency"]),
                            }
                            for a in database.list_character_animations(asset_id)
                        ]
                    except Exception:
                        entry["anims"] = []
                parts: list[dict] = []
                try:
                    rows = database.list_character_parts(asset_id)
                except Exception:
                    rows = []
                for row in rows:
                    try:
                        payload = json.loads(row["payload"]) if row["payload"] else {}
                    except Exception:
                        payload = {}
                    if not payload.get("visible", True):
                        continue
                    left = int(payload.get("left") or payload.get("x") or 0)
                    top = int(payload.get("top") or payload.get("y") or 0)
                    w = int(payload.get("width") or 0)
                    h = int(payload.get("height") or 0)
                    if w <= 0 or h <= 0:
                        continue
                    parts.append(
                        {
                            "left": left,
                            "top": top,
                            "w": w,
                            "h": h,
                            # A part belongs at its own source rect position
                            # (same placement the Mark tab uses); the legacy
                            # payload x/y is a stale default.
                            "x": left,
                            "y": top,
                        }
                    )
                entry["parts"] = parts
            scene_data.append(entry)

        audio_data = self._audio_export_data(timeline)

        self._export_worker = ExportWorker(
            out_path,
            self.stage_width,
            self.stage_height,
            scene_data,
            audio_data,
        )
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished_ok.connect(self._export_finished)
        self._export_worker.failed.connect(self._export_failed)
        self.export_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.status_label.setText("⬇ Exporting video… 0%")
        self._on_export_progress(0)
        self._export_worker.start()
        return self._export_worker

    def _on_export_progress(self, pct: int) -> None:
        """Update the export progress bar + status line."""
        self.export_progress.setValue(int(pct))
        self.export_progress.setFormat(f"⬇ {int(pct)}%")
        self.export_progress.setVisible(True)
        self.status_label.setText(
            f"⬇ Exporting video… {int(pct)}%  "
            f"({self.stage_width}×{self.stage_height}, 30 FPS)"
        )

    def _export_finished(self, out_path: str) -> None:
        self._retire_export_worker()
        self.export_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.export_progress.setValue(100)
        self.export_progress.setFormat("✅ 100%")
        self.status_label.setText(f"✅ Video exported: {out_path}")
        QTimer.singleShot(2500, self.export_progress.hide)

    def _export_failed(self, message: str) -> None:
        self._retire_export_worker()
        self.export_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.export_progress.hide()
        self.status_label.setText(f"❌ Export failed: {message}")

    def _retire_export_worker(self) -> None:
        """Keep finished workers alive: dropping the last Python reference
        deletes the QThread while run() may still be executing - a fatal
        'QThread: Destroyed while thread is still running' abort."""
        worker = self._export_worker
        self._export_worker = None
        if worker is None:
            return
        self._retired_workers.append(worker)
        if len(self._retired_workers) > 5:
            self._retired_workers.pop(0)  # thread long finished - safe to drop

    def _pixmaps_at(self, t: float | None = None):
        if t is None:
            t = self.timeline.playhead
        background_id, character_ids, _audio = self.timeline.assets_at(t)
        return background_id, character_ids

    def _render_preview(self, background_id: int | None = None, character_ids=None) -> None:
        if background_id is None and character_ids is None:
            background_id, character_ids = self._pixmaps_at()
        if character_ids is None:
            character_ids = []

        W, H = self._render_w, self._render_h
        t_now = self.timeline.playhead
        # Whole-frame camera zoom (Effect tab) for the playhead time
        zoom = self._scene_zoom_at(self.timeline.playhead)
        zoomed = abs(zoom - 1.0) > 0.005
        # Screen positions of drawn assets, for click hit-testing
        self._char_rects: list[tuple[int, object, tuple[int, int, int, int]]] = []
        self._bg_rects: list[tuple[int, object, tuple[int, int, int, int]]] = []
        # Painter-space rects of drawn scene clips (clip uid -> x,y,w,h), used
        # for the selection border (the hit rects above bake in camera zoom).
        self._char_draw_rects: dict[int, tuple[int, int, int, int]] = {}
        # Signature of everything the frame depends on. When it matches the
        # previous frame we skip the whole composite + setPixmap pass —
        # big win for static scenes while scrubbing/dragging.
        self._frame_sig: list = [round(zoom, 3), W, H]

        if getattr(self, "_canvas_size", None) != (W, H):
            self._preview_canvas = QPixmap(W, H)
            self._canvas_size = (W, H)
        canvas = self._preview_canvas
        canvas.fill(QColor("#ffffff"))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if zoomed:
            # Bake the camera zoom into the painter instead of re-compositing
            # the whole frame a second time into a fresh pixmap.
            painter.translate(W / 2.0, H / 2.0)
            painter.scale(zoom, zoom)
            painter.translate(-W / 2.0, -H / 2.0)

        drawn = False
        if background_id is not None:
            background = self._cached_background(background_id)
            if background is not None and background.get("image_path"):
                path = background_store.absolute_path(background["image_path"])
                if path.is_file():
                    pixmap = self._cache.pixmap(("bg", background_id), path)
                    if not pixmap.isNull():
                        bg_clip = None
                        for c in self.timeline.scene_clips:
                            if not (c.start <= t_now < c.start + c.duration):
                                continue
                            if (
                                c.data and len(c.data) >= 2
                                and c.data[0] == "background"
                                and c.data[1] == background_id
                            ):
                                bg_clip = c
                        raw_scale = getattr(bg_clip, "size_scale", 1.0) if bg_clip else 1.0
                        bg_pct = max(
                            MIN_CHARACTER_SIZE_PCT,
                            min(MAX_CHARACTER_SIZE_PCT, int(round(float(raw_scale or 1.0) * 100))),
                        )
                        bg_scale = bg_pct / 100.0
                        scaled = self._cache.scaled(
                            ("bg", background_id), pixmap,
                            max(1, int(W * bg_scale)), max(1, int(H * bg_scale)),
                            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                        )
                        pos_x, pos_y = (
                            self._char_position_at(bg_clip, t_now)
                            if bg_clip is not None else (0.0, 0.0)
                        )
                        off_x = int(pos_x * W / max(1, self.stage_width))
                        off_y = int(pos_y * H / max(1, self.stage_height))
                        x = (W - scaled.width()) // 2 + off_x
                        y = (H - scaled.height()) // 2 + off_y
                        painter.drawPixmap(x, y, scaled)
                        drawn = True
                        if zoom != 1.0:
                            rect_x = int(W / 2.0 + (x - W / 2.0) * zoom)
                            rect_y = int(H / 2.0 + (y - H / 2.0) * zoom)
                            rect_w = int(scaled.width() * zoom)
                            rect_h = int(scaled.height() * zoom)
                        else:
                            rect_x, rect_y = x, y
                            rect_w, rect_h = scaled.width(), scaled.height()
                        if bg_clip is not None:
                            self._bg_rects.append(
                                (background_id, bg_clip, (rect_x, rect_y, rect_w, rect_h))
                            )
                            self._char_draw_rects[bg_clip.uid] = (
                                x, y, scaled.width(), scaled.height(),
                            )
                        self._frame_sig.append(
                            ("bg", background_id, bg_scale, off_x, off_y)
                        )

        if character_ids:
            t_now = self.timeline.playhead
            drag = getattr(self, "_char_drag", None)
            drag_scale = W / max(1, self.stage_width)
            # Resolve one render item per covering character CLIP. The same
            # character can have multiple clips on the timeline; each clip
            # carries its own position/animation. Collapsing by character id
            # here made duplicate draws share a single covering clip, so
            # moving one character moved all of its copies.
            wanted = set(character_ids)
            render_items: list[tuple[int, object]] = []
            for c in self.timeline.scene_clips:
                if not (c.start <= t_now < c.start + c.duration):
                    continue
                if not (
                    c.data
                    and len(c.data) >= 2
                    and c.data[0] == "character"
                ):
                    continue
                if c.data[1] not in wanted:
                    continue
                render_items.append((c.data[1], c))
            n = len(render_items)
            for i, (cid, clip) in enumerate(render_items):
                character = self._cached_character(cid)
                if not character or not character.get("image_path"):
                    continue
                # find the animation assigned to this character's clip
                anim_name = getattr(clip, "animation", "idle") or "idle"
                parts = self._cached_parts(cid)

                stage_pix = self._cache.pixmap(
                    ("char", cid),
                    character_store.absolute_path(character["image_path"]),
                )

                # Resolve the animation row assigned to this character's clip.
                # IK keyframe animations (Character Details Animation tab) are
                # preferred, so imported characters play the same animation
                # they play in character details; legacy walk presets are the
                # fallback.
                anim = self._character_anim_for_clip(int(cid), anim_name)

                # Per-character clip (offsets/size/speed come from it)
                src_clip = clip
                size_scale = getattr(src_clip, "size_scale", 1.0) if src_clip is not None else 1.0
                char_h = max(32, int(H * 0.6 * size_scale))

                # 1) Skeleton-animated frame (walk cycle etc.), rendered by the
                #    same model as the character animation tab. The character
                #    actually walks when it has body parts + an animation.
                #    Rendered at display resolution (render_scale < 1) instead
                #    of the full 2048px stage — up to 16x cheaper per frame.
                pixmap = None
                anim_key = None
                if anim is not None:
                    speed_mul = getattr(src_clip, "anim_speed", 1.0) if src_clip is not None else 1.0
                    render_scale = min(1.0, max(0.3, (char_h * 1.5) / 2048.0))
                    tick = int(t_now * 30.0)  # 33ms frame bucket
                    anim_key = (
                        "anim", cid, anim.get("id"), round(float(anim["speed"]), 3),
                        round(float(speed_mul), 3), tick, char_h,
                    )
                    try:
                        pixmap = character_animator.render_character_anim(
                            cid, anim, t_now,
                            speed_mul=speed_mul,
                            render_scale=render_scale,
                        )
                    except Exception:
                        pixmap = None
                    if pixmap is not None and pixmap.isNull():
                        pixmap = None
                is_animated = pixmap is not None

                # 2) Fallback: static assembly / whole image (idle bob below)
                src_key = None
                if pixmap is None:
                    parsed = []
                    sig_bits = []
                    if not stage_pix.isNull() and parts:
                        for row in parts:
                            try:
                                data = json.loads(row["payload"]) if row["payload"] else {}
                            except Exception:
                                data = {}
                            if not data.get("visible", True):
                                continue
                            left = int(data.get("left") or data.get("x") or 0)
                            top = int(data.get("top") or data.get("y") or 0)
                            w = int(data.get("width") or 0)
                            h = int(data.get("height") or 0)
                            if w <= 0 or h <= 0:
                                continue
                            # The crop belongs at its own source rect position
                            # (the legacy payload x/y is a stale default).
                            parsed.append((left, top, w, h, left, top))
                            sig_bits.append((row["id"], left, top, w, h))
                    if parsed:
                        # Compose once per parts layout (cached), at ~1.4x the
                        # display height instead of the full 2048px canvas.
                        asm_scale = min(1.0, max(0.3, (char_h * 1.4) / 2048.0))
                        src_key = ("asm", cid, round(asm_scale, 3), tuple(sig_bits))

                        def _build_assembled(
                            _parsed=tuple(parsed), _s=asm_scale, _stage=stage_pix
                        ) -> QPixmap:
                            canvas_size = max(64, int(2048 * _s))
                            asm = QPixmap(canvas_size, canvas_size)
                            asm.fill(Qt.transparent)
                            ap = QPainter(asm)
                            ap.setRenderHint(QPainter.SmoothPixmapTransform)
                            ap.scale(_s, _s)
                            for (left, top, w, h, px, py) in _parsed:
                                crop = _stage.copy(left, top, w, h)
                                if crop.isNull():
                                    continue
                                ap.drawPixmap(px, py, crop)
                            ap.end()
                            return asm

                        pixmap = self._cache.canvas(src_key, _build_assembled)
                    if pixmap is None or pixmap.isNull():
                        # Whole image fallback (cached decode).
                        pixmap = stage_pix
                        src_key = (
                            "whole", cid, file_mtime(character_store.absolute_path(character["image_path"]))
                        )

                if not pixmap.isNull():
                    scaled = self._cache.scaled(
                        anim_key if is_animated else (src_key, char_h),
                        pixmap, int(char_h * 0.8), char_h,
                        Qt.KeepAspectRatio, Qt.SmoothTransformation,
                    )
                    flip_h = getattr(src_clip, "flip_h", False) if src_clip else False
                    flip_v = getattr(src_clip, "flip_v", False) if src_clip else False
                    if flip_h or flip_v:
                        scaled = QPixmap.fromImage(
                            scaled.toImage().mirrored(flip_h, flip_v)
                        )
                    offset = (i - (n - 1) / 2.0) * (scaled.width() + 10)
                    # Per-character stage offset: interpolated between
                    # startpoint and endpoint for the current playhead time.
                    if src_clip is not None:
                        t_show = t_now
                        if drag is not None and drag["clip"] is src_clip:
                            # While dragging, show the point being set:
                            # the position at clip start (Start mode) or end (End mode).
                            t_show = (
                                src_clip.start
                                if drag.get("mode") != "end"
                                else src_clip.start + src_clip.duration
                            )
                        pos_x, pos_y = self._char_position_at(src_clip, t_show)
                        off_x = int(pos_x * drag_scale)
                        off_y = int(pos_y * drag_scale)
                    else:
                        off_x = off_y = 0
                    # Idle bob for the static fallback; animated frames
                    # already contain the full walk cycle.
                    bob_offset = 0
                    if not is_animated and anim is not None:
                        try:
                            speed = float(anim["speed"])
                            bob_amount = float(anim["bob_amount"])
                            bob_freq = float(anim["bob_frequency"])
                            phase = t_now * (speed * 30.0)
                            bob = bob_amount * abs(math.sin(phase * bob_freq))
                            bob_offset = int(bob * (char_h / 2048.0))
                        except Exception:
                            bob_offset = 0
                    target_x = int((W - scaled.width()) // 2 + offset) + off_x
                    target_y = H - scaled.height() - int(H * 0.04) - bob_offset + off_y
                    # Transform the hit-rect for the frame zoom so stage
                    # clicks/double-clicks still hit the right character.
                    if zoom != 1.0:
                        rect_x = int(W / 2.0 + (target_x - W / 2.0) * zoom)
                        rect_y = int(H / 2.0 + (target_y - H / 2.0) * zoom)
                        rect_w = int(scaled.width() * zoom)
                        rect_h = int(scaled.height() * zoom)
                    else:
                        rect_x, rect_y = target_x, target_y
                        rect_w, rect_h = scaled.width(), scaled.height()
                    self._char_rects.append((cid, clip, (rect_x, rect_y, rect_w, rect_h)))
                    self._char_draw_rects[clip.uid] = (
                        target_x, target_y, scaled.width(), scaled.height(),
                    )
                    painter.drawPixmap(target_x, target_y, scaled)
                    drawn = True
                    if is_animated:
                        self._frame_sig.append(
                            (cid, anim_key, target_x, target_y, flip_h, flip_v)
                        )
                    else:
                        self._frame_sig.append(
                            (cid, src_key, char_h, bob_offset, target_x, target_y,
                             flip_h, flip_v)
                        )

        # Selection border around the selected character clip (editor overlay,
        # not part of the video). Painter space already has camera zoom baked in.
        sel_uid = self.timeline.selected_uid
        sel_rect = self._char_draw_rects.get(sel_uid) if sel_uid is not None else None
        if sel_rect is not None:
            sx, sy, sw, sh = sel_rect
            pad = 4
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#38bdf8"), 3, Qt.DashLine))
            painter.drawRect(sx - pad, sy - pad, sw + 2 * pad, sh + 2 * pad)
            painter.setPen(QPen(QColor("#ffffff"), 1, Qt.DashLine))
            painter.drawRect(sx - pad, sy - pad, sw + 2 * pad, sh + 2 * pad)
            self._frame_sig.append(("sel", sel_uid, sx, sy, sw, sh))

        # Text overlay clips covering the playhead (drawn above characters).
        t_now = self.timeline.playhead
        for c in self.timeline.scene_clips:
            if not (c.data and len(c.data) >= 2 and c.data[0] == "text"):
                continue
            if not (c.start <= t_now < c.start + c.duration):
                continue
            content = getattr(c, "text", "") or ""
            if not content:
                continue
            font_px = max(8, int(H * 0.09 * float(getattr(c, "size_scale", 1.0) or 1.0)))
            font = QFont("Segoe UI", font_px)
            font.setBold(True)
            painter.setFont(font)
            fm = QFontMetrics(font)
            off_x = float(getattr(c, "x_offset", 0.0) or 0.0) * (W / max(1, self.stage_width))
            off_y = float(getattr(c, "y_offset", 0.0) or 0.0) * (H / max(1, self.stage_height))
            tx = int(W / 2 + off_x - fm.horizontalAdvance(content) / 2)
            ty = int(H / 2 + off_y - fm.height() / 2) + fm.ascent()
            painter.setPen(QColor(0, 0, 0, 180))
            painter.drawText(tx + 2, ty + 2, content)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(tx, ty, content)
            self._frame_sig.append(("text", c.uid, content, tx, ty, font_px))
            drawn = True

        if not drawn:
            painter.setPen(QColor(MUTED))
            painter.setFont(QFont("Segoe UI", max(9, H // 24)))
            painter.drawText(
                canvas.rect(),
                Qt.AlignCenter,
                f"{self.stage_width}×{self.stage_height}\n\n"
                "Add background / character clips\nand play to preview",
            )
        painter.end()

        if drawn:
            sig = tuple(self._frame_sig)
            if sig == getattr(self, "_last_frame_sig", None):
                # Nothing changed since the last painted frame — keep the
                # label's current pixmap instead of re-blitting the canvas.
                return
            self._last_frame_sig = sig
        else:
            self._last_frame_sig = None
        self.preview.setPixmap(canvas)
