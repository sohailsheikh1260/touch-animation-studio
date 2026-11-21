"""Since module screen."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

from screens.theme import BG, CARD_STYLE, MUTED, TEXT

ICON = "📜"
NAME = "Since"
DESC = "Changelog & version notes"


INFO = (ICON, NAME, DESC)


class SinceScreen(QWidget):
    def __init__(self, show_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.show_home = show_home

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 32)
        layout.setSpacing(16)

        top = QHBoxLayout()
        back_btn = QPushButton("← Back to Home")
        back_btn.clicked.connect(self.show_home)
        top.addWidget(back_btn)
        top.addStretch()
        layout.addLayout(top)

        title = QLabel(f"{ICON} {NAME}")
        title.setStyleSheet(f"color: {TEXT}; font-size: 26px; font-weight: bold;")
        title.setAlignment(Qt.AlignHCenter)
        layout.addWidget(title)

        subtitle = QLabel("Changelog & version notes")
        subtitle.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignHCenter)
        layout.addWidget(subtitle)

        body = QLabel(
            "🏠 Home — 6 modules (Project, Background, Character, Animation,\n"
            "          Audio, Knowledge) + this one (Since)\n"
            "🎬 Project editor — timeline, screen presets, MP4 export\n"
            "🎵 Audio sync, playback, export with sound\n"
            "🖥 Preview stage now fills the editor panel\n"
            "💾 Timeline auto-saves to SQLite\n"
            "🔒 Clean shutdown on close (no crash)\n"
            "\n"
            "More updates coming soon..."
        )
        body.setStyleSheet(
            f"color: {TEXT}; font-size: 14px; background-color: {BG};"
            " border: 1px solid #334155; border-radius: 12px; padding: 18px;"
        )
        body.setAlignment(Qt.AlignCenter)
        layout.addWidget(body)
        layout.addStretch()
