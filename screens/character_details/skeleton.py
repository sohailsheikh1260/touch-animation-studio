"""Skeleton tab - 80% main + 20% sidebar with skeleton from character's skeleton_id."""

import math

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import database
from screens.character_details.skeleton_loader import (
    load_character_skeleton_data,
    part_draw_key,
)
from screens.character_details.styles import (
    ALL_PART_NAMES,
    HEADING_STYLE,
    MUTED,
    TEXT,
    make_hidden_icon,
    make_lock_icon,
    make_unlock_icon,
    make_visible_icon,
)
from screens.theme import BG, CARD_BG, MUTED, TEXT

# Styles
MAIN_STYLE = (
    f"QWidget {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px; }}"
)

SIDEBAR_STYLE = (
    f"QWidget {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px; }}"
)

BUTTON_STYLE = (
    f"QPushButton {{ background-color: #0e7490; color: #ffffff;"
    "  border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; }}"
    "QPushButton:hover { background-color: #0891b2; }"
)

SECONDARY_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #334155; color: {TEXT};"
    "  border: 1px solid #475569; border-radius: 8px; padding: 8px 16px; font-size: 13px; }}"
    "QPushButton:hover { background-color: #475569; }"
)

TOGGLE_STYLE = (
    f"QPushButton {{ background-color: #334155; color: {TEXT};"
    "  border: 1px solid #475569; border-radius: 8px; padding: 8px 10px; font-size: 12px; }}"
    "QPushButton:hover { background-color: #475569; }"
    "QPushButton:checked { background-color: #0e7490; color: #ffffff; border-color: #0e7490; }"
)

SPIN_STYLE = (
    f"QDoubleSpinBox {{ background-color: #334155; color: {TEXT};"
    "  border: 1px solid #475569; border-radius: 4px; padding: 4px 6px; font-size: 12px; }}"
    "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {"
    "  background-color: #475569; border: none; width: 16px; }"
)

COMBO_STYLE = (
    f"QComboBox {{ background-color: #334155; color: {TEXT}; "
    "border: 1px solid #475569; border-radius: 4px; padding: 4px 8px; font-size: 12px; }}"
    "QComboBox::drop-down { border: none; }"
    "QComboBox QAbstractItemView { background-color: #1e293b; color: #e2e8f0; "
    "selection-background-color: #0e7490; }"
)

