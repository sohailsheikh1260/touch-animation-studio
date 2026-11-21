"""Character Mask Master details page - editable mask/default JSON data."""

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import database
from screens.theme import BG, CARD_BG, MUTED, TEXT


class CharacterMaskDetailsPage(QWidget):
    """Mask metadata, assigned characters, and reusable data editors."""

    edit_requested = Signal(int)
    character_selected = Signal(int)

    def __init__(
        self,
        go_back,
        set_status,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._go_back = go_back
        self._set_status = set_status
        self._mask_id: int | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-right: 1px solid #334155; }}"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 8px;"
            "  padding: 8px 16px; font-size: 13px; }"
            "QPushButton:hover { background-color: #334155; }"
        )
        back_btn.clicked.connect(self._go_back)
        sidebar_layout.addWidget(back_btn)

        self.sidebar_name = QLabel("Mask Name")
        self.sidebar_name.setWordWrap(True)
        self.sidebar_name.setStyleSheet(
            f"color: {TEXT}; font-size: 16px; font-weight: bold;"
        )
        sidebar_layout.addWidget(self.sidebar_name)

        self.sidebar_description = QLabel("")
        self.sidebar_description.setWordWrap(True)
        self.sidebar_description.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        sidebar_layout.addWidget(self.sidebar_description)

        edit_btn = QPushButton("✎  Edit Mask")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setStyleSheet(
            f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 8px; padding: 8px 12px; }"
            "QPushButton:hover { background-color: #334155; }"
        )
        edit_btn.clicked.connect(self._on_edit)
        sidebar_layout.addWidget(edit_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #334155;")
        sidebar_layout.addWidget(sep)

        characters_label = QLabel("CHARACTERS")
        characters_label.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        sidebar_layout.addWidget(characters_label)

        self.character_list = QListWidget()
        self.character_list.itemClicked.connect(self._on_character_clicked)
        sidebar_layout.addWidget(self.character_list, 1)
        root.addWidget(self.sidebar, 1)

        self.main_area = QFrame()
        self.main_area.setStyleSheet(f"background-color: {BG};")
        main_layout = QVBoxLayout(self.main_area)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        self.main_title = QLabel("Character Mask Details")
        self.main_title.setStyleSheet(
            f"color: {TEXT}; font-size: 20px; font-weight: bold;"
        )
        main_layout.addWidget(self.main_title)

        hint = QLabel(
            "Edit these JSON objects independently. Character creation copies "
            "both values into the selected character."
        )
        hint.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        hint.setWordWrap(True)
        main_layout.addWidget(hint)

        editors = QHBoxLayout()
        editors.setSpacing(12)

        self.mask_data_input = self._make_editor("Mask data (JSON)", editors)
        self.default_data_input = self._make_editor("Default data (JSON)", editors)
        main_layout.addLayout(editors, 1)

        save_btn = QPushButton("💾  Save Mask Data")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: #e2e8f0;"
            "  border: none; border-radius: 8px; padding: 10px;"
            "  font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #22c55e; }"
        )
        save_btn.clicked.connect(self._on_save_data)
        main_layout.addWidget(save_btn)

        root.addWidget(self.main_area, 4)

    @staticmethod
    def _make_editor(title: str, parent_layout: QHBoxLayout) -> QTextEdit:
        column = QVBoxLayout()
        column.setSpacing(8)
        label = QLabel(title)
        label.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: bold;")
        column.addWidget(label)

        editor = QTextEdit()
        editor.setPlainText("{}")
        editor.setStyleSheet(
            f"QTextEdit {{ background-color: {CARD_BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 8px;"
            "  padding: 8px 12px; font-family: Consolas, monospace; font-size: 13px; }"
        )
        column.addWidget(editor, 1)
        parent_layout.addLayout(column, 1)
        return editor

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        sidebar_width = int(self.width() * 0.2)
        self.sidebar.setFixedWidth(max(180, min(sidebar_width, 280)))

    def show_mask(self, mask) -> None:
        self._mask_id = int(mask["id"])
        self.sidebar_name.setText(mask["name"])
        self.sidebar_description.setText(mask["description"] or "No description")
        self.main_title.setText(f"🎭  {mask['name']}")
        self.mask_data_input.setPlainText(self._pretty_json(mask["mask_data"]))
        self.default_data_input.setPlainText(self._pretty_json(mask["default_data"]))
        self._refresh_characters()
        if self._set_status:
            self._set_status(f"Viewing character mask: {mask['name']}")

    def _refresh_characters(self) -> None:
        self.character_list.clear()
        if self._mask_id is None:
            return
        for character in database.list_characters_using_mask(self._mask_id):
            item = QListWidgetItem(character["name"])
            item.setData(Qt.UserRole, character["id"])
            self.character_list.addItem(item)

    def _on_character_clicked(self, item: QListWidgetItem) -> None:
        character_id = item.data(Qt.UserRole)
        if character_id is not None:
            self.character_selected.emit(int(character_id))

    def _on_edit(self) -> None:
        if self._mask_id is not None:
            self.edit_requested.emit(self._mask_id)

    def _on_save_data(self) -> None:
        if self._mask_id is None:
            return
        try:
            database.update_character_mask_data(
                self._mask_id,
                self.mask_data_input.toPlainText(),
                self.default_data_input.toPlainText(),
            )
        except ValueError as exc:
            if self._set_status:
                self._set_status(f"Cannot save mask data: {exc}")
            return
        if self._set_status:
            self._set_status("Saved character mask data.")

    @staticmethod
    def _pretty_json(value: str) -> str:
        try:
            return json.dumps(json.loads(value or "{}"), indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            return value or "{}"
