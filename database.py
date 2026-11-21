"""SQLite database layer for Touch Animation Studio.

The database file (touch_animation.db) is created automatically next to
this file on first run. Uses Python's built-in sqlite3 module.
"""

import json as _json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "touch_animation.db"

# Supported audio categories. Keep this as the single source of truth so the
# UI and the database layer agree on the allowed values.
AUDIO_TYPES = ("effect", "animal", "vehicle", "other", "voice", "dialogs")
AUDIO_SCOPES = ("global", "project")

# Supported character categories, in the order shown in the character drawer.
CHARACTER_TYPES = ("human", "animal", "vehicle", "tool", "birds")

_AUDIOS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS audios (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        audio_type  TEXT NOT NULL DEFAULT 'effect',
        scope       TEXT NOT NULL DEFAULT 'global',
        project_id  INTEGER,
        audio_path  TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
    )
"""

_AUDIOS_UNIQUE_INDEX_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_audios_name_scope"
    " ON audios (name, scope, IFNULL(project_id, 0))"
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    """Open a connection with sensible defaults for the app."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist yet."""
    with closing(get_connection()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                description TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                image_path  TEXT NOT NULL DEFAULT '',
                character_type TEXT NOT NULL DEFAULT 'human',
                mask_id     INTEGER DEFAULT NULL,
                mask_data   TEXT NOT NULL DEFAULT '{}',
                default_data TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_masks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL UNIQUE,
                description  TEXT NOT NULL DEFAULT '',
                mask_data    TEXT NOT NULL DEFAULT '{}',
                default_data TEXT NOT NULL DEFAULT '{}',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_parts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                part_name    TEXT    NOT NULL,
                note         TEXT    NOT NULL DEFAULT '',
                layer_index  INTEGER NOT NULL DEFAULT 0,
                is_locked    INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL,
                FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backgrounds (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                image_path  TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(_AUDIOS_TABLE_SQL)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS markers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                image_path  TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marker_parts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                marker_id    INTEGER NOT NULL,
                part_name    TEXT    NOT NULL,
                note         TEXT    NOT NULL DEFAULT '',
                layer_index  INTEGER NOT NULL DEFAULT 0,
                is_locked    INTEGER NOT NULL DEFAULT 0,
                payload      TEXT    NOT NULL DEFAULT '{}',
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL,
                FOREIGN KEY (marker_id) REFERENCES markers (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skeletons (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                kind        TEXT    NOT NULL,
                asset_kind  TEXT    NOT NULL DEFAULT '',
                asset_id    INTEGER NOT NULL DEFAULT 0,
                track       INTEGER NOT NULL DEFAULT 0,
                animation   TEXT    NOT NULL DEFAULT 'idle',
                text        TEXT    NOT NULL DEFAULT '',
                flip_h      INTEGER NOT NULL DEFAULT 0,
                flip_v      INTEGER NOT NULL DEFAULT 0,
                start       REAL    NOT NULL DEFAULT 0,
                duration    REAL    NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_animations (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id   INTEGER NOT NULL,
                name           TEXT    NOT NULL DEFAULT 'walk',
                speed          REAL    NOT NULL DEFAULT 0.07,
                leg_amplitude  REAL    NOT NULL DEFAULT 25,
                arm_amplitude  REAL    NOT NULL DEFAULT 18,
                bob_amount     REAL    NOT NULL DEFAULT 12,
                bob_frequency  REAL    NOT NULL DEFAULT 2,
                mouth_type     TEXT    NOT NULL DEFAULT 'normal',
                brow_type      INTEGER NOT NULL DEFAULT 1,
                is_talking     INTEGER NOT NULL DEFAULT 0,
                smile_toggle   INTEGER NOT NULL DEFAULT 0,
                angry_toggle   INTEGER NOT NULL DEFAULT 0,
                talk_toggle    INTEGER NOT NULL DEFAULT 0,
                eye_toggle     INTEGER NOT NULL DEFAULT 0,
                left_handle    TEXT    NOT NULL DEFAULT '',
                right_handle   TEXT    NOT NULL DEFAULT '',
                eyebrow        TEXT    NOT NULL DEFAULT '',
                mouth          TEXT    NOT NULL DEFAULT '',
                eye            TEXT    NOT NULL DEFAULT '',
                config         TEXT    NOT NULL DEFAULT '{}',
                created_at     TEXT    NOT NULL,
                updated_at     TEXT    NOT NULL,
                FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_ik_animations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                name         TEXT    NOT NULL DEFAULT 'My Animation',
                anim_type    TEXT    NOT NULL DEFAULT 'Custom',
                duration     REAL    NOT NULL DEFAULT 2.0,
                fps          REAL    NOT NULL DEFAULT 30,
                loop         INTEGER NOT NULL DEFAULT 1,
                speed        REAL    NOT NULL DEFAULT 1.0,
                payload      TEXT    NOT NULL DEFAULT '{}',
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL,
                FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()

        _migrate()


def _migrate() -> None:
    """Move older schemas forward (additive/renaming migrations)."""
    with closing(get_connection()) as conn:
        # audios.image_path -> audio_path
        audio_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(audios)").fetchall()
        ]
        if audio_cols and "audio_path" not in audio_cols and "image_path" in audio_cols:
            conn.execute("ALTER TABLE audios RENAME COLUMN image_path TO audio_path")
            audio_cols = [
                r["name"] for r in conn.execute("PRAGMA table_info(audios)").fetchall()
            ]

        # audios: category + global/project scope. Older rows become global
        # "effect" audio (the only kind the old schema supported).
        if audio_cols and not {"audio_type", "scope", "project_id"}.issubset(audio_cols):
            conn.execute("DROP INDEX IF EXISTS idx_audios_name_scope")
            conn.execute("ALTER TABLE audios RENAME TO audios_legacy")
            conn.execute(_AUDIOS_TABLE_SQL)
            conn.execute(
                "INSERT INTO audios"
                " (id, name, audio_type, scope, project_id, audio_path, created_at, updated_at)"
                " SELECT id, name, 'effect', 'global', NULL, audio_path, created_at, updated_at"
                " FROM audios_legacy"
            )
            conn.execute("DROP TABLE audios_legacy")
        conn.execute(_AUDIOS_UNIQUE_INDEX_SQL)

        # projects: remember the editor screen size (preview stage preset)
        project_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()
        ]
        if project_cols and "screen_preset" not in project_cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN screen_preset TEXT"
                " NOT NULL DEFAULT 'youtube-hd'"
            )
        if project_cols and "screen_width" not in project_cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN screen_width INTEGER NOT NULL DEFAULT 1280"
            )
        if project_cols and "screen_height" not in project_cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN screen_height INTEGER NOT NULL DEFAULT 720"
            )

        # markers: optional image attached to a marker
        marker_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(markers)").fetchall()
        ]
        if marker_cols and "image_path" not in marker_cols:
            conn.execute(
                "ALTER TABLE markers ADD COLUMN image_path TEXT NOT NULL DEFAULT ''"
            )

        # clips: add track column for multi-row timelines
        clip_cols = [r["name"] for r in conn.execute("PRAGMA table_info(clips)").fetchall()]
        if clip_cols and "track" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN track INTEGER NOT NULL DEFAULT 0")
        if clip_cols and "animation" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN animation TEXT NOT NULL DEFAULT 'idle'")
        if clip_cols and "x_offset" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN x_offset REAL NOT NULL DEFAULT 0")
        if clip_cols and "y_offset" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN y_offset REAL NOT NULL DEFAULT 0")
        if clip_cols and "size_scale" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN size_scale REAL NOT NULL DEFAULT 1")
        if clip_cols and "x_end" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN x_end REAL")
        if clip_cols and "y_end" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN y_end REAL")
        if clip_cols and "anim_speed" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN anim_speed REAL NOT NULL DEFAULT 1")
        if clip_cols and "zoom_start" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN zoom_start REAL NOT NULL DEFAULT 1")
        if clip_cols and "zoom_end" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN zoom_end REAL")
        if clip_cols and "text" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN text TEXT NOT NULL DEFAULT ''")
        if clip_cols and "flip_h" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN flip_h INTEGER NOT NULL DEFAULT 0")
        if clip_cols and "flip_v" not in clip_cols:
            conn.execute("ALTER TABLE clips ADD COLUMN flip_v INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        # character_parts: add JSON payload column for x/y/width/height annotations
        part_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(character_parts)").fetchall()
        ]
        if part_cols and "payload" not in part_cols:
            conn.execute(
                "ALTER TABLE character_parts ADD COLUMN payload TEXT NOT NULL DEFAULT '{}'"
            )
        # characters: add skeleton_id column for skeleton reference
        char_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(characters)").fetchall()
        ]
        if char_cols and "skeleton_id" not in char_cols:
            conn.execute("ALTER TABLE characters ADD COLUMN skeleton_id INTEGER DEFAULT NULL")
        if char_cols and "character_type" not in char_cols:
            conn.execute(
                "ALTER TABLE characters ADD COLUMN character_type TEXT NOT NULL DEFAULT 'human'"
            )
        if char_cols and "mask_id" not in char_cols:
            conn.execute("ALTER TABLE characters ADD COLUMN mask_id INTEGER DEFAULT NULL")
        if char_cols and "mask_data" not in char_cols:
            conn.execute("ALTER TABLE characters ADD COLUMN mask_data TEXT NOT NULL DEFAULT '{}'")
        if char_cols and "default_data" not in char_cols:
            conn.execute("ALTER TABLE characters ADD COLUMN default_data TEXT NOT NULL DEFAULT '{}'")
        # character_masks: add data columns to databases created by the first
        # Character Mask Master schema.
        mask_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(character_masks)").fetchall()
        ]
        if mask_cols and "mask_data" not in mask_cols:
            conn.execute("ALTER TABLE character_masks ADD COLUMN mask_data TEXT NOT NULL DEFAULT '{}'")
        if mask_cols and "default_data" not in mask_cols:
            conn.execute("ALTER TABLE character_masks ADD COLUMN default_data TEXT NOT NULL DEFAULT '{}'")
        # character_parts: unified draw-order index shared by the Mark,
        # Skeleton and Animation tabs. Seeded from the legacy payload "z".
        part_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(character_parts)").fetchall()
        ]
        if part_cols and "layer_index" not in part_cols:
            conn.execute(
                "ALTER TABLE character_parts ADD COLUMN layer_index INTEGER NOT NULL DEFAULT 0"
            )
            legacy = conn.execute(
                "SELECT id, payload FROM character_parts"
            ).fetchall()
            for row in legacy:
                try:
                    z = int((_json.loads(row["payload"] or "{}") or {}).get("z", 0))
                except (ValueError, TypeError):
                    z = 0
                if z:
                    conn.execute(
                        "UPDATE character_parts SET layer_index = ? WHERE id = ?",
                        (z, int(row["id"])),
                    )
        # character_parts: unified lock state shared by the Mark, Skeleton
        # and Animation tabs. Seeded from the legacy payload "locked" key.
        part_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(character_parts)").fetchall()
        ]
        if part_cols and "is_locked" not in part_cols:
            conn.execute(
                "ALTER TABLE character_parts ADD COLUMN is_locked INTEGER NOT NULL DEFAULT 0"
            )
            legacy = conn.execute(
                "SELECT id, payload FROM character_parts"
            ).fetchall()
            for row in legacy:
                try:
                    locked = bool((_json.loads(row["payload"] or "{}") or {}).get("locked", False))
                except (ValueError, TypeError):
                    locked = False
                if locked:
                    conn.execute(
                        "UPDATE character_parts SET is_locked = 1 WHERE id = ?",
                        (int(row["id"]),),
                    )
        # character_animations: add mouth/brow/talking columns
        anim_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(character_animations)").fetchall()
        ]
        if anim_cols:
            if "mouth_type" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN mouth_type TEXT NOT NULL DEFAULT 'normal'")
            if "brow_type" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN brow_type INTEGER NOT NULL DEFAULT 1")
            if "is_talking" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN is_talking INTEGER NOT NULL DEFAULT 0")
            if "smile_toggle" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN smile_toggle INTEGER NOT NULL DEFAULT 0")
            if "angry_toggle" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN angry_toggle INTEGER NOT NULL DEFAULT 0")
            if "talk_toggle" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN talk_toggle INTEGER NOT NULL DEFAULT 0")
            if "eye_toggle" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN eye_toggle INTEGER NOT NULL DEFAULT 0")
            if "left_handle" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN left_handle TEXT NOT NULL DEFAULT ''")
            if "right_handle" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN right_handle TEXT NOT NULL DEFAULT ''")
            if "eyebrow" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN eyebrow TEXT NOT NULL DEFAULT ''")
            if "mouth" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN mouth TEXT NOT NULL DEFAULT ''")
            if "eye" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN eye TEXT NOT NULL DEFAULT ''")
            if "config" not in anim_cols:
                conn.execute("ALTER TABLE character_animations ADD COLUMN config TEXT NOT NULL DEFAULT '{}'")
        # skeleton_bones: make character_id nullable and add skeleton_id column for skeleton master templates
        bone_cols = [
            r["name"] for r in conn.execute("PRAGMA table_info(skeleton_bones)").fetchall()
        ]
        if bone_cols:
            # Check if character_id is NOT NULL (old schema) - need to recreate table
            char_id_not_null = any(c["name"] == "character_id" and c["notnull"] == 1 for c in conn.execute("PRAGMA table_info(skeleton_bones)").fetchall())
            if char_id_not_null:
                # Recreate table with nullable character_id and new skeleton_id column
                conn.execute("ALTER TABLE skeleton_bones RENAME TO skeleton_bones_legacy")
                conn.execute(
                    """
                    CREATE TABLE skeleton_bones (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        character_id  INTEGER,
                        skeleton_id   INTEGER,
                        bone_name     TEXT    NOT NULL,
                        parent_name   TEXT    DEFAULT NULL,
                        x_offset      REAL    NOT NULL DEFAULT 0,
                        y_offset      REAL    NOT NULL DEFAULT 0,
                        length        REAL    NOT NULL DEFAULT 50,
                        angle         REAL    NOT NULL DEFAULT 0,
                        z_order       INTEGER NOT NULL DEFAULT 0,
                        image_part    TEXT,
                        image_dx      REAL    NOT NULL DEFAULT 0,
                        image_dy      REAL    NOT NULL DEFAULT 0,
                        image_index   INTEGER NOT NULL DEFAULT 0,
                        is_locked     INTEGER NOT NULL DEFAULT 0,
                        created_at    TEXT    NOT NULL,
                        updated_at    TEXT    NOT NULL,
                        FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE,
                        FOREIGN KEY (skeleton_id)  REFERENCES skeletons (id) ON DELETE CASCADE,
                        CHECK (character_id IS NOT NULL OR skeleton_id IS NOT NULL)
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO skeleton_bones (id, character_id, skeleton_id, bone_name, parent_name, x_offset, y_offset, length, angle, z_order, created_at, updated_at)"
                    " SELECT id, character_id, NULL, bone_name, parent_name, x_offset, y_offset, length, angle, z_order, created_at, updated_at FROM skeleton_bones_legacy"
                )
                conn.execute("DROP TABLE skeleton_bones_legacy")
            elif "skeleton_id" not in bone_cols:
                # Just add skeleton_id column
                conn.execute("ALTER TABLE skeleton_bones ADD COLUMN skeleton_id INTEGER")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_skeleton_bones_skeleton_id "
                    "ON skeleton_bones (skeleton_id)"
                )
        # skeleton_bones: attached body part image and its offset (from character details skeleton tab)
        if bone_cols:
            if "image_part" not in bone_cols:
                conn.execute("ALTER TABLE skeleton_bones ADD COLUMN image_part TEXT")
            if "image_dx" not in bone_cols:
                conn.execute("ALTER TABLE skeleton_bones ADD COLUMN image_dx REAL NOT NULL DEFAULT 0")
            if "image_dy" not in bone_cols:
                conn.execute("ALTER TABLE skeleton_bones ADD COLUMN image_dy REAL NOT NULL DEFAULT 0")
            if "image_index" not in bone_cols:
                conn.execute("ALTER TABLE skeleton_bones ADD COLUMN image_index INTEGER NOT NULL DEFAULT 0")
            if "is_locked" not in bone_cols:
                conn.execute("ALTER TABLE skeleton_bones ADD COLUMN is_locked INTEGER NOT NULL DEFAULT 0")
        # skeleton_bones table for hierarchical skeleton (used by characters AND skeleton masters)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skeleton_bones (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id  INTEGER,
                skeleton_id   INTEGER,
                bone_name     TEXT    NOT NULL,
                parent_name   TEXT    DEFAULT NULL,
                x_offset      REAL    NOT NULL DEFAULT 0,
                y_offset      REAL    NOT NULL DEFAULT 0,
                length        REAL    NOT NULL DEFAULT 50,
                angle         REAL    NOT NULL DEFAULT 0,
                z_order       INTEGER NOT NULL DEFAULT 0,
                image_part    TEXT,
                image_dx      REAL    NOT NULL DEFAULT 0,
                image_dy      REAL    NOT NULL DEFAULT 0,
                image_index   INTEGER NOT NULL DEFAULT 0,
                is_locked     INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL,
                FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE,
                FOREIGN KEY (skeleton_id)  REFERENCES skeletons (id) ON DELETE CASCADE,
                CHECK (character_id IS NOT NULL OR skeleton_id IS NOT NULL)
            )
            """
        )
        # skeleton_bone_images: multiple attached images per bone (replaces the
        # single image_part/image_dx/image_dy/image_index columns on skeleton_bones)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skeleton_bone_images (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                bone_id     INTEGER NOT NULL,
                part_name   TEXT,
                image_dx    REAL    NOT NULL DEFAULT 0,
                image_dy    REAL    NOT NULL DEFAULT 0,
                image_index INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL,
                FOREIGN KEY (bone_id) REFERENCES skeleton_bones (id) ON DELETE CASCADE
            )
            """
        )
        # One-time migration: legacy bones stored a single attached image in
        # their own columns — copy it into the new table
        conn.execute(
            """
            INSERT INTO skeleton_bone_images
                (bone_id, part_name, image_dx, image_dy, image_index, created_at, updated_at)
            SELECT b.id, b.image_part, b.image_dx, b.image_dy, b.image_index, ?, ?
            FROM skeleton_bones b
            WHERE b.image_part IS NOT NULL AND b.image_part != ''
              AND NOT EXISTS (SELECT 1 FROM skeleton_bone_images bi WHERE bi.bone_id = b.id)
            """,
            (_now(), _now()),
        )
        # Per-character skeleton bones: give every character that references a
        # skeleton template its own copy of the template's bones (and attached
        # images), so editing a character never mutates the shared template.
        for row in conn.execute(
            """
            SELECT c.id AS character_id, c.skeleton_id
            FROM characters c
            WHERE c.skeleton_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM skeleton_bones b WHERE b.character_id = c.id
              )
            """
        ).fetchall():
            _copy_skeleton_bones(conn, row["character_id"], row["skeleton_id"])
        conn.commit()


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------
def create_project(name: str, description: str = "") -> sqlite3.Row:
    """Create a project. Raises ValueError if the name is taken/empty."""
    name = name.strip()
    if not name:
        raise ValueError("Project name cannot be empty.")
    now = _now()
    with closing(get_connection()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO projects (name, description, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (name, description.strip(), now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A project named '{name}' already exists.") from exc
        return get_project(cur.lastrowid)


def get_project(project_id: int) -> sqlite3.Row:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()


def list_projects() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()


def rename_project(project_id: int, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Project name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            conn.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, _now(), project_id),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A project named '{new_name}' already exists.") from exc


def update_project(project_id: int, name: str, description: str) -> None:
    """Update a project's name and description together."""
    name = name.strip()
    if not name:
        raise ValueError("Project name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            conn.execute(
                "UPDATE projects SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description.strip(), _now(), project_id),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A project named '{name}' already exists.") from exc


