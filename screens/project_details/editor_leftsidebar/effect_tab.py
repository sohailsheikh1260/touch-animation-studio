"""Effect tab (whole-frame camera zoom) for the editor sidebar."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from screens.theme import TEXT

from .common import BUTTON_STYLE, PANEL_LABEL_STYLE, ListTab


class EffectTab(ListTab):
    """Frame zoom controls for the selected clip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🖼 Effect", parent=parent)

        # Callbacks set by the sidebar.
        self.on_zoom_changed = None  # callable(point_key: str, value: int)
        self.on_zoom_commit = None   # callable()
        self.on_nudge = None         # callable(direction: str)

        self._zoom_spins: dict[str, QSpinBox] = {}

        self._build_zoom_tool()

    # ------------------------------------------------------------- builders
    def _build_zoom_tool(self) -> None:
        zoom_item = QListWidgetItem()
        zoom_item.setSizeHint(QSize(0, 172))
        zoom_widget = QWidget()
        zoom_widget.setStyleSheet("background: transparent;")
        zoom_col = QVBoxLayout(zoom_widget)
        zoom_col.setContentsMargins(8, 6, 8, 6)
        zoom_col.setSpacing(6)

        zoom_caption = QLabel("🔍 Frame Zoom (selected clip)")
        zoom_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )
        zoom_col.addWidget(zoom_caption)

        for label_text, point_key in (
            ("Zoom Start:", "start"),
            ("Zoom End:", "end"),
        ):
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)

            label = QLabel(label_text)
            label.setStyleSheet(
                f"background: transparent; color: {TEXT}; font-size: 12px;"
                f" {PANEL_LABEL_STYLE}"
            )
            spin = QSpinBox()
            spin.setRange(50, 300)
            spin.setSuffix("%")
            spin.setValue(100)
            spin.valueChanged.connect(
                lambda v, k=point_key: self._on_zoom_spin_changed(k, v)
            )
            spin.editingFinished.connect(self._on_zoom_commit)

            row.addWidget(label)
            row.addWidget(spin, 1)
            zoom_col.addWidget(row_w)
            self._zoom_spins[point_key] = spin

        # Move buttons (⬅ ⬆ ⬇ ➡) — same targets as the Tools nudge arrows
        nudge_row_w = QWidget()
        nudge_row = QHBoxLayout(nudge_row_w)
        nudge_row.setContentsMargins(0, 0, 0, 0)
        nudge_row.setSpacing(6)

        nudge_label = QLabel("⬌ Nudge:")
        nudge_label.setStyleSheet(
            f"background: transparent; color: {TEXT}; font-size: 12px;"
            f" {PANEL_LABEL_STYLE}"
        )
        nudge_row.addWidget(nudge_label)
        for text, direction in (
            ("⬅", "left"),
            ("⬆", "up"),
            ("⬇", "down"),
            ("➡", "right"),
        ):
            button = QPushButton(text)
            button.setFixedSize(30, 26)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(BUTTON_STYLE)
            button.setToolTip("Nudge point (follows Drag sets mode in Tools)")
            button.clicked.connect(
                lambda checked=False, d=direction: self._on_nudge_clicked(d)
            )
            nudge_row.addWidget(button)
        zoom_col.addWidget(nudge_row_w)

        zoom_col.addStretch()
        self.list.addItem(zoom_item)
        self.list.setItemWidget(zoom_item, zoom_widget)

    # ------------------------------------------------------------- actions
    def _on_zoom_spin_changed(self, point_key: str, value: int) -> None:
        callback = getattr(self, "on_zoom_changed", None)
        if callable(callback):
            callback(point_key, value)

    def _on_zoom_commit(self) -> None:
        callback = getattr(self, "on_zoom_commit", None)
        if callable(callback):
            callback()

    def set_clip_zoom(self, start_pct: int, end_pct: int) -> None:
        """Reflect the selected clip's frame zoom (no callbacks)."""
        values = {"start": start_pct, "end": end_pct}
        for key, spin in self._zoom_spins.items():
            spin.blockSignals(True)
            pct = max(spin.minimum(), min(spin.maximum(), values[key]))
            spin.setValue(pct)
            spin.blockSignals(False)

    def _on_nudge_clicked(self, direction: str) -> None:
        callback = getattr(self, "on_nudge", None)
        if callable(callback):
            callback(direction)
