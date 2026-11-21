"""Marker module screen - CRUD + marker details page (SQLite-backed).

Grid of marker cards (thumbnail, name, description). Clicking a card opens a
dedicated details page with the full image, name, description and meta plus
Edit / Delete actions. "＋ Add Marker" opens a slide-in drawer with name,
description and an optional image.
"""

from PySide6.QtCore import QEvent, QPoint, QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import database
from screens.character_details.mark_character import MarkCharacterPage
from screens.marker import image_store
from screens.marker.mark_store import MarkerMarkStore
from screens.theme import BG, BACK_BUTTON_STYLE, CARD_BG, MUTED, TEXT

ICON = "📍"
NAME = "Marker"
DESC = "Add markers with a name, description and image"
INFO = (ICON, NAME, DESC)

DRAWER_WIDTH = 340
CARD_W, CARD_H = 200, 240
GRID_COLUMNS = 3
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"

CARD_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    f"  border: 2px solid {CARD_BG}; border-radius: 14px; }}"
    "QFrame:hover { border-color: #38bdf8; }"
)
CARD_LABEL_STYLE = "background-color: transparent; border: none;"
PLACEHOLDER_STYLE = f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"

CREATE_BUTTON_STYLE = (
    "QPushButton { background-color: #0d9488; color: #e2e8f0;"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 20px; font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #14b8a6; }"
)

INPUT_STYLE = (
    f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

DESCRIPTION_STYLE = (
    f"QTextEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

PREVIEW_STYLE = (
    f"QLabel {{ background-color: {BG}; border: 1px dashed #334155;"
    f"  border-radius: 12px; color: {MUTED}; font-size: 13px; }}"
)

DETAIL_STYLE = f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"

BODY_FRAME_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px; }}"
)

SAVE_BUTTON_STYLE = (
    "QPushButton { background-color: #16a34a; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px;"
    "  font-size: 15px; font-weight: bold; }"
    "QPushButton:hover { background-color: #22c55e; }"
)

EDIT_BUTTON_STYLE = (
    "QPushButton { background-color: #1d4ed8; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px;"
    "  font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #2563eb; }"
)

DANGER_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
    "  border: none; border-radius: 8px; padding: 10px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
    "QPushButton:disabled { color: #64748b; }"
)


