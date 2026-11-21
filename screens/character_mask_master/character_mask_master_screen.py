"""Character Mask Master module screen - Grid + Details page (SQLite-backed).

- Grid page: boxes of reusable character masks.
- Clicking a box opens the CharacterMaskDetailsPage.
- "＋ Add Mask" opens a drawer for create/edit.
"""

from PySide6.QtCore import QEvent, QPoint, QPropertyAnimation, QEasingCurve, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import database
from screens.character_mask_master.character_mask_details import CharacterMaskDetailsPage
from screens.theme import BG, CARD_BG, MUTED, TEXT

ICON = "🎭"
NAME = "Character Mask Master"
DESC = "Manage reusable character masks"
INFO = (ICON, NAME, DESC)

DRAWER_WIDTH = 340
CARD_W, CARD_H = 180, 216
GRID_COLUMNS = 3

CARD_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    "  border: 2px solid #334155; border-radius: 14px; }}"
    "QFrame:hover { border-color: #38bdf8; }"
)
CARD_LABEL_STYLE = "background-color: transparent; border: none;"

TOP_BUTTON_STYLE = (
    f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px; }"
    "QPushButton:hover { background-color: #334155; }"
)
CREATE_BUTTON_STYLE = (
    "QPushButton { background-color: #7c3aed; color: #e2e8f0;"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 20px; font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #8b5cf6; }"
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
DETAIL_STYLE = f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
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


class CharacterMaskMasterScreen(QWidget):
    """Manage reusable character-mask templates."""

    mask_selected = Signal(int)

    def __init__(self, go_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        database.init_db()
        self._editing_id: int | None = None
        self._details_id: int | None = None

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._build_grid_page())
        self.details_page = CharacterMaskDetailsPage(
            self.show_grid,
            set_status=lambda message: self.status_label.setText(message),
        )
        self.details_page.edit_requested.connect(self.open_drawer)
        stack.addWidget(self.details_page)

        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.overlay.hide()
        self.overlay.installEventFilter(self)

        self.drawer = QFrame(self)
        self.drawer.setFixedWidth(DRAWER_WIDTH)
        self.drawer.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-left: 2px solid #7c3aed; }}"
        )
        self._build_drawer(self.drawer)

        self._anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        self.stack = stack
        self.refresh()

    def _build_grid_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(14)

        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(TOP_BUTTON_STYLE)
        back_btn.clicked.connect(self.show_home)

        self.title = QLabel(f"{ICON}  Character Mask Master")
        self.title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")

        create_btn = QPushButton("＋ Add Mask")
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

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        self.empty_label = QLabel("No character masks yet — click “＋ Add Mask”!")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
        root.addWidget(self.empty_label, 1)
        self.empty_label.hide()
        root.addWidget(self.scroll, 1)
        return page

    def show_grid(self) -> None:
        self._details_id = None
        self.stack.setCurrentIndex(0)

    def show_home(self) -> None:
        self._details_id = None
        window = self.window()
        if hasattr(window, "show_home"):
            window.show_home()

    def show_details(self, mask_id: int) -> None:
        mask = database.get_character_mask(mask_id)
        if mask is None:
            return
        self._details_id = mask_id
        self.details_page.show_mask(mask)
        self.stack.setCurrentIndex(1)
        self.mask_selected.emit(mask_id)

    def refresh(self) -> None:
        entries = database.list_character_masks()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_items = bool(entries)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)
        for i, entry in enumerate(entries):
            row, col = divmod(i, GRID_COLUMNS)
            self.grid.addWidget(self._make_card(entry), row, col)
        self.status_label.setText(f"{len(entries)} character mask(s)")

    def _make_card(self, entry) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(CARD_W, CARD_H)
        card.setStyleSheet(CARD_STYLE)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(8)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        delete_btn = QPushButton("🗑")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setToolTip("Delete character mask")
        delete_btn.setStyleSheet(
            "QPushButton { background-color: #7f1d1d; color: #e2e8f0;"
            "  border: none; border-radius: 12px; font-size: 12px; }"
            "QPushButton:hover { background-color: #991b1b; }"
        )
        delete_btn.hide()
        delete_btn.clicked.connect(
            lambda checked=False, mid=entry["id"]: self._delete_mask_from_card(mid)
        )
        top_bar.addWidget(delete_btn)
        inner.addLayout(top_bar)

        icon_label = QLabel(ICON)
        icon_label.setStyleSheet(
            f"font-size: 34px; background-color: {BG}; border: none; border-radius: 8px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedHeight(140)

        name_label = QLabel(entry["name"])
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: bold; {CARD_LABEL_STYLE}"
        )
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)

        desc_label = QLabel(entry["description"] or "No description")
        desc_label.setStyleSheet(DETAIL_STYLE)
        desc_label.setAlignment(Qt.AlignHCenter)
        desc_label.setWordWrap(True)

        inner.addWidget(icon_label)
        inner.addWidget(name_label)
        inner.addWidget(desc_label)
        card._delete_btn = delete_btn

        def mousePressEvent(event, mid=entry["id"]):  # noqa: N802
            if event.button() == Qt.LeftButton:
                self.show_details(mid)

        def enterEvent(event):  # noqa: N802
            delete_btn.show()
            super(QFrame, card).enterEvent(event)

        def leaveEvent(event):  # noqa: N802
            delete_btn.hide()
            super(QFrame, card).leaveEvent(event)

        card.mousePressEvent = mousePressEvent
        card.enterEvent = enterEvent
        card.leaveEvent = leaveEvent
        return card

    def _build_drawer(self, drawer: QFrame) -> None:
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.drawer_title = QLabel("Add Character Mask")
        self.drawer_title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: bold;"
        )
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(TOP_BUTTON_STYLE)
        close_btn.clicked.connect(self.close_drawer)
        header.addWidget(self.drawer_title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        name_hint = QLabel("Mask name")
        name_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_name = QLineEdit()
        self.drawer_name.setPlaceholderText("e.g. Upper Body, Face, Prop")
        self.drawer_name.setStyleSheet(INPUT_STYLE)
        self.drawer_name.returnPressed.connect(self._on_save)
        layout.addWidget(name_hint)
        layout.addWidget(self.drawer_name)

        desc_hint = QLabel("Description")
        desc_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_description = QTextEdit()
        self.drawer_description.setPlaceholderText(
            "Optional description of this character mask..."
        )
        self.drawer_description.setStyleSheet(DESCRIPTION_STYLE)
        self.drawer_description.setFixedHeight(180)
        layout.addWidget(desc_hint)
        layout.addWidget(self.drawer_description)

        layout.addStretch()

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾  Save Mask")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    def open_drawer(self, mask_id: int | None = None) -> None:
        self._editing_id = mask_id
        if mask_id is None:
            self.drawer_title.setText("Add Character Mask")
            self.drawer_name.clear()
            self.drawer_description.clear()
            self.delete_btn.hide()
        else:
            mask = database.get_character_mask(mask_id)
            if mask is None:
                return
            self.drawer_title.setText("Edit Character Mask")
            self.drawer_name.setText(mask["name"])
            self.drawer_description.setPlainText(mask["description"])
            self.delete_btn.show()

        self.drawer_name.setFocus()
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
        if self._anim.endValue().x() >= self.width():
            self.drawer.hide()
            self.overlay.hide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.overlay and event.type() == QEvent.MouseButtonPress:
            self.close_drawer()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        is_open = self.drawer.isVisible() and self._anim.state() != QPropertyAnimation.Running
        x = self.width() - DRAWER_WIDTH if is_open else self.width()
        self.drawer.setGeometry(x, 0, DRAWER_WIDTH, self.height())

    def _on_save(self) -> None:
        name = self.drawer_name.text().strip()
        description = self.drawer_description.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter the character mask name.")
            return
        try:
            if self._editing_id is None:
                mask = database.create_character_mask(name, description)
                message = f"Created '{mask['name']}'."
                new_id = mask["id"]
            else:
                database.update_character_mask(self._editing_id, name, description)
                message = f"Saved '{name}'."
                new_id = self._editing_id
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot save character mask", str(exc))
            return

        self.refresh()
        if self.stack.currentIndex() == 1 and self._details_id is not None:
            updated = database.get_character_mask(new_id)
            if updated is not None:
                self.details_page.show_mask(updated)
            else:
                self.show_grid()
        self.close_drawer()
        self.status_label.setText(message)

    def _on_delete(self) -> None:
        if self._editing_id is None:
            return
        mask = database.get_character_mask(self._editing_id)
        if mask is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete character mask",
            f"Delete character mask '{mask['name']}'?\n\n"
            "Characters using this mask will be cleared. This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_character_mask(mask["id"])
        self.refresh()
        if self.stack.currentIndex() == 1:
            self.show_grid()
        self.close_drawer()
        self.status_label.setText(f"Deleted '{mask['name']}'.")

    def _delete_mask_from_card(self, mask_id: int) -> None:
        mask = database.get_character_mask(mask_id)
        if mask is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete character mask",
            f"Delete character mask '{mask['name']}'?\n\n"
            "Characters using this mask will be cleared. This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_character_mask(mask["id"])
        self.refresh()
        if self.stack.currentIndex() == 1:
            self.show_grid()
        self.status_label.setText(f"Deleted '{mask['name']}'.")