def update_project_screen_size(
    project_id: int, preset_id: str, width: int, height: int
) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE projects SET screen_preset = ?, screen_width = ?, screen_height = ?,"
            " updated_at = ? WHERE id = ?",
            (preset_id, int(width), int(height), _now(), project_id),
        )
        conn.commit()


def delete_project(project_id: int) -> list[sqlite3.Row]:
    """Delete a project and its project-scoped audio rows.

    Returns the deleted project audio rows so the caller can remove their
    files from disk. Global audio is never touched.
    """
    audios = list_audios(project_id=project_id, scope="project")
    with closing(get_connection()) as conn:
        conn.execute(
            "DELETE FROM audios WHERE project_id = ? AND scope = 'project'",
            (project_id,),
        )
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    return audios


# ---------------------------------------------------------------------------
# Clips (timeline) persistence
# ---------------------------------------------------------------------------
def save_clips(project_id: int, clips: list[tuple]) -> None:
    """Replace all timeline clips of a project.

    Each clip tuple: (kind, asset_kind, asset_id, start, duration, track, animation)
    plus optional (x_offset, y_offset) for on-stage positioning:
        kind        -> "scene" | "audio"
        asset_kind  -> "background" | "character" | "audio"
        asset_id    -> db id of the media row
        start       -> timeline start (seconds)
        duration    -> clip duration (seconds)
        track       -> track/row index (scene tracks 0..N; audio = 0)
        animation   -> animation name for character clips (default 'idle')
        x_offset    -> stage-space X offset for character clips (default 0)
        y_offset    -> stage-space Y offset for character clips (default 0)
        flip_h/flip_v -> mirror flags for character clips (default False)
    """
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM clips WHERE project_id = ?", (project_id,))
        rows = []
        for c in clips:
            text = str(c[15]) if len(c) >= 16 else ""
            flip_h = flip_v = False
            if len(c) == 5:
                kind, asset_kind, asset_id, start, duration = c
                track = 0
                animation = "idle"
                x_offset = 0.0
                y_offset = 0.0
            elif len(c) == 6:
                kind, asset_kind, asset_id, start, duration, track = c
                animation = "idle"
                x_offset = 0.0
                y_offset = 0.0
            else:
                kind, asset_kind, asset_id, start, duration, track, animation = c[:7]
                x_offset = float(c[7]) if len(c) >= 9 else 0.0
                y_offset = float(c[8]) if len(c) >= 9 else 0.0
                size_scale = float(c[9]) if len(c) >= 10 else 1.0
                x_end = float(c[10]) if len(c) >= 12 and c[10] is not None else None
                y_end = float(c[11]) if len(c) >= 12 and c[11] is not None else None
                anim_speed = float(c[12]) if len(c) >= 13 else 1.0
                zoom_start = float(c[13]) if len(c) >= 15 else 1.0
                zoom_end = float(c[14]) if len(c) >= 15 and c[14] is not None else None
                flip_h = bool(c[16]) if len(c) >= 17 else False
                flip_v = bool(c[17]) if len(c) >= 18 else False
            rows.append(
                (
                    project_id,
                    kind,
                    asset_kind,
                    int(asset_id),
                    int(track),
                    str(animation or "idle"),
                    text,
                    float(start),
                    float(duration),
                    float(x_offset),
                    float(y_offset),
                    float(size_scale),
                    x_end,
                    y_end,
                    float(anim_speed),
                    float(zoom_start),
                    zoom_end,
                    int(flip_h),
                    int(flip_v),
                    _now(),
                    _now(),
                )
            )
        conn.executemany(
            "INSERT INTO clips (project_id, kind, asset_kind, asset_id, track, animation,"
            " text, start, duration, x_offset, y_offset, size_scale, x_end, y_end, anim_speed,"
            " zoom_start, zoom_end, flip_h, flip_v, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


def list_clips(project_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM clips WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()


def delete_clips_by_project(project_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM clips WHERE project_id = ?", (project_id,))
        conn.commit()


def count_projects() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()
        return row["n"]


# ---------------------------------------------------------------------------
# Characters CRUD
# ---------------------------------------------------------------------------
def _normalise_character_type(character_type: str | None) -> str:
    value = (character_type or "human").strip().lower()
    return value if value in CHARACTER_TYPES else "human"


def _normalise_mask_data(value: object, field_name: str = "Mask data") -> str:
    """Validate and serialise a JSON object used by character masks."""
    if value is None or value == "":
        return "{}"
    if isinstance(value, str):
        text = value.strip() or "{}"
        try:
            parsed = _json.loads(text)
        except _json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON.") from exc
    elif isinstance(value, dict):
        parsed = value
    else:
        raise ValueError(f"{field_name} must be a JSON object.")
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return _json.dumps(parsed, ensure_ascii=False, sort_keys=True)


def _assign_character_mask(
    conn: sqlite3.Connection,
    character_id: int,
    mask_id: int | None,
) -> None:
    """Set a character's mask and copy the template data into the character."""
    mask = None
    if mask_id is not None:
        mask = conn.execute(
            "SELECT * FROM character_masks WHERE id = ?", (int(mask_id),)
        ).fetchone()
        if mask is None:
            raise ValueError("Selected character mask does not exist.")

    conn.execute(
        "UPDATE characters SET mask_id = ?, mask_data = ?, default_data = ?,"
        " updated_at = ? WHERE id = ?",
        (
            mask_id,
            mask["mask_data"] if mask is not None else "{}",
            mask["default_data"] if mask is not None else "{}",
            _now(),
            int(character_id),
        ),
    )


def create_character(
    name: str,
    image_path: str = "",
    skeleton_id: int | None = None,
    character_type: str = "human",
    mask_id: int | None = None,
) -> sqlite3.Row:
    """Create a character. Raises ValueError if the name is taken/empty."""
    name = name.strip()
    if not name:
        raise ValueError("Character name cannot be empty.")
    character_type = _normalise_character_type(character_type)
    now = _now()
    with closing(get_connection()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO characters"
                " (name, image_path, skeleton_id, character_type, mask_id, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, image_path, skeleton_id, character_type, mask_id, now, now),
            )
            _assign_character_mask(conn, cur.lastrowid, mask_id)
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A character named '{name}' already exists.") from exc
        if skeleton_id:
            # Give the character its own copy of the template's bones
            copy_skeleton_template_to_character(cur.lastrowid, skeleton_id)
        return get_character(cur.lastrowid)


def get_character(character_id: int) -> sqlite3.Row:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM characters WHERE id = ?", (character_id,)
        ).fetchone()


def list_characters() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM characters ORDER BY updated_at DESC"
        ).fetchall()


def list_characters_with_skeleton() -> list[sqlite3.Row]:
    """List characters that have skeleton bones defined."""
    with closing(get_connection()) as conn:
        return conn.execute(
            """
            SELECT c.id, c.name FROM characters c
            JOIN skeleton_bones sb ON sb.character_id = c.id
            GROUP BY c.id, c.name
            ORDER BY c.name
            """
        ).fetchall()


def rename_character(character_id: int, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Character name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            conn.execute(
                "UPDATE characters SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, _now(), character_id),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A character named '{new_name}' already exists.") from exc


def update_character_image(character_id: int, image_path: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE characters SET image_path = ?, updated_at = ? WHERE id = ?",
            (image_path, _now(), character_id),
        )
        conn.commit()


def update_character_skeleton(character_id: int, skeleton_id: int | None) -> None:
    old = get_character(character_id)
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE characters SET skeleton_id = ?, updated_at = ? WHERE id = ?",
            (skeleton_id, _now(), character_id),
        )
        conn.commit()
    if skeleton_id and (old is None or old["skeleton_id"] != skeleton_id):
        # Re-copy the new template's bones, replacing the previous per-character copy
        copy_skeleton_template_to_character(character_id, skeleton_id, replace=True)


def update_character_type(character_id: int, character_type: str) -> None:
    """Set the character category."""
    character_type = _normalise_character_type(character_type)
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE characters SET character_type = ?, updated_at = ? WHERE id = ?",
            (character_type, _now(), character_id),
        )
        conn.commit()


