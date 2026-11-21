"""Animation module screen."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from screens.theme import BACK_BUTTON_STYLE, MUTED, TEXT

INFO = ("🎬", "Animation", "Create keyframes and play animations")
PLACEHOLDER = (
    "The Animation workspace is under construction.\n"
    "Here you will create keyframes and play animations — coming soon!"
)


class AnimationScreen(QWidget):
    def __init__(self, go_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 32)
        layout.setSpacing(16)

        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.clicked.connect(go_home)

        icon, name, _ = INFO
        title = QLabel(f"{icon}  {name}")
        title.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: bold;")

        desc = QLabel(PLACEHOLDER)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"color: {MUTED}; font-size: 15px;")

        layout.addWidget(back_btn, 0, Qt.AlignLeft)
        layout.addStretch()
        layout.addWidget(title, 0, Qt.AlignHCenter)
        layout.addWidget(desc, 0, Qt.AlignHCenter)
        layout.addStretch()
