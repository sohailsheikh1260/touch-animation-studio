"""Since module screen - a simple placeholder page.

Plain UI: a header with a back button and a centred message. No lists.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from screens.theme import BACK_BUTTON_STYLE, CARD_BG, MUTED, TEXT

ICON = "📅"
NAME = "Since"
DESC = "A simple page with just a back button"
INFO = (ICON, NAME, DESC)

CENTER_STYLE = (
    f"color: {TEXT}; font-size: 20px; font-weight: bold;"
    " background-color: transparent; border: none;"
)

HINT_STYLE = (
    f"color: {MUTED}; font-size: 14px;"
    " background-color: transparent; border: none;"
)


class SinceScreen(QWidget):
    """Simple screen with a back button and a placeholder body."""

    def __init__(self, on_back, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.on_back = on_back

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(20)

        # --- header: back button + title ---
        header = QHBoxLayout()
        header.setSpacing(12)

        back = QPushButton("← Back")
        back.setCursor(Qt.PointingHandCursor)
        back.setStyleSheet(BACK_BUTTON_STYLE)
        back.clicked.connect(self._go_back)
        header.addWidget(back)

        title = QLabel(f"{ICON} {NAME}")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 22px; font-weight: bold;"
            " background-color: transparent; border: none;"
        )
        header.addWidget(title)
        header.addStretch()

        layout.addLayout(header)

        # --- simple body ---
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG};"
            "  border: 1px solid #334155; border-radius: 16px; }"
        )

        body = QVBoxLayout(card)
        body.setContentsMargins(32, 32, 32, 32)
        body.setSpacing(10)

        heading = QLabel("Since")
        heading.setStyleSheet(CENTER_STYLE)
        heading.setAlignment(Qt.AlignCenter)

        hint = QLabel("Nothing here yet.")
        hint.setStyleSheet(HINT_STYLE)
        hint.setAlignment(Qt.AlignCenter)

        body.addStretch()
        body.addWidget(heading)
        body.addWidget(hint)
        body.addStretch()

        layout.addWidget(card, 1)

    def _go_back(self) -> None:
        if callable(self.on_back):
            self.on_back()
