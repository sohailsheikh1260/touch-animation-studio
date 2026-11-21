"""Preview-stage widgets, interaction handlers and cached asset lookups.

Extracted from ProjectEditorPage; host page supplies timeline, status_label,
left_sidebar and the render/persist helpers used here.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import database
from screens.project_details.clip import MAX_CHARACTER_SIZE_PCT, MIN_CHARACTER_SIZE_PCT
from screens.project_details.editor_leftsidebar import PANEL_LABEL_STYLE, PANEL_STYLE
from screens.project_details.screen_presets import SCREEN_PRESETS
from screens.theme import BG, CARD_BG, MUTED, TEXT

STAGE_MAX_W, STAGE_MAX_H = 1024, 576  # max preview render size (stage gets fit into this)


class SelectablePreviewLabel(QLabel):
    """Preview canvas: click selects, drag moves, wheel resizes a character."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.on_character_double_click = None  # callable(click_pos)
        self.on_character_press = None         # callable(click_pos)
        self.on_character_drag_move = None     # callable(move_pos)
        self.on_character_drag_end = None      # callable()
        self.on_wheel = None                   # callable(event) -> bool

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if callable(self.on_character_double_click):
            self.on_character_double_click(event.position().toPoint())
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if callable(self.on_character_press):
            self.on_character_press(event.position().toPoint())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if callable(self.on_character_drag_move):
            self.on_character_drag_move(event.position().toPoint())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if callable(self.on_character_drag_end):
            self.on_character_drag_end(event.position().toPoint())
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if callable(self.on_wheel) and self.on_wheel(event):
            return
        super().wheelEvent(event)