SCROLL_STYLE = (
    "QScrollArea { border: none; background: transparent; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
    "QScrollBar:vertical { background: #1e293b; width: 8px; border-radius: 4px; margin: 0; }"
    "QScrollBar::handle:vertical { background: #475569; border-radius: 4px; min-height: 30px; }"
    "QScrollBar::handle:vertical:hover { background: #0e7490; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)

HEADING_STYLE = f"color: {TEXT}; font-size: 16px; font-weight: bold;"
MUTED_STYLE = f"color: {MUTED}; font-size: 13px;"
INFO_STYLE = f"color: {TEXT}; font-size: 14px;"


class BoneCanvas(QLabel):
    """QLabel canvas that forwards mouse/wheel events for bone dragging and zoom/pan."""

    def __init__(self, page: "SkeletonPage", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = page
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_press(event.position(), event.button())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_move(event.position())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_release(event.button())

    def wheelEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_wheel(event.angleDelta().y(), event.position())

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_leave()
        super().leaveEvent(event)


class SkeletonPage(QWidget):
    """Skeleton tab: static skeleton + body parts from character's skeleton_id, with drag tools."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._character = None
        self._bones = []
        self._bone_map = {}
        self._character = None
        self._bones = []
        self._bone_map = {}
        self._pixmap = None
        # visibility toggles
        self._show_skeleton = True
        self._show_body_parts = True
        # cached body part crops: part_name -> QPixmap
        self._part_crops: dict[str, QPixmap] = {}
        # attached images per bone: bone_name -> list of
        # {"id": int, "part": str | None, "dx": float, "dy": float, "index": int}
        self._bone_images: dict[str, list[dict]] = {}
        # locked bones: can't be dragged
        self._locked_bones: set[str] = set()
        # locked attached images per bone: bone_name -> set of image record ids that are locked
        self._locked_images: dict[str, set[int]] = {}
        # unified part draw-order index (shared with the Mark Character tab)
        self._part_layers: dict[str, int] = {}
        # unified part lock state (shared with the Mark Character tab)
        self._part_locks: dict[str, bool] = {}
        # hide/show flag per part (the Mark tab's payload "visible")
        self._part_visible: dict[str, bool] = {}
        # bone dragging state
        self._dragging_bone: str | None = None
        self._drag_start_mouse: tuple[float, float] | None = None
        self._drag_start_offset: tuple[float, float] | None = None
        # part-image dragging state (adjusting image position on the bone)
        self._drag_part_image: dict | None = None
        self._drag_part_start_mouse: tuple[float, float] | None = None
        self._drag_part_start: tuple[float, float] | None = None
        self._hover_part_image: dict | None = None
        # live (unsaved) bone offsets while dragging: bone_name -> (x_off, y_off)
        self._live_offsets: dict[str, tuple[float, float]] = {}
        self._hover_bone: str | None = None
        self._was_running = False
        # interaction mode: "select" (drag bones) or "image" (adjust attached images)
        self._mode = "select"
        # currently selected attached image (record + bone) shown in the sidebar editor
        self._selected_image_bone: str | None = None
        self._selected_image: dict | None = None
        # sidebar block widget of the currently selected image (for auto-scroll)
        self._selected_block: QWidget | None = None
        # image record whose part dropdown should pop open after a list rebuild
        self._pending_open_record: dict | None = None
        # view state: zoom + pan
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._panning = False
        self._pan_start_mouse: tuple[float, float] | None = None
        self._pan_start: tuple[float, float] | None = None
        # Extra drawable space around the canvas (world padding) so content
        # isn't cut off when zooming in / panning past the visible area
        self._world_pad = 800

        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)

        # ---- Main area (80%) ----
        main_widget = QWidget()
        main_widget.setStyleSheet(MAIN_STYLE)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        self.canvas = BoneCanvas(self)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setMinimumSize(500, 500)
        self.canvas.setStyleSheet(f"background-color: {BG}; border-radius: 8px;")
        main_layout.addWidget(self.canvas, 1)

        # Controls
        controls = QHBoxLayout()

        self.show_skeleton_btn = QPushButton("🦴 Skeleton: Show")
        self.show_skeleton_btn.setCheckable(True)
        self.show_skeleton_btn.setChecked(True)
        self.show_skeleton_btn.setToolTip("Show or hide the skeleton bones and joints")
        self.show_skeleton_btn.setStyleSheet(TOGGLE_STYLE)
        self.show_skeleton_btn.toggled.connect(self._on_show_skeleton_toggled)
        controls.addWidget(self.show_skeleton_btn)

        self.show_parts_btn = QPushButton("🖼 Parts: Show")
        self.show_parts_btn.setCheckable(True)
        self.show_parts_btn.setChecked(True)
        self.show_parts_btn.setToolTip("Show or hide the body part images")
        self.show_parts_btn.setStyleSheet(TOGGLE_STYLE)
        self.show_parts_btn.toggled.connect(self._on_show_parts_toggled)
        controls.addWidget(self.show_parts_btn)

        self.lock_all_btn = QPushButton("🔒 Lock All")
        self.lock_all_btn.setToolTip("Lock or unlock every bone in this skeleton")
        self.lock_all_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.lock_all_btn.clicked.connect(self._on_lock_all_clicked)
        controls.addWidget(self.lock_all_btn)

        controls.addStretch()

        self.reset_view_btn = QPushButton("🔍 Reset View")
        self.reset_view_btn.setCursor(Qt.PointingHandCursor)
        self.reset_view_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.reset_view_btn.clicked.connect(self._reset_view)
        controls.addWidget(self.reset_view_btn)

        tip = QLabel(
            "💡 Drag a yellow joint to move a bone • Click an image to select it, "
            "then drag it to position • Scroll to zoom • Right-drag to pan"
        )
        tip.setWordWrap(True)
        tip.setMaximumWidth(340)
        tip.setStyleSheet(MUTED_STYLE)
        controls.addWidget(tip)
        main_layout.addLayout(controls)

        # ---- Sidebar ----
        sidebar = QWidget()
        sidebar.setStyleSheet(SIDEBAR_STYLE)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        title = QLabel("Skeleton Info")
        title.setStyleSheet(HEADING_STYLE)
        sidebar_layout.addWidget(title)

        self.info_label = QLabel("No skeleton loaded")
        self.info_label.setStyleSheet(MUTED_STYLE)
        self.info_label.setWordWrap(True)
        sidebar_layout.addWidget(self.info_label)

        # ---- Interaction mode buttons removed ----
        # The Select / Image Pose / Lock buttons have been removed from the sidebar.
        # Mode state (_mode) is kept for compatibility but the UI no longer reflects it.

        # ---- Image position editor removed ----
        # The Image Position editor section has been removed from the sidebar.
        # Sidebar layout proceeds directly to the bone list scroll area.
        self.bones_list = QWidget()
        self.bones_list_layout = QVBoxLayout(self.bones_list)
        self.bones_list_layout.setContentsMargins(0, 8, 0, 0)
        self.bones_list_layout.setSpacing(4)
        self.bones_list.setStyleSheet("background: transparent;")

        # Scrollable bone list so long skeletons/big image lists stay usable
        self.bones_scroll = QScrollArea()
        self.bones_scroll.setWidgetResizable(True)
        self.bones_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.bones_scroll.setWidget(self.bones_list)
        self.bones_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.bones_scroll.setStyleSheet(SCROLL_STYLE)
        sidebar_layout.addWidget(self.bones_scroll, 1)

        root.addWidget(main_widget, 7)
        root.addWidget(sidebar, 3)

    def set_character(self, character) -> None:
        """Load character and its skeleton from DB using character's skeleton_id."""
        # Convert sqlite3.Row to dict for safe key access
        if hasattr(character, "keys"):
            self._character = dict(character)
        else:
            self._character = character

        self._reset_drag_state()
        if self._character is None:
            self._clear()
            return

        # Use shared loader - single source of truth for both tabs
        data = load_character_skeleton_data(self._character)

        self._bones = data["bones"]
        self._bone_map = data["bone_map"]
        self._part_crops = data["part_crops"]
        self._bone_images = data["bone_images"]
        self._locked_bones = data["locked_bones"]
        # Unified part draw-order index (shared with the Mark Character tab)
        self._part_layers = data.get("part_layers", {})
        # Unified part lock state (shared with the Mark Character tab)
        self._part_locks = data.get("part_locks", {})
        # Hide/show flags (shared with the Mark Character tab)
        self._part_visible = data.get("part_visible", {})
        # Load locked image IDs per bone
        self._locked_images = data.get("locked_images", {})
        # Convert lists to sets for fast lookup
        for bone_name, rec_ids in self._locked_images.items():
            if not isinstance(rec_ids, set):
                self._locked_images[bone_name] = set(rec_ids)

        if not self._bones:
            # Capture before _clear() wipes self._character
            skeleton_id = self._character.get("skeleton_id")
            self._clear()
            if skeleton_id:
                self.info_label.setText("Skeleton template has no bones")
            else:
                self.info_label.setText("No skeleton assigned to this character")
            return

        self._refresh_bone_list()
        self._draw_skeleton()
        skeleton_id = self._character.get("skeleton_id")
        self.info_label.setText(f"Skeleton ID: {skeleton_id}\nBones: {len(self._bones)}")

    def _clear(self) -> None:
        self._character = None
        self._bones = []
        self._bone_map = {}
        self._bone_images = {}
        self._part_crops = {}
        self._locked_bones = set()
        self._reset_drag_state()
        self.canvas.setText("No skeleton")
        self._refresh_bone_list()
        if hasattr(self, "lock_all_btn"):
            self._update_lock_all_btn()

    def _refresh_bone_list(self) -> None:
        """Rebuild the bone list in sidebar."""
        while self.bones_list_layout.count():
            item = self.bones_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._selected_block = None

        if not self._bones:
            empty = QLabel("No bones in skeleton")
            empty.setStyleSheet(MUTED_STYLE)
            empty.setWordWrap(True)
            self.bones_list_layout.addWidget(empty)
            return

        sorted_bones = sorted(self._bones, key=lambda b: (b["z_order"], b["bone_name"]))

        open_combo = None
        for bone in sorted_bones:
            bone_name = bone["bone_name"]
            block = QWidget()
            block.setStyleSheet(f"background-color: #1e293b; border-radius: 6px;")
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(8, 6, 8, 6)
            block_layout.setSpacing(4)

            header = QHBoxLayout()
            header.setSpacing(8)

            depth = self._get_bone_depth(bone_name)
            indent = QLabel("  " * depth)
            header.addWidget(indent)

            name_label = QLabel(f"🦴 {bone_name}")
            name_label.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 600;")
            header.addWidget(name_label, 1)

            if bone["parent_name"]:
                parent_label = QLabel(f"← {bone['parent_name']}")
                parent_label.setStyleSheet(MUTED_STYLE)
                parent_label.setFixedWidth(120)
                header.addWidget(parent_label)

            # Lock toggle per bone
            is_locked = bone_name in self._locked_bones
            lock_btn = QPushButton()
            lock_btn.setFixedSize(30, 26)
            lock_btn.setToolTip(
                f"{bone_name} is locked — click to unlock"
                if is_locked
                else f"Lock {bone_name} so it can't be dragged"
            )
            lock_btn.setCursor(Qt.PointingHandCursor)
            lock_btn.setStyleSheet(
                "QPushButton { background-color: #334155; color: #e2e8f0;"
                "  border: 1px solid #475569; border-radius: 5px; font-size: 12px; }"
                "QPushButton:hover { background-color: #0e7490; }"
                "QPushButton:pressed { background-color: #2563eb; color: #ffffff; }"
            )
            if is_locked:
                lock_btn.setIcon(make_lock_icon(20))
            else:
                lock_btn.setIcon(make_unlock_icon(20))
            lock_btn.clicked.connect(
                lambda _=False, bn=bone_name: self._on_bone_lock_toggled(bn)
            )
            header.addWidget(lock_btn)
            block_layout.addLayout(header)

            # One row per attached image: thumbnail select + part dropdown + remove
            records = self._bone_images.get(bone_name, [])
            for record in records:
                part = record["part"]
                img_row = QHBoxLayout()
                img_row.setSpacing(4)

                img_btn = QPushButton()
                img_btn.setCheckable(True)
                img_btn.setChecked(record is self._selected_image)
                img_btn.setFixedSize(36, 26)
                crop = self._part_crops.get(part)
                if crop is not None and not crop.isNull():
                    img_btn.setIcon(
                        QIcon(crop.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    )
                    img_btn.setIconSize(QSize(20, 20))
                    img_btn.setToolTip(f"Click to select this image ({part}) for positioning")
                else:
                    img_btn.setToolTip("Click to select this image for positioning")
                img_btn.setCursor(Qt.PointingHandCursor)
                img_btn.setStyleSheet(
                    "QPushButton { background-color: #334155; color: #e2e8f0;"
                    "  border: 1px solid #475569; border-radius: 5px; }"
                    "QPushButton:hover { background-color: #475569; }"
                    "QPushButton:checked { background-color: #0e7490; border-color: #0891b2; }"
                )
                img_btn.clicked.connect(
                    lambda _=False, bn=bone_name, rec=record: self._on_image_row_clicked(bn, rec)
                )
                img_row.addWidget(img_btn)

                # Part dropdown directly in the row
                dropdown = QComboBox()
                dropdown.addItems(["— None —"] + ALL_PART_NAMES)
                dropdown.setToolTip("Choose the body part for this image")
                dropdown.setStyleSheet(COMBO_STYLE)
                if part:
                    idx = dropdown.findText(part)
                    if idx >= 0:
                        dropdown.setCurrentIndex(idx)
                dropdown.currentTextChanged.connect(
                    lambda text, bn=bone_name, rec=record: self._on_part_changed(bn, rec, text)
                )
                if record is self._pending_open_record:
                    open_combo = dropdown
                img_row.addWidget(dropdown, 1)

                remove_btn = QPushButton("✕")
                remove_btn.setFixedSize(24, 26)
                remove_btn.setToolTip(f"Remove this image from {bone_name}")
                remove_btn.setCursor(Qt.PointingHandCursor)
                remove_btn.setStyleSheet(
                    "QPushButton { background-color: #334155; color: #e2e8f0;"
                    "  border: 1px solid #475569; border-radius: 5px; font-size: 12px; }"
                    "QPushButton:hover { background-color: #b91c1c; }"
                )
                remove_btn.clicked.connect(
                    lambda _=False, bn=bone_name, rec=record: self._on_image_removed(bn, rec)
                )
                img_row.addWidget(remove_btn)

                # Lock toggle for this attached image (part lock OR record lock)
                is_locked = self._image_effective_locked(record)
                lock_btn = QPushButton()
                lock_btn.setFixedSize(24, 26)
                lock_btn.setToolTip(
                    f"{record['part'] or 'image'} is locked — click to unlock"
                    if is_locked
                    else f"Lock {record['part'] or 'image'} so it can't be repositioned"
                )
                lock_btn.setCursor(Qt.PointingHandCursor)
                lock_btn.setStyleSheet(
                    "QPushButton { background-color: #334155; color: #e2e8f0;"
                    "  border: 1px solid #475569; border-radius: 5px; font-size: 11px; }"
                    "QPushButton:hover { background-color: #0e7490; color: #ffffff; }"
                    "QPushButton:pressed { background-color: #1e40af; color: #ffffff; }"
                )
                if is_locked:
                    lock_btn.setIcon(make_lock_icon(20))
                else:
                    lock_btn.setIcon(make_unlock_icon(20))
                lock_btn.clicked.connect(
                    lambda _=False, bn=bone_name, rec=record: self._on_image_lock_toggled(bn, rec)
                )
                img_row.addWidget(lock_btn)

                # Hide/show toggle (the Mark tab's per-part visibility flag)
                is_shown = self._record_shown(record)
                vis_btn = QPushButton()
                vis_btn.setFixedSize(24, 26)
                vis_btn.setToolTip(
                    f"Hide {record['part'] or 'image'} (shared with the Mark Character tab)"
                    if is_shown
                    else f"Show {record['part'] or 'image'} (shared with the Mark Character tab)"
                )
                vis_btn.setCursor(Qt.PointingHandCursor)
                vis_btn.setStyleSheet(
                    "QPushButton { background-color: #334155; color: #e2e8f0;"
                    "  border: 1px solid #475569; border-radius: 5px; font-size: 11px; }"
                    "QPushButton:hover { background-color: #0e7490; color: #ffffff; }"
                    "QPushButton:pressed { background-color: #1e40af; color: #ffffff; }"
                )
                if is_shown:
                    vis_btn.setIcon(make_visible_icon(20))
                else:
                    vis_btn.setIcon(make_hidden_icon(20))
                vis_btn.clicked.connect(
                    lambda _=False, bn=bone_name, rec=record: self._on_image_visible_toggled(bn, rec)
                )
                img_row.addWidget(vis_btn)

                # Index control buttons: + / -
                idx_row = QHBoxLayout()
                idx_row.setSpacing(2)
                plus_btn = QPushButton("+")
                plus_btn.setFixedSize(20, 20)
                plus_btn.setCursor(Qt.PointingHandCursor)
                plus_btn.setToolTip(
                    "Raise this body part's draw order (shared with the Mark Character tab)"
                )
                plus_btn.setStyleSheet(
                    "QPushButton { background-color: #0e7490; color: #e2e8f0;"
                    "  border: none; border-radius: 4px; font-size: 12px; font-weight: bold; }"
                    "QPushButton:hover { background-color: #0891b2; }"
                )
                plus_btn.clicked.connect(
                    lambda _=False, bn=bone_name, rec=record: self._on_image_index_plus(bn, rec)
                )
                idx_row.addWidget(plus_btn)

                minus_btn = QPushButton("-")
                minus_btn.setFixedSize(20, 20)
                minus_btn.setCursor(Qt.PointingHandCursor)
                minus_btn.setToolTip(
                    "Lower this body part's draw order (shared with the Mark Character tab)"
                )
                minus_btn.setStyleSheet(
                    "QPushButton { background-color: #0e7490; color: #e2e8f0;"
                    "  border: none; border-radius: 4px; font-size: 12px; font-weight: bold; }"
                    "QPushButton:hover { background-color: #0891b2; }"
                )
                minus_btn.clicked.connect(
                    lambda _=False, bn=bone_name, rec=record: self._on_image_index_minus(bn, rec)
                )
                idx_row.addWidget(minus_btn)

                # Index label showing the part's unified layer value
                layer_val = (
                    self._part_layers.get(record["part"], record.get("index", 0))
                    if record.get("part")
                    else record.get("index", 0)
                )
                idx_label = QLabel(str(layer_val))
                idx_label.setStyleSheet(INFO_STYLE)
                idx_label.setFixedWidth(28)
                idx_label.setAlignment(Qt.AlignCenter)
                idx_row.addWidget(idx_label, 0)

                img_row.addLayout(idx_row)

                block_layout.addLayout(img_row)

            if any(record is self._selected_image for record in records):
                self._selected_block = block

            # Attach another image to this bone
            add_btn = QPushButton("+ 🖼 Add Image")
            add_btn.setToolTip(f"Attach another body part image to {bone_name}")
            add_btn.setCursor(Qt.PointingHandCursor)
            add_btn.setStyleSheet(
                "QPushButton { background-color: #334155; color: #e2e8f0;"
                "  border: 1px solid #475569; border-radius: 5px; font-size: 12px; }"
                "QPushButton:hover { background-color: #0e7490; }"
            )
            add_btn.clicked.connect(
                lambda _=False, bn=bone_name: self._on_add_image(bn)
            )
            block_layout.addWidget(add_btn)

            self.bones_list_layout.addWidget(block)

        # After "+ Add Image": pop the new row's part dropdown open right away
        if self._pending_open_record is not None and open_combo is not None:
            QTimer.singleShot(60, open_combo.showPopup)
        self._pending_open_record = None

    def _on_add_image(self, bone_name: str) -> None:
        """Attach another image slot to a bone (saved to DB immediately)."""
        bone = self._bone_map.get(bone_name)
        if bone is None:
            return
        try:
            row = database.add_skeleton_bone_image(bone["id"], None, 0.0, 0.0, 0)
        except Exception as e:
            self.info_label.setText(f"Failed to add image: {e}")
            return
        record = {
            "id": row["id"], "part": None, "dx": 0.0, "dy": 0.0, "index": 0,
        }
        self._bone_images.setdefault(bone_name, []).append(record)
        # Select the new slot and pop its part dropdown open right away
        self._pending_open_record = record
        self._set_selected_image(bone_name, record)
        self._draw_skeleton()

    def _on_part_changed(self, bone_name: str, record: dict, part_name: str) -> None:
        """Update an attached image's body part when its dropdown changes (saved to DB)."""
        part = None if part_name == "— None —" else part_name
        record["part"] = part
        record["dx"] = 0.0
        record["dy"] = 0.0
        record["index"] = 0
        try:
            database.update_skeleton_bone_image(record["id"], part, 0.0, 0.0, 0)
        except Exception as e:
            self.info_label.setText(f"Failed to save bone image: {e}")
        if record is self._selected_image:
            self._refresh_image_editor()
        self._refresh_bone_list()
        self._draw_skeleton()

    def _on_image_removed(self, bone_name: str, record: dict) -> None:
        """Remove an attached image from a bone (saved to DB)."""
        try:
            database.delete_skeleton_bone_image(record["id"])
        except Exception as e:
            self.info_label.setText(f"Failed to remove image: {e}")
        if record is self._selected_image:
            self._selected_image = None
            self._selected_image_bone = None
            self._refresh_image_editor()
        records = self._bone_images.get(bone_name, [])
        if record in records:
            records.remove(record)
        if not records:
            self._bone_images.pop(bone_name, None)
        self._refresh_bone_list()
        self._draw_skeleton()

    # ---- Sidebar tool selection & image position editor ----

    def _set_mode(self, mode: str) -> None:
        """Switch between select (bones) and image (image position) modes.

        The Select / Image Pose / Lock buttons have been removed from the sidebar;
        this method is kept for compatibility but only updates the internal state.
        """
        self._mode = mode

    def _set_selected_image(self, bone_name: str | None, record: dict | None = None) -> None:
        """Mark an attached image as selected and refresh the editor + bone list."""
        if record is None:
            bone_name = None
        self._selected_image_bone = bone_name
        self._selected_image = record
        self._refresh_image_editor()
        self._refresh_bone_list()
        self._scroll_to_selected()

    def _on_image_row_clicked(self, bone_name: str, record: dict) -> None:
        """Select a bone's attached image from the sidebar list."""
        self._set_selected_image(bone_name, record)
        self._draw_skeleton()

    def _on_editor_part_changed(self, part_name: str) -> None:
        """Body part dropdown inside the image editor changed."""
        record = self._selected_image
        bone_name = self._selected_image_bone
        if record is None or bone_name is None:
            return
        self._on_part_changed(bone_name, record, part_name)

    def _on_editor_remove_clicked(self) -> None:
        """Remove the image currently being edited in the sidebar."""
        record = self._selected_image
        bone_name = self._selected_image_bone
        if record is None or bone_name is None:
            return
        self._on_image_removed(bone_name, record)

    def _scroll_to_selected(self) -> None:
        """Scroll the bone list so the selected image's bone block is visible."""
        if self._selected_block is not None:
            self.bones_scroll.ensureWidgetVisible(self._selected_block, 0, 60)

    def _refresh_image_editor(self) -> None:
        """Update the sidebar image-position editor from state.

        The Image Position editor section has been removed from the sidebar;
        this method is kept for compatibility but does nothing.
        """
        # The editor section is no longer part of the UI; nothing to refresh.
        pass

    def _on_image_spin_changed(self, _value: float) -> None:
        """Live-preview the offset while the user edits the spinboxes.

        The Image Position editor has been removed from the sidebar; this
        method is kept for compatibility but does nothing.
        """
        pass

    def _on_image_spin_committed(self) -> None:
        """Persist offsets when the user finishes editing a spinbox.

        The Image Position editor has been removed; this method is kept for
        compatibility but does nothing.
        """
        pass

    def _on_image_index_changed(self, _value: float) -> None:
        """Live-preview draw index change.

        The Image Position editor has been removed; this method is kept for
        compatibility but does nothing.
        """
        pass

    def _on_image_index_committed(self) -> None:
        """Persist draw index when the user finishes editing.

        The Image Position editor has been removed; this method is kept for
        compatibility but does nothing.
        """
        pass

    def _on_image_index_plus(self, bone_name: str, record: dict) -> None:
        """Raise the record's body part in the unified draw order.

        The layer index is stored once per part (character_parts.layer_index)
        and is the same index the Mark Character tab edits, so all three tabs
        stay in sync. Slots without a part fall back to the per-record image
        index.
        """
        part = record.get("part")
        char_id = self._character.get("id") if self._character else None
        if part and char_id is not None:
            try:
                new_layer = database.bump_character_part_layer_by_name(
                    int(char_id), part, +1
                )
            except Exception as e:
                self.info_label.setText(f"Failed to save layer index: {e}")
                return
            if new_layer is not None:
                self._part_layers[part] = new_layer
                self._refresh_bone_list()
                self._draw_skeleton()
                return
        self._bump_record_index(bone_name, record, +1)

    def _on_image_index_minus(self, bone_name: str, record: dict) -> None:
        """Lower the record's body part in the unified draw order."""
        part = record.get("part")
        char_id = self._character.get("id") if self._character else None
        if part and char_id is not None:
            try:
                new_layer = database.bump_character_part_layer_by_name(
                    int(char_id), part, -1
                )
            except Exception as e:
                self.info_label.setText(f"Failed to save layer index: {e}")
                return
            if new_layer is not None:
                self._part_layers[part] = new_layer
                self._refresh_bone_list()
                self._draw_skeleton()
                return
        self._bump_record_index(bone_name, record, -1)

    def _bump_record_index(self, bone_name: str, record: dict, delta: int) -> None:
        """Legacy fallback: cycle this record's image index within its bone."""
        current_index = record.get("index", 0)
        records = self._bone_images.get(bone_name, [])
        if not records:
            return
        max_index = len(records) - 1
        new_index = min(max(current_index + delta, 0), max_index)
        if new_index != current_index:
            record["index"] = new_index
            try:
                database.update_skeleton_bone_image(
                    record["id"], record["part"], 0.0, 0.0, int(new_index),
                )
            except Exception as e:
                self.info_label.setText(f"Failed to save image index: {e}")
                return
            # Refresh the bone list and redraw to reflect the change
            self._refresh_bone_list()
            self._draw_skeleton()

    def _on_image_offset_reset(self) -> None:
        """Reset the selected image offset to (0, 0) and save.

        The Image Position editor has been removed; this method is kept for
        compatibility but does nothing.
        """
        pass

    def _persist_image(self, record: dict) -> None:
        """Save an attached image's part + offset + index to the DB."""
        try:
            database.update_skeleton_bone_image(
                record["id"], record["part"], float(record["dx"]), float(record["dy"]), int(record["index"]),
            )
        except Exception as e:
            self.info_label.setText(f"Failed to save bone image: {e}")

    def _get_bone_depth(self, bone_name: str) -> int:
        depth = 0
        current = self._bone_map.get(bone_name)
        while current and current["parent_name"]:
            depth += 1
            current = self._bone_map.get(current["parent_name"])
            if depth > 20:
                break
        return depth

    def _on_show_skeleton_toggled(self, checked: bool) -> None:
        """Show/hide the skeleton bones and joints."""
        self._show_skeleton = bool(checked)
        self.show_skeleton_btn.setText(
            "🦴 Skeleton: Show" if checked else "🦴 Skeleton: Hide"
        )
        self._draw_skeleton()

    def _on_show_parts_toggled(self, checked: bool) -> None:
        """Show/hide the body part images."""
        self._show_body_parts = bool(checked)
        self.show_parts_btn.setText("🖼 Parts: Show" if checked else "🖼 Parts: Hide")
        self._draw_skeleton()

    def _on_bone_lock_toggled(self, bone_name: str) -> None:
        """Toggle a bone's lock state and save it to the DB."""
        bone = self._bone_map.get(bone_name)
        if bone is None:
            return
        is_locked = bone_name not in self._locked_bones
        if is_locked:
            self._locked_bones.add(bone_name)
        else:
            self._locked_bones.discard(bone_name)
        try:
            database.set_skeleton_bone_locked(bone["id"], is_locked)
        except Exception as e:
            self.info_label.setText(f"Failed to save lock state: {e}")
        # Register the new cursor/tooltip state in the sidebar row
        self._update_lock_all_btn()
        self._refresh_bone_list()

    def _record_shown(self, record: dict) -> bool:
        """False when the record's body part is hidden.

        Uses the Mark tab's hide/show flag (payload "visible"), shared by
        all three tabs. Records without a body part are always shown.
        """
        part = record.get("part")
        if not part:
            return True
        return bool(self._part_visible.get(part, True))

    def _image_effective_locked(self, record: dict) -> bool:
        """Effective lock for an attached image.

        The part-level lock (character_parts.is_locked - the same lock the
        Mark Character tab edits) wins; the per-record skeleton_bone_images
        lock still applies on its own for slots without a body part.
        """
        part = record.get("part")
        if part and self._part_locks.get(part, False):
            return True
        return bool(record.get("is_locked", False))

    def _on_image_lock_toggled(self, bone_name: str, record: dict) -> None:
        """Toggle the lock for an attached image and save it.

        Images attached to a body part share that part's unified lock (the
        same lock the Mark Character tab edits), so locking here locks it
        everywhere. Slots without a matching part fall back to the
        per-record lock stored on the bone image itself.
        """
        part = record.get("part")
        char_id = self._character.get("id") if self._character else None
        if part and char_id is not None:
            now_locked = not bool(self._part_locks.get(part, False))
            try:
                ok = database.set_character_part_locked_by_name(
                    int(char_id), part, now_locked
                )
            except Exception as e:
                self.info_label.setText(f"Failed to save lock state: {e}")
                return
            if ok:
                self._part_locks[part] = now_locked
                self._update_lock_all_btn()
                self._refresh_bone_list()
                return
            # No matching character_parts row -> record-level lock below.
        # Record-level fallback (image slot without a body part)
        image_id = record["id"]
        bone = self._bone_map.get(bone_name)
        if bone is None:
            return
        # Initialize the locked set for this bone if needed
        if bone_name not in self._locked_images:
            self._locked_images[bone_name] = set()
        if image_id in self._locked_images[bone_name]:
            self._locked_images[bone_name].discard(image_id)
            new_label = "🔓"
            new_tooltip = f"Lock {record['part'] or 'image'} so it can't be repositioned"
        else:
            self._locked_images[bone_name].add(image_id)
            new_label = "🔒"
            new_tooltip = f"{record['part'] or 'image'} is locked — click to unlock"
        record["is_locked"] = image_id in self._locked_images[bone_name]
        # Persist the lock state to the DB
        try:
            database.update_skeleton_bone_image(
                image_id, record["part"], float(record["dx"]), float(record["dy"]), int(record["index"]), int(record["is_locked"]),
            )
        except Exception as e:
            self.info_label.setText(f"Failed to save bone image lock: {e}")
            # Revert the in-memory state
            if image_id in self._locked_images.get(bone_name, set()):
                self._locked_images[bone_name].discard(image_id)
                record["is_locked"] = False
            return
        # Refresh UI
        self._update_lock_all_btn()
        self._refresh_bone_list()

    def _on_image_visible_toggled(self, bone_name: str, record: dict) -> None:
        """Hide/show the record's body part.

        This is the exact same flag the Mark Character tab's eye button
        toggles (payload "visible"), so hiding a part here hides it in the
        Mark tab's canvas and in the Animation tab as well.
        """
        part = record.get("part")
        char_id = self._character.get("id") if self._character else None
        if not part or char_id is None:
            self.info_label.setText("Assign a body part to this image first")
            return
        now_shown = not bool(self._part_visible.get(part, True))
        try:
            ok = database.set_character_part_visible_by_name(
                int(char_id), part, now_shown
            )
        except Exception as e:
            self.info_label.setText(f"Failed to save visibility: {e}")
            return
        if not ok:
            self.info_label.setText(f"No body part named '{part}'")
            return
        self._part_visible[part] = now_shown
        self._refresh_bone_list()
        self._draw_skeleton()

    def _on_lock_all_clicked(self) -> None:
        """Lock or unlock all bones at once."""
        lock_all = len(self._locked_bones) < len(self._bone_map)
        new_locked = set(self._bone_map) if lock_all else set()
        for bone_name, bone in self._bone_map.items():
            was_locked = bone_name in self._locked_bones
            now_locked = bone_name in new_locked
            if was_locked != now_locked:
                try:
                    database.set_skeleton_bone_locked(bone["id"], now_locked)
                except Exception as e:
                    self.info_label.setText(f"Failed to save lock state: {e}")
        self._locked_bones = new_locked
        self._update_lock_all_btn()
        self._refresh_bone_list()
        self._draw_skeleton()

    def _on_lock_toggled(self) -> None:
        """Lock or unlock the selected/bone under cursor."""
        # If a bone is selected in the list, lock/unlock that bone
        if self._selected_image_bone:
            bone_name = self._selected_image_bone
        else:
            # Try to lock the bone under the cursor (hit test)
            name = self._hit_test_bone(mx=0, my=0)  # simplified - will use actual mouse pos
            bone_name = name if name else None
        
        if bone_name and bone_name in self._bone_map:
            was_locked = bone_name in self._locked_bones
            if was_locked:
                self._locked_bones.discard(bone_name)
            else:
                self._locked_bones.add(bone_name)
            try:
                bone = self._bone_map[bone_name]
                database.set_skeleton_bone_locked(bone["id"], bone_name in self._locked_bones)
            except Exception as e:
                self.info_label.setText(f"Failed to save lock state: {e}")
            self._update_lock_all_btn()
            self._refresh_bone_list()
            self._draw_skeleton()

    def _update_lock_all_btn(self) -> None:
        """Update the Lock All button label based on current state."""
        all_locked = bool(self._bone_map) and len(self._locked_bones) >= len(self._bone_map)
        self.lock_all_btn.setText("🔓 Unlock All" if all_locked else "🔒 Lock All")

    def _draw_skeleton(self) -> None:
        """Draw skeleton from bone hierarchy with walking animation and body parts."""
        if not self._bones:
            self.canvas.setText("No skeleton")
            return

        # Visible content matches the canvas size, but we draw into a larger
        # padded world so zooming/panning past the edges doesn't cut content.
        w = max(500, self.canvas.width())
        h = max(500, self.canvas.height())
        pad = self._world_pad
        pw, ph = w + 2 * pad, h + 2 * pad
        cx, cy = pw // 2, ph // 2

        pm = QPixmap(pw, ph)
        pm.fill(QColor(BG))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)

        bone_positions = self._compute_bone_positions(cx, cy)

        # Draw body parts first (lowest layer, under the skeleton)
        if self._show_body_parts:
            self._draw_body_parts(p, bone_positions)

        # Draw skeleton (bones/joints/names) on top of body parts
        if self._show_skeleton:
            self._draw_bone_lines(p, bone_positions)
            self._draw_joints(p, bone_positions)

        p.end()
        self._pixmap = pm
        self._update_canvas()

    def _draw_bone_lines(self, p: QPainter, bone_positions: dict) -> None:
        """Draw bone lines."""
        bone_color = QColor("#38bdf8")
        pen = p.pen()
        pen.setColor(bone_color)
        pen.setWidth(4)
        p.setPen(pen)

        for bone in self._bones:
            parent_name = bone["parent_name"]
            if parent_name and parent_name in bone_positions:
                x1, y1 = bone_positions[parent_name]
                x2, y2 = bone_positions[bone["bone_name"]]
                p.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _draw_joints(self, p: QPainter, bone_positions: dict) -> None:
        """Draw joints (highlight hovered/dragged one) and bone names."""
        joint_color = QColor("#facc15")
        highlight = self._dragging_bone or self._hover_bone
        pen = p.pen()

        for bone_name, (x, y) in bone_positions.items():
            if bone_name == highlight:
                pen.setColor(QColor("#4ade80"))
                pen.setWidth(14 if self._dragging_bone else 13)
            elif bone_name in self._locked_bones:
                pen.setColor(QColor("#94a3b8"))
                pen.setWidth(10)
            else:
                pen.setColor(joint_color)
                pen.setWidth(10)
            p.setPen(pen)
            p.drawPoint(int(x), int(y))

        # Draw bone names
        p.setPen(QColor(TEXT))
        for bone_name, (x, y) in bone_positions.items():
            p.drawText(int(x) + 12, int(y) + 4, bone_name)

    def _draw_body_parts(self, painter: QPainter, bone_positions: dict) -> None:
        """Draw all body part images attached to bones (with adjustable offsets).

        Images are drawn in the unified draw order: the part's layer index
        (the same index the Mark Character tab edits), then the bone-image
        index as tiebreaker - higher draws on top. Locked images are drawn
        semi-transparent to indicate they cannot be repositioned.
        """
        entries = [
            (bone_name, record)
            for bone_name, records in self._bone_images.items()
            for record in records
        ]
        ordered = sorted(entries, key=lambda item: part_draw_key(self._part_layers, item))
        for bone_name, record in ordered:
            # Hidden parts (Mark tab hide/show) are not drawn at all
            if not self._record_shown(record):
                continue
            rect = self._part_image_rect(bone_positions, bone_name, record)
            if rect is None:
                continue
            x, y, rw, rh = rect
            painter.drawPixmap(int(x), int(y), self._part_crops[record["part"]])

    def _part_image_rect(self, bone_positions: dict, bone_name: str, record: dict) -> tuple | None:
        """Top-left position and size of an attached image, or None."""
        crop = self._part_crops.get(record["part"])
        if not crop or crop.isNull() or bone_name not in bone_positions:
            return None
        x, y = bone_positions[bone_name]
        return (x - crop.width() / 2 + record["dx"], y - crop.height() / 2 + record["dy"],
                crop.width(), crop.height())

    def _compute_bone_positions(self, root_x: float, root_y: float) -> dict:
        """Compute world positions for all bones from hierarchy (static pose)."""
        positions = {}
        root_bone = next((b for b in self._bones if not b["parent_name"]), None)
        if root_bone:
            rx_off, ry_off = self._effective_offsets(root_bone)
            positions[root_bone["bone_name"]] = (root_x + rx_off, root_y + ry_off)

        sorted_bones = sorted(self._bones, key=lambda b: b["z_order"])

        for bone in sorted_bones:
            name = bone["bone_name"]
            if name in positions:
                continue

            parent_name = bone["parent_name"]
            if parent_name and parent_name in positions:
                px, py = positions[parent_name]
                angle_deg = bone["angle"]
                x_off, y_off = self._effective_offsets(bone)

                angle_rad = math.radians(angle_deg)
                length = bone["length"]

                child_x = px + x_off + math.sin(angle_rad) * length
                child_y = py + y_off + math.cos(angle_rad) * length

                positions[name] = (child_x, child_y)
            elif not parent_name:
                rx_off, ry_off = self._effective_offsets(bone)
                positions[name] = (root_x + rx_off, root_y + ry_off)

        return positions

    def _effective_offsets(self, bone) -> tuple[float, float]:
        """Bone offsets, overridden by unsaved drag offsets while dragging."""
        name = bone["bone_name"]
        live = self._live_offsets.get(name)
        if live:
            return float(live[0]), float(live[1])
        return float(bone["x_offset"]), float(bone["y_offset"])

    def _update_canvas(self) -> None:
        if self._pixmap:
            _, _, _, _, scale, ox, oy = self._view_params()
            cw, ch = self.canvas.width(), self.canvas.height()
            if cw <= 0 or ch <= 0 or scale <= 0:
                return
            # Composite view at current zoom/pan: world pixmap drawn at scale,
            # with its top-left at (ox, oy)
            out = QPixmap(cw, ch)
            out.fill(QColor(BG))
            p = QPainter(out)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            dw = max(1, int(self._pixmap.width() * scale))
            dh = max(1, int(self._pixmap.height() * scale))
            p.drawPixmap(int(round(ox)), int(round(oy)), dw, dh, self._pixmap)
            p.end()
            self.canvas.setPixmap(out)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-render the world at the new canvas size (no timer anymore)
        self._draw_skeleton()

    # ---- Bone dragging ----

    def _view_params(self) -> tuple[float, float, float, float, float, float, float]:
        """Current canvas view: (w, h, center_x, center_y, scale, origin_x, origin_y).

        The skeleton is drawn into a padded pixmap of (w + 2*pad, h + 2*pad) with
        the root at the pixmap center. `scale = fit * zoom`, where fit is based on
        the visible content (w, h) so the default view is unchanged. The pixmap
        origin maps to (origin_x, origin_y) in widget coords.
        """
        w = max(500, self.canvas.width())
        h = max(500, self.canvas.height())
        cw, ch = self.canvas.width(), self.canvas.height()
        pad = self._world_pad
        pw, ph = w + 2 * pad, h + 2 * pad
        scale = (min(cw / w, ch / h) if cw > 0 and ch > 0 else 1.0) * self._zoom
        ox = cw / 2 - (pw / 2) * scale + self._pan_x
        oy = ch / 2 - (ph / 2) * scale + self._pan_y
        return w, h, pw // 2, ph // 2, scale, ox, oy

    def _hit_test_bone(self, mx: float, my: float) -> str | None:
        """Return the name of the bone joint nearest to canvas coords (mx, my)."""
        _, _, cx, cy, scale, _, _ = self._view_params()
        positions = self._compute_bone_positions(cx, cy)
        hit_radius = 15.0 / scale
        nearest = None
        best = hit_radius * hit_radius
        for name, (bx, by) in positions.items():
            if name in self._locked_bones:
                continue
            dx, dy = mx - bx, my - by
            d2 = dx * dx + dy * dy
            if d2 < best:
                best = d2
                nearest = name
        return nearest

    def _hit_test_part_image(
        self, mx: float, my: float, margin: float = 0.0
    ) -> tuple[str, dict] | None:
        """Return (bone_name, record) whose attached image contains canvas coords (mx, my)."""
        _, _, cx, cy, _, _, _ = self._view_params()
        positions = self._compute_bone_positions(cx, cy)
        for bone_name, records in self._bone_images.items():
            if bone_name in self._locked_bones:
                continue
            for record in records:
                # Skip hidden and locked images
                if not self._record_shown(record) or self._image_effective_locked(record):
                    continue
                rect = self._part_image_rect(positions, bone_name, record)
                if rect is None:
                    continue
                rx, ry, rw, rh = rect
                if (rx - margin <= mx <= rx + rw + margin
                        and ry - margin <= my <= ry + rh + margin):
                    return bone_name, record
        return None

    def _nearest_part_image(
        self, mx: float, my: float, limit: float
    ) -> tuple[str, dict] | None:
        """Return (bone_name, record) whose attached image center is closest (within limit)."""
        _, _, cx, cy, _, _, _ = self._view_params()
        positions = self._compute_bone_positions(cx, cy)
        nearest = None
        best = limit * limit
        for bone_name, records in self._bone_images.items():
            if bone_name in self._locked_bones:
                continue
            for record in records:
                # Skip hidden and locked images
                if not self._record_shown(record) or self._image_effective_locked(record):
                    continue
                rect = self._part_image_rect(positions, bone_name, record)
                if rect is None:
                    continue
                icx, icy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
                dx, dy = mx - icx, my - icy
                d2 = dx * dx + dy * dy
                if d2 < best:
                    best = d2
                    nearest = (bone_name, record)
        return nearest

    def _reset_drag_state(self) -> None:
        self._dragging_bone = None
        self._drag_start_mouse = None
        self._drag_start_offset = None
        self._live_offsets = {}
        self._hover_bone = None
        self._drag_part_image = None
        self._drag_part_start_mouse = None
        self._drag_part_start = None
        self._hover_part_image = None
        self._selected_image_bone = None
        self._selected_image = None
        self._refresh_image_editor()
        self._panning = False
        self._pan_start_mouse = None
        self._pan_start = None
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    def _reset_view(self) -> None:
        """Reset zoom and pan to default fit view."""
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_canvas()

    def _on_canvas_press(self, wpos, button=Qt.LeftButton) -> None:
        # Right / middle button always pans
        if button != Qt.LeftButton:
            self._start_pan(wpos)
            return
        if not self._bones:
            self._start_pan(wpos)
            return
        _, _, _, _, scale, ox, oy = self._view_params()
        mx = (wpos.x() - ox) / scale
        my = (wpos.y() - oy) / scale

        name = self._hit_test_bone(mx, my)

        # Image mode: attached images are grabbed first (even over joints)
        if self._mode == "image":
            hit = self._hit_test_part_image(mx, my, margin=10.0 / scale)
            if hit is None:
                hit = self._nearest_part_image(mx, my, limit=50.0 / scale)
            if hit is not None:
                self._start_drag_image(hit[0], hit[1], mx, my)
                return

        if name is None and self._mode == "select":
            hit = self._hit_test_part_image(mx, my)
            if hit is None:
                # Left press on empty space pans the view
                self._start_pan(wpos)
                return
            self._start_drag_image(hit[0], hit[1], mx, my)
            return

        bone = self._bone_map.get(name) if name else None
        if bone is not None:
            self._dragging_bone = name
            self._drag_start_mouse = (mx, my)
            self._drag_start_offset = self._effective_offsets(bone)
            self.canvas.setCursor(Qt.ClosedHandCursor)
            self._draw_skeleton()
            return

        # No joint hit: try the body part images attached to bones
        hit = self._hit_test_part_image(mx, my)
        if hit is not None:
            self._start_drag_image(hit[0], hit[1], mx, my)
            return

        # Left press on empty space pans the view
        self._start_pan(wpos)

    def _start_drag_image(self, bone_name: str, record: dict, mx: float, my: float) -> None:
        """Start dragging an attached body part image."""
        self._set_selected_image(bone_name, record)
        self._drag_part_image = record
        self._drag_part_start_mouse = (mx, my)
        self._drag_part_start = (record["dx"], record["dy"])
        self.canvas.setCursor(Qt.SizeAllCursor)
        self._draw_skeleton()

    def _start_pan(self, wpos) -> None:
        self._panning = True
        self._pan_start_mouse = (wpos.x(), wpos.y())
        self._pan_start = (self._pan_x, self._pan_y)
        self.canvas.setCursor(Qt.ClosedHandCursor)

    def _on_canvas_move(self, wpos) -> None:
        if self._panning and self._pan_start_mouse is not None:
            dx = wpos.x() - self._pan_start_mouse[0]
            dy = wpos.y() - self._pan_start_mouse[1]
            self._pan_x = self._pan_start[0] + dx
            self._pan_y = self._pan_start[1] + dy
            self._update_canvas()
            return
        if not self._bones or self._pixmap is None:
            return
        _, _, _, _, scale, ox, oy = self._view_params()
        mx = (wpos.x() - ox) / scale
        my = (wpos.y() - oy) / scale

        if self._dragging_bone:
            sx, sy = self._drag_start_mouse
            self._live_offsets[self._dragging_bone] = (
                self._drag_start_offset[0] + (mx - sx),
                self._drag_start_offset[1] + (my - sy),
            )
            self._draw_skeleton()
            return

        if self._drag_part_image:
            record = self._drag_part_image
            sx, sy = self._drag_part_start_mouse
            record["dx"] = self._drag_part_start[0] + (mx - sx)
            record["dy"] = self._drag_part_start[1] + (my - sy)
            self._draw_skeleton()
            return

        # Hover: highlight nearest joint, or attached image under cursor
        hover = self._hit_test_bone(mx, my)
        hover_hit = None if hover else self._hit_test_part_image(mx, my)
        hover_record = hover_hit[1] if hover_hit else None
        if hover != self._hover_bone or hover_record is not self._hover_part_image:
            self._hover_bone = hover
            self._hover_part_image = hover_record
            cursor = Qt.PointingHandCursor if (hover or hover_record) else Qt.OpenHandCursor
            self.canvas.setCursor(cursor)
            self._draw_skeleton()

    def _on_canvas_release(self, button=Qt.LeftButton) -> None:
        if self._panning:
            self._panning = False
            self._pan_start_mouse = None
            self._pan_start = None
            self.canvas.setCursor(Qt.OpenHandCursor)
            return
        if self._drag_part_image:
            record = self._drag_part_image
            self._drag_part_image = None
            self._drag_part_start_mouse = None
            self._drag_part_start = None
            self.canvas.setCursor(Qt.OpenHandCursor)
            # Persist the new offset to the database immediately
            self._persist_image(record)
            # Update the in-memory bone image record so the display reflects
            # the new position right away, without a full DB reload that could
            # snap the part back to its previous offset.
            bone_name = self._selected_image_bone
            if bone_name and self._bone_images.get(bone_name):
                for rec in self._bone_images[bone_name]:
                    if rec["id"] == record["id"]:
                        rec["dx"] = record["dx"]
                        rec["dy"] = record["dy"]
                        break
            self._draw_skeleton()
            return
        if not self._dragging_bone:
            return
        name = self._dragging_bone
        bone = self._bone_map.get(name)
        self._dragging_bone = None
        self._drag_start_mouse = None
        self._drag_start_offset = None
        self.canvas.setCursor(Qt.OpenHandCursor)

        if bone is not None and name in self._live_offsets:
            x_off, y_off = self._live_offsets[name]
            try:
                database.update_skeleton_bone(
                    bone["id"],
                    bone["bone_name"],
                    bone["parent_name"],
                    float(x_off),
                    float(y_off),
                    bone["length"],
                    bone["angle"],
                    bone["z_order"],
                )
            except Exception as e:
                self._live_offsets.pop(name, None)
                self.info_label.setText(f"Failed to save bone position: {e}")
            self._reload_bones()

        self._draw_skeleton()

    def _on_canvas_wheel(self, delta_y: int, wpos) -> None:
        """Zoom in/out, keeping the world point under the cursor fixed."""
        if not self._pixmap:
            return
        _, _, _, _, old_scale, ox, oy = self._view_params()
        world_x = (wpos.x() - ox) / old_scale
        world_y = (wpos.y() - oy) / old_scale

        factor = 1.15 if delta_y > 0 else 1 / 1.15
        new_zoom = min(5.0, max(0.3, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        self._zoom = new_zoom

        # Re-compute with new zoom and adjust pan so the cursor stays over
        # the same world point.
        _, _, _, _, new_scale, _, _ = self._view_params()
        cw, ch = self.canvas.width(), self.canvas.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        self._pan_x = wpos.x() - world_x * new_scale - cw / 2 + (pw / 2) * new_scale
        self._pan_y = wpos.y() - world_y * new_scale - ch / 2 + (ph / 2) * new_scale
        self._update_canvas()

    def _on_canvas_leave(self) -> None:
        if self._panning:
            self._panning = False
            self._pan_start_mouse = None
            self._pan_start = None
            self.canvas.setCursor(Qt.OpenHandCursor)
            self._update_canvas()
            return
        if self._dragging_bone:
            # Cancel drag when the cursor leaves the canvas
            name = self._dragging_bone
            self._dragging_bone = None
            self._drag_start_mouse = None
            self._drag_start_offset = None
            self._live_offsets.pop(name, None)
            self.canvas.setCursor(Qt.OpenHandCursor)
            self._draw_skeleton()
            return
        if self._drag_part_image:
            # Cancel image drag when the cursor leaves the canvas
            record = self._drag_part_image
            record["dx"], record["dy"] = self._drag_part_start
            self._drag_part_image = None
            self._drag_part_start_mouse = None
            self._drag_part_start = None
            self.canvas.setCursor(Qt.OpenHandCursor)
            self._draw_skeleton()
            return
        if self._hover_bone or self._hover_part_image:
            self._hover_bone = None
            self._hover_part_image = None
            self.canvas.setCursor(Qt.OpenHandCursor)
            self._draw_skeleton()

    def _reload_bones(self) -> None:
        """Re-read bones from DB so saved offsets are reflected everywhere."""
        character_id = self._character.get("id") if self._character else None
        if not character_id:
            return
        rows = database.list_skeleton_bones(character_id)
        self._bones = list(rows)
        self._bone_map = {b["bone_name"]: b for b in self._bones}
        self._live_offsets = {}
        # Reload bone images from DB (preserving selection)
        selected_id = self._selected_image["id"] if self._selected_image else None
        bone_ids = [b["id"] for b in self._bones]
        by_bone = database.list_skeleton_bone_images(bone_ids) if bone_ids else {}
        self._bone_images = {}
        for b in self._bones:
            records = [
                {
                    "id": row["id"],
                    "part": row["part_name"],
                    "dx": float(row["image_dx"] or 0.0),
                    "dy": float(row["image_dy"] or 0.0),
                    "index": int(row["image_index"] or 0),
                }
                for row in by_bone.get(b["id"], [])
            ]
            if records:
                self._bone_images[b["bone_name"]] = records
        self._locked_bones = {
            b["bone_name"]
            for b in self._bones
            if "is_locked" in b.keys() and b["is_locked"]
        }
        # Keep the selection pointing at the same image after a reload
        self._selected_image = None
        if selected_id is not None and self._selected_image_bone:
            for record in self._bone_images.get(self._selected_image_bone, []):
                if record["id"] == selected_id:
                    self._selected_image = record
                    break
            if self._selected_image is None:
                self._selected_image_bone = None
        self._refresh_bone_list()