"""Background library tab for the project editor sidebar."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

import database
from screens.background import image_store as background_store

from .common import ListTab


class BackgroundTab(ListTab):
    """List of backgrounds with add-to-timeline actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🌄 Backgrounds", QSize(40, 40), parent)

    def refresh(self) -> None:
        """Rebuild the background list from the database."""
        self.list.clear()
        for background in database.list_backgrounds():
            self.add_asset_row(
                background["name"],
                "background",
                background["id"],
                background_store.absolute_path(background["image_path"]),
            )
