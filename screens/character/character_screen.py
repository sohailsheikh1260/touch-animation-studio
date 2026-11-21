"""Character module screen - CRUD with drawer + grid (SQLite-backed).

- Grid page: boxes of characters (image + name), "＋ Create Character" button.
- Clicking a box opens the **Character Details screen**, which lives in its
  own folder: `screens/character_details/` (see `CharacterDetailsPage`).
- The drawer still slides in from the right for create/edit/delete forms.
"""

from PySide6.QtCore import QEvent, QPropertyAnimation, QEasingCurve, Qt, QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

import database
from screens.character import image_store
from screens.character_details import CharacterDetailsPage
from screens.theme import BG, CARD_BG, MUTED, TEXT

ICON = "🧍"
NAME = "Character"
DESC = "Design and rig your characters"
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
    "QPushButton { background-color: #0e7490; color: #e2e8f0;"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 20px; font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #0891b2; }"
)

EDIT_BUTTON_STYLE = (
    "QPushButton { background-color: #0e7490; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px 24px;"
    "  font-size: 15px; font-weight: bold; }"
    "QPushButton:hover { background-color: #0891b2; }"
)

DELETE_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
    "  border: none; border-radius: 8px; padding: 10px 24px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
)

INPUT_STYLE = (
    f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

IMAGE_PANEL_STYLE = (
    f"QLabel {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px;"
    f"  color: {MUTED}; font-size: 14px; }}"
)

MUTED_TEXT = f"color: {MUTED}; font-size: 13px;"
INFO_TEXT = f"color: {TEXT}; font-size: 14px;"

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"


class CharacterScreen(QWidget):
    def __init__(self, go_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        database.init_db()
        self._editing_id: int | None = None
        self._details_id: int | None = None  # character shown on the details page
        self._pending_image: str | None = None  # absolute path chosen, not yet saved

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._build_characters_page())  # index 0: grid
        self.details_page = CharacterDetailsPage(
            self.show_characters,
            set_status=lambda message: self.status_label.setText(message),
        )
        stack.addWidget(self.details_page)              # index 1: details

        # ---- Slide-in drawer + overlay (children of the whole screen) ----
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.overlay.hide()
        self.overlay.installEventFilter(self)

        self.drawer = QFrame(self)
        self.drawer.setFixedWidth(DRAWER_WIDTH)
        self.drawer.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-left: 2px solid #0e7490; }}"
        )
        self._build_drawer(self.drawer)

        self._anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        self.stack = stack
        self.refresh()

    # ================================================== Page 0: characters
    def _build_characters_page(self) -> QWidget:
        page = QWidget()

        root = QVBoxLayout(page)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(14)

        # ---- Top bar ----
        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(TOP_BUTTON_STYLE)
        back_btn.clicked.connect(self.show_home)

        self.title = QLabel(f"{ICON}  Characters")
        self.title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")

        create_btn = QPushButton("＋ Create Character")
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

        # ---- Character boxes grid (scrollable) ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        self.empty_label = QLabel("No characters yet — click “＋ Create Character”!")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
        root.addWidget(self.empty_label, 1)
        self.empty_label.hide()

        root.addWidget(self.scroll, 1)
        return page

    # ------------------------------------------------------- Navigation
    def show_characters(self) -> None:
        self._details_id = None
        self.stack.setCurrentIndex(0)

    def show_home(self) -> None:
        self._details_id = None
        window = self.window()
        if hasattr(window, "show_home"):
            window.show_home()

    def show_details(self, character_id: int) -> None:
        character = database.get_character(character_id)
        if character is None:
            return
        self._details_id = character_id
        self.details_page.show_character(character)
        self.stack.setCurrentIndex(1)

    # ------------------------------------------------------------ Grid list
    def refresh(self) -> None:
        characters = database.list_characters()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_items = bool(characters)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

        for i, character in enumerate(characters):
            card = self._make_card(character)
            row, col = divmod(i, GRID_COLUMNS)
            self.grid.addWidget(card, row, col)
        self.status_label.setText(
            f"{len(characters)} character(s) · images stored in images/ folder"
        )

    def _make_card(self, character) -> QFrame:
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

        path = image_store.absolute_path(character["image_path"])
        if character["image_path"] and path.is_file():
            pixmap = QPixmap(str(path)).scaled(
                150, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            image_label.setPixmap(pixmap)
        else:
            image_label.setText("No image")
            image_label.setStyleSheet(PLACEHOLDER_STYLE)

        name_label = QLabel(character["name"])
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: bold; {CARD_LABEL_STYLE}"
        )
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)

        inner.addWidget(image_label)
        inner.addWidget(name_label)

        # Delete button at the bottom of the card
        delete_btn = QPushButton("🗑")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #f87171; "
            "border: none; padding: 4px; font-size: 13px; }"
            "QPushButton:hover { color: #ef4444; }"
        )
        delete_btn.clicked.connect(lambda _, cid=character["id"]: self._confirm_delete(cid))

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 8, 0, 0)
        bottom.addStretch()
        bottom.addWidget(delete_btn)
        inner.addLayout(bottom)

        def mousePressEvent(event, cid=character["id"]):  # noqa: N802 (Qt naming)
            if event.button() == Qt.LeftButton:
                self.show_details(cid)

        card.mousePressEvent = mousePressEvent
        return card

    def _confirm_delete(self, character_id: int) -> None:
        character = database.get_character(character_id)
        if character is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete character",
            f"Delete character '{character['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_character(character_id)
        image_store.delete_image(character["image_path"])
        self.refresh()
        if self.stack.currentIndex() == 1:
            self.show_characters()
        self.status_label.setText(f"Deleted '{character['name']}'.")

    # -------------------------------------------------------- Drawer UI
    def _build_drawer(self, drawer: QFrame) -> None:
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.drawer_title = QLabel("Create Character")
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

        name_hint = QLabel("Character name")
        name_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_name = QLineEdit()
        self.drawer_name.setPlaceholderText("e.g. Hero")
        self.drawer_name.setStyleSheet(INPUT_STYLE)
        self.drawer_name.returnPressed.connect(self._on_save)
        layout.addWidget(name_hint)
        layout.addWidget(self.drawer_name)

        # Character type dropdown
        type_hint = QLabel("Character type")
        type_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_character_type = QComboBox()
        self.drawer_character_type.setStyleSheet(INPUT_STYLE)
        self.drawer_character_type.addItems(database.CHARACTER_TYPES)
        layout.addWidget(type_hint)
        layout.addWidget(self.drawer_character_type)

        # Skeleton dropdown
        skeleton_hint = QLabel("Skeleton (optional)")
        skeleton_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_skeleton = QComboBox()
        self.drawer_skeleton.setStyleSheet(INPUT_STYLE)
        self.drawer_skeleton.addItem("(No skeleton)", None)
        layout.addWidget(skeleton_hint)
        layout.addWidget(self.drawer_skeleton)

        # Character mask dropdown
        mask_hint = QLabel("Mask (optional)")
        mask_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_mask = QComboBox()
        self.drawer_mask.setStyleSheet(INPUT_STYLE)
        layout.addWidget(mask_hint)
        layout.addWidget(self.drawer_mask)

        image_hint = QLabel("Character image")
        image_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_preview = QLabel("No image chosen")
        self.drawer_preview.setStyleSheet(IMAGE_PANEL_STYLE)
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
        self.delete_btn.setStyleSheet(DELETE_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾  Save Character")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: #e2e8f0;"
            "  border: none; border-radius: 8px; padding: 10px;"
            "  font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background-color: #22c55e; }"
        )
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    # ---------------------------------------------------- Drawer behavior
    def open_drawer(self, character_id: int | None = None) -> None:
        self._editing_id = character_id
        self._pending_image = None

        # Populate skeleton dropdown from skeleton master table
        self.drawer_skeleton.clear()
        self.drawer_skeleton.addItem("(No skeleton)", None)
        try:
            skeletons = database.list_skeletons()
            for s in skeletons:
                self.drawer_skeleton.addItem(s["name"], s["id"])
        except Exception:
            pass

        # Populate mask dropdown from Character Mask Master templates
        self.drawer_mask.clear()
        self.drawer_mask.addItem("(No mask)", None)
        for mask in database.list_character_masks():
            self.drawer_mask.addItem(mask["name"], mask["id"])

        if character_id is None:
            self.drawer_title.setText("Create Character")
            self.drawer_name.clear()
            self.drawer_character_type.setCurrentIndex(0)
            self.drawer_skeleton.setCurrentIndex(0)
            self.drawer_mask.setCurrentIndex(0)
            self._update_drawer_preview(None)
            self.delete_btn.hide()
        else:
            character = database.get_character(character_id)
            if character is None:
                return
            self.drawer_title.setText("Edit Character")
            self.drawer_name.setText(character["name"])
            stored_type = character["character_type"] or "human"
            type_idx = self.drawer_character_type.findText(stored_type)
            self.drawer_character_type.setCurrentIndex(type_idx if type_idx >= 0 else 0)
            # Select current skeleton if any
            skeleton_id = character["skeleton_id"]
            if skeleton_id:
                idx = self.drawer_skeleton.findData(skeleton_id)
                if idx >= 0:
                    self.drawer_skeleton.setCurrentIndex(idx)
            mask_id = character["mask_id"]
            if mask_id:
                idx = self.drawer_mask.findData(mask_id)
                if idx >= 0:
                    self.drawer_mask.setCurrentIndex(idx)
            self._update_drawer_preview(character["image_path"] or None)
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
        overlay = getattr(self, "overlay", None)
        if overlay is not None and obj is overlay and event.type() == QEvent.MouseButtonPress:
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
        source, _ = QFileDialog.getOpenFileName(self, "Choose character image", "", IMAGE_FILTER)
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
            QMessageBox.warning(self, "Missing name", "Enter the character name.")
            return

        skeleton_id = self.drawer_skeleton.currentData()
        character_type = self.drawer_character_type.currentText()
        mask_id = self.drawer_mask.currentData()

        try:
            stored = image_store.save_image(self._pending_image) if self._pending_image else None
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid image", str(exc))
            return

        try:
            if self._editing_id is None:
                character = database.create_character(
                    name,
                    stored or "",
                    skeleton_id,
                    character_type=character_type,
                    mask_id=mask_id,
                )
                message = f"Created '{character['name']}'."
                new_id = character["id"]
                # Seed default animation presets (incl. idle) for the new character
                try:
                    presets = {
                        "walk": {"speed": 0.07, "legAmplitude": 25, "armAmplitude": 18, "bobAmount": 12, "bobFrequency": 2, "mouthType": "normal", "browType": 1, "isTalking": False},
                        "idle": {"speed": 0.03, "legAmplitude": 3, "armAmplitude": 5, "bobAmount": 4, "bobFrequency": 1, "mouthType": "normal", "browType": 1, "isTalking": False},
                        "talking": {"speed": 0.03, "legAmplitude": 2, "armAmplitude": 8, "bobAmount": 3, "bobFrequency": 1, "mouthType": "normal", "browType": 2, "isTalking": True},
                        "smile": {"speed": 0.03, "legAmplitude": 2, "armAmplitude": 6, "bobAmount": 3, "bobFrequency": 1, "mouthType": "smile", "browType": 3, "isTalking": False},
                        "aggressive": {"speed": 0.05, "legAmplitude": 15, "armAmplitude": 12, "bobAmount": 6, "bobFrequency": 2, "mouthType": "aggressive", "browType": 4, "isTalking": True},
                    }
                    for aname, p in presets.items():
                        database.create_character_animation(
                            new_id, aname,
                            speed=p["speed"], leg_amplitude=p["legAmplitude"],
                            arm_amplitude=p["armAmplitude"], bob_amount=p["bobAmount"],
                            bob_frequency=p["bobFrequency"],
                            mouth_type=p["mouthType"], brow_type=p["browType"],
                            is_talking=p["isTalking"],
                        )
                except Exception:
                    pass
            else:
                old = database.get_character(self._editing_id)
                database.rename_character(self._editing_id, name)
                database.update_character_skeleton(self._editing_id, skeleton_id)
                database.update_character_type(self._editing_id, character_type)
                database.assign_character_mask(self._editing_id, mask_id)
                if stored:
                    database.update_character_image(self._editing_id, stored)
                    image_store.delete_image(old["image_path"])
                message = f"Saved '{name}'."
                new_id = self._editing_id
        except ValueError as exc:
            if stored:
                image_store.delete_image(stored)
            QMessageBox.warning(self, "Cannot save character", str(exc))
            return

        self.refresh()
        # Keep the details page in sync if the drawer was opened there
        if self.stack.currentIndex() == 1 and self._details_id is not None:
            updated = database.get_character(new_id)
            if updated is not None:
                self.details_page.show_character(updated)
            else:
                self.show_characters()
        self.close_drawer()
        self.status_label.setText(message)

    def _on_delete(self) -> None:
        if self._editing_id is None:
            return
        character = database.get_character(self._editing_id)
        if character is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete character",
            f"Delete character '{character['name']}'?\n\n"
            "This also deletes its image file and cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_character(character["id"])
        image_store.delete_image(character["image_path"])
        self.refresh()
        if self.stack.currentIndex() == 1:
            self.show_characters()
        self.close_drawer()
        self.status_label.setText(f"Deleted '{character['name']}'.")
