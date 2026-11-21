"""Shared skeleton + body parts loader for character details tabs.

Single source of truth for loading:
- Skeleton bones (the character's own copy from its skeleton template)
- Character body part crops (from character_parts + character image)
- Bone-attached images with offsets (from skeleton_bone_images)

Both Skeleton tab and Animation tab use this to guarantee identical data.
"""

import json
from typing import Any

from PySide6.QtGui import QImage, QPixmap

import database
from screens.character import image_store


def load_character_skeleton_data(
    character: dict[str, Any], as_image: bool = False
) -> dict[str, Any]:
    """Load all skeleton-related data for a character.

    Set ``as_image=True`` to get QImage part crops (safe to paint from
    non-GUI threads, e.g. the video export worker); the default keeps the
    QPixmap crops the character details tabs use.

    Returns dict with:
        - bones: list of bone rows (the character's own copy from its template)
        - bone_map: {bone_name: bone_row}
        - bone_id_to_name: {bone_id: bone_name}
        - part_crops: {part_name: QPixmap | QImage (with as_image=True)}
        - bone_images: {bone_name: [{id, part, dx, dy, index}, ...]}
        - locked_bones: set of locked bone_names
    """
    result = {
        "bones": [],
        "bone_map": {},
        "bone_id_to_name": {},
        "part_crops": {},
        "bone_images": {},
        "locked_bones": set(),
        "locked_images": {},  # NEW: {bone_name: set of image ids that are locked}
        "part_layers": {},  # unified draw-order index per part (Mark tab's z)
        "part_locks": {},  # unified lock state per part (Mark tab's locked)
        "part_visible": {},  # hide/show flag per part (Mark tab's payload "visible")
    }

    if not character or not character.get("id"):
        return result

    char_id = character["id"]
    skeleton_id = character.get("skeleton_id")

    # 1. Load the character's own bones (copied from its skeleton template)
    rows = database.list_skeleton_bones(char_id)
    if not rows and skeleton_id:
        # Legacy character linked to a template without a per-character copy
        # yet - copy the template bones to this character once, then load them
        database.copy_skeleton_template_to_character(char_id, skeleton_id)
        rows = database.list_skeleton_bones(char_id)
    if rows:
        result["bones"] = list(rows)
        result["bone_map"] = {b["bone_name"]: b for b in result["bones"]}
        result["bone_id_to_name"] = {b["id"]: b["bone_name"] for b in result["bones"] if b["id"] is not None}
        result["locked_bones"] = {
            b["bone_name"]
            for b in result["bones"]
            if "is_locked" in b.keys() and b["is_locked"]
        }

    if not result["bones"]:
        return result

    # 2. Load character body parts and create cropped pixmaps from character image
    image_path = character.get("image_path")
    if image_path:
        if as_image:
            # QImage decodes safely on worker threads (QPixmap does not).
            stage_pix = QImage()
            path = image_store.absolute_path(image_path)
            if path.is_file():
                stage_pix = QImage(str(path))
        else:
            stage_pix = QPixmap()
            path = image_store.absolute_path(image_path)
            if path.is_file():
                stage_pix = QPixmap(str(path))

        if not stage_pix.isNull():
            for row in database.list_character_parts(char_id):
                data = json.loads(row["payload"]) if row["payload"] else {}
                part_name = row["part_name"]

                src_left = int(data.get("left") or data.get("x") or 0)
                src_top = int(data.get("top") or data.get("y") or 0)
                w = int(data.get("width") or 0)
                h = int(data.get("height") or 0)

                # Unified draw-order index (same value the Mark tab edits).
                try:
                    layer = int(row["layer_index"])
                except (IndexError, KeyError, TypeError, ValueError):
                    layer = int(data.get("z", 0) or 0)
                result["part_layers"][part_name] = layer

                # Unified lock state (same value the Mark tab edits).
                try:
                    locked = bool(int(row["is_locked"]))
                except (IndexError, KeyError, TypeError, ValueError):
                    locked = bool(data.get("locked", False))
                result["part_locks"][part_name] = locked

                # Hide/show flag - the very same state the Mark tab toggles.
                result["part_visible"][part_name] = bool(data.get("visible", True))

                if w <= 0 or h <= 0:
                    continue

                crop = stage_pix.copy(src_left, src_top, w, h)
                if not crop.isNull():
                    result["part_crops"][part_name] = crop

    # 3. Load skeleton bone images (attached images per bone with offsets)
    bone_ids = list(result["bone_id_to_name"].keys())
    if bone_ids:
        by_bone = database.list_skeleton_bone_images(bone_ids)
        for bone_id, records in by_bone.items():
            bone_name = result["bone_id_to_name"].get(bone_id)
            if not bone_name:
                continue
            result["bone_images"][bone_name] = [
                {
                    "id": row["id"],
                    "part": row["part_name"],
                    "dx": float(row["image_dx"] or 0.0),
                    "dy": float(row["image_dy"] or 0.0),
                    "index": int(row["image_index"] or 0),
                    "is_locked": bool(row["is_locked"]),
                    # Part-level unified lock (shared with the Mark tab)
                    "part_locked": bool(result["part_locks"].get(row["part_name"], False)),
                    # Part-level hide/show flag (shared with the Mark tab)
                    "part_visible": bool(result["part_visible"].get(row["part_name"], True)),
                }
                for row in records
            ]
        # Build locked_images: {bone_name: set of locked image ids}
        locked_images: dict[str, set[int]] = {}
        for bone_name, records in result["bone_images"].items():
            locked_ids = {rec["id"] for rec in records if rec.get("is_locked", False)}
            if locked_ids:
                locked_images[bone_name] = locked_ids
        result["locked_images"] = locked_images

    return result


def part_draw_key(part_layers: dict, item: tuple[str, dict]) -> tuple:
    """Unified draw-order sort key shared by the Skeleton and Animation tabs.

    Primary sort: the part's layer index (character_parts.layer_index - the
    same index the Mark Character tab edits). The bone-image index, bone
    name and part name are stable tiebreakers (e.g. several image slots of
    the same part attached to one bone).
    """
    bone_name, record = item
    part = record.get("part") or ""
    layer = part_layers.get(part, 0) if part else 0
    try:
        layer = int(layer)
    except (TypeError, ValueError):
        layer = 0
    return (layer, int(record.get("index", 0) or 0), bone_name, part)


def get_ordered_body_parts(
    bone_images: dict, part_crops: dict, part_layers: dict | None = None
) -> list[tuple[str, dict]]:
    """Return all attached body parts sorted by the unified draw order."""
    entries = [
        (bone_name, record)
        for bone_name, records in bone_images.items()
        for record in records
    ]
    return sorted(entries, key=lambda item: part_draw_key(part_layers or {}, item))