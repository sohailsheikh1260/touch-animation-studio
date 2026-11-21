"""Chat tab for the project editor sidebar."""

from PySide6.QtWidgets import (
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from screens.ai_chat.agent import AIChatAgent

from .common import make_caption


class ChatTab(QWidget):
    """Caption plus the Groq-powered chat panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.caption = make_caption("💬 Chat")
        self.panel = AIChatAgent()

        layout.addWidget(self.caption)
        layout.addWidget(self.panel, 1)