def assign_character_mask(character_id: int, mask_id: int | None) -> None:
    """Assign a mask template and snapshot its data as the character's default."""
    with closing(get_connection()) as conn:
        _assign_character_mask(conn, character_id, mask_id)
        conn.commit()


def delete_character(character_id: int) -> sqlite3.Row:
    """Delete a character row and return it (so the caller can clean up its image)."""
    row = get_character(character_id)
    if row is None:
        return None
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM characters WHERE id = ?", (character_id,))
        conn.commit()
    return row


# ---------------------------------------------------------------------------
# Character body-parts (annotations) CRUD
# ---------------------------------------------------------------------------
def create_character_part(
    character_id: int,
    part_name: str,
    note: str = "",
    payload: str = "{}",
    layer_index: int | None = None,
    is_locked: bool | None = None,
) -> sqlite3.Row:
    """Add a body-part annotation for a character (name + optional JSON payload).

    `layer_index` is the unified draw-order index shared by the Mark,
    Skeleton and Animation tabs. When omitted it is derived from the legacy
    payload "z" (so imports keep their ordering), defaulting to 0.

    `is_locked` is the unified lock state shared by the same three tabs.
    When omitted it is derived from the legacy payload "locked" key,
    defaulting to unlocked.
    """
    part_name = part_name.strip()
    if not part_name:
        raise ValueError("Part name cannot be empty.")
    if layer_index is None:
        try:
            data = _json.loads(payload) if isinstance(payload, str) else payload
            layer_index = int((data or {}).get("z", 0))
        except (ValueError, TypeError):
            layer_index = 0
    if is_locked is None:
        try:
            data = _json.loads(payload) if isinstance(payload, str) else payload
            is_locked = bool((data or {}).get("locked", False))
        except (ValueError, TypeError):
            is_locked = False
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO character_parts (character_id, part_name, note, layer_index, is_locked, payload, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(character_id), part_name, note.strip(), int(layer_index),
                1 if is_locked else 0, str(payload), now, now,
            ),
        )
        conn.commit()
        return get_character_part(cur.lastrowid)