class MarkerScreen(QWidget):
    def __init__(self, show_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.show_home = show_home
        database.init_db()
        self._editing_id: int | None = None
        self._detail_id: int | None = None
        self._pending_image: str | None = None  # absolute path, not saved yet
        self._clear_image = False

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(14)

        # ---- Top bar: back button + add button ----
        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.clicked.connect(self.show_home)

        self.create_btn = QPushButton("＋ Add Marker")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.setStyleSheet(CREATE_BUTTON_STYLE)
        self.create_btn.clicked.connect(lambda: self.open_drawer())

        top_bar = QHBoxLayout()
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.create_btn)
        root.addLayout(top_bar)

        # ---- Two pages: list and details ----
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.pages.addWidget(self._build_list_page())   # index 0
        self.pages.addWidget(self._build_details_page())  # index 1

        # ---- Slide-in drawer + overlay ----
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.overlay.hide()
        self.overlay.installEventFilter(self)

        self.drawer = QFrame(self)
        self.drawer.setFixedWidth(DRAWER_WIDTH)
        self.drawer.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-left: 2px solid #0d9488; }}"
        )
        self._build_drawer(self.drawer)

        self._anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        self.refresh()

    # ------------------------------------------------------------ List page
    def _build_list_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        welcome = QLabel(f"Welcome to the {NAME} screen!")
        welcome.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: bold;")
        welcome.setAlignment(Qt.AlignHCenter)
        layout.addWidget(welcome)

        subtitle = QLabel("Click a marker to open its details page.")
        subtitle.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignHCenter)
        layout.addWidget(subtitle)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        layout.addWidget(self.status_label, 0, Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        self.empty_label = QLabel("No markers yet — click “＋ Add Marker”!")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
        layout.addWidget(self.empty_label, 1)
        self.empty_label.hide()

        layout.addWidget(self.scroll, 1)
        return page

    # --------------------------------------------------------- Details page
    def _build_details_page(self) -> QWidget:
        """Marker details: top bar + the 🏷 Mark Character page (no tabs)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ---- Top bar: back · title · edit/delete ----
        back_btn = QPushButton("← Back to Markers")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(180)
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.clicked.connect(self.close_details)

        self.detail_title = QLabel(f"{ICON}  Marker Details")
        self.detail_title.setStyleSheet(
            f"color: {TEXT}; font-size: 22px; font-weight: bold;"
        )

        self.edit_btn = QPushButton("✏️  Edit")
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setStyleSheet(EDIT_BUTTON_STYLE)
        self.edit_btn.clicked.connect(self._edit_from_details)

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._delete_from_details)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(back_btn)
        top.addStretch()
        top.addWidget(self.detail_title)
        top.addStretch()
        top.addWidget(self.edit_btn)
        top.addWidget(self.delete_btn)
        layout.addLayout(top)

        # Description + timestamps in one compact line
        self.detail_info = QLabel("")
        self.detail_info.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        self.detail_info.setWordWrap(True)
        layout.addWidget(self.detail_info, 0, Qt.AlignLeft)

        # Messages coming from the mark page (add/rename/delete part, ...)
        self.detail_status = QLabel("")
        self.detail_status.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        layout.addWidget(self.detail_status, 0, Qt.AlignLeft)

        # ---- 🏷 Mark Character page (renders the image on 2048x2048) ----
        self.mark_page = MarkCharacterPage(
            set_status=self._set_detail_status, store=MarkerMarkStore()
        )
        layout.addWidget(self.mark_page, 1)
        return page

    def _set_detail_status(self, message: str) -> None:
        self.detail_status.setText(message or "")

    def _build_info_tab(self) -> QWidget:
        """Second tab: image, name, description, meta + edit/delete actions."""
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent; border: none;")
        host = QWidget()
        body = QVBoxLayout(host)
        body.setContentsMargins(0, 8, 8, 8)
        body.setSpacing(16)

        # Image
        self.detail_image = QLabel("No image")
        self.detail_image.setStyleSheet(PREVIEW_STYLE)
        self.detail_image.setAlignment(Qt.AlignCenter)
        self.detail_image.setFixedHeight(300)
        body.addWidget(self.detail_image)

        # Name + description card
        info = QFrame()
        info.setStyleSheet(BODY_FRAME_STYLE)
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(20, 20, 20, 20)
        info_layout.setSpacing(10)

        self.info_name = QLabel("")
        self.info_name.setStyleSheet(
            f"color: {TEXT}; font-size: 24px; font-weight: bold; {CARD_LABEL_STYLE}"
        )
        self.info_name.setWordWrap(True)
        info_layout.addWidget(self.info_name)

        desc_hint = QLabel("Description")
        desc_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        info_layout.addWidget(desc_hint)

        self.detail_description = QLabel("")
        self.detail_description.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; {CARD_LABEL_STYLE}"
        )
        self.detail_description.setWordWrap(True)
        self.detail_description.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        info_layout.addWidget(self.detail_description)

        self.detail_meta = QLabel("")
        self.detail_meta.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.detail_meta.setWordWrap(True)
        info_layout.addWidget(self.detail_meta)

        body.addWidget(info)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.edit_btn = QPushButton("✏️  Edit Marker")
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setStyleSheet(EDIT_BUTTON_STYLE)
        self.edit_btn.clicked.connect(self._edit_from_details)

        self.delete_btn = QPushButton("🗑  Delete Marker")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._delete_from_details)

        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch()
        body.addLayout(actions)
        body.addStretch()

        scroll.setWidget(host)
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll, 1)
        return tab

    def open_details(self, marker_id: int) -> None:
        entry = database.get_marker(marker_id)
        if entry is None:
            self.refresh()
            return
        self._detail_id = marker_id
        self._fill_details(entry)
        self.tabs.setCurrentIndex(0)  # land on the 🏷 Mark Character tab
        self.pages.setCurrentIndex(1)
        self.create_btn.hide()

    def close_details(self) -> None:
        self._detail_id = None
        self.pages.setCurrentIndex(0)
        self.create_btn.show()
        self.refresh()

    def _fill_details(self, entry) -> None:
        self.detail_title.setText(f"{ICON}  {entry['name']}")
        self.info_name.setText(f"{ICON}  {entry['name']}")

        desc = entry["description"].strip()
        self.detail_description.setText(desc if desc else "No description provided.")
        self.detail_description.setStyleSheet(
            f"color: {TEXT if desc else MUTED}; font-size: 14px; {CARD_LABEL_STYLE}"
        )

        self.detail_meta.setText(
            f"Created {entry['created_at']}  ·  Updated {entry['updated_at']}"
        )

        pixmap = QPixmap()
        if entry["image_path"]:
            path = image_store.absolute_path(entry["image_path"])
            if path.is_file():
                pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self.detail_image.setText("")
            self.detail_image.setPixmap(
                pixmap.scaled(760, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.detail_image.setPixmap(QPixmap())
            self.detail_image.setText("No image for this marker")

        # 🏷 Mark Character tab - same widget, marker-backed store
        self.mark_page.show_owner(entry)

    def _edit_from_details(self) -> None:
        if self._detail_id is not None:
            self.open_drawer(self._detail_id)

    def _delete_from_details(self) -> None:
        if self._detail_id is not None:
            self._delete_marker(self._detail_id, then_back=True)

    # -------------------------------------------------------- Drawer UI
    def _build_drawer(self, drawer: QFrame) -> None:
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.drawer_title = QLabel("Add Marker")
        self.drawer_title.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: bold;")
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(BACK_BUTTON_STYLE)
        close_btn.clicked.connect(self.close_drawer)
        header.addWidget(self.drawer_title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        name_hint = QLabel("Marker name")
        name_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_name = QLineEdit()
        self.drawer_name.setPlaceholderText("e.g. Scene start")
        self.drawer_name.setStyleSheet(INPUT_STYLE)
        self.drawer_name.returnPressed.connect(self._on_save)
        layout.addWidget(name_hint)
        layout.addWidget(self.drawer_name)

        desc_hint = QLabel("Description")
        desc_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_description = QTextEdit()
        self.drawer_description.setPlaceholderText("What is this marker for?")
        self.drawer_description.setStyleSheet(DESCRIPTION_STYLE)
        self.drawer_description.setFixedHeight(130)
        layout.addWidget(desc_hint)
        layout.addWidget(self.drawer_description)

        image_hint = QLabel("Image (optional)")
        image_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_preview = QLabel("No image chosen")
        self.drawer_preview.setStyleSheet(PREVIEW_STYLE)
        self.drawer_preview.setAlignment(Qt.AlignCenter)
        self.drawer_preview.setFixedHeight(160)

        choose_btn = QPushButton("🖼  Choose Image...")
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.setStyleSheet(BACK_BUTTON_STYLE)
        choose_btn.clicked.connect(self._on_choose_image)

        self.remove_image_btn = QPushButton("✕  Remove Image")
        self.remove_image_btn.setCursor(Qt.PointingHandCursor)
        self.remove_image_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.remove_image_btn.clicked.connect(self._on_remove_image)
        self.remove_image_btn.hide()

        img_row = QHBoxLayout()
        img_row.addWidget(choose_btn)
        img_row.addWidget(self.remove_image_btn)

        layout.addWidget(image_hint)
        layout.addWidget(self.drawer_preview)
        layout.addLayout(img_row)

        layout.addStretch()

        self.drawer_delete_btn = QPushButton("🗑  Delete")
        self.drawer_delete_btn.setCursor(Qt.PointingHandCursor)
        self.drawer_delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.drawer_delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.drawer_delete_btn)

        self.save_btn = QPushButton("💾  Save Marker")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    # ---------------------------------------------------- Drawer behavior
    def open_drawer(self, marker_id: int | None = None) -> None:
        self._editing_id = marker_id
        self._pending_image = None
        self._clear_image = False

        if marker_id is None:
            self.drawer_title.setText("Add Marker")
            self.drawer_name.clear()
            self.drawer_description.clear()
            self.drawer_delete_btn.hide()
            self.remove_image_btn.hide()
            self._update_drawer_preview(None)
        else:
            entry = database.get_marker(marker_id)
            if entry is None:
                return
            self.drawer_title.setText("Edit Marker")
            self.drawer_name.setText(entry["name"])
            self.drawer_description.setPlainText(entry["description"])
            self.drawer_delete_btn.show()
            self.remove_image_btn.setVisible(bool(entry["image_path"]))
            self._update_drawer_preview(entry["image_path"] or None)

        self.drawer_name.setFocus()

        # Slide in from the right edge
        h = self.height()
        self.overlay.setGeometry(0, 0, self.width(), h)
        self.overlay.show()
        self.overlay.raise_()
        self.drawer.setGeometry(self.width(), 0, DRAWER_WIDTH, h)
        self.drawer.show()
        self.drawer.raise_()
        self._anim.stop()
        self._anim.setStartValue(QPoint(self.width(), 0))
        self._anim.setEndValue(QPoint(self.width() - DRAWER_WIDTH, 0))
        self._anim.start()

    def close_drawer(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.drawer.pos())
        self._anim.setEndValue(QPoint(self.width(), 0))
        self._anim.start()

    def _after_anim(self) -> None:
        """After the slide-out finishes, stop the drawer & overlay from eating clicks."""
        if self._anim.endValue().x() >= self.width():
            self.drawer.hide()
            self.overlay.hide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        if obj is self.overlay and event.type() == QEvent.MouseButtonPress:
            self.close_drawer()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        is_open = self.drawer.isVisible() and self._anim.state() != QPropertyAnimation.Running
        x = self.width() - DRAWER_WIDTH if is_open else self.width()
        self.drawer.setGeometry(x, 0, DRAWER_WIDTH, self.height())

    # -------------------------------------------------------- Image picking
    def _update_drawer_preview(self, stored_path: str | None) -> None:
        pixmap = QPixmap()
        if self._pending_image:
            pixmap = QPixmap(self._pending_image)
        elif stored_path:
            path = image_store.absolute_path(stored_path)
            if path.is_file():
                pixmap = QPixmap(str(path))

        if not pixmap.isNull():
            scaled = pixmap.scaled(280, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.drawer_preview.setText("")
            self.drawer_preview.setPixmap(scaled)
        else:
            self.drawer_preview.setPixmap(QPixmap())
            self.drawer_preview.setText("No image chosen")

    def _on_choose_image(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Choose marker image", "", IMAGE_FILTER)
        if not source:
            return
        pixmap = QPixmap(source)
        if pixmap.isNull():
            QMessageBox.warning(self, "Invalid image", "That file could not be loaded as an image.")
            return
        self._pending_image = source
        self._clear_image = False
        self.remove_image_btn.setVisible(self._editing_id is not None)
        self._update_drawer_preview(None)

    def _on_remove_image(self) -> None:
        self._pending_image = None
        self._clear_image = True
        self.remove_image_btn.hide()
        self._update_drawer_preview(None)

    # ------------------------------------------------------------- Actions
    def _on_save(self) -> None:
        name = self.drawer_name.text().strip()
        description = self.drawer_description.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter the marker name.")
            return

        stored: str | None = None
        if self._pending_image:
            try:
                stored = image_store.save_image(self._pending_image)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid image", str(exc))
                return

        old_image = ""
        if self._editing_id is not None:
            old = database.get_marker(self._editing_id)
            old_image = old["image_path"] if old else ""

        # None = keep current image, "" = clear it
        image_path: str | None = None
        if stored:
            image_path = stored
        elif self._clear_image:
            image_path = ""

        try:
            if self._editing_id is None:
                entry = database.create_marker(name, description, stored or "")
                message = f"Created '{entry['name']}'."
            else:
                database.update_marker(self._editing_id, name, description, image_path)
                message = f"Saved '{name}'."
        except ValueError as exc:
            if stored:
                image_store.delete_image(stored)
            QMessageBox.warning(self, "Cannot save marker", str(exc))
            return

        # A replaced or cleared image file is no longer needed
        if stored and old_image and old_image != stored:
            image_store.delete_image(old_image)
        elif self._clear_image and old_image:
            image_store.delete_image(old_image)

        self.refresh()
        if self._detail_id == self._editing_id:
            refreshed = database.get_marker(self._detail_id)
            if refreshed:
                self._fill_details(refreshed)
        self.close_drawer()
        self.status_label.setText(message)

    def _on_delete(self) -> None:
        if self._editing_id is None:
            return
        self._delete_marker(self._editing_id, then_back=True)

    def _delete_marker(self, marker_id: int, then_back: bool = False) -> None:
        entry = database.get_marker(marker_id)
        if entry is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete marker",
            f"Delete marker '{entry['name']}'?\n\n"
            "This also deletes its image file and cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_marker(marker_id)
        image_store.delete_image(entry["image_path"])
        self.status_label.setText(f"Deleted '{entry['name']}'.")

        if then_back and self._detail_id == marker_id:
            self.close_details()
        else:
            self.refresh()
            self.close_drawer()

    # ------------------------------------------------------------ Grid list
    def refresh(self) -> None:
        entries = database.list_markers()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_items = bool(entries)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

        for i, entry in enumerate(entries):
            card = self._make_card(entry)
            row, col = divmod(i, GRID_COLUMNS)
            self.grid.addWidget(card, row, col)
        self.status_label.setText(f"{len(entries)} marker(s)")

    def _make_card(self, entry) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(CARD_W, CARD_H)
        card.setStyleSheet(CARD_STYLE)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(8)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setFixedHeight(120)
        image_label.setStyleSheet(
            f"background-color: {BG}; border: none; border-radius: 8px;"
        )

        pixmap = QPixmap()
        if entry["image_path"]:
            path = image_store.absolute_path(entry["image_path"])
            if path.is_file():
                pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            image_label.setPixmap(
                pixmap.scaled(170, 116, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            image_label.setText("No image")
            image_label.setStyleSheet(PLACEHOLDER_STYLE)

        name_label = QLabel(entry["name"])
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: bold; {CARD_LABEL_STYLE}"
        )
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)

        desc_text = entry["description"] or "No description"
        desc_label = QLabel(desc_text)
        desc_label.setStyleSheet(DETAIL_STYLE)
        desc_label.setAlignment(Qt.AlignHCenter)
        desc_label.setWordWrap(True)

        inner.addWidget(image_label)
        inner.addWidget(name_label)
        inner.addWidget(desc_label)

        def mousePressEvent(event, marker_id=entry["id"]):  # noqa: N802 (Qt naming)
            if event.button() == Qt.LeftButton:
                self.open_details(marker_id)

        card.mousePressEvent = mousePressEvent
        return card
