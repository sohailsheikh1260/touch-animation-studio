"""Smoke test: Save Scene -> Scenes tab -> Import at the playhead."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database

database.DB_PATH = Path(tempfile.mkdtemp()) / "flow.db"
database.init_db()

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from screens.project.project_screen import ProjectScreen

screen = ProjectScreen(lambda: None)
project = database.create_project("Flow")
screen.show_details(project["id"])
editor = screen.editor
assert editor.project_id == project["id"]

# Build a small timeline: a background on row 1, a character on row 1.
bg = database.create_background("Sky")
char = database.create_character("Bob")
editor._on_add_asset_to_timeline("background", bg["id"])
editor._on_add_asset_to_timeline("character", char["id"])
assert len(editor.timeline.scene_clips) == 2, editor.timeline.scene_clips
editor._on_seek(0.0)

# --- Save Scene (from the Tools tab form) -----------------------------
editor.left_sidebar.tools_tab.scene_name_input.setText("Opening")
editor.left_sidebar.tools_tab.set_scene_time_range(0.0, 4.0)
editor.left_sidebar.tools_tab._on_save_scene_clicked()

rows = database.list_scenes()
assert len(rows) == 1, rows
assert rows[0]["name"] == "Opening"
assert rows[0]["project_id"] is None, "scenes are stored globally"
assert len(database.scene_clip_payload(rows[0])) == 2
print("status:", editor.status_label.text())
assert "Saved scene" in editor.status_label.text()
# The Scenes tab now shows it and is the visible tab.
assert editor.left_sidebar.scenes_tab.list.count() == 1
assert editor.left_sidebar._lib_buttons["scenes"].isChecked()
print("saved:", rows[0]["name"], rows[0]["start_time"], rows[0]["end_time"])

# --- Import at a paused playhead of 4s --------------------------------
editor._on_seek(4.0)
assert abs(editor.timeline.playhead - 4.0) < 1e-6
before = sorted(round(c.start, 2) for c in editor.timeline.scene_clips)
payload = database.scene_clip_payload(rows[0])
editor._on_import_scene(rows[0]["id"])
after = sorted(round(c.start, 2) for c in editor.timeline.scene_clips)
expected = sorted(before + [round(p["start"] + 4.0, 2) for p in payload])
print("clip starts:", after, "expected:", expected)
assert after == expected, (after, expected)
assert len(after) == len(before) + len(payload)
assert "Imported scene" in editor.status_label.text()
assert editor.timeline.playhead == 4.0
print("status:", editor.status_label.text())

# Persisted to the clips table on the next debounce flush.
editor._flush_deferred()
saved = database.list_clips(project["id"])
assert len(saved) == len(before) + len(payload), len(saved)
flow_clip_count = len(saved)
print("persisted clips:", len(saved))

# Importing again at 6s stacks another copy at 6s.
editor._on_seek(6.0)
editor._on_import_scene(rows[0]["id"])
after = sorted(round(c.start, 2) for c in editor.timeline.scene_clips)
expected = sorted(expected + [round(p["start"] + 6.0, 2) for p in payload])
print("clip starts:", after)
assert after == expected, (after, expected)
expected_flow_count = len(editor.timeline.scene_clips)

# Validation: empty name / bad range never reach the table.
editor._on_save_scene("", 0, 4)
assert "scene name" in editor.status_label.text()
editor._on_save_scene("Bad", 5, 5)
assert "after its start" in editor.status_label.text()
assert len(database.list_scenes()) == 1

# --- Cross-project: the scene saved in "Flow" is usable everywhere ------
other = database.create_project("Other Flow")
screen.show_details(other["id"])
assert editor.project_id == other["id"]
assert editor.left_sidebar.scenes_tab.list.count() == 1, "global scenes tab"
assert editor.timeline.scene_clips == [], "new project starts empty"
editor._on_seek(3.0)
editor._on_import_scene(rows[0]["id"])
starts = sorted(round(c.start, 2) for c in editor.timeline.scene_clips)
expected = sorted(round(p["start"] + 3.0, 2) for p in payload)
print("other-project clip starts:", starts, "expected:", expected)
assert starts == expected, (starts, expected)
assert "Imported scene" in editor.status_label.text()
# Project A's own timeline is untouched (the second import added one copy).
assert len(database.list_clips(project["id"])) == expected_flow_count
print("ALL OK")
