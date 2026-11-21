"""Animation library tab for the project editor sidebar."""

from PySide6.QtWidgets import QWidget

import database

from .common import ListTab


class AnimationTab(ListTab):
    """Shows only the selected character's animation presets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🎬 Animations", parent=parent)
        self.character_id: int | None = None

    def set_character(self, character_id: int | None) -> None:
        """Filter the tab to one character's animations."""
        self.character_id = (
            int(character_id) if character_id is not None else None
        )
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the animation list for the selected character."""
        self.list.clear()
        if self.character_id is None:
            self.caption.setText("🎬 Animations")
            self.add_hint_item(
                "Select a character first (Char tab, stage or timeline) "
                "to see its animations."
            )
            return

        try:
            character = database.get_character(int(self.character_id))
        except Exception:
            character = None

        name = character["name"] if character is not None else "?"
        self.caption.setText(f"🎬 Animations — {name}")

        try:
            animations = database.list_character_ik_animations(int(self.character_id))
        except Exception:
            animations = []
        if not animations:
            # Fallback for characters that only ever got procedural walk
            # presets.
            try:
                animations = database.list_character_animations(int(self.character_id))
            except Exception:
                animations = []

        for animation in animations:
            self.add_asset_row(
                f"🎬 {animation['name']}",
                "animation",
                animation["id"],
            )
        if not animations:
            self.add_hint_item("No animations for this character yet.")