def get_character_part(part_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_parts WHERE id = ?", (part_id,)
        ).fetchone()


def list_character_parts(character_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_parts WHERE character_id = ? ORDER BY id",
            (int(character_id),),
        ).fetchall()


def update_character_part(
    part_id: int,
    part_name: str,
    note: str = "",
    payload: str = "{}",
    layer_index: int | None = None,
    is_locked: bool | None = None,
) -> None:
    """Update a body part row.

    `layer_index` / `is_locked` are the unified draw-order index and lock
    state shared by the Mark, Skeleton and Animation tabs. When omitted
    (None) the existing column value is left unchanged — the payload's
    legacy "z"/"locked" keys are no longer authoritative.
    """
    part_name = part_name.strip()
    if not part_name:
        raise ValueError("Part name cannot be empty.")
    sets = ["part_name = ?", "note = ?", "payload = ?", "updated_at = ?"]
    params: list = [part_name, note.strip(), str(payload), _now()]
    if layer_index is not None:
        sets.append("layer_index = ?")
        params.append(max(0, int(layer_index)))
    if is_locked is not None:
        sets.append("is_locked = ?")
        params.append(1 if is_locked else 0)
    params.append(int(part_id))
    with closing(get_connection()) as conn:
        conn.execute(
            f"UPDATE character_parts SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Unified part draw-order index (shared by Mark / Skeleton / Animation tabs)
# ---------------------------------------------------------------------------
def set_character_part_layer(part_id: int, layer_index: int) -> None:
    """Set a body part's unified draw-order index (clamped at 0)."""
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE character_parts SET layer_index = ?, updated_at = ? WHERE id = ?",
            (max(0, int(layer_index)), _now(), int(part_id)),
        )
        conn.commit()


def bump_character_part_layer(part_id: int, delta: int) -> int | None:
    """Shift a part's draw-order index by delta; returns the new value."""
    part = get_character_part(part_id)
    if part is None:
        return None
    try:
        current = int(part["layer_index"])
    except (IndexError, KeyError, TypeError):
        current = 0
    new_layer = max(0, current + int(delta))
    if new_layer != current:
        set_character_part_layer(part_id, new_layer)
    return new_layer


def bump_character_part_layer_by_name(
    character_id: int, part_name: str, delta: int
) -> int | None:
    """Shift a part's draw-order index by (character, part name).

    Used by the Skeleton tab, whose bone images reference parts by name.
    Returns the new value, or None when no such part exists.
    """
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT id, layer_index FROM character_parts WHERE character_id = ? AND part_name = ?",
            (int(character_id), str(part_name)),
        ).fetchone()
        if row is None:
            return None
        new_layer = max(0, int(row["layer_index"]) + int(delta))
        conn.execute(
            "UPDATE character_parts SET layer_index = ?, updated_at = ? WHERE id = ?",
            (new_layer, _now(), int(row["id"])),
        )
        conn.commit()
    return new_layer


def get_character_part_layer_by_name(character_id: int, part_name: str) -> int:
    """Layer index for a (character, part name); 0 when unknown."""
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT layer_index FROM character_parts WHERE character_id = ? AND part_name = ?",
            (int(character_id), str(part_name)),
        ).fetchone()
    if row is None:
        return 0
    try:
        return int(row["layer_index"])
    except (TypeError, ValueError):
        return 0


def is_character_part_locked_by_name(character_id: int, part_name: str) -> bool:
    """Lock state for a (character, part name); False when unknown."""
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT is_locked FROM character_parts WHERE character_id = ? AND part_name = ?",
            (int(character_id), str(part_name)),
        ).fetchone()
    if row is None:
        return False
    try:
        return bool(int(row["is_locked"]))
    except (TypeError, ValueError):
        return False


def set_character_part_locked(part_id: int, locked: bool) -> None:
    """Set a body part's unified lock state (shared by all three tabs)."""
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE character_parts SET is_locked = ?, updated_at = ? WHERE id = ?",
            (1 if locked else 0, _now(), int(part_id)),
        )
        conn.commit()


def set_character_part_locked_by_name(
    character_id: int, part_name: str, locked: bool
) -> bool:
    """Set a part's unified lock state by (character, part name).

    Used by the Skeleton tab, whose bone images reference parts by name.
    Returns False when no such part exists.
    """
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT id FROM character_parts WHERE character_id = ? AND part_name = ?",
            (int(character_id), str(part_name)),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE character_parts SET is_locked = ?, updated_at = ? WHERE id = ?",
            (1 if locked else 0, _now(), int(row["id"])),
        )
        conn.commit()
    return True


def set_character_part_visible_by_name(
    character_id: int, part_name: str, visible: bool
) -> bool:
    """Set the Mark tab's hide/show flag (payload "visible") by part name.

    The Skeleton tab shares this exact state, so hiding a part here hides
    it everywhere. All other payload keys (geometry etc.) are preserved.
    Returns False when no such part exists.
    """
    with closing(get_connection()) as conn:
        row = conn.execute(
            "SELECT id, payload FROM character_parts WHERE character_id = ? AND part_name = ?",
            (int(character_id), str(part_name)),
        ).fetchone()
        if row is None:
            return False
        try:
            data = _json.loads(row["payload"] or "{}") or {}
        except (ValueError, TypeError):
            data = {}
        data["visible"] = bool(visible)
        conn.execute(
            "UPDATE character_parts SET payload = ?, updated_at = ? WHERE id = ?",
            (_json.dumps(data), _now(), int(row["id"])),
        )
        conn.commit()
    return True


