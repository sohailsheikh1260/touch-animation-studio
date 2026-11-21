"""Character details screen - container with same-layout tabs.

- 🏷 Mark Character : image canvas + body-part markup (mark_character.py)
- 🦴 Skeleton : skeleton view + bone/image editing (skeleton.py)
- 🎬 Animation : animation editing (animation.py)

CharacterScreen keeps using `CharacterDetailsPage.show_character(character)`.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from screens.character_details.animation import AnimationPage
from screens.character_details.mark_character import MarkCharacterPage
from screens.character_details.skeleton import SkeletonPage
from screens.character_details.styles import TOP_BUTTON_STYLE
from screens.theme import TEXT

ICON = "🧍"


class CharacterDetailsPage(QWidget):
    """Character details screen: top bar + tab strip + the tab pages."""

    def __init__(
        self,
        show_characters,
        set_status=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._show_characters = show_characters  # callback: back to grid page
        self._set_status = set_status or (lambda message: None)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(16)

        # ---- Top bar (shared by all tabs) ----
        back_btn = QPushButton("← Back to Characters")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(200)
        back_btn.setStyleSheet(TOP_BUTTON_STYLE)
        back_btn.clicked.connect(self._show_characters)

        self.details_title = QLabel(f"{ICON}  Character Details")
        self.details_title.setStyleSheet(
            f"color: {TEXT}; font-size: 22px; font-weight: bold;"
        )

        top_bar = QHBoxLayout()
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.details_title)
        top_bar.addStretch()
        root.addLayout(top_bar)

        # ---- Tabs ----
        self.mark_page = MarkCharacterPage(set_status=self._set_status)
        self.skeleton_page = SkeletonPage()
        self.animation_page = AnimationPage()

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: none; }"
            "QTabBar::tab { background-color: #1e293b; color: #e2e8f0;"
            "  padding: 8px 18px; margin-right: 4px;"
            "  border-top-left-radius: 8px; border-top-right-radius: 8px;"
            "  font-size: 14px; }"
            "QTabBar::tab:selected { background-color: #0e7490; color: #ffffff; }"
        )
        self.tabs.addTab(self.mark_page, "🏷 Mark Character")
        self.tabs.addTab(self.skeleton_page, "🦴 Skeleton")
        self.tabs.addTab(self.animation_page, "🎬 Animation")
        root.addWidget(self.tabs, 1)

    # ============================================================ Public API
    def show_character(self, character) -> None:
        """Fill all tabs with the given character row."""
        self.details_title.setText(f"{ICON}  {character['name']}")
        self.mark_page.show_character(character)
        self.skeleton_page.set_character(character)
        self.animation_page.set_character(character)