class PreviewEditorMixin:
    """Preview panel and character/effect tool handlers for the editor page.

    Host contract: timeline, status_label, left_sidebar, preview, _render_w,
    stage_width, _cache, _request_preview(), _render_preview(),
    _on_timeline_change(), _asset_display_name().
    """

    _SIZE_WHEEL_STEP_PCT = 10

    def _build_preview_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        caption = QLabel("🖥 Preview")
        caption.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; font-weight: bold; {PANEL_LABEL_STYLE}"
        )
        header.addWidget(caption)
        header.addStretch()

        # ---- Screen size preset dropdown ----
        size_caption = QLabel("Screen size:")
        size_caption.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; {PANEL_LABEL_STYLE}"
        )
        self.stage_combo = QComboBox()
        self.stage_combo.setCursor(Qt.PointingHandCursor)
        self.stage_combo.setFixedWidth(190)
        self.stage_combo.setStyleSheet(
            f"QComboBox {{ background-color: {BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 8px; padding: 4px 10px;"
            "  font-size: 12px; }"
            "QComboBox QAbstractItemView {"
            f"  background-color: {CARD_BG}; color: {TEXT};"
            "  selection-background-color: #334155;"
            "}"
        )
        current_category = None
        for preset in SCREEN_PRESETS:
            if preset["category"] != current_category:
                current_category = preset["category"]
                # Non-selectable separator row per category
                self.stage_combo.insertItem(
                    self.stage_combo.count(), f"—— {current_category} ——"
                )
                separator_item = self.stage_combo.model().item(self.stage_combo.count() - 1)
                separator_item.setFlags(Qt.NoItemFlags)
                separator_item.setForeground(QBrush(QColor(MUTED)))
            self.stage_combo.addItem(
                f"{preset['name']}  ({preset['width']}×{preset['height']})",
                preset["id"],
            )
        self.stage_combo.currentIndexChanged.connect(self._on_preset_changed)
        header.addWidget(size_caption)
        header.addWidget(self.stage_combo)
        layout.addLayout(header)

        # ---- Custom size row (visible only for the Custom preset) ----
        width_caption = QLabel("W")
        height_caption = QLabel("H")
        for caption_ in (width_caption, height_caption):
            caption_.setStyleSheet(
                f"color: {MUTED}; font-size: 11px; {PANEL_LABEL_STYLE}"
            )
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(160, 7680)
            spin.setSingleStep(10)
            spin.setFixedWidth(86)
            spin.setStyleSheet(
                f"QSpinBox {{ background-color: {BG}; color: {TEXT};"
                "  border: 1px solid #334155; border-radius: 8px;"
                "  padding: 4px; font-size: 12px; }"
            )
            spin.valueChanged.connect(self._on_custom_size_changed)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(6)
        custom_row.addStretch()
        custom_row.addWidget(width_caption)
        custom_row.addWidget(self.width_spin)
        custom_row.addWidget(height_caption)
        custom_row.addWidget(self.height_spin)
        layout.addLayout(custom_row)
        self._custom_widgets = (width_caption, self.width_spin, height_caption, self.height_spin)
        self._set_custom_row_visible(False)

        self.preview = SelectablePreviewLabel("Add clips to the timeline\nand press ▶ Play")
        self.preview.on_character_double_click = self._on_preview_character_double_click
        self.preview.on_character_press = self._on_preview_character_press
        self.preview.on_character_drag_move = self._on_preview_character_drag_move
        self.preview.on_character_drag_end = self._on_preview_character_drag_end
        self.preview.on_wheel = self._on_preview_wheel
        self.preview.setStyleSheet(
            f"QLabel {{ background-color: #111827; border: 1px dashed #334155;"
            f"  border-radius: 10px; color: {MUTED}; font-size: 14px; }}"
        )
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(STAGE_MAX_W, STAGE_MAX_H)
        self.preview.setMouseTracking(True)
        layout.addWidget(self.preview, 0, Qt.AlignHCenter)
        layout.addStretch()
        return panel

    def _preview_to_stage_pos(self, pos):
        """Convert a label position to a stage-render canvas position."""
        offset_x = (self.preview.width() - self._render_w) // 2
        offset_y = (self.preview.height() - self._render_h) // 2
        return pos.x() - offset_x, pos.y() - offset_y

    def _hit_asset_at_pos(self, pos):
        """(kind, asset_id, clip) under a stage position, or three Nones.

        Characters win over the background; the owning clip is returned too so
        drag/resize act on the exact clip that was grabbed.
        """
        cx, cy = self._preview_to_stage_pos(pos)
        for attr, kind in (("_char_rects", "character"), ("_bg_rects", "background")):
            for asset_id, clip, (x, y, w, h) in reversed(getattr(self, attr, [])):
                if x <= cx < x + w and y <= cy < y + h:
                    return kind, asset_id, clip
        return None, None, None

    def _covering_scene_clip(self, kind: str, asset_id: int):
        """The scene clip covering the playhead for a character/background."""
        candidates = [
            c for c in self.timeline.scene_clips
            if c.data and len(c.data) >= 2 and c.data[0] == kind and c.data[1] == asset_id
        ]
        if not candidates:
            return None
        t = self.timeline.playhead
        covering = [c for c in candidates if c.start <= t < c.start + c.duration]
        return covering[-1] if covering else candidates[-1]

    def _clip_progress_at(self, clip, t: float) -> float:
        """0..1 progress of a clip at time t (0 before start, 1 after end)."""
        if clip is None or clip.duration <= 0:
            return 0.0
        p = (t - clip.start) / clip.duration
        return max(0.0, min(1.0, p))

    def _char_position_at(self, clip, t: float):
        """Stage-space (x, y) offset of a character clip at time t.

        Interpolates from the startpoint (x_offset/y_offset) to the endpoint
        (x_end/y_end) across the clip duration. No endpoint -> static position.
        """
        sx = getattr(clip, "x_offset", 0.0)
        sy = getattr(clip, "y_offset", 0.0)
        ex = sx if getattr(clip, "x_end", None) is None else clip.x_end
        ey = sy if getattr(clip, "y_end", None) is None else clip.y_end
        p = self._clip_progress_at(clip, t)
        return (sx + (ex - sx) * p, sy + (ey - sy) * p)

    def _on_preview_character_double_click(self, pos) -> None:
        """Double-click a character/background on the stage -> select its clip."""
        kind, asset_id, clip = self._hit_asset_at_pos(pos)
        if kind is None:
            return
        if clip is None:
            clip = self._covering_scene_clip(kind, asset_id)
        if clip is None:
            self.status_label.setText("No scene clip found on the timeline.")
            return
        self.timeline.selected_uid = clip.uid
        self.timeline.select_track(clip.track)
        self._sync_character_tools(clip)
        self.timeline.update()
        self._request_preview()  # refresh the selection border on the stage
        label = "background" if kind == "background" else "character"
        self.status_label.setText(
            f"Selected {label} '{clip.name}' — scroll or use Tools → Size to resize."
        )

    def _drag_point_mode(self) -> str:
        """Current Tools-tab drag mode: "start" or "end"."""
        try:
            return self.left_sidebar.drag_point_mode()
        except Exception:
            return "start"

    def _on_preview_character_press(self, pos) -> None:
        """Click (or start dragging) a character/background on the stage."""
        self._char_drag = None
        kind, asset_id, clip = self._hit_asset_at_pos(pos)
        if kind is None:
            return
        if clip is None:
            clip = self._covering_scene_clip(kind, asset_id)
        if clip is None:
            return
        mode = self._drag_point_mode()
        self.timeline.selected_uid = clip.uid
        self.timeline.select_track(clip.track)
        self._sync_character_tools(clip)
        self.timeline.update()
        self._request_preview()  # refresh the selection border on the stage
        label = "background" if kind == "background" else "character"
        self.status_label.setText(
            f"Selected {label} '{clip.name}' — drag to set the {mode.upper()} point, "
            f"scroll to resize; it moves from start to end over the clip duration."
        )
        self._char_drag = {
            "clip": clip,
            "kind": kind,
            "mode": mode,
            "press": (pos.x(), pos.y()),
            "base": self._char_position_at(clip, self.timeline.playhead),
            "scale": self._render_w / max(1, self.stage_width),
        }

    def _on_preview_character_drag_move(self, pos) -> None:
        """Drag the pressed character, setting the point chosen in the Tools tab.

        "Start" mode sets the startpoint, "End" mode sets the endpoint; the
        scene clip then travels from start to end over the clip duration.
        """
        drag = getattr(self, "_char_drag", None)
        if drag is None:
            return
        clip = drag["clip"]
        dx = (pos.x() - drag["press"][0]) / drag["scale"]
        dy = (pos.y() - drag["press"][1]) / drag["scale"]
        target_x = drag["base"][0] + dx
        target_y = drag["base"][1] + dy
        if drag["mode"] == "end":
            clip.x_end = target_x
            clip.y_end = target_y
        else:
            clip.x_offset = target_x
            clip.y_offset = target_y
        self._render_preview()

    def _on_preview_character_drag_end(self, pos) -> None:
        drag = getattr(self, "_char_drag", None)
        if drag is None:
            return
        clip = drag["clip"]
        self._char_drag = None
        ex = clip.x_offset if getattr(clip, "x_end", None) is None else clip.x_end
        ey = clip.y_offset if getattr(clip, "y_end", None) is None else clip.y_end
        label = "Background" if drag.get("kind") == "background" else ""
        label = f"{label} " if label else ""
        if abs(ex - clip.x_offset) > 0.5 or abs(ey - clip.y_offset) > 0.5:
            self.status_label.setText(
                f"{label}'{clip.name}' moves from ({int(clip.x_offset)}, {int(clip.y_offset)}) "
                f"to ({int(ex)}, {int(ey)}) over {clip.duration:.1f}s (arrives at clip end)."
            )
        else:
            self.status_label.setText(
                f"Moved '{clip.name}' (no motion). Scrub inside the clip and drag to set motion."
            )
        self._on_timeline_change()  # persist + refresh
        self._sync_character_tools(clip)

    def _apply_animation_to_selected_character(self, animation_id: int) -> None:
        """Apply an animation to the character clip selected on the timeline.

        The user is expected to: click a character clip on a timeline row
        (this selects it), then click "＋" on an animation list item.
        """
        clip = self._selected_scene_clip()
        if clip is None or not (clip.data and clip.data[0] == "character"):
            self.status_label.setText(
                "Select a character clip on the timeline first, then add an animation."
            )
            return
        anim_name = self._asset_display_name("animation", animation_id)
        clip.animation = anim_name
        self.status_label.setText(f"Applied animation '{anim_name}' to '{clip.name}'.")
        self._on_timeline_change()

    def _selected_scene_clip(self):
        """The scene clip currently selected on the timeline (character/background)."""
        uid = self.timeline.selected_uid
        if uid is None:
            return None
        for clip in self.timeline.scene_clips:
            if clip.uid == uid:
                return clip
        return None

    def _set_selected_scene_scale(
        self, percent: int, *, persist: bool = False, announce: bool = False
    ) -> None:
        """Apply one clamped, uniform scale to the selected scene clip."""
        clip = self._selected_scene_clip()
        if clip is None:
            self.status_label.setText(
                "Select a character or background on the stage or timeline first."
            )
            return
        pct = max(MIN_CHARACTER_SIZE_PCT, min(MAX_CHARACTER_SIZE_PCT, int(percent)))
        clip.size_scale = pct / 100.0
        self.left_sidebar.set_character_scale(pct)
        self._render_preview()
        if persist:
            self._on_timeline_change()  # debounced project-clips save
        if announce:
            self.status_label.setText(f"'{clip.name}' size: {pct}%.")

    def _on_scale_changed(self, value: int) -> None:
        """Tools tab size slider/spinbox: scale the selected scene clip."""
        self._set_selected_scene_scale(value)

    def _on_preview_wheel(self, event) -> bool:
        """Wheel over the preview resizes the selected scene asset in real time."""
        delta = event.angleDelta().y() or event.pixelDelta().y()
        clip = self._selected_scene_clip()
        if not delta or clip is None:
            return False
        steps = 1 if delta > 0 else -1
        current = int(round(getattr(clip, "size_scale", 1.0) * 100))
        self._set_selected_scene_scale(
            current + steps * self._SIZE_WHEEL_STEP_PCT,
            persist=True,
            announce=True,
        )
        event.accept()
        return True

    def _on_scale_commit(self) -> None:
        """Persist once when the size slider/spinbox is released."""
        if self._selected_scene_clip() is not None:
            self._on_timeline_change()

    def _sync_scale_slider(self, clip) -> None:
        if clip is not None:
            pct = int(round(getattr(clip, "size_scale", 1.0) * 100))
            pct = max(MIN_CHARACTER_SIZE_PCT, min(MAX_CHARACTER_SIZE_PCT, pct))
            self.left_sidebar.set_character_scale(pct)

    def _on_timeline_selection_changed(self, uid) -> None:
        """Timeline selection changed -> re-sync the Tools/Effect/Anim panels.

        Selecting different character clips (even back-to-back) always
        reflects the newly selected clip's characterId in the Anim tab.
        """
        clip = None
        if uid is not None:
            for c in self.timeline.scene_clips:
                if c.uid == uid:
                    clip = c
                    break
        self._request_preview()  # refresh the selection border on the stage
        if clip is None:
            self.left_sidebar.set_anim_character(None)
            self.left_sidebar.flip_h_btn.setEnabled(False)
            self.left_sidebar.flip_v_btn.setEnabled(False)
            self.left_sidebar.set_character_flip(False, False)
            return
        kind = (clip.data or (None, None))[0]
        if kind in ("character", "background"):
            self._sync_character_tools(clip)
        else:
            self.left_sidebar.set_anim_character(None)

    def _sync_character_tools(self, clip) -> None:
        """Update the Tools-tab controls from the selected scene clip."""
        if clip is None:
            return
        self._sync_scale_slider(clip)
        # The Animations tab shows only this character's animations
        kind, asset_id = (clip.data or (None, None))[:2]
        self.left_sidebar.set_anim_character(
            asset_id if kind == "character" else None
        )
        sx = getattr(clip, "x_offset", 0.0)
        sy = getattr(clip, "y_offset", 0.0)
        ex = sx if getattr(clip, "x_end", None) is None else clip.x_end
        ey = sy if getattr(clip, "y_end", None) is None else clip.y_end
        self.left_sidebar.set_character_positions(sx, sy, ex, ey)
        self.left_sidebar.set_character_speed(getattr(clip, "anim_speed", 1.0))
        is_character = kind == "character"
        self.left_sidebar.flip_h_btn.setEnabled(is_character)
        self.left_sidebar.flip_v_btn.setEnabled(is_character)
        self.left_sidebar.set_character_flip(
            bool(getattr(clip, "flip_h", False)) if is_character else False,
            bool(getattr(clip, "flip_v", False)) if is_character else False,
        )
        zs = getattr(clip, "zoom_start", 1.0)
        ze = getattr(clip, "zoom_end", None)
        self.left_sidebar.set_clip_zoom(
            int(round(zs * 100)),
            int(round((zs if ze is None else ze) * 100)),
        )

    def _on_speed_changed(self, value: float) -> None:
        """Tools tab speed spinner: scale the selected character's walk speed."""
        clip = self._selected_scene_clip()
        if clip is None:
            self.status_label.setText(
                "Select a character or background on the stage or timeline first."
            )
            return
        clip.anim_speed = max(0.1, float(value))
        self._render_preview()

    def _on_speed_commit(self) -> None:
        if self._selected_scene_clip() is not None:
            self._on_timeline_change()

    def _set_character_flip(self, axis: str, value: bool) -> None:
        """Tools tab flip toggles: mirror the selected character only."""
        clip = self._selected_scene_clip()
        if clip is None or not (clip.data and clip.data[0] == "character"):
            self.status_label.setText("Select a character first to flip it.")
            self._sync_character_tools(clip)
            return
        setattr(clip, "flip_h" if axis == "h" else "flip_v", bool(value))
        self._sync_character_tools(clip)
        self._render_preview()
        self._on_timeline_change()
        label = "horizontally" if axis == "h" else "vertically"
        state = "on" if value else "off"
        self.status_label.setText(f"Flip {label} {state} for '{clip.name}'.")

    def _on_flip_h(self, value: bool) -> None:
        self._set_character_flip("h", value)

    def _on_flip_v(self, value: bool) -> None:
        self._set_character_flip("v", value)

    def _scene_zoom_at(self, t: float) -> float:
        """Whole-frame camera zoom at time t from covering scene clips.

        A clip's zoom goes zoom_start -> zoom_end across its duration.
        If several covering clips have zooms, the strongest wins
        (max for zoom-in, min for zoom-out).
        """
        values = []
        for clip in self.timeline.scene_clips:
            if not (clip.start <= t < clip.start + clip.duration):
                continue
            zs = getattr(clip, "zoom_start", 1.0)
            ze = getattr(clip, "zoom_end", None)
            if ze is None:
                if abs(zs - 1.0) > 0.005:
                    values.append(zs)
            else:
                z = zs + (ze - zs) * self._clip_progress_at(clip, t)
                values.append(z)
        if not values:
            return 1.0
        ups = [v for v in values if v > 1.0]
        downs = [v for v in values if v < 1.0]
        if ups:
            return max(ups)
        if downs:
            return min(downs)
        return 1.0

    def _on_zoom_changed(self, point_key: str, value: int) -> None:
        """Effect tab zoom spinboxes: whole-frame zoom on the selected clip."""
        clip = self._selected_scene_clip()
        if clip is None:
            self.status_label.setText("Select a clip on the timeline first (click its block).")
            return
        if point_key == "start":
            clip.zoom_start = max(0.1, value / 100.0)
        else:
            clip.zoom_end = max(0.1, value / 100.0)
        self._render_preview()

    def _on_zoom_commit(self) -> None:
        if self._selected_scene_clip() is not None:
            self._on_timeline_change()

    _NUDGE_STEP = 10  # stage pixels per arrow click

    def _on_nudge(self, direction: str) -> None:
        """Arrow buttons move the point chosen in 'Drag sets' (Start/End)."""
        clip = self._selected_scene_clip()
        if clip is None:
            self.status_label.setText(
                "Select a character or background on the stage or timeline first."
            )
            return
        mode = self._drag_point_mode()
        step = self._NUDGE_STEP
        if mode == "end":
            # End point defaults to the start point until moved
            ex = clip.x_end if getattr(clip, "x_end", None) is not None else clip.x_offset
            ey = clip.y_end if getattr(clip, "y_end", None) is not None else clip.y_offset
            if direction == "left":
                clip.x_end = ex - step
            elif direction == "right":
                clip.x_end = ex + step
            elif direction == "up":
                clip.y_end = ey - step
            elif direction == "down":
                clip.y_end = ey + step
        else:
            if direction == "left":
                clip.x_offset -= step
            elif direction == "right":
                clip.x_offset += step
            elif direction == "up":
                clip.y_offset -= step
            elif direction == "down":
                clip.y_offset += step
        point_label = "start" if mode == "start" else "end"
        self.status_label.setText(
            f"Nudged '{clip.name}' {mode} point {direction}."
        )
        if mode == "end":
            ex = clip.x_end if getattr(clip, "x_end", None) is not None else clip.x_offset
            ey = clip.y_end if getattr(clip, "y_end", None) is not None else clip.y_offset
            self.status_label.setText(
                f"'{clip.name}' now moves to ({int(ex)}, {int(ey)}) at clip end."
            )
        self._render_preview()
        self._on_timeline_change()  # persist
        self._sync_character_tools(clip)

    def _on_position_changed(self, point_key: str, value: int) -> None:
        """Tools tab position spinboxes: set the selected scene clip's points."""
        clip = self._selected_scene_clip()
        if clip is None:
            self.status_label.setText(
                "Select a character or background on the stage or timeline first."
            )
            return
        if point_key == "start_x":
            clip.x_offset = value
        elif point_key == "start_y":
            clip.y_offset = value
        elif point_key == "end_x":
            clip.x_end = value
        elif point_key == "end_y":
            clip.y_end = value
        self._render_preview()

    def _on_position_commit(self) -> None:
        if self._selected_scene_clip() is not None:
            self._on_timeline_change()

    # ------------------------------------------------ cached db lookups
    def _cached_background(self, bg_id: int):
        try:
            return self._cache.db(("background", bg_id), lambda: database.get_background(bg_id))
        except Exception:
            return None

    def _cached_character(self, cid: int):
        try:
            return self._cache.db(("character", cid), lambda: database.get_character(cid))
        except Exception:
            return None

    def _cached_parts(self, cid: int) -> list:
        try:
            return self._cache.db(("parts", cid), lambda: database.list_character_parts(cid)) or []
        except Exception:
            return []

    def _cached_anims(self, cid: int) -> list:
        try:
            return self._cache.db(("anims", cid), lambda: database.list_character_animations(cid)) or []
        except Exception:
            return []

    def _cached_ik_anims(self, cid: int) -> list:
        """Saved IK keyframe animations (Character Details Animation tab)."""
        try:
            return (
                self._cache.db(
                    ("ikanims", cid),
                    lambda: database.list_character_ik_animations(int(cid)),
                )
                or []
            )
        except Exception:
            return []

    def _character_anim_for_clip(self, cid: int, anim_name: str) -> dict | None:
        """The animation row assigned to a character clip.

        IK keyframe animations (the ones created/played in the Character
        Details Animation tab) win; procedural walk-cycle presets are the
        fallback - so importing a character into a project plays the exact same
        animation the character details page plays.
        """
        ik_anims = self._cached_ik_anims(cid)
        anim = None
        for a in ik_anims:
            if a.get("name") == anim_name:
                anim = a
                break
        if anim is None and ik_anims:
            anim = ik_anims[0]
        if anim is None:
            anims = self._cached_anims(cid)
            for a in anims:
                if a.get("name") == anim_name:
                    anim = a
                    break
            if anim is None and anims:
                anim = anims[0]
        return anim
