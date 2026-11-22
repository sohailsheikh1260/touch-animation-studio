"""Smoke test for the Scenes feature (DB + sidebar UI)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database

# --- database layer on a throwaway file -------------------------------
database.DB_PATH = Path(tempfile.mkdtemp()) / "smoke.db"
database.init_db()

project = database.create_project("Smoke", "desc")
other_project = database.create_project("Other", "desc")
scene = database.create_scene(
    "Intro", 0.0, 4.0,
    [{"name": "🧍 Bob", "kind": "scene", "asset_kind": "character", "asset_id": 7,
      "start": 0.0, "duration": 3.0, "track": 0, "animation": "walk",
      "x_offset": 1.0, "x_end": None}],
)
assert scene["id"] > 0
assert scene["project_id"] is None, "scenes must be stored globally"
rows = database.list_scenes()
assert len(rows) == 1, rows
assert database.scene_clip_payload(rows[0])[0]["asset_id"] == 7
assert database.get_scene(scene["id"])["name"] == "Intro"
assert database.list_scenes()[0]["id"] == scene["id"]

for bad in (("", 0, 1), ("x", 5, 5), ("x", 6, 2)):
    try:
        database.create_scene(*bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"expected ValueError for {bad}")

assert database.delete_scene(scene["id"]) is not None
assert database.list_scenes() == []
print("database: OK")

# Re-create a scene for the UI checks below.
scene = database.create_scene(
    "Chase", 2.0, 6.0,
    [{"name": "🧍 Bob", "kind": "scene", "asset_kind": "character", "asset_id": 7,
      "start": 2.5, "duration": 3.0, "track": 0}],
)

# --- UI ---------------------------------------------------------------
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from screens.project_details.editor_leftsidebar import EditorLeftSidebar
from screens.project_details.editor_leftsidebar.scenes_tab import ScenesTab
from screens.project_details.editor_leftsidebar.tools_tab import ToolsTab

# Tools tab: the three inputs + save button exist and are reachable.
tools = ToolsTab()
assert tools.scene_name_input is not None
assert tools.scene_start_spin.value() == 0.0
assert tools.scene_end_spin.value() == 3.0
tools.scene_name_input.setText("Chase")
tools.set_scene_time_range(2.0, 6.5)
assert tools.scene_range() == ("Chase", 2.0, 6.5), tools.scene_range()
print("tools tab: OK")

# Scenes tab: refresh shows the saved scene with an Import button.
sidebar = EditorLeftSidebar()
sidebar.set_project(project["id"])
sidebar.refresh_scenes()
scenes = sidebar.scenes_tab
assert scenes.list.count() == 1, scenes.list.count()
print("scenes tab rows:", scenes.list.count())

# Scenes are global: another project sees the very same list.
sidebar.set_project(other_project["id"])
sidebar.refresh_scenes()
assert scenes.list.count() == 1, scenes.list.count()
sidebar.set_project(project["id"])
sidebar.refresh_scenes()
print("cross-project list: OK")

imported = []
sidebar.on_import_scene = imported.append
sidebar.tools_tab.on_save_scene = lambda *a: None
from PySide6.QtWidgets import QPushButton
row_widget = scenes.list.itemWidget(scenes.list.item(0))
buttons = row_widget.findChildren(QPushButton) if row_widget else []
assert any(b.text() == "Import" for b in buttons), [b.text() for b in buttons]
[b for b in buttons if b.text() == "Import"][0].click()
assert imported == [scene["id"]], imported

# Tab switching: scenes sits next to tools and can be shown.
assert list(sidebar._tabs) == [
    "character", "background", "audio", "animation", "tools", "scenes", "effect", "chat"
], list(sidebar._tabs)
sidebar.show_tab("scenes")
assert sidebar._lib_buttons["scenes"].isChecked()
assert not sidebar.scenes_tab.isHidden()
assert sidebar.tools_tab.isHidden()
print("sidebar tabs: OK")

# Tab buttons must fit the fixed 300px sidebar (276px of usable width).
keys = list(sidebar._lib_buttons)
total = sum(sidebar._lib_buttons[k].sizeHint().width() for k in keys) + 2 * (len(keys) - 1)
print("tab button total width:", total, "(usable 276)")
assert total <= 276, total
print("ALL OK")
