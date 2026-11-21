"""Background module screen - CRUD with a slide-in drawer panel (SQLite-backed).

Same pattern as the character screen: grid of background boxes (image + name),
"＋ Create Background" button opens a drawer that slides in from the right,
clicking an existing box opens the drawer in edit mode.
"""

from PySide6.QtCore import QEvent, QPropertyAnimation, QEasingCurve, Qt, QPoint
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
    QVBoxLayout,
    QWidget,
)

import database
from screens.background import image_store
from screens.theme import BG, CARD_BG, MUTED, TEXT

ICON = "🌄"
NAME = "Background"
DESC = "Set up scenes and background layers"
INFO = (ICON, NAME, DESC)

DRAWER_WIDTH = 340
CARD_W, CARD_H = 180, 216
GRID_COLUMNS = 3

CARD_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    f"  border: 2px solid {CARD_BG}; border-radius: 14px; }}"
    "QFrame:hover { border-color: #38bdf8; }"
)
CARD_LABEL_STYLE = "background-color: transparent; border: none;"
PLACEHOLDER_STYLE = f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"

TOP_BUTTON_STYLE = (
    f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px; }"
    "QPushButton:hover { background-color: #334155; }"
)

CREATE_BUTTON_STYLE = (
    "QPushButton { background-color: #b45309; color: #e2e8f0;"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 20px; font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #d97706; }"
)

INPUT_STYLE = (
    f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

PREVIEW_STYLE = (
    f"QLabel {{ background-color: {BG}; border: 1px dashed #334155;"
    f"  border-radius: 12px; color: {MUTED}; font-size: 13px; }}"
)

SAVE_BUTTON_STYLE = (
    "QPushButton { background-color: #16a34a; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px;"
    "  font-size: 15px; font-weight: bold; }"
    "QPushButton:hover { background-color: #22c55e; }"
)

DANGER_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
    "  border: none; border-radius: 8px; padding: 10px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
    "QPushButton:disabled { color: #64748b; }"
)

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"


