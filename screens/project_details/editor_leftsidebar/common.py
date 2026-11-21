"""Shared styles and widgets for the editor sidebar tabs."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from screens.theme import BG, CARD_BG, MUTED, TEXT

PANEL_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px; }}"
)
PANEL_LABEL_STYLE = "background-color: transparent; border: none;"
LIST_STYLE = (
    f"QListWidget {{ background-color: {BG}; color: {TEXT};"
    "  border: none; padding: 4px; font-size: 13px; }"
    "QListWidget::item { padding: 4px; border-radius: 6px; }"
    "QListWidget::item:selected { background-color: #334155; }"
)
BUTTON_STYLE = (
    f"QPushButton {{ background-color: #334155; color: {TEXT};"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 14px; font-size: 13px; }"
    "QPushButton:hover { background-color: #475569; }"
    "QPushButton:disabled { color: #64748b; }"
)


def make_caption(text: str) -> QLabel:
    """Small muted caption shown above each tab's content."""
    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED}; font-size: 11px; {PANEL_LABEL_STYLE}")
    return label


class ListTab(QWidget):
    """Base widget for tabs made of a caption and a QListWidget."""

    def __init__(
        self,
        caption: str,
        icon_size: QSize | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.caption = make_caption(caption)
        self.list = QListWidget()
        self.list.setStyleSheet(LIST_STYLE)
        self.list.setIconSize(icon_size or QSize(1, 1))
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.caption)
        layout.addWidget(self.list, 1)

        # Callback set by the sidebar: callable(kind: str, asset_id: int).
        self.on_add_asset = None

    def _add_asset(self, kind: str, asset_id: int) -> None:
        callback = getattr(self, "on_add_asset", None)
        if callable(callback):
            callback(kind, asset_id)

    def make_add_row(
        self,
        text: str,
        icon_path=None,
        tooltip: str = "Add to the selected timeline row",
        on_edit=None,
    ):
        """Build a list-item row: optional icon, name label and a "+" button.

        Pass ``on_edit`` (a zero-arg callable) to add an extra "✎" edit
        action button to the right of the "+" button (used by the character
        list to open the character details page).

        Returns (item, row_widget, add_btn); call addItem/setItemWidget on the
        list and connect add_btn afterwards.
        """
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 44))

        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(6)

        icon_label = QLabel()
        icon_label.setStyleSheet(PANEL_LABEL_STYLE)
        if icon_path is not None and icon_path.is_file():
            icon_label.setPixmap(QIcon(str(icon_path)).pixmap(36, 36))

        name_label = QLabel(text)
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; {PANEL_LABEL_STYLE}"
        )

        add_btn = QPushButton("＋")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedSize(28, 28)
        add_btn.setStyleSheet(BUTTON_STYLE)
        add_btn.setToolTip(tooltip)

        row.addWidget(icon_label)
        row.addWidget(name_label, 1)
        if callable(on_edit):
            edit_btn = QPushButton("✎")
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setFixedSize(28, 28)
            edit_btn.setStyleSheet(BUTTON_STYLE + "QPushButton { padding: 0; }")
            edit_btn.setToolTip(
                "Edit this character in Character Details (leaves the editor)"
            )
            edit_btn.clicked.connect(lambda checked=False: on_edit())
            row.addWidget(edit_btn)
        row.addWidget(add_btn)
        return item, row_widget, add_btn

    def add_asset_row(
        self,
        text: str,
        kind: str,
        asset_id: int,
        icon_path=None,
        on_edit=None,
    ) -> None:
        """Add a media row and wire its "+" button to the sidebar callback."""
        item, row_widget, add_btn = self.make_add_row(
            text, icon_path, on_edit=on_edit
        )
        item.setData(Qt.UserRole, (kind, asset_id))
        add_btn.clicked.connect(
            lambda checked=False, k=kind, aid=asset_id: self._add_asset(k, aid)
        )
        self.list.addItem(item)
        self.list.setItemWidget(item, row_widget)

    def add_hint_item(self, text: str) -> None:
        """Add a non-interactive hint row (used by the Animations tab)."""
        item = QListWidgetItem()
        item.setData(Qt.UserRole, None)
        hint = QLabel(text)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"background: transparent; color: {MUTED}; font-size: 11px;"
        )
        item.setSizeHint(QSize(0, 40))
        self.list.addItem(item)
        self.list.setItemWidget(item, hint)
