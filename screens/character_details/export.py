"""Export helper for character data (parts + animations) to a JSON file."""

import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

import database


def build_character_export(character_id: int) -> dict | None:
    """Collect all data for a character into a dict ready for JSON export."""
    character = database.get_character(character_id)
    if character is None:
        return None
    parts = database.list_character_parts(character_id)
    parts_out = []

    def _layer_of(p) -> int:
        try:
            return int(p["layer_index"])
        except (IndexError, KeyError, TypeError, ValueError):
            return 0

    for p in parts:
        try:
            payload = json.loads(p["payload"]) if p["payload"] else {}
        except Exception:
            payload = {}
        try:
            is_locked = bool(int(p["is_locked"]))
        except (IndexError, KeyError, TypeError, ValueError):
            is_locked = bool(payload.get("locked", False))
        parts_out.append({
            "id": p["id"],
            "part_name": p["part_name"],
            "note": p["note"],
            "layer_index": _layer_of(p),
            "is_locked": is_locked,
            "payload": payload,
            "created_at": p["created_at"],
            "updated_at": p["updated_at"],
        })
    anims = database.list_character_animations(character_id)
    anims_out = []
    for a in anims:
        anims_out.append({
            "id": a["id"],
            "name": a["name"],
            "speed": a["speed"],
            "legAmplitude": a["leg_amplitude"],
            "armAmplitude": a["arm_amplitude"],
            "bobAmount": a["bob_amount"],
            "bobFrequency": a["bob_frequency"],
            "mouthType": a["mouth_type"],
            "browType": a["brow_type"],
            "isTalking": bool(a["is_talking"]),
            "created_at": a["created_at"],
            "updated_at": a["updated_at"],
        })
    return {
        "character": {
            "id": character["id"],
            "name": character["name"],
            "image_path": character["image_path"],
            "created_at": character["created_at"],
            "updated_at": character["updated_at"],
        },
        "parts": parts_out,
        "animations": anims_out,
    }


def import_character_file(character_id: int, path: str) -> dict:
    """Import character parts and animations from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Character JSON must contain an object.")

    part_count = 0
    for p in data.get("parts", []):
        payload = p.get("payload", {})
        payload_dict = payload if isinstance(payload, dict) else {}
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        layer_index = p.get("layer_index")
        if layer_index is None:
            # Legacy exports: derive the layer from the payload "z".
            try:
                layer_index = int(payload_dict.get("z", 0))
            except (ValueError, TypeError):
                layer_index = 0
        is_locked = p.get("is_locked")
        if is_locked is None:
            # Legacy exports: derive the lock from the payload "locked".
            is_locked = bool(payload_dict.get("locked", False))
        database.create_character_part(
            character_id, p.get("part_name", "part"), p.get("note", ""), payload,
            layer_index=layer_index,
            is_locked=bool(is_locked),
        )
        part_count += 1

    animation_count = 0
    for a in data.get("animations", []):
        database.create_character_animation(
            character_id,
            a.get("name", "walk"),
            speed=a.get("speed", 0.07),
            leg_amplitude=a.get("legAmplitude", 25),
            arm_amplitude=a.get("armAmplitude", 18),
            bob_amount=a.get("bobAmount", 12),
            bob_frequency=a.get("bobFrequency", 2),
            mouth_type=a.get("mouthType", "normal"),
            brow_type=a.get("browType", 1),
            is_talking=a.get("isTalking", False),
        )
        animation_count += 1

    return {"parts": part_count, "animations": animation_count}


def import_character(character_id: int, parent=None) -> bool:
    """Open a file dialog and import parts + animations from a JSON file."""
    path, _ = QFileDialog.getOpenFileName(
        parent, "Import character data", "", "JSON files (*.json)"
    )
    if not path:
        return False
    try:
        result = import_character_file(character_id, path)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(parent, "Import failed", str(exc))
        return False
    QMessageBox.information(
        parent,
        "Imported",
        f"Imported from:\n{path}\n\n"
        f"{result['parts']} part(s), {result['animations']} animation(s)",
    )
    return True


def export_character(character_id: int, parent=None) -> bool:
    """Open a save dialog and write the character data to a JSON file."""
    data = build_character_export(character_id)
    if data is None:
        QMessageBox.warning(parent, "Export failed", "Character not found.")
        return False
    default_name = f"{data['character']['name']}_export.json"
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export character data", default_name, "JSON files (*.json)"
    )
    if not path:
        return False
    try:
        Path(path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        QMessageBox.warning(parent, "Export failed", str(exc))
        return False
    QMessageBox.information(parent, "Exported", f"Saved to:\n{path}")
    return True