class BackgroundScreen(QWidget):
    def __init__(self, go_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        database.init_db()
        self._editing_id: int | None = None
        self._pending_image: str | None = None  # absolute path chosen, not yet saved

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(14)

        # ---- Top bar ----
        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(TOP_BUTTON_STYLE)
        back_btn.clicked.connect(go_home)

        self.title = QLabel(f"{ICON}  Backgrounds")
        self.title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")

        create_btn = QPushButton("＋ Create Background")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.setStyleSheet(CREATE_BUTTON_STYLE)
        create_btn.clicked.connect(lambda: self.open_drawer())

        top_bar = QHBoxLayout()
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.title)
        top_bar.addStretch()
        top_bar.addWidget(create_btn)
        root.addLayout(top_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        root.addWidget(self.status_label, 0, Qt.AlignLeft)

        # ---- Background boxes grid (scrollable) ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        self.empty_label = QLabel("No backgrounds yet — click “＋ Create Background”!")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
        root.addWidget(self.empty_label, 1)
        self.empty_label.hide()

        root.addWidget(self.scroll, 1)

        # ---- Slide-in drawer + overlay ----
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.overlay.hide()
        self.overlay.installEventFilter(self)

        self.drawer = QFrame(self)
        self.drawer.setFixedWidth(DRAWER_WIDTH)
        self.drawer.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-left: 2px solid #b45309; }}"
        )
        self._build_drawer(self.drawer)

        self._anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        self.refresh()

    # -------------------------------------------------------- Drawer UI
    def _build_drawer(self, drawer: QFrame) -> None:
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.drawer_title = QLabel("Create Background")
        self.drawer_title.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: bold;")
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(TOP_BUTTON_STYLE)
        close_btn.clicked.connect(self.close_drawer)
        header.addWidget(self.drawer_title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        name_hint = QLabel("Background name")
        name_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_name = QLineEdit()
        self.drawer_name.setPlaceholderText("e.g. City Sunset")
        self.drawer_name.setStyleSheet(INPUT_STYLE)
        self.drawer_name.returnPressed.connect(self._on_save)
        layout.addWidget(name_hint)
        layout.addWidget(self.drawer_name)

        image_hint = QLabel("Background image")
        image_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_preview = QLabel("No image chosen")
        self.drawer_preview.setStyleSheet(PREVIEW_STYLE)
        self.drawer_preview.setAlignment(Qt.AlignCenter)
        self.drawer_preview.setFixedHeight(200)
        choose_btn = QPushButton("🖼  Choose Image...")
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.setStyleSheet(TOP_BUTTON_STYLE)
        choose_btn.clicked.connect(self._on_choose_image)
        layout.addWidget(image_hint)
        layout.addWidget(self.drawer_preview)
        layout.addWidget(choose_btn)

        layout.addStretch()

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾  Save Background")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    # ---------------------------------------------------- Drawer behavior
    def open_drawer(self, background_id: int | None = None) -> None:
        self._editing_id = background_id
        self._pending_image = None

        if background_id is None:
            self.drawer_title.setText("Create Background")
            self.drawer_name.clear()
            self._update_drawer_preview(None)
            self.delete_btn.hide()
        else:
            background = database.get_background(background_id)
            if background is None:
                return
            self.drawer_title.setText("Edit Background")
            self.drawer_name.setText(background["name"])
            self._update_drawer_preview(background["image_path"] or None)
            self.delete_btn.show()

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

    def _update_drawer_preview(self, stored_path: str | None) -> None:
        pixmap = QPixmap()
        if self._pending_image:
            pixmap = QPixmap(self._pending_image)
        elif stored_path:
            path = image_store.absolute_path(stored_path)
            if path.is_file():
                pixmap = QPixmap(str(path))

        if not pixmap.isNull():
            scaled = pixmap.scaled(280, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.drawer_preview.setText("")
            self.drawer_preview.setPixmap(scaled)
        else:
            self.drawer_preview.setPixmap(QPixmap())
            self.drawer_preview.setText("No image chosen")

    # ------------------------------------------------------------- Actions
    def _on_choose_image(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Choose background image", "", IMAGE_FILTER)
        if not source:
            return
        try:
            pixmap = QPixmap(source)
            if pixmap.isNull():
                raise ValueError("That file could not be loaded as an image.")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return
        self._pending_image = source
        self._update_drawer_preview(None)

    def _on_save(self) -> None:
        name = self.drawer_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter the background name.")
            return

        try:
            stored = image_store.save_image(self._pending_image) if self._pending_image else None
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return

        try:
            if self._editing_id is None:
                background = database.create_background(name, stored or "")
                message = f"Created '{background['name']}'."
            else:
                old = database.get_background(self._editing_id)
                database.rename_background(self._editing_id, name)
                if stored:
                    database.update_background_image(self._editing_id, stored)
                    image_store.delete_image(old["image_path"])
                message = f"Saved '{name}'."
        except ValueError as exc:
            if stored:
                image_store.delete_image(stored)
            QMessageBox.warning(self, "Cannot save background", str(exc))
            return

        self.refresh()
        self.close_drawer()
        self.status_label.setText(message)

    def _on_delete(self) -> None:
        if self._editing_id is None:
            return
        self._delete_background(self._editing_id, close_drawer=True)

    def _delete_background(self, background_id: int, close_drawer: bool = False) -> None:
        background = database.get_background(background_id)
        if background is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete background",
            f"Delete background '{background['name']}'?\n\n"
            "This also deletes its image file and cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_background(background["id"])
        image_store.delete_image(background["image_path"])
        self.refresh()
        if close_drawer:
            self.close_drawer()
        self.status_label.setText(f"Deleted '{background['name']}'.")

    # ------------------------------------------------------------ Grid list
    def refresh(self) -> None:
        backgrounds = database.list_backgrounds()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_items = bool(backgrounds)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

        for i, background in enumerate(backgrounds):
            card = self._make_card(background)
            row, col = divmod(i, GRID_COLUMNS)
            self.grid.addWidget(card, row, col)
        self.status_label.setText(
            f"{len(backgrounds)} background(s) · images stored in backgrounds/ folder"
        )

    def _make_card(self, background) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(CARD_W, CARD_H)
        card.setStyleSheet(CARD_STYLE)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(8)

        image_label = QLabel()
        image_label.setStyleSheet(
            f"background-color: {BG}; border: none; border-radius: 8px;"
        )
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setFixedHeight(140)

        path = image_store.absolute_path(background["image_path"])
        if background["image_path"] and path.is_file():
            pixmap = QPixmap(str(path)).scaled(
                150, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            image_label.setPixmap(pixmap)
        else:
            image_label.setText("No image")
            image_label.setStyleSheet(PLACEHOLDER_STYLE)

        name_label = QLabel(background["name"])
        name_label.setStyleSheet(f"color: {TEXT}; font-size: 15px; font-weight: bold; {CARD_LABEL_STYLE}")
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)

        inner.addWidget(image_label)
        inner.addWidget(name_label)

        delete_btn = QPushButton("🗑")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setToolTip(f"Delete background '{background['name']}'")
        delete_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #f87171; "
            "border: none; padding: 4px; font-size: 13px; }"
            "QPushButton:hover { color: #ef4444; }"
        )
        delete_btn.clicked.connect(
            lambda _checked=False, bid=background["id"]: self._delete_background(bid)
        )

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 8, 0, 0)
        bottom.addStretch()
        bottom.addWidget(delete_btn)
        inner.addLayout(bottom)

        def mousePressEvent(event, bid=background["id"]):  # noqa: N802 (Qt naming)
            if event.button() == Qt.LeftButton:
                self.open_drawer(bid)

        card.mousePressEvent = mousePressEvent
        return card
