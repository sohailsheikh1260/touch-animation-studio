"""Mark Character tab - character image canvas + body-part annotations.

- 80% main layout: character image on a 2048x2048 white canvas with zoom/pan.
- 20% tool sidebar: zoom slider + body-part list (name + top/left/width/height
  coordinates stored as JSON payload), drawn as semi-transparent red boxes
  ("#ff000042") that stay glued to the image across zoom and pan.
"""

import json

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import database
from screens.character import image_store
from screens.character_details.export import export_character, import_character
from screens.character_details.styles import (
    ALL_PART_NAMES,
    DELETE_BUTTON_STYLE,
    HEADING_STYLE,
    IMAGE_PANEL_STYLE,
    INFO_TEXT,
    INPUT_STYLE,
    MUTED_TEXT,
    PLACEHOLDER_STYLE,
    TOP_BUTTON_STYLE,
    make_delete_icon,
    make_edit_icon,
    make_hidden_icon,
    make_lock_icon,
    make_select_icon,
    make_unlock_icon,
    make_visible_icon,
)

ICON = "🧍"


def default_part_payload() -> str:
    """Default coordinates/size for a new part (drag to reposition later)."""
    return json.dumps(
        {
            "top": 200,
            "left": 200,
            "width": 200,
            "height": 200,
            "x": 200,
            "y": 200,
        }
    )


def seed_default_marks(owner_id: int, store=None) -> int:
    """Add every standard mark the owner is missing.

    Shared by the Mark tab's "Add All Parts" button and by the
    create-character drawer's Marking option, so both produce exactly the
    same default character marks. Returns how many marks were created.
    """
    store = store or CharacterMarkStore()
    used = {p["part_name"] for p in store.list_parts(owner_id)}
    payload = default_part_payload()
    added = 0
    for name in store.part_names:
        if name in used:
            continue
        used.add(name)  # a name listed twice in part_names = one part
        try:
            store.create_part(owner_id, name, "", payload)
        except ValueError:
            continue  # skip names the store rejects
        added += 1
    return added


def copy_marker_marks(marker_id: int, character_id: int) -> int:
    """Copy a marker's marks onto a character (same names + box geometry).

    Used by the create-character drawer's Marker option: a new character can
    start from a marker's markup instead of starting empty. Names already on
    the character are kept, so this is safe to call again. Returns how many
    marks were copied.
    """
    used = {p["part_name"] for p in database.list_character_parts(character_id)}
    copied = 0
    for part in database.list_marker_parts(marker_id):
        name = part["part_name"]
        if name in used:
            continue
        used.add(name)
        try:
            database.create_character_part(
                character_id, name, part["note"] or "", part["payload"] or "{}"
            )
        except ValueError:
            continue  # skip names the database rejects
        copied += 1
    return copied


class CharacterMarkStore:
    """Data access used by the Mark tab when the subject is a character.

    MarkCharacterPage never talks to SQLite directly - it goes through a
    store, so the identical UI can be reused for other subjects (see
    screens/marker/mark_store.py for the marker variant).
    """

    kind = "Character"
    icon = ICON
    part_names = ALL_PART_NAMES
    image_store = image_store  # screens.character.image_store
    fill_canvas = False  # keep the source aspect ratio on the 2048² canvas

    def get_owner(self, owner_id: int):
        return database.get_character(owner_id)

    def list_parts(self, owner_id: int) -> list:
        return database.list_character_parts(owner_id)

    def get_part(self, part_id: int):
        return database.get_character_part(part_id)

    def create_part(self, owner_id: int, part_name: str, note: str = "", payload: str = "{}"):
        return database.create_character_part(owner_id, part_name, note, payload)

    def update_part(self, part_id: int, part_name: str, note: str = "", payload: str = "{}"):
        return database.update_character_part(part_id, part_name, note, payload)

    def delete_part(self, part_id: int) -> None:
        database.delete_character_part(part_id)

    def set_part_locked(self, part_id: int, locked: bool) -> None:
        database.set_character_part_locked(part_id, locked)

    def bump_part_layer(self, part_id: int, delta: int):
        return database.bump_character_part_layer(part_id, delta)

    def export_owner(self, owner_id: int, parent) -> None:
        export_character(owner_id, parent)

    def import_owner(self, owner_id: int, parent) -> bool:
        return import_character(owner_id, parent)