def delete_character_part(part_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM character_parts WHERE id = ?", (int(part_id),))
        conn.commit()


# ---------------------------------------------------------------------------
# Skeleton bones CRUD
# ---------------------------------------------------------------------------
def create_skeleton_bone(
    character_id: int,
    bone_name: str,
    parent_name: str | None = None,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    length: float = 50.0,
    angle: float = 0.0,
    z_order: int = 0,
) -> sqlite3.Row:
    """Add a bone to the character's skeleton."""
    bone_name = bone_name.strip()
    if not bone_name:
        raise ValueError("Bone name cannot be empty.")
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO skeleton_bones (character_id, bone_name, parent_name, x_offset, y_offset, length, angle, z_order, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(character_id), bone_name, parent_name, float(x_offset), float(y_offset), float(length), float(angle), int(z_order), now, now),
        )
        conn.commit()
        return get_skeleton_bone(cur.lastrowid)


def get_skeleton_bone(bone_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM skeleton_bones WHERE id = ?", (bone_id,)
        ).fetchone()


def list_skeleton_bones(character_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM skeleton_bones WHERE character_id = ? ORDER BY z_order, id",
            (int(character_id),),
        ).fetchall()


def list_skeleton_master_bones(skeleton_id: int) -> list[sqlite3.Row]:
    """List bones for a skeleton master template."""
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM skeleton_bones WHERE skeleton_id = ? ORDER BY z_order, id",
            (int(skeleton_id),),
        ).fetchall()


def _copy_skeleton_bones(
    conn: sqlite3.Connection,
    character_id: int,
    skeleton_id: int,
    replace: bool = False,
) -> int:
    """Copy a skeleton template's bones (and attached images) to a character.

    Bones are stored per character (character_id set, skeleton_id NULL) so a
    character can be edited without touching the shared template. Must be
    called with an open connection; the caller commits.

    Returns the number of bones copied.
    """
    existing = conn.execute(
        "SELECT COUNT(*) FROM skeleton_bones WHERE character_id = ?",
        (int(character_id),),
    ).fetchone()[0]
    if existing:
        if not replace:
            return 0
        conn.execute(
            "DELETE FROM skeleton_bones WHERE character_id = ?", (int(character_id),)
        )
    template_bones = conn.execute(
        "SELECT * FROM skeleton_bones WHERE skeleton_id = ? ORDER BY z_order, id",
        (int(skeleton_id),),
    ).fetchall()
    now = _now()
    copied = 0
    for bone in template_bones:
        cur = conn.execute(
            "INSERT INTO skeleton_bones (character_id, bone_name, parent_name,"
            " x_offset, y_offset, length, angle, z_order, is_locked, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(character_id),
                bone["bone_name"],
                bone["parent_name"],
                float(bone["x_offset"]),
                float(bone["y_offset"]),
                float(bone["length"]),
                float(bone["angle"]),
                int(bone["z_order"]),
                int(bone["is_locked"]) if "is_locked" in bone.keys() else 0,
                now,
                now,
            ),
        )
        new_bone_id = cur.lastrowid
        # Copy attached body-part images so each character owns its parts too
        images = conn.execute(
            "SELECT * FROM skeleton_bone_images WHERE bone_id = ? ORDER BY image_index, id",
            (bone["id"],),
        ).fetchall()
        for img in images:
            conn.execute(
                "INSERT INTO skeleton_bone_images (bone_id, part_name,"
                " image_dx, image_dy, image_index, is_locked, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_bone_id,
                    img["part_name"],
                    float(img["image_dx"]),
                    float(img["image_dy"]),
                    int(img["image_index"]),
                    int(img["is_locked"]) if "is_locked" in img.keys() else 0,
                    now,
                    now,
                ),
            )
        copied += 1
    return copied


def copy_skeleton_template_to_character(
    character_id: int,
    skeleton_id: int,
    replace: bool = False,
) -> int:
    """Copy a skeleton template's bones to a character (see _copy_skeleton_bones)."""
    with closing(get_connection()) as conn:
        copied = _copy_skeleton_bones(conn, character_id, skeleton_id, replace)
        conn.commit()
        return copied


def create_skeleton_master_bone(
    skeleton_id: int,
    bone_name: str,
    parent_name: str | None = None,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    length: float = 50.0,
    angle: float = 0.0,
    z_order: int = 0,
) -> sqlite3.Row:
    """Add a bone to the skeleton master template."""
    bone_name = bone_name.strip()
    if not bone_name:
        raise ValueError("Bone name cannot be empty.")
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO skeleton_bones (skeleton_id, bone_name, parent_name, x_offset, y_offset, length, angle, z_order, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(skeleton_id), bone_name, parent_name, float(x_offset), float(y_offset), float(length), float(angle), int(z_order), now, now),
        )
        conn.commit()
        return get_skeleton_bone(cur.lastrowid)


def update_skeleton_bone(
    bone_id: int,
    bone_name: str,
    parent_name: str | None = None,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    length: float = 50.0,
    angle: float = 0.0,
    z_order: int = 0,
) -> None:
    bone_name = bone_name.strip()
    if not bone_name:
        raise ValueError("Bone name cannot be empty.")
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE skeleton_bones SET bone_name = ?, parent_name = ?, x_offset = ?, y_offset = ?, length = ?, angle = ?, z_order = ?, updated_at = ? WHERE id = ?",
            (bone_name, parent_name, float(x_offset), float(y_offset), float(length), float(angle), int(z_order), _now(), int(bone_id)),
        )
        conn.commit()


def list_skeleton_bone_images(bone_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    """List attached images for the given bones, grouped by bone id."""
    ids = [int(b) for b in bone_ids]
    if not ids:
        return {}
    # Ensure is_locked column exists (migration for existing DBs)
    with closing(get_connection()) as conn:
        col_info = conn.execute(
            "PRAGMA table_info(skeleton_bone_images)"
        ).fetchall()
        col_names = [c[1] for c in col_info]
        if "is_locked" not in col_names:
            conn.execute(
                "ALTER TABLE skeleton_bone_images ADD COLUMN is_locked INTEGER NOT NULL DEFAULT 0"
            )
    placeholders = ",".join("?" * len(ids))
    with closing(get_connection()) as conn:
        rows = conn.execute(
            f"SELECT * FROM skeleton_bone_images WHERE bone_id IN ({placeholders})"
            " ORDER BY bone_id, image_index, id",
            ids,
        ).fetchall()
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["bone_id"], []).append(row)
    return grouped


def add_skeleton_bone_image(
    bone_id: int,
    part_name: str | None = None,
    image_dx: float = 0.0,
    image_dy: float = 0.0,
    image_index: int = 0,
) -> sqlite3.Row:
    """Attach a new image to a bone (a bone can hold multiple images)."""
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO skeleton_bone_images (bone_id, part_name, image_dx, image_dy, image_index, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(bone_id), part_name, float(image_dx), float(image_dy), int(image_index), now, now),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM skeleton_bone_images WHERE id = ?", (cur.lastrowid,)
        ).fetchone()


def update_skeleton_bone_image(
    image_id: int,
    part_name: str | None,
    image_dx: float = 0.0,
    image_dy: float = 0.0,
    image_index: int = 0,
    is_locked: int = 0,
) -> None:
    """Update an attached bone image's part, offset, draw index and lock state."""
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE skeleton_bone_images SET part_name = ?, image_dx = ?, image_dy = ?, image_index = ?, is_locked = ?, updated_at = ? WHERE id = ?",
            (part_name, float(image_dx), float(image_dy), int(image_index), int(is_locked), _now(), int(image_id)),
        )
        conn.commit()


def delete_skeleton_bone_image(image_id: int) -> None:
    """Remove an attached image from its bone."""
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM skeleton_bone_images WHERE id = ?", (int(image_id),))
        conn.commit()


def set_skeleton_bone_locked(bone_id: int, locked: bool) -> None:
    """Lock/unlock a bone so it can't be dragged in the skeleton editor."""
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE skeleton_bones SET is_locked = ?, updated_at = ? WHERE id = ?",
            (1 if locked else 0, _now(), int(bone_id)),
        )
        conn.commit()


def delete_skeleton_bone(bone_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM skeleton_bones WHERE id = ?", (int(bone_id),))
        conn.commit()


# ---------------------------------------------------------------------------
# Character animations CRUD
# ---------------------------------------------------------------------------
def create_character_animation(
    character_id: int,
    name: str = "walk",
    speed: float = 0.07,
    leg_amplitude: float = 25,
    arm_amplitude: float = 18,
    bob_amount: float = 12,
    bob_frequency: float = 2,
    mouth_type: str = "normal",
    brow_type: int = 1,
    is_talking: bool = False,
    smile_toggle: bool = False,
    angry_toggle: bool = False,
    talk_toggle: bool = False,
    eye_toggle: bool = False,
    left_handle: str = "",
    right_handle: str = "",
    eyebrow: str = "",
    mouth: str = "",
    eye: str = "",
    config=None,
) -> sqlite3.Row:
    """Add an animation preset for a character."""
    name = name.strip() or "walk"
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO character_animations"
            " (character_id, name, speed, leg_amplitude, arm_amplitude, bob_amount, bob_frequency, mouth_type, brow_type, is_talking, smile_toggle, angry_toggle, talk_toggle, eye_toggle, left_handle, right_handle, eyebrow, mouth, eye, config, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(character_id), name, float(speed), float(leg_amplitude), float(arm_amplitude),
             float(bob_amount), float(bob_frequency), mouth_type, int(brow_type), 1 if is_talking else 0,
             1 if smile_toggle else 0, 1 if angry_toggle else 0, 1 if talk_toggle else 0, 1 if eye_toggle else 0,
             str(left_handle or ""), str(right_handle or ""), str(eyebrow or ""), str(mouth or ""), str(eye or ""),
             _json.dumps(config) if not isinstance(config, str) else (config or "{}"), now, now),
        )
        conn.commit()
        return get_character_animation(cur.lastrowid)


