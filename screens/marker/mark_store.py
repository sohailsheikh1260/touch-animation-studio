"""Mark-tab data store for markers.

Lets MarkCharacterPage (screens/character_details/mark_character.py) run its
identical UI against markers: same canvas, zoom/pan, markup boxes - but the
rows live in marker_parts / markers instead of character_parts / characters.
"""

import database
from screens.marker import image_store

KIND = "Marker"
ICON = "📍"

# Suggested markup names shown in the "＋ Add Part" dropdown (free text too).
MARKER_PART_NAMES = [
  "head",
  "body",
  "hand_left_upper",
  "hand_left_lower"
  "hand_right_upper",
  "hand_right_lower",
  "leg_left_upper",
  "leg_left_lower"
  "leg_right_upper",
  "leg_right_lower",
  "lip_happy",
  "lip_",
  "lip_",
  "lip_",
  "lip_",

]


class MarkerMarkStore:
    """Same interface as CharacterMarkStore, backed by the markers tables."""

    kind = KIND
    icon = ICON
    part_names = MARKER_PART_NAMES
    image_store = image_store  # screens.marker.image_store
    fill_canvas = True  # marker image is rendered over the full 2048x2048 canvas

    def get_owner(self, owner_id: int):
        return database.get_marker(owner_id)

    def list_parts(self, owner_id: int) -> list:
        return database.list_marker_parts(owner_id)

    def get_part(self, part_id: int):
        return database.get_marker_part(part_id)

    def create_part(self, owner_id: int, part_name: str, note: str = "", payload: str = "{}"):
        return database.create_marker_part(owner_id, part_name, note, payload)

    def update_part(self, part_id: int, part_name: str, note: str = "", payload: str = "{}"):
        return database.update_marker_part(part_id, part_name, note, payload)

    def delete_part(self, part_id: int) -> None:
        database.delete_marker_part(part_id)

    def set_part_locked(self, part_id: int, locked: bool) -> None:
        database.set_marker_part_locked(part_id, locked)

    def bump_part_layer(self, part_id: int, delta: int):
        return database.bump_marker_part_layer(part_id, delta)

    def export_owner(self, owner_id: int, parent) -> None:
        """Markers have no export file yet - kept for interface parity."""
        return None

    def import_owner(self, owner_id: int, parent) -> bool:
        """Markers have no import file yet - kept for interface parity."""
        return False
