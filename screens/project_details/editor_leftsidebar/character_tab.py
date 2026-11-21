"""Character library tab for the project editor sidebar."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

import database
from screens.character import image_store as character_store

from .common import ListTab


class CharacterTab(ListTab):
    """List of characters with add-to-timeline and edit actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🧍 Characters", QSize(40, 40), parent)
        # Callback set by the sidebar: callable(character_id: int).
        self.on_edit_character = None

    def refresh(self) -> None:
        """Rebuild the character list from the database."""
        self.list.clear()
        for character in database.list_characters():
            self.add_asset_row(
                character["name"],
                "character",
                character["id"],
                character_store.absolute_path(character["image_path"]),
                on_edit=lambda cid=character["id"]: self._edit_character(cid),
            )

    def _edit_character(self, character_id: int) -> None:
        callback = getattr(self, "on_edit_character", None)
        if callable(callback):
            callback(character_id)