def get_character_animation(animation_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_animations WHERE id = ?", (int(animation_id),)
        ).fetchone()


def list_character_animations(character_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_animations WHERE character_id = ? ORDER BY id",
            (int(character_id),),
        ).fetchall()


def update_character_animation(
    animation_id: int,
    name: str | None = None,
    speed: float | None = None,
    leg_amplitude: float | None = None,
    arm_amplitude: float | None = None,
    bob_amount: float | None = None,
    bob_frequency: float | None = None,
    mouth_type: str | None = None,
    brow_type: int | None = None,
    is_talking: bool | None = None,
    smile_toggle: bool | None = None,
    angry_toggle: bool | None = None,
    talk_toggle: bool | None = None,
    eye_toggle: bool | None = None,
    left_handle: str | None = None,
    right_handle: str | None = None,
    eyebrow: str | None = None,
    mouth: str | None = None,
    eye: str | None = None,
    config=None,
) -> None:
    """Update one or more fields of an animation preset."""
    fields = []
    values = []
    if name is not None:
        fields.append("name = ?")
        values.append(name.strip() or "walk")
    if speed is not None:
        fields.append("speed = ?")
        values.append(float(speed))
    if leg_amplitude is not None:
        fields.append("leg_amplitude = ?")
        values.append(float(leg_amplitude))
    if arm_amplitude is not None:
        fields.append("arm_amplitude = ?")
        values.append(float(arm_amplitude))
    if bob_amount is not None:
        fields.append("bob_amount = ?")
        values.append(float(bob_amount))
    if bob_frequency is not None:
        fields.append("bob_frequency = ?")
        values.append(float(bob_frequency))
    if mouth_type is not None:
        fields.append("mouth_type = ?")
        values.append(mouth_type)
    if brow_type is not None:
        fields.append("brow_type = ?")
        values.append(int(brow_type))
    if is_talking is not None:
        fields.append("is_talking = ?")
        values.append(1 if is_talking else 0)
    if smile_toggle is not None:
        fields.append("smile_toggle = ?")
        values.append(1 if smile_toggle else 0)
    if angry_toggle is not None:
        fields.append("angry_toggle = ?")
        values.append(1 if angry_toggle else 0)
    if talk_toggle is not None:
        fields.append("talk_toggle = ?")
        values.append(1 if talk_toggle else 0)
    if eye_toggle is not None:
        fields.append("eye_toggle = ?")
        values.append(1 if eye_toggle else 0)
    if left_handle is not None:
        fields.append("left_handle = ?")
        values.append(str(left_handle))
    if right_handle is not None:
        fields.append("right_handle = ?")
        values.append(str(right_handle))
    if eyebrow is not None:
        fields.append("eyebrow = ?")
        values.append(str(eyebrow))
    if mouth is not None:
        fields.append("mouth = ?")
        values.append(str(mouth))
    if eye is not None:
        fields.append("eye = ?")
        values.append(str(eye))
    if config is not None:
        fields.append("config = ?")
        values.append(_json.dumps(config) if not isinstance(config, str) else (config or "{}"))
    if not fields:
        return
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(int(animation_id))
    with closing(get_connection()) as conn:
        conn.execute(
            f"UPDATE character_animations SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()


def delete_character_animation(animation_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM character_animations WHERE id = ?", (int(animation_id),))
        conn.commit()


# ---------------------------------------------------------------------------
# Character IK animations CRUD (keyframe animations for the Animation tab)
# ---------------------------------------------------------------------------
def create_character_ik_animation(
    character_id: int,
    name: str = "My Animation",
    anim_type: str = "Custom",
    duration: float = 2.0,
    fps: float = 30.0,
    loop: bool = True,
    speed: float = 1.0,
    payload: dict | list | None = None,
) -> int:
    """Create a keyframe animation and return its id."""
    now = _now()
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO character_ik_animations
                (character_id, name, anim_type, duration, fps, loop, speed,
                 payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(character_id),
                str(name),
                str(anim_type),
                float(duration),
                float(fps),
                1 if loop else 0,
                float(speed),
                _json.dumps(payload if payload is not None else {}),
                now,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_character_ik_animation(animation_id: int) -> sqlite3.Row | None:
    """Return one IK animation row, or None."""
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_ik_animations WHERE id = ?",
            (int(animation_id),),
        ).fetchone()


def list_character_ik_animations(character_id: int) -> list[sqlite3.Row]:
    """All IK animations of a character, oldest first."""
    with closing(get_connection()) as conn:
        return conn.execute(
            """
            SELECT * FROM character_ik_animations
            WHERE character_id = ?
            ORDER BY id
            """,
            (int(character_id),),
        ).fetchall()


def update_character_ik_animation(
    animation_id: int,
    name: str,
    anim_type: str,
    duration: float,
    fps: float,
    loop: bool,
    speed: float,
    payload: dict | list | None = None,
) -> None:
    """Update an IK animation's settings and keyframe payload."""
    with closing(get_connection()) as conn:
        conn.execute(
            """
            UPDATE character_ik_animations
            SET name = ?, anim_type = ?, duration = ?, fps = ?, loop = ?,
                speed = ?, payload = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(name),
                str(anim_type),
                float(duration),
                float(fps),
                1 if loop else 0,
                float(speed),
                _json.dumps(payload if payload is not None else {}),
                _now(),
                int(animation_id),
            ),
        )
        conn.commit()


def delete_character_ik_animation(animation_id: int) -> None:
    """Delete an IK animation row."""
    with closing(get_connection()) as conn:
        conn.execute(
            "DELETE FROM character_ik_animations WHERE id = ?", (int(animation_id),)
        )
        conn.commit()


def count_character_ik_animations(character_id: int | None = None) -> int:
    with closing(get_connection()) as conn:
        if character_id is None:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM character_ik_animations"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM character_ik_animations WHERE character_id = ?",
                (int(character_id),),
            ).fetchone()
        return int(row["n"])


# ---------------------------------------------------------------------------
# Backgrounds CRUD
# ---------------------------------------------------------------------------
def create_background(name: str, image_path: str = "") -> sqlite3.Row:
    """Create a background. Raises ValueError if the name is taken/empty."""
    name = name.strip()
    if not name:
        raise ValueError("Background name cannot be empty.")
    now = _now()
    with closing(get_connection()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO backgrounds (name, image_path, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (name, image_path, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A background named '{name}' already exists.") from exc
        return get_background(cur.lastrowid)


def get_background(background_id: int) -> sqlite3.Row:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM backgrounds WHERE id = ?", (background_id,)
        ).fetchone()


def list_backgrounds() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM backgrounds ORDER BY updated_at DESC"
        ).fetchall()


def rename_background(background_id: int, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Background name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            conn.execute(
                "UPDATE backgrounds SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, _now(), background_id),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A background named '{new_name}' already exists.") from exc


def update_background_image(background_id: int, image_path: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE backgrounds SET image_path = ?, updated_at = ? WHERE id = ?",
            (image_path, _now(), background_id),
        )
        conn.commit()


def delete_background(background_id: int) -> sqlite3.Row:
    """Delete a background row and return it (so the caller can clean up its image)."""
    row = get_background(background_id)
    if row is None:
        return None
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM backgrounds WHERE id = ?", (background_id,))
        conn.commit()
    return row


def count_characters() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM characters").fetchone()
        return row["n"]


def count_backgrounds() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM backgrounds").fetchone()
        return row["n"]


# ---------------------------------------------------------------------------
# Audios CRUD
# ---------------------------------------------------------------------------
def _normalise_audio_type(audio_type: str | None) -> str:
    value = (audio_type or "effect").strip().lower()
    return value if value in AUDIO_TYPES else "other"


def _normalise_audio_scope(
    scope: str | None, project_id: int | None
) -> tuple[str, int | None]:
    """Return a valid (scope, project_id) pair.

    Project audio always has a project id; global audio never does.
    """
    value = (scope or "").strip().lower()
    if value == "project":
        if project_id is None:
            raise ValueError("Choose a project for project audio.")
        return "project", int(project_id)
    if project_id is not None:
        return "project", int(project_id)
    return "global", None


def _audio_name_taken(
    conn: sqlite3.Connection,
    name: str,
    scope: str,
    project_id: int | None,
    exclude_id: int | None = None,
) -> bool:
    sql = "SELECT id FROM audios WHERE name = ? AND scope = ?"
    params: list = [name, scope]
    if scope == "project":
        sql += " AND project_id = ?"
        params.append(project_id)
    else:
        sql += " AND project_id IS NULL"
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(int(exclude_id))
    return conn.execute(sql, params).fetchone() is not None


def create_audio(
    name: str,
    audio_path: str = "",
    audio_type: str = "effect",
    scope: str = "global",
    project_id: int | None = None,
) -> sqlite3.Row:
    """Create an audio. Raises ValueError if the name is taken/empty."""
    name = name.strip()
    if not name:
        raise ValueError("Audio name cannot be empty.")
    audio_type = _normalise_audio_type(audio_type)
    scope, project_id = _normalise_audio_scope(scope, project_id)
    now = _now()
    with closing(get_connection()) as conn:
        if project_id is not None and conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone() is None:
            raise ValueError("The selected project no longer exists.")
        if _audio_name_taken(conn, name, scope, project_id):
            raise ValueError(
                f"An audio named '{name}' already exists in this library."
            )
        try:
            cur = conn.execute(
                "INSERT INTO audios"
                " (name, audio_type, scope, project_id, audio_path, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, audio_type, scope, project_id, audio_path, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"An audio named '{name}' already exists in this library."
            ) from exc
        return get_audio(cur.lastrowid)


def get_audio(audio_id: int) -> sqlite3.Row:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM audios WHERE id = ?", (audio_id,)
        ).fetchone()


def list_audios(
    project_id: int | None = None,
    scope: str | None = None,
    audio_type: str | None = None,
) -> list[sqlite3.Row]:
    """List audio rows.

    - scope="global": global audio only.
    - scope="project" + project_id: that project's audio only.
    - project_id only: global audio plus that project's audio (usable in the
      project editor).
    - no filters: everything (the "All audio" library view).
    """
    clauses: list[str] = []
    params: list = []
    scope = (scope or "").strip().lower()
    if scope == "global":
        clauses.append("scope = 'global'")
    elif scope == "project":
        clauses.append("scope = 'project'")
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(int(project_id))
    elif project_id is not None:
        clauses.append("(scope = 'global' OR (scope = 'project' AND project_id = ?))")
        params.append(int(project_id))

    if audio_type and audio_type not in ("all", ""):
        audio_type = _normalise_audio_type(audio_type)
        clauses.append("audio_type = ?")
        params.append(audio_type)

    sql = "SELECT * FROM audios"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY updated_at DESC, id DESC"
    with closing(get_connection()) as conn:
        return conn.execute(sql, params).fetchall()


def list_audios_for_project(project_id: int) -> list[sqlite3.Row]:
    """Global audio plus the given project's audio (what the editor can use)."""
    return list_audios(project_id=project_id)


def list_project_audios(project_id: int) -> list[sqlite3.Row]:
    """Only the given project's audio (never global audio)."""
    return list_audios(project_id=project_id, scope="project")


def rename_audio(audio_id: int, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Audio name cannot be empty.")
    row = get_audio(audio_id)
    if row is None:
        return
    scope = row["scope"] if "scope" in row.keys() else "global"
    project_id = row["project_id"] if "project_id" in row.keys() else None
    with closing(get_connection()) as conn:
        if _audio_name_taken(conn, new_name, scope, project_id, exclude_id=audio_id):
            raise ValueError(
                f"An audio named '{new_name}' already exists in this library."
            )
        try:
            conn.execute(
                "UPDATE audios SET name = ?, updated_at = ? WHERE id = ?",
                (new_name, _now(), audio_id),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"An audio named '{new_name}' already exists in this library."
            ) from exc


def update_audio(
    audio_id: int,
    name: str,
    audio_type: str = "effect",
    scope: str = "global",
    project_id: int | None = None,
    audio_path: str | None = None,
) -> None:
    """Update an audio's name, category and library (global/project) in one go."""
    name = name.strip()
    if not name:
        raise ValueError("Audio name cannot be empty.")
    audio_type = _normalise_audio_type(audio_type)
    scope, project_id = _normalise_audio_scope(scope, project_id)
    if get_audio(audio_id) is None:
        raise ValueError("Audio not found.")
    with closing(get_connection()) as conn:
        if project_id is not None and conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone() is None:
            raise ValueError("The selected project no longer exists.")
        if _audio_name_taken(conn, name, scope, project_id, exclude_id=audio_id):
            raise ValueError(
                f"An audio named '{name}' already exists in this library."
            )
        fields = [
            "name = ?",
            "audio_type = ?",
            "scope = ?",
            "project_id = ?",
            "updated_at = ?",
        ]
        values: list = [name, audio_type, scope, project_id, _now()]
        if audio_path is not None:
            fields.append("audio_path = ?")
            values.append(audio_path)
        values.append(int(audio_id))
        try:
            conn.execute(
                f"UPDATE audios SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"An audio named '{name}' already exists in this library."
            ) from exc


def update_audio_file(audio_id: int, audio_path: str) -> None:
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE audios SET audio_path = ?, updated_at = ? WHERE id = ?",
            (audio_path, _now(), audio_id),
        )
        conn.commit()


def delete_audio(audio_id: int) -> sqlite3.Row:
    """Delete an audio row and return it (so the caller can clean up its file)."""
    row = get_audio(audio_id)
    if row is None:
        return None
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM audios WHERE id = ?", (audio_id,))
        conn.commit()
    return row


def delete_audios_by_project(project_id: int) -> list[sqlite3.Row]:
    """Delete all project-scoped audio rows for a project (global stays)."""
    rows = list_project_audios(project_id)
    with closing(get_connection()) as conn:
        conn.execute(
            "DELETE FROM audios WHERE project_id = ? AND scope = 'project'",
            (int(project_id),),
        )
        conn.commit()
    return rows


def count_audios() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audios").fetchone()
        return row["n"]


# ---------------------------------------------------------------------------
# Markers CRUD (simple name + description)
# ---------------------------------------------------------------------------


def create_marker(name: str, description: str = "", image_path: str = "") -> sqlite3.Row:
    """Create a marker. Raises ValueError if the name is taken/empty."""
    name = name.strip()
    if not name:
        raise ValueError("Marker name cannot be empty.")
    now = _now()
    with closing(get_connection()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO markers (name, description, image_path, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (name, description.strip(), image_path.strip(), now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A marker named '{name}' already exists.") from exc
        return get_marker(cur.lastrowid)


def get_marker(marker_id: int) -> sqlite3.Row:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM markers WHERE id = ?", (marker_id,)
        ).fetchone()


def list_markers() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM markers ORDER BY updated_at DESC"
        ).fetchall()


def update_marker(
    marker_id: int,
    name: str,
    description: str,
    image_path: str | None = None,
) -> None:
    """Update a marker's name/description (and optionally its image).

    Pass image_path=None to keep the current image, "" to clear it.
    """
    name = name.strip()
    if not name:
        raise ValueError("Marker name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            if image_path is None:
                conn.execute(
                    "UPDATE markers SET name = ?, description = ?, updated_at = ?"
                    " WHERE id = ?",
                    (name, description.strip(), _now(), marker_id),
                )
            else:
                conn.execute(
                    "UPDATE markers SET name = ?, description = ?, image_path = ?,"
                    " updated_at = ? WHERE id = ?",
                    (name, description.strip(), image_path.strip(), _now(), marker_id),
                )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A marker named '{name}' already exists.") from exc


def delete_marker(marker_id: int) -> sqlite3.Row:
    """Delete a marker row (and its markup boxes) and return it."""
    row = get_marker(marker_id)
    if row is None:
        return None
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM marker_parts WHERE marker_id = ?", (int(marker_id),))
        conn.execute("DELETE FROM markers WHERE id = ?", (marker_id,))
        conn.commit()
    return row


def count_markers() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM markers").fetchone()
        return row["n"]


# ---------------------------------------------------------------------------
# Marker body-parts (markup boxes) CRUD - mirrors character_parts
# ---------------------------------------------------------------------------


def create_marker_part(
    marker_id: int,
    part_name: str,
    note: str = "",
    payload: str = "{}",
    layer_index: int | None = None,
    is_locked: bool | None = None,
) -> sqlite3.Row:
    """Add a markup box for a marker (name + JSON payload).

    `layer_index` is the draw-order index (derived from the payload "z" when
    omitted, so imports keep their ordering). `is_locked` follows the same
    rule from the payload's "locked" key.
    """
    part_name = part_name.strip()
    if not part_name:
        raise ValueError("Part name cannot be empty.")
    if layer_index is None:
        try:
            data = _json.loads(payload) if isinstance(payload, str) else payload
            layer_index = int((data or {}).get("z", 0))
        except (ValueError, TypeError):
            layer_index = 0
    if is_locked is None:
        try:
            data = _json.loads(payload) if isinstance(payload, str) else payload
            is_locked = bool((data or {}).get("locked", False))
        except (ValueError, TypeError):
            is_locked = False
    now = _now()
    with closing(get_connection()) as conn:
        cur = conn.execute(
            "INSERT INTO marker_parts (marker_id, part_name, note, layer_index,"
            " is_locked, payload, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                int(marker_id), part_name, note.strip(), int(layer_index),
                1 if is_locked else 0, str(payload), now, now,
            ),
        )
        conn.commit()
        return get_marker_part(cur.lastrowid)


def get_marker_part(part_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM marker_parts WHERE id = ?", (int(part_id),)
        ).fetchone()


def list_marker_parts(marker_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM marker_parts WHERE marker_id = ? ORDER BY id",
            (int(marker_id),),
        ).fetchall()


def update_marker_part(
    part_id: int,
    part_name: str,
    note: str = "",
    payload: str = "{}",
    layer_index: int | None = None,
    is_locked: bool | None = None,
) -> None:
    """Update a marker markup box.

    `layer_index` / `is_locked` are left unchanged when passed as None.
    """
    part_name = part_name.strip()
    if not part_name:
        raise ValueError("Part name cannot be empty.")
    sets = ["part_name = ?", "note = ?", "payload = ?", "updated_at = ?"]
    params: list = [part_name, note.strip(), str(payload), _now()]
    if layer_index is not None:
        sets.append("layer_index = ?")
        params.append(max(0, int(layer_index)))
    if is_locked is not None:
        sets.append("is_locked = ?")
        params.append(1 if is_locked else 0)
    params.append(int(part_id))
    with closing(get_connection()) as conn:
        conn.execute(
            f"UPDATE marker_parts SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()


def set_marker_part_layer(part_id: int, layer_index: int) -> None:
    """Set a marker box's draw-order index (clamped at 0)."""
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE marker_parts SET layer_index = ?, updated_at = ? WHERE id = ?",
            (max(0, int(layer_index)), _now(), int(part_id)),
        )
        conn.commit()


def bump_marker_part_layer(part_id: int, delta: int) -> int | None:
    """Shift a marker box's draw-order index by delta; returns the new value."""
    part = get_marker_part(part_id)
    if part is None:
        return None
    try:
        current = int(part["layer_index"])
    except (IndexError, KeyError, TypeError, ValueError):
        current = 0
    new_layer = max(0, current + int(delta))
    if new_layer != current:
        set_marker_part_layer(part_id, new_layer)
    return new_layer


def set_marker_part_locked(part_id: int, locked: bool) -> None:
    """Set a marker box's lock state."""
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE marker_parts SET is_locked = ?, updated_at = ? WHERE id = ?",
            (1 if locked else 0, _now(), int(part_id)),
        )
        conn.commit()


def delete_marker_part(part_id: int) -> None:
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM marker_parts WHERE id = ?", (int(part_id),))
        conn.commit()


def delete_marker_parts_by_marker(marker_id: int) -> None:
    """Drop every markup box of a marker (used when the marker goes away)."""
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM marker_parts WHERE marker_id = ?", (int(marker_id),))
        conn.commit()


# ---------------------------------------------------------------------------
# Skeletons CRUD (simple name-based)
# ---------------------------------------------------------------------------

DEFAULT_BONES = [
    # (bone_name, parent_name, x_offset, y_offset, length, angle, z_order)
    # Root
    ("torso", None, 0, 0, 100, 0, 0),
    # Head
    ("head", "torso", 0, -180, 80, 0, 1),
    # Left arm
    ("left_shoulder", "torso", -40, -80, 10, 0, 2),
    ("left_elbow", "left_shoulder", 0, 50, 50, 0, 3),
    ("left_wrist", "left_elbow", 0, 50, 50, 0, 4),
    # Right arm
    ("right_shoulder", "torso", 40, -80, 10, 0, 2),
    ("right_elbow", "right_shoulder", 0, 50, 50, 0, 3),
    ("right_wrist", "right_elbow", 0, 50, 50, 0, 4),
    # Left leg
    ("left_hip", "torso", -20, 20, 10, 0, 2),
    ("left_knee", "left_hip", 0, 70, 70, 0, 3),
    ("left_ankle", "left_knee", 0, 70, 70, 0, 4),
    # Right leg
    ("right_hip", "torso", 20, 20, 10, 0, 2),
    ("right_knee", "right_hip", 0, 70, 70, 0, 3),
    ("right_ankle", "right_knee", 0, 70, 70, 0, 4),
]


def create_skeleton(name: str, description: str = "", with_default_bones: bool = True) -> sqlite3.Row:
    """Create a skeleton. Raises ValueError if the name is taken/empty.
    
    If with_default_bones is True (default), creates a standard humanoid bone hierarchy.
    """
    name = name.strip()
    if not name:
        raise ValueError("Skeleton name cannot be empty.")
    now = _now()
    with closing(get_connection()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO skeletons (name, description, created_at, updated_at)"
                " VALUES (?, ?, ?, ?)",
                (name, description.strip(), now, now),
            )
            skeleton_id = cur.lastrowid
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A skeleton named '{name}' already exists.") from exc

        # Create default bones for the new skeleton
        if with_default_bones:
            for bone_name, parent_name, x_off, y_off, length, angle, z_order in DEFAULT_BONES:
                conn.execute(
                    "INSERT INTO skeleton_bones (skeleton_id, bone_name, parent_name, x_offset, y_offset, length, angle, z_order, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (skeleton_id, bone_name, parent_name, float(x_off), float(y_off), float(length), float(angle), int(z_order), now, now),
                )
            conn.commit()

        return get_skeleton(skeleton_id)


def get_skeleton(skeleton_id: int) -> sqlite3.Row:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM skeletons WHERE id = ?", (skeleton_id,)
        ).fetchone()


def list_skeletons() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM skeletons ORDER BY updated_at DESC"
        ).fetchall()