class MarkCharacterPage(QWidget):
    """Tab 1: mark/markup the character image with body parts."""

    def __init__(
        self,
        set_status=None,
        parent: QWidget | None = None,
        store=None,
    ) -> None:
        super().__init__(parent)
        self._set_status = set_status or (lambda message: None)
        self._store = store or CharacterMarkStore()
        self._character_id: int | None = None
        self._zoom = 0.33  # default zoom: 33% (Mark tab only)
        self._offset = QPoint(0, 0)

        # ---- Interactive box selection / move / resize ----
        self._selected_part_id: int | None = None
        self._drag: dict | None = None      # active move/resize drag data
        self._live: dict[int, dict] = {}    # part_id -> payload override (image coords)
        self._boxes: dict[int, QRect] = {}  # part_id -> on-canvas rect (last paint)
        self._view = (0, 0, 1.0, 1.0)       # img_x, img_y, scale_x, scale_y

        self._build_ui()
        self.details_image.installEventFilter(self)

    # ============================================================ UI setup
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Body: Main (80%) + Tool sidebar (20%) ----
        main_col = QVBoxLayout()
        main_col.setSpacing(14)

        # Main: character image
        self.details_image = QLabel("No image")
        self.details_image.setStyleSheet(IMAGE_PANEL_STYLE)
        self.details_image.setAlignment(Qt.AlignCenter)
        self.details_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.details_image.setMinimumSize(240, 240)

        zoom_row = QHBoxLayout()
        self.zoom_in_btn = QPushButton("＋ Zoom In")
        self.zoom_in_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_in_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.zoom_in_btn.clicked.connect(self._on_zoom_in)
        self.zoom_out_btn = QPushButton("－ Zoom Out")
        self.zoom_out_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_out_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.zoom_out_btn.clicked.connect(self._on_zoom_out)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(20, 300)
        self.zoom_slider.setValue(33)  # default zoom: 33%
        self.zoom_slider.setToolTip("Zoom level")
        self.zoom_slider.setStyleSheet(
            "QSlider::groove:horizontal { background-color: #0f172a; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background-color: #38bdf8; width: 18px; margin: -6px 0; border-radius: 9px; }"
        )
        self.zoom_reset_btn = QPushButton("⟲ Reset Zoom")
        self.zoom_reset_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_reset_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.zoom_reset_btn.clicked.connect(self._on_zoom_reset)
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider)
        zoom_row.addWidget(self.zoom_in_btn)
        zoom_row.addWidget(self.zoom_out_btn)
        zoom_row.addWidget(self.zoom_slider)
        zoom_row.addWidget(self.zoom_reset_btn)

        move_row = QHBoxLayout()
        move_row.setSpacing(10)
        self.move_left_btn = QPushButton("◀")
        self.move_left_btn.setFixedSize(44, 44)
        self.move_left_btn.setCursor(Qt.PointingHandCursor)
        self.move_left_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.move_left_btn.clicked.connect(lambda: self._move_by(-1, 0))
        self.move_right_btn = QPushButton("▶")
        self.move_right_btn.setFixedSize(44, 44)
        self.move_right_btn.setCursor(Qt.PointingHandCursor)
        self.move_right_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.move_right_btn.clicked.connect(lambda: self._move_by(1, 0))
        self.move_up_btn = QPushButton("▲")
        self.move_up_btn.setFixedSize(44, 44)
        self.move_up_btn.setCursor(Qt.PointingHandCursor)
        self.move_up_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.move_up_btn.clicked.connect(lambda: self._move_by(0, -1))
        self.move_down_btn = QPushButton("▼")
        self.move_down_btn.setFixedSize(44, 44)
        self.move_down_btn.setCursor(Qt.PointingHandCursor)
        self.move_down_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.move_down_btn.clicked.connect(lambda: self._move_by(0, 1))
        move_row.addStretch()
        move_row.addWidget(self.move_up_btn)
        move_row.addWidget(self.move_left_btn)
        move_row.addWidget(self.move_right_btn)
        move_row.addWidget(self.move_down_btn)
        move_row.addStretch()

        main_col.addWidget(self.details_image)
        main_col.addLayout(zoom_row)
        main_col.addLayout(move_row)
        main_col.addStretch()

        sidebar = QVBoxLayout()
        sidebar.setSpacing(14)
        tools_caption = QLabel("🧰 Tools")
        tools_caption.setStyleSheet(HEADING_STYLE)
        self.tools_hint = QLabel("Zoom the character image or move it around.")
        self.tools_hint.setStyleSheet(MUTED_TEXT)
        sidebar.addWidget(tools_caption)
        sidebar.addWidget(self.tools_hint)
        sidebar.addWidget(self.zoom_slider)
        self.tools_info = QLabel("")
        self.tools_info.setStyleSheet(MUTED_TEXT)
        sidebar.addWidget(self.tools_info)
        sidebar.addStretch()

        # Right: info rows
        self.details_name = QLabel("")
        self.details_name.setStyleSheet(
            f"color: #e2e8f0; font-size: 28px; font-weight: bold; background-color: transparent; border: none;"
        )
        self.details_name.setWordWrap(True)

        # Kept (unused in the sidebar) so show_character() keeps working.
        self.details_id = QLabel("")
        self.details_image_path = QLabel("")
        self.details_created = QLabel("")
        self.details_updated = QLabel("")
        parts_caption = QLabel("🧬  Body Parts")
        parts_caption.setStyleSheet(HEADING_STYLE)

        self.parts_host = QWidget()
        self.parts_layout = QVBoxLayout(self.parts_host)
        self.parts_layout.setContentsMargins(0, 0, 0, 0)
        self.parts_layout.setSpacing(6)

        part_input_row = QHBoxLayout()
        # Part name: editable dropdown with the standard rig part names
        self.part_input = QComboBox()
        self.part_input.setEditable(True)
        self.part_input.setInsertPolicy(QComboBox.NoInsert)
        self.part_input.addItems(self._store.part_names)
        self.part_input.setStyleSheet(INPUT_STYLE)
        self.add_part_btn = QPushButton("＋ Add Part")
        self.add_part_btn.setCursor(Qt.PointingHandCursor)
        self.add_part_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.add_part_btn.clicked.connect(self._on_add_part)
        part_input_row.addWidget(self.part_input, 1)
        part_input_row.addWidget(self.add_part_btn)

        # Bulk actions: one full-width button per row so the narrow (20%)
        # sidebar never overflows horizontally, even at the minimum window size.
        self.add_all_btn = QPushButton("＋ Add All Parts")
        self.add_all_btn.setCursor(Qt.PointingHandCursor)
        self.add_all_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.add_all_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_all_btn.setEnabled(False)  # enabled when parts are missing
        self.add_all_btn.clicked.connect(self._on_add_all_parts)

        self.delete_all_btn = QPushButton("🗑 Delete All Parts")
        self.delete_all_btn.setCursor(Qt.PointingHandCursor)
        self.delete_all_btn.setStyleSheet(DELETE_BUTTON_STYLE)
        self.delete_all_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.delete_all_btn.setEnabled(False)  # enabled when parts exist
        self.delete_all_btn.clicked.connect(self._on_delete_all_parts)

        sidebar.addWidget(parts_caption)
        sidebar.addWidget(self.parts_host, 1)
        sidebar.addLayout(part_input_row)
        sidebar.addWidget(self.add_all_btn)
        sidebar.addWidget(self.delete_all_btn)
        sidebar.addStretch()

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addLayout(main_col, 8)   # 80% main layout
        body.addLayout(sidebar, 2)   # 20% tool sidebar
        root.addLayout(body)

    # ============================================================ Public API
    def show_character(self, character) -> None:
        """Fill the tab with the given subject row (character or marker)."""
        self.show_owner(character)

    def show_owner(self, row) -> None:
        """Fill the tab with the given subject row (character or marker)."""
        self._character_id = row["id"]
        self._selected_part_id = None
        self._drag = None
        self._live = {}
        self._boxes = {}
        self.details_name.setText(f"{self._store.icon}  {row['name']}")
        self.details_id.setText(str(row["id"]))

        path = self._store.image_store.absolute_path(row["image_path"])
        if row["image_path"] and path.is_file():
            self.details_image_path.setText(f"{path.parent.name}/{path.name}")
        else:
            self.details_image_path.setText("—")

        self.details_created.setText(row["created_at"])
        self.details_updated.setText(row["updated_at"])

        self._apply_image_view()
        self._refresh_parts()

    # -------------------------------------------------------- Body parts
    def _layer_of_part(self, p) -> int:
        """Unified draw-order index of a part row (legacy payload z fallback)."""
        try:
            return int(p["layer_index"])
        except (IndexError, KeyError, TypeError, ValueError):
            try:
                return int(json.loads(p["payload"] or "{}").get("z", 0))
            except Exception:
                return 0

    def _part_locked(self, p) -> bool:
        """Unified lock state of a part row (legacy payload fallback)."""
        try:
            return bool(int(p["is_locked"]))
        except (IndexError, KeyError, TypeError, ValueError):
            try:
                return bool(json.loads(p["payload"] or "{}").get("locked", False))
            except Exception:
                return False

    def _refresh_parts(self) -> None:
        if self._character_id is None:
            return
        # clear layout children
        while self.parts_layout.count():
            item = self.parts_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        parts = self._store.list_parts(self._character_id)
        # Sort by the unified draw-order index (shared with the Skeleton and
        # Animation tabs), then id.
        parts = sorted(parts, key=lambda p: (self._layer_of_part(p), p["id"]))
        # Load the character image once for thumbnails
        stage_pix = QPixmap()
        character = self._store.get_owner(self._character_id)
        if character is not None and character["image_path"]:
            path = self._store.image_store.absolute_path(character["image_path"])
            if path.is_file():
                stage_pix = QPixmap(str(path))
        for part in parts:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            part_data = json.loads(part["payload"]) if part["payload"] else {}
            # Coordinates: top/left (fallback to old y/x for legacy parts)
            pt = int(part_data.get("top") or part_data.get("y") or 0)
            pl = int(part_data.get("left") or part_data.get("x") or 0)
            pw = int(part_data.get("width") or 0)
            ph = int(part_data.get("height") or 0)
            # Thumbnail icon of the part
            thumb = QLabel()
            thumb.setFixedSize(32, 32)
            thumb.setStyleSheet("background-color: #0f172a; border-radius: 4px;")
            thumb.setAlignment(Qt.AlignCenter)
            if not stage_pix.isNull() and pw > 0 and ph > 0:
                crop = stage_pix.copy(pl, pt, pw, ph)
                if not crop.isNull():
                    thumb.setPixmap(crop.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(thumb)
            label = QLabel(
                f"<b>{part['part_name']}</b><br>"
                f"<small>top: {pt} · left: {pl} · w: {pw} · h: {ph} · layer: {self._layer_of_part(part)}</small>"
            )
            label.setStyleSheet(INFO_TEXT)
            vis_btn = QPushButton()
            vis_btn.setFixedSize(30, 30)
            vis_btn.setCursor(Qt.PointingHandCursor)
            vis_btn.setStyleSheet(TOP_BUTTON_STYLE)
            vis_btn.clicked.connect(
                lambda checked=False, pid=part["id"]: self._on_toggle_visibility(pid)
            )
            try:
                pdata = json.loads(part["payload"]) if part["payload"] else {}
            except Exception:
                pdata = {}
            if pdata.get("visible", True):
                vis_btn.setIcon(make_visible_icon())
            else:
                vis_btn.setIcon(make_hidden_icon())
            lock_btn = QPushButton()
            lock_btn.setIcon(make_unlock_icon())
            lock_btn.setFixedSize(30, 30)
            lock_btn.setCursor(Qt.PointingHandCursor)
            lock_btn.setStyleSheet(TOP_BUTTON_STYLE)
            lock_btn.clicked.connect(
                lambda checked=False, pid=part["id"]: self._on_toggle_lock(pid)
            )
            # reflect locked state
            try:
                pdata = json.loads(part["payload"]) if part["payload"] else {}
            except Exception:
                pdata = {}
            if self._part_locked(part):
                lock_btn.setIcon(make_lock_icon())
            z_up_btn = QPushButton("▲")
            z_up_btn.setFixedSize(24, 24)
            z_up_btn.setCursor(Qt.PointingHandCursor)
            z_up_btn.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px; padding: 0; font-size: 11px; font-weight: bold; }"
                "QPushButton:hover { background-color: #334155; }"
            )
            z_up_btn.clicked.connect(
                lambda checked=False, pid=part["id"]: self._change_z(pid, 1)
            )
            z_down_btn = QPushButton("▼")
            z_down_btn.setFixedSize(24, 24)
            z_down_btn.setCursor(Qt.PointingHandCursor)
            z_down_btn.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-radius: 4px; padding: 0; font-size: 11px; font-weight: bold; }"
                "QPushButton:hover { background-color: #334155; }"
            )
            z_down_btn.clicked.connect(
                lambda checked=False, pid=part["id"]: self._change_z(pid, -1)
            )
            select_btn = QPushButton()
            select_btn.setIcon(make_select_icon())
            select_btn.setFixedSize(30, 30)
            select_btn.setCursor(Qt.PointingHandCursor)
            select_btn.setStyleSheet(TOP_BUTTON_STYLE)
            select_btn.clicked.connect(
                lambda checked=False, pid=part["id"]: self._on_select_part(pid)
            )
            edit_btn = QPushButton()
            edit_btn.setIcon(make_edit_icon())
            edit_btn.setFixedSize(30, 30)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setStyleSheet(TOP_BUTTON_STYLE)
            edit_btn.clicked.connect(
                lambda checked=False, pid=part["id"], pname=part["part_name"]: self._on_rename_part(pid, pname)
            )
            del_btn = QPushButton()
            del_btn.setIcon(make_delete_icon())
            del_btn.setFixedSize(30, 30)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(TOP_BUTTON_STYLE)
            del_btn.clicked.connect(lambda checked=False, pid=part["id"]: self._on_delete_part(pid))
            h.addWidget(label)
            h.addStretch()
            h.addWidget(z_up_btn)
            h.addWidget(z_down_btn)
            h.addWidget(vis_btn)
            h.addWidget(lock_btn)
            h.addWidget(select_btn)
            h.addWidget(edit_btn)
            h.addWidget(del_btn)
            if part["id"] == self._selected_part_id:
                row.setStyleSheet("background-color: #1e3a5f; border-radius: 6px;")
            self.parts_layout.addWidget(row)

        if not parts:
            empty = QLabel("No body parts yet — add one above.")
            empty.setStyleSheet(PLACEHOLDER_STYLE)
            self.parts_layout.addWidget(empty)

        self._refresh_part_dropdown()

    def _refresh_part_dropdown(self) -> None:
        """Hide already-added part names from the dropdown."""
        if self._character_id is None:
            self._update_bulk_buttons(set(), 0)
            return
        try:
            parts = self._store.list_parts(self._character_id)
        except Exception:
            parts = []
        used = {p["part_name"] for p in parts}
        self._update_bulk_buttons(used, len(parts))
        current = self.part_input.currentText()
        self.part_input.blockSignals(True)
        self.part_input.clear()
        for name in self._store.part_names:
            if name in used:
                continue
            self.part_input.addItem(name)
        self.part_input.blockSignals(False)
        # Restore typed text if it was a custom/unused name
        if current and current not in used:
            self.part_input.setEditText(current)
        else:
            self.part_input.setCurrentIndex(-1)
            self.part_input.setEditText("")

    def _update_bulk_buttons(self, used: set, part_count: int) -> None:
        """Sync the bulk action buttons with the parts currently added."""
        missing = [name for name in self._store.part_names if name not in used]
        self.add_all_btn.setEnabled(bool(missing))
        self.delete_all_btn.setEnabled(part_count > 0)

    def _on_add_part(self) -> None:
        if self._character_id is None:
            return
        character = self._store.get_owner(self._character_id)
        if character is None:
            self._refresh_parts()
            self._set_status(f"{self._store.kind} no longer exists.")
            return
        name = self.part_input.currentText().strip()
        if not name:
            return
        payload = default_part_payload()
        try:
            self._store.create_part(self._character_id, name, "", payload)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot add part", str(exc))
            return
        # Reset the editable dropdown (clear() would wipe the item list!)
        self.part_input.setCurrentIndex(-1)
        self.part_input.setEditText("")
        self._refresh_parts()
        self._apply_image_view()
        self._set_status(f"Added body part '{name}'.")

    def _on_add_all_parts(self) -> None:
        """Add every standard part that is not on the character yet."""
        if self._character_id is None:
            return
        character = self._store.get_owner(self._character_id)
        if character is None:
            self._refresh_parts()
            self._set_status(f"{self._store.kind} no longer exists.")
            return
        added = seed_default_marks(self._character_id, self._store)
        self._refresh_parts()
        self._apply_image_view()
        if added:
            self._set_status(f"Added {added} missing body part(s).")
        else:
            self._set_status("All body parts are already added.")

    def _on_delete_all_parts(self) -> None:
        """Remove every body part of the character (after confirmation)."""
        if self._character_id is None:
            return
        try:
            parts = self._store.list_parts(self._character_id)
        except Exception:
            parts = []
        if not parts:
            self._refresh_parts()
            self._set_status("No body parts to delete.")
            return
        answer = QMessageBox.question(
            self,
            "Delete all parts",
            f"Delete all {len(parts)} body part(s) of this character?\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        for part in parts:
            self._store.delete_part(part["id"])
        # Drop selection / live-drag state tied to the removed parts
        self._selected_part_id = None
        self._drag = None
        self._live = {}
        self._boxes = {}
        self._refresh_parts()
        self._apply_image_view()
        self._set_status(f"Deleted {len(parts)} body part(s).")

    def _on_delete_part(self, part_id: int) -> None:
        self._store.delete_part(part_id)
        if self._selected_part_id == part_id:
            self._selected_part_id = None
        self._live.pop(part_id, None)
        self._drag = None
        self._refresh_parts()
        self._apply_image_view()

    def _on_toggle_lock(self, part_id: int) -> None:
        part = self._store.get_part(part_id)
        if part is None:
            return
        # The lock lives in character_parts.is_locked - the single state
        # shared with the Skeleton and Animation tabs.
        now_locked = not self._part_locked(part)
        try:
            self._store.set_part_locked(part_id, now_locked)
        except Exception as e:
            self._set_status(f"Failed to save lock state: {e}")
            return
        if now_locked and self._selected_part_id == part_id:
            self._selected_part_id = None
            self._live.pop(part_id, None)
            self._drag = None
        self._refresh_parts()
        self._apply_image_view()

    def _on_toggle_visibility(self, part_id: int) -> None:
        part = self._store.get_part(part_id)
        if part is None:
            return
        try:
            data = json.loads(part["payload"]) if part["payload"] else {}
        except Exception:
            data = {}
        data["visible"] = not bool(data.get("visible", True))
        try:
            self._store.update_part(part_id, part["part_name"], part["note"] or "", json.dumps(data))
        except ValueError:
            return
        self._refresh_parts()
        self._apply_image_view()

    def _on_export(self) -> None:
        if self._character_id is None:
            return
        self._store.export_owner(self._character_id, self)

    def _on_import(self) -> None:
        if self._character_id is None:
            return
        if self._store.import_owner(self._character_id, self):
            self._refresh_parts()
            self._apply_image_view()

    def _change_z(self, part_id: int, delta: int) -> None:
        """Shift the part's unified draw-order index (layer).

        This is the single index shared with the Skeleton and Animation tabs
        (character_parts.layer_index), so reordering here reorders everywhere.
        """
        try:
            new_layer = self._store.bump_part_layer(part_id, delta)
        except Exception as e:
            self._set_status(f"Failed to update layer: {e}")
            return
        if new_layer is None:
            return
        self._refresh_parts()
        self._apply_image_view()

    def _on_rename_part(self, part_id: int, old_name: str) -> None:
        # Build list of unused part names (plus the current one) for the dropdown
        used = set()
        try:
            for p in self._store.list_parts(self._character_id):
                if p["id"] != part_id:
                    used.add(p["part_name"])
        except Exception:
            pass
        available = [n for n in self._store.part_names if n not in used or n == old_name]

        dlg = QDialog(self)
        dlg.setWindowTitle("Rename part")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("New part name:"))
        combo = QComboBox(dlg)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.addItems(available)
        if old_name in available:
            combo.setCurrentText(old_name)
        else:
            combo.setEditText(old_name)
        layout.addWidget(combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return
        new_name = combo.currentText().strip()
        if not new_name or new_name == old_name:
            return
        part = self._store.get_part(part_id)
        if part is None:
            return
        try:
            self._store.update_part(
                part_id, new_name, part["note"] or "", part["payload"] or "{}"
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot rename", str(exc))
            return
        self._refresh_parts()
        self._apply_image_view()
        self._set_status(f"Renamed to '{new_name}'.")

    def _on_select_part(self, part_id: int) -> None:
        if self._selected_part_id == part_id:
            # toggle off
            self._selected_part_id = None
            self._drag = None
        else:
            self._selected_part_id = part_id
            self._live[part_id] = self._part_payload(part_id)
        self._refresh_parts()
        self._apply_image_view()
        if self._selected_part_id is not None:
            part = self._store.get_part(part_id)
            if part is not None:
                self._set_status(f"Selected '{part['part_name']}' — drag to move, drag corners to resize.")

    # ---------------------------------------------------- Image zoom / pan
    def _apply_image_view(self) -> None:
        """Composite the character image with zoom + pan offset."""
        if self._character_id is None:
            return
        character = self._store.get_owner(self._character_id)
        if character is None:
            return
        pixmap = QPixmap()
        if character["image_path"]:
            path = self._store.image_store.absolute_path(character["image_path"])
            if path.is_file():
                pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.details_image.setPixmap(QPixmap())
            self.details_image.setText("No image")
            return
        base_w, base_h = 2048, 2048  # default render size
        canvas = QPixmap(base_w, base_h)
        canvas.fill(QColor("#0f172a"))  # white square background behind the image
        # Stores with fill_canvas=True (markers) stretch the image over the whole
        # 2048x2048 canvas; characters keep the source aspect ratio. Box math is
        # unaffected - scale_x/scale_y are tracked separately.
        aspect = (
            Qt.IgnoreAspectRatio
            if getattr(self._store, "fill_canvas", False)
            else Qt.KeepAspectRatio
        )
        scaled = pixmap.scaled(
            max(1, int(base_w * self._zoom)),
            max(1, int(base_h * self._zoom)),
            aspect,
            Qt.SmoothTransformation,
        )
        x = (base_w - scaled.width()) // 2 + self._offset.x()
        y = (base_h - scaled.height()) // 2 + self._offset.y()
        painter = QPainter(canvas)
        painter.drawPixmap(x, y, scaled)
        img_x = (base_w - scaled.width()) // 2 + self._offset.x()
        img_y = (base_h - scaled.height()) // 2 + self._offset.y()
        # Exact scale factors (image -> canvas), so boxes stay glued to the image
        src_w = max(1, pixmap.width())
        src_h = max(1, pixmap.height())
        scale_x = scaled.width() / src_w
        scale_y = scaled.height() / src_h
        self._view = (img_x, img_y, scale_x, scale_y)
        self._boxes = {}
        fill_color = QColor(0xFF, 0x00, 0x00, 0x42)  # "#ff000042" semi-transparent red
        sel_pen = QColor("#ff0000")
        for part in sorted(
            self._store.list_parts(self._character_id),
            key=lambda p: (self._layer_of_part(p), p["id"]),
        ):
            part_data = json.loads(part["payload"]) if part["payload"] else {}
            if not part_data.get("visible", True):
                continue
            # Live drag override wins over DB values while moving/resizing
            part_data = self._live.get(part["id"], part_data)
            # Coordinates: left = horizontal, top = vertical (fallback to old x/y)
            # Scaled by zoom so the box stays glued to the image at any zoom level.
            left = int(part_data.get("left") or part_data.get("x") or 0)
            top = int(part_data.get("top") or part_data.get("y") or 0)
            box_x = img_x + int(left * scale_x)
            box_y = img_y + int(top * scale_y)
            box_w = max(1, int(int(part_data.get("width") or 0) * scale_x))
            box_h = max(1, int(int(part_data.get("height") or 0) * scale_y))
            rect = QRect(box_x, box_y, box_w, box_h)
            self._boxes[part["id"]] = rect
            if part["id"] == self._selected_part_id:
                # Selected: opaque red outline + corner handles
                painter.setPen(sel_pen)
                painter.setBrush(fill_color)
                painter.drawRect(rect)
                # Show part name just above the box
                painter.setPen(QColor("#e2e8f0"))
                painter.drawText(box_x, max(12, box_y - 4), part["part_name"])
                pen_w = max(2, int(2 / max(scale_x, 0.001)))
                handle = 8
                painter.setBrush(QColor("#facc15"))
                painter.setPen(QColor("#a16207"))
                for hx, hy in (
                    (box_x, box_y),
                    (box_x + box_w - handle, box_y),
                    (box_x, box_y + box_h - handle),
                    (box_x + box_w - handle, box_y + box_h - handle),
                ):
                    painter.drawRect(QRect(hx, hy, handle, handle))
                painter.setPen(sel_pen)
            else:
                painter.setPen(fill_color)
                painter.setBrush(fill_color)
                painter.drawRect(rect)
                painter.setPen(QColor("#e2e8f0"))
                painter.drawText(box_x, max(12, box_y - 4), part["part_name"])
        painter.end()
        self.details_image.setPixmap(canvas)
        if hasattr(self, "tools_info"):
            self.tools_info.setText(f"Image: {base_w}×{base_h} · Zoom: {int(self._zoom * 100)}%")

    def _on_zoom_in(self) -> None:
        self._zoom = min(3.0, round(self._zoom * 1.25, 2))
        self._apply_image_view()

    def _on_zoom_out(self) -> None:
        self._zoom = max(0.2, round(self._zoom / 1.25, 2))
        self._apply_image_view()

    def _on_zoom_reset(self) -> None:
        self._zoom = 0.33  # back to the Mark-tab default (33%)
        self._offset = QPoint(0, 0)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(33)
        self.zoom_slider.blockSignals(False)
        self._apply_image_view()

    def _on_zoom_slider(self, value: int) -> None:
        self._zoom = value / 100.0
        self._apply_image_view()

    def _move_by(self, dx: int, dy: int) -> None:
        self._offset = self._offset + QPoint(dx * 12, dy * 12)
        self._apply_image_view()

    # ------------------------------------------- Box select / move / resize
    HANDLE = 8  # on-canvas corner handle size (px)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        if obj is self.details_image:
            et = event.type()
            if et == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self._on_select(event)
                return True
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                return self._on_press(event)
            if et == QEvent.MouseMove:
                return self._on_drag_move(event)
            if et == QEvent.MouseButtonRelease and self._drag is not None:
                self._finish_drag()
                return True
            if et == QEvent.Leave:
                self.details_image.setCursor(Qt.ArrowCursor)
                return False
        return super().eventFilter(obj, event)

    # --- coordinate helpers -------------------------------------------------
    def _event_canvas_pos(self, event) -> QPoint:
        """Map a widget event position into the 2048x2048 canvas space."""
        pm = self.details_image.pixmap()
        if pm is None or pm.isNull():
            return QPoint(-1, -1)
        ox = (self.details_image.width() - pm.width()) // 2
        oy = (self.details_image.height() - pm.height()) // 2
        return event.position().toPoint() - QPoint(ox, oy)

    def _canvas_to_image(self, cpos) -> tuple[float, float]:
        img_x, img_y, scale_x, scale_y = self._view
        return ((cpos.x() - img_x) / scale_x, (cpos.y() - img_y) / scale_y)

    def _part_payload(self, part_id: int) -> dict:
        live = self._live.get(part_id)
        if live is not None:
            return live
        part = self._store.get_part(part_id)
        return json.loads(part["payload"]) if part and part["payload"] else {}

    def _handle_at(self, rect: QRect, cpos: QPoint) -> int:
        """Corner under cursor: 0=TL, 1=TR, 2=BL, 3=BR, else -1."""
        h = self.HANDLE
        corners = (
            QRect(rect.x(), rect.y(), h, h),
            QRect(rect.right() - h + 1, rect.y(), h, h),
            QRect(rect.x(), rect.bottom() - h + 1, h, h),
            QRect(rect.right() - h + 1, rect.bottom() - h + 1, h, h),
        )
        for i, cr in enumerate(corners):
            if cr.contains(cpos):
                return i
        return -1

    # --- interaction --------------------------------------------------------
    def _on_select(self, event) -> None:
        cpos = self._event_canvas_pos(event)
        for pid in reversed(list(self._boxes.keys())):
            rect = self._boxes.get(pid)
            if rect is not None and rect.contains(cpos):
                self._selected_part_id = pid
                self._live[pid] = self._part_payload(pid)
                part = self._store.get_part(pid)
                self.details_image.setCursor(Qt.OpenHandCursor)
                self._set_status(f"Selected '{part['part_name']}' — drag to move, drag corners to resize.")
                self._apply_image_view()
                return
        self._selected_part_id = None
        self._drag = None
        self.details_image.setCursor(Qt.ArrowCursor)
        self._apply_image_view()

    def _on_press(self, event) -> bool:
        if self._selected_part_id is None:
            return False
        # Locked parts cannot be moved/resized
        part = self._store.get_part(self._selected_part_id)
        if part is not None and self._part_locked(part):
            return False
        cpos = self._event_canvas_pos(event)
        rect = self._boxes.get(self._selected_part_id)
        if rect is None:
            return False
        handle = self._handle_at(rect, cpos)
        if handle >= 0:
            orig = self._part_payload(self._selected_part_id)
            left = float(orig.get("left") or orig.get("x") or 0)
            top = float(orig.get("top") or orig.get("y") or 0)
            w = float(orig.get("width") or 0)
            hh = float(orig.get("height") or 0)
            # Anchor = the corner opposite the grabbed handle
            anchor = {
                0: (left + w, top + hh),
                1: (left, top + hh),
                2: (left + w, top),
                3: (left, top),
            }[handle]
            self._drag = {
                "mode": "resize",
                "handle": handle,
                "anchor": anchor,
                "orig": (left, top, w, hh),
            }
            self.details_image.setCursor(Qt.SizeFDiagCursor)
            return True
        if rect.contains(cpos):
            cur_img = self._canvas_to_image(cpos)
            orig = self._part_payload(self._selected_part_id)
            left = float(orig.get("left") or orig.get("x") or 0)
            top = float(orig.get("top") or orig.get("y") or 0)
            self._drag = {
                "mode": "move",
                "grab_dx": cur_img[0] - left,
                "grab_dy": cur_img[1] - top,
            }
            self.details_image.setCursor(Qt.ClosedHandCursor)
            return True
        # click on empty canvas -> deselect
        self._selected_part_id = None
        self.details_image.setCursor(Qt.ArrowCursor)
        self._apply_image_view()
        return False

    def _on_drag_move(self, event) -> bool:
        if self._drag is None:
            # hover feedback: corner -> resize cursor, inside box -> open hand
            if self._selected_part_id is not None:
                cpos = self._event_canvas_pos(event)
                rect = self._boxes.get(self._selected_part_id)
                if rect is not None:
                    if self._handle_at(rect, cpos) >= 0:
                        self.details_image.setCursor(Qt.SizeFDiagCursor)
                    elif rect.contains(cpos):
                        self.details_image.setCursor(Qt.OpenHandCursor)
                    else:
                        self.details_image.setCursor(Qt.ArrowCursor)
            return False
        cpos = self._event_canvas_pos(event)
        cur_img = self._canvas_to_image(cpos)
        pid = self._selected_part_id
        live = self._live.setdefault(pid, self._part_payload(pid))
        if self._drag["mode"] == "move":
            live["left"] = int(cur_img[0] - self._drag["grab_dx"])
            live["top"] = int(cur_img[1] - self._drag["grab_dy"])
        else:  # resize
            ax, ay = self._drag["anchor"]
            x0, x1 = sorted((cur_img[0], ax))
            y0, y1 = sorted((cur_img[1], ay))
            live["left"] = int(x0)
            live["top"] = int(y0)
            live["width"] = max(1, int(x1 - x0))
            live["height"] = max(1, int(y1 - y0))
        # Persist every coordinate change to SQLite while dragging
        self._persist_part(pid)
        self._apply_image_view()
        return True

    def _persist_part(self, part_id: int) -> None:
        """Write the current (possibly live-dragged) payload straight to the DB."""
        live = self._live.get(part_id)
        if not live:
            return
        part = self._store.get_part(part_id)
        if part is None:
            return
        self._store.update_part(part_id, part["part_name"], part["note"] or "", json.dumps(live))

    def _finish_drag(self) -> None:
        drag = self._drag
        self._drag = None
        pid = self._selected_part_id
        if drag is None or pid is None:
            return
        self._persist_part(pid)
        self._live.pop(pid, None)
        part = self._store.get_part(pid)
        if part is None:
            return
        self.details_image.setCursor(Qt.OpenHandCursor)
        self._refresh_parts()
        self._apply_image_view()
        self._set_status("Box updated.")


