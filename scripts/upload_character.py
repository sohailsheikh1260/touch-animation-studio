"""Bulk-upload character images into Touch Animation Studio.

Copies every image found in ``assets/characters`` into the app's ``images``
folder and registers it in the ``characters`` table of ``touch_animation.db``.

All paths are resolved from the project root, so it works no matter which
folder you run it from:

    python scripts/upload_character.py
    uv run python scripts/upload_character.py

Re-runs are safe: names already in the database are skipped, and files an
earlier failed run already copied are adopted instead of duplicated.
"""

import hashlib
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database  # noqa: E402  - project root must be on sys.path first

# Windows consoles often default to a legacy code page (cp1252) that cannot
# print non-ASCII file names — force UTF-8 so odd names can't crash the run.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# --- Configuration (all relative to the project root) ---
SOURCE_DIR = ROOT / "assets" / "characters"  # Folder containing character images to upload
DEST_DIR = ROOT / "images"  # Where the app stores character images on disk
IMAGE_PREFIX = "images"  # Stored in image_path column as "images/xxx.png"

DEFAULT_CHARACTER_TYPE = "human"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _orphaned_dest_files(dest_dir: Path, referenced: set[str]) -> dict[str, str]:
    """Map content hash -> file name for stored files no database row points at.

    Lets a re-run adopt files an earlier (failed) run already copied instead
    of duplicating them on disk.
    """
    orphans: dict[str, str] = {}
    if not dest_dir.is_dir():
        return orphans
    for path in sorted(dest_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if f"{IMAGE_PREFIX}/{path.name}" in referenced:
            continue
        orphans.setdefault(_sha1(path), path.name)
    return orphans


def upload_multiple_characters(
    source_dir: str | Path = SOURCE_DIR,
    character_type: str = DEFAULT_CHARACTER_TYPE,
    mask_id: int | None = None,
    skip_existing: bool = True,
) -> list[dict]:
    """Copy every image from `source_dir` and insert a `characters` row.

    Returns the inserted rows. Names already present are skipped so the
    script can be re-run safely.
    """
    source_dir = Path(source_dir)
    if character_type not in database.CHARACTER_TYPES:
        print(
            f"Unknown character type '{character_type}',"
            f" using '{DEFAULT_CHARACTER_TYPE}'."
            f" Allowed: {', '.join(database.CHARACTER_TYPES)}"
        )
        character_type = DEFAULT_CHARACTER_TYPE

    if not source_dir.is_dir():
        print(f"Source folder not found: {source_dir}")
        return []

    image_files = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not image_files:
        print(f"No supported images found in '{source_dir}'.")
        return []

    DEST_DIR.mkdir(exist_ok=True)

    # The app's own schema/init keeps this script in sync with database.py.
    database.init_db()
    conn = database.get_connection()
    inserted_rows: list[dict] = []
    copied_files: list[Path] = []  # Cleaned up if the transaction fails
    skipped = reused = 0
    skipped_names: list[str] = []

    try:
        existing = {
            row["name"] for row in conn.execute("SELECT name FROM characters")
        }
        referenced = {
            row["image_path"]
            for row in conn.execute("SELECT image_path FROM characters")
        }
        orphans = _orphaned_dest_files(DEST_DIR, referenced)

        mask_data = "{}"
        default_data = "{}"
        if mask_id is not None:
            mask = conn.execute(
                "SELECT mask_data, default_data FROM character_masks WHERE id = ?",
                (int(mask_id),),
            ).fetchone()
            if mask is None:
                raise ValueError(f"Character mask id={mask_id} does not exist.")
            mask_data = mask["mask_data"]
            default_data = mask["default_data"]

        now_iso = _now()
        for source in image_files:
            base_name = source.stem.strip() or uuid.uuid4().hex

            # characters.name is UNIQUE in the app's schema
            if skip_existing and base_name in existing:
                skipped += 1
                if len(skipped_names) < 5:
                    skipped_names.append(base_name)
                continue

            ext = source.suffix.lower()
            if ext == ".jpeg":
                ext = ".jpg"

            # Adopt a file an earlier run already copied when content matches
            stored_name = orphans.pop(_sha1(source), None)
            if stored_name is not None:
                reused += 1
            else:
                stored_name = f"{uuid.uuid4().hex}{ext}"
                shutil.copy2(source, DEST_DIR / stored_name)
                copied_files.append(DEST_DIR / stored_name)

            image_path = f"{IMAGE_PREFIX}/{stored_name}"
            cursor = conn.execute(
                """
                INSERT INTO characters (
                    name,
                    image_path,
                    character_type,
                    mask_id,
                    mask_data,
                    default_data,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    base_name,
                    image_path,
                    character_type,
                    mask_id,
                    mask_data,
                    default_data,
                    now_iso,
                    now_iso,
                ),
            )
            existing.add(base_name)
            inserted_rows.append(
                {
                    "id": cursor.lastrowid,
                    "name": base_name,
                    "image_path": image_path,
                    "character_type": character_type,
                    "mask_id": mask_id,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
            )

        conn.commit()
    except Exception:
        conn.rollback()
        # Clean up newly copied files if the transaction rolled back
        for path in copied_files:
            path.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    print(
        f"Done: {len(inserted_rows)} inserted, {skipped} skipped,"
        f" {reused} existing files reused."
    )
    if skipped:
        sample = ", ".join(skipped_names)
        if skipped > len(skipped_names):
            sample += f", ... (+{skipped - len(skipped_names)} more)"
        print(f"Already in database: {sample}")
    return inserted_rows


if __name__ == "__main__":
    results = upload_multiple_characters()
    for row in results[:10]:
        print(
            f"Inserted id={row['id']} | name={row['name']} | "
            f"type={row['character_type']} | path={row['image_path']}"
        )
    if len(results) > 10:
        print(f"... and {len(results) - 10} more characters.")
