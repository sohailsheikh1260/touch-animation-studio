"""Scenes tab - saved scenes with an Import button.

Scenes are created in the Tools tab ("Save Scene"); each one is a named
timeline range plus the clip payload captured from it. Scenes are global:
the same list shows up in every project. Clicking Import places the scene
on the canvas starting at the current playhead.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import database
from screens.theme import MUTED, TEXT

from .common import BUTTON_STYLE, PANEL_LABEL_STYLE, ListTab

CAPTION = "🎬 Scenes"

IMPORT_BUTTON_STYLE = (
    BUTTON_STYLE
    + "QPushButton { background-color: #0e7490; padding: 4px 10px;"
    + "  font-size: 11px; font-weight: bold; }"
    "QPushButton:hover { background-color: #0891b2; }"
)


class ScenesTab(ListTab):
    """List of saved scenes (global), each with an Import button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(CAPTION, parent=parent)
        # Callback set by the sidebar: callable(scene_id: int).
        self.on_import = None

    # ------------------------------------------------------------- data
    def refresh(self) -> None:
        """Reload the (project-independent) scene list."""
        self.list.clear()
        rows = database.list_scenes()
        if not rows:
            self.add_hint_item(
                "No saved scenes yet.\n"
                "Fill in the Tools tab and press Save Scene."
            )
            return
        for row in rows:
            self._add_scene_row(row)

    def _add_scene_row(self, row) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, ("scene", int(row["id"])))
        item.setSizeHint(QSize(0, 54))

        widget = QWidget()
        widget.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(widget)
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(6)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        name_label = QLabel(str(row["name"]))
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 13px; font-weight: bold; {PANEL_LABEL_STYLE}"
        )
        name_label.setToolTip(str(row["name"]))

        try:
            start = float(row["start_time"])
            end = float(row["end_time"])
        except (KeyError, TypeError, ValueError):
            start = end = 0.0
        try:
            clip_count = len(database.scene_clip_payload(row))
        except Exception:
            clip_count = 0
        meta_label = QLabel(f"{start:.1f}s - {end:.1f}s  ·  {clip_count} clip(s)")
        meta_label.setStyleSheet(
            f"color: {MUTED}; font-size: 11px; {PANEL_LABEL_STYLE}"
        )

        text_col.addWidget(name_label)
        text_col.addWidget(meta_label)
        row_layout.addLayout(text_col, 1)

        import_btn = QPushButton("Import")
        import_btn.setCursor(Qt.PointingHandCursor)
        import_btn.setFixedSize(64, 28)
        import_btn.setStyleSheet(IMPORT_BUTTON_STYLE)
        import_btn.setToolTip(
            "Import this scene onto the canvas starting at the current playhead"
        )
        scene_id = int(row["id"])
        import_btn.clicked.connect(
            lambda checked=False, sid=scene_id: self._on_import(sid)
        )
        row_layout.addWidget(import_btn)

        self.list.addItem(item)
        self.list.setItemWidget(item, widget)

    # ------------------------------------------------------------- actions
    def _on_import(self, scene_id: int) -> None:
        callback = getattr(self, "on_import", None)
        if callable(callback):
            callback(scene_id)