def update_skeleton(skeleton_id: int, name: str, description: str) -> None:
    """Update a skeleton's name and description together."""
    name = name.strip()
    if not name:
        raise ValueError("Skeleton name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            conn.execute(
                "UPDATE skeletons SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description.strip(), _now(), skeleton_id),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A skeleton named '{name}' already exists.") from exc


def delete_skeleton(skeleton_id: int) -> sqlite3.Row:
    """Delete a skeleton row and return it."""
    row = get_skeleton(skeleton_id)
    if row is None:
        return None
    with closing(get_connection()) as conn:
        conn.execute("DELETE FROM skeletons WHERE id = ?", (skeleton_id,))
        conn.commit()
    return row


def count_skeletons() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM skeletons").fetchone()
        return row["n"]


# ---------------------------------------------------------------------------
# Character mask masters CRUD
# ---------------------------------------------------------------------------
def create_character_mask(
    name: str,
    description: str = "",
    mask_data: object = None,
    default_data: object = None,
) -> sqlite3.Row:
    """Create a reusable character mask template."""
    name = name.strip()
    if not name:
        raise ValueError("Mask name cannot be empty.")
    mask_data = _normalise_mask_data(mask_data, "Mask data")
    default_data = _normalise_mask_data(default_data, "Default data")
    now = _now()
    with closing(get_connection()) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO character_masks"
                " (name, description, mask_data, default_data, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (name, description.strip(), mask_data, default_data, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A mask named '{name}' already exists.") from exc
    return get_character_mask(cur.lastrowid)


def get_character_mask(mask_id: int) -> sqlite3.Row | None:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_masks WHERE id = ?", (int(mask_id),)
        ).fetchone()


def list_character_masks() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM character_masks ORDER BY updated_at DESC"
        ).fetchall()


def update_character_mask(
    mask_id: int,
    name: str,
    description: str = "",
) -> None:
    """Update a mask template's name and description."""
    name = name.strip()
    if not name:
        raise ValueError("Mask name cannot be empty.")
    with closing(get_connection()) as conn:
        try:
            conn.execute(
                "UPDATE character_masks"
                " SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (name, description.strip(), _now(), int(mask_id)),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"A mask named '{name}' already exists.") from exc


def update_character_mask_data(
    mask_id: int,
    mask_data: object,
    default_data: object,
) -> None:
    """Update the reusable data and defaults stored by a mask template."""
    mask_data = _normalise_mask_data(mask_data, "Mask data")
    default_data = _normalise_mask_data(default_data, "Default data")
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE character_masks"
            " SET mask_data = ?, default_data = ?, updated_at = ? WHERE id = ?",
            (mask_data, default_data, _now(), int(mask_id)),
        )
        conn.commit()


def list_characters_using_mask(mask_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            "SELECT * FROM characters WHERE mask_id = ? ORDER BY name",
            (int(mask_id),),
        ).fetchall()


def delete_character_mask(mask_id: int) -> sqlite3.Row | None:
    """Delete a mask and clear it from any characters using it."""
    row = get_character_mask(mask_id)
    if row is None:
        return None
    with closing(get_connection()) as conn:
        conn.execute(
            "UPDATE characters SET mask_id = NULL, mask_data = '{}', default_data = '{}',"
            " updated_at = ? WHERE mask_id = ?",
            (_now(), int(mask_id)),
        )
        conn.execute("DELETE FROM character_masks WHERE id = ?", (int(mask_id),))
        conn.commit()
    return row


def count_character_masks() -> int:
    with closing(get_connection()) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM character_masks").fetchone()
        return row["n"]
