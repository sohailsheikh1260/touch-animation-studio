"""Tools tab (text, size, position, flip, speed, nudge) for the sidebar."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from screens.project_details.clip import MAX_CHARACTER_SIZE_PCT, MIN_CHARACTER_SIZE_PCT
from screens.theme import BG, MUTED, TEXT

from .common import BUTTON_STYLE, PANEL_LABEL_STYLE, ListTab

SAVE_SCENE_BUTTON_STYLE = (
    "QPushButton { background-color: #16a34a; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 7px 14px;"
    "  font-size: 13px; font-weight: bold; }"
    "QPushButton:hover { background-color: #22c55e; }"
)


class ToolsTab(ListTab):
    """Editing tools for the currently selected scene clip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🛠 Tools", parent=parent)

        # Callbacks set by the sidebar.
        self.on_add_text = None          # callable(text: str)
        self.on_save_scene = None        # callable(name: str, start: float, end: float)
        self.on_scale_changed = None     # callable(percent: int)
        self.on_scale_commit = None      # callable()
        self.on_position_changed = None  # callable(point_key, value: int)
        self.on_position_commit = None   # callable()
        self.on_flip_h = None            # callable(bool)
        self.on_flip_v = None            # callable(bool)
        self.on_speed_changed = None     # callable(value: float)
        self.on_speed_commit = None      # callable()
        self.on_nudge = None             # callable(direction: str)

        self._pos_spins: dict[str, QSpinBox] = {}
        self.flip_h_btn: QPushButton
        self.flip_v_btn: QPushButton

        self._build_scene_tool()
        self._build_text_tool()
        self._build_scale_tool()
        self._build_positions_tool()
        self._build_flip_tool()

    # ------------------------------------------------------------- builders
    def _build_scene_tool(self) -> None:
        """Scene name / start / end inputs + the Save Scene button."""
        scene_item = QListWidgetItem()
        scene_item.setSizeHint(QSize(0, 140))
        scene_widget = QWidget()
        scene_widget.setStyleSheet("background: transparent;")
        scene_col = QVBoxLayout(scene_widget)
        scene_col.setContentsMargins(8, 6, 8, 6)
        scene_col.setSpacing(6)

        scene_caption = QLabel("🎬 Save Scene")
        scene_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )
        scene_col.addWidget(scene_caption)

        self.scene_name_input = QLineEdit()
        self.scene_name_input.setPlaceholderText("Scene name…")
        self.scene_name_input.setStyleSheet(
            f"background-color: {BG}; color: {TEXT}; border: 1px solid #334155;"
            " border-radius: 6px; padding: 4px 8px; font-size: 12px;"
        )
        scene_col.addWidget(self.scene_name_input)

        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(6)

        for label_text, attr in (("Start", "scene_start_spin"), ("End", "scene_end_spin")):
            label = QLabel(label_text)
            label.setStyleSheet(
                f"background: transparent; color: {TEXT}; font-size: 12px;"
                f" {PANEL_LABEL_STYLE}"
            )
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 36000.0)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setSuffix("s")
            spin.setFixedWidth(80)
            spin.setToolTip("Scene time range on the timeline (seconds)")
            setattr(self, attr, spin)
            time_row.addWidget(label)
            time_row.addWidget(spin)
        time_row.addStretch()
        scene_col.addLayout(time_row)

        self.scene_start_spin.setValue(0.0)
        self.scene_end_spin.setValue(3.0)

        save_scene_btn = QPushButton("💾 Save Scene")
        save_scene_btn.setCursor(Qt.PointingHandCursor)
        save_scene_btn.setStyleSheet(SAVE_SCENE_BUTTON_STYLE)
        save_scene_btn.setToolTip(
            "Save the clips inside Start/End as a reusable scene (see the Scenes tab)"
        )
        save_scene_btn.clicked.connect(self._on_save_scene_clicked)
        self.scene_name_input.returnPressed.connect(self._on_save_scene_clicked)
        scene_col.addWidget(save_scene_btn)

        scene_col.addStretch()
        self.list.addItem(scene_item)
        self.list.setItemWidget(scene_item, scene_widget)

    def _build_text_tool(self) -> None:
        text_item = QListWidgetItem()
        text_item.setSizeHint(QSize(0, 82))
        text_widget = QWidget()
        text_widget.setStyleSheet("background: transparent;")
        text_col = QVBoxLayout(text_widget)
        text_col.setContentsMargins(8, 6, 8, 6)
        text_col.setSpacing(6)

        text_caption = QLabel("🅣 Text")
        text_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )
        text_row = QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(6)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type text…")
        self.text_input.setStyleSheet(
            f"background-color: {BG}; color: {TEXT}; border: 1px solid #334155;"
            " border-radius: 6px; padding: 4px 8px; font-size: 12px;"
        )
        add_text_btn = QPushButton("＋ Add")
        add_text_btn.setCursor(Qt.PointingHandCursor)
        add_text_btn.setStyleSheet(BUTTON_STYLE)
        add_text_btn.clicked.connect(self._on_add_text_clicked)
        self.text_input.returnPressed.connect(self._on_add_text_clicked)

        text_row.addWidget(self.text_input, 1)
        text_row.addWidget(add_text_btn)
        text_col.addWidget(text_caption)
        text_col.addLayout(text_row)

        self.list.addItem(text_item)
        self.list.setItemWidget(text_item, text_widget)

    def _build_scale_tool(self) -> None:
        scale_item = QListWidgetItem()
        scale_item.setSizeHint(QSize(0, 130))
        scale_widget = QWidget()
        scale_widget.setStyleSheet("background: transparent;")
        scale_layout = QVBoxLayout(scale_widget)
        scale_layout.setContentsMargins(8, 6, 8, 6)
        scale_layout.setSpacing(6)

        scale_caption = QLabel("📐 Size")
        scale_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )
        self.scale_value_label = QLabel("Exact:")
        self.scale_value_label.setStyleSheet(
            f"background: transparent; color: {MUTED}; font-size: 11px;"
            f" {PANEL_LABEL_STYLE}"
        )
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(
            MIN_CHARACTER_SIZE_PCT, MAX_CHARACTER_SIZE_PCT
        )
        self.scale_slider.setValue(100)
        self.scale_slider.setTickPosition(QSlider.TicksBelow)
        self.scale_slider.setTickInterval(50)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(
            MIN_CHARACTER_SIZE_PCT, MAX_CHARACTER_SIZE_PCT
        )
        self.scale_spin.setSuffix("%")
        self.scale_spin.setValue(100)
        self.scale_spin.setFixedWidth(70)
        self.scale_spin.setToolTip("Exact character size (percent)")

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.addWidget(self.scale_value_label)
        value_row.addStretch()
        value_row.addWidget(self.scale_spin)

        scale_layout.addWidget(scale_caption)
        scale_layout.addWidget(self.scale_slider)
        scale_layout.addLayout(value_row)

        self.list.addItem(scale_item)
        self.list.setItemWidget(scale_item, scale_widget)

        self.scale_slider.valueChanged.connect(self._on_scale_value_changed)
        self.scale_slider.sliderReleased.connect(self._on_scale_released)
        self.scale_spin.valueChanged.connect(self._on_scale_spin_changed)
        self.scale_spin.editingFinished.connect(self._on_scale_released)

    def _build_positions_tool(self) -> None:
        pos_item = QListWidgetItem()
        pos_item.setSizeHint(QSize(0, 260))
        pos_widget = QWidget()
        pos_widget.setStyleSheet("background: transparent;")
        pos_col = QVBoxLayout(pos_widget)
        pos_col.setContentsMargins(8, 6, 8, 6)
        pos_col.setSpacing(6)

        pos_caption = QLabel("↔ Positions")
        pos_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )
        pos_col.addWidget(pos_caption)

        for label_text, point_key in (
            ("Start X:", "start_x"),
            ("Start Y:", "start_y"),
            ("End X:", "end_x"),
            ("End Y:", "end_y"),
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
            spin.setRange(-5000, 5000)
            spin.setFixedWidth(70)
            spin.valueChanged.connect(
                lambda v, k=point_key: self._on_position_spin_changed(k, v)
            )
            spin.editingFinished.connect(self._on_position_commit)

            row.addWidget(label)
            row.addWidget(spin, 1)
            pos_col.addWidget(row_w)
            self._pos_spins[point_key] = spin

        # Drag mode: which point does the next stage-drag define?
        mode_row_w = QWidget()
        mode_row = QHBoxLayout(mode_row_w)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(8)

        mode_label = QLabel("Drag sets:")
        mode_label.setStyleSheet(
            f"background: transparent; color: {TEXT}; font-size: 12px;"
            f" {PANEL_LABEL_STYLE}"
        )
        self.drag_mode_start = QRadioButton("Start")
        self.drag_mode_end = QRadioButton("End")
        self.drag_mode_start.setChecked(True)
        for radio in (self.drag_mode_start, self.drag_mode_end):
            radio.setStyleSheet(
                f"background: transparent; color: {TEXT}; font-size: 12px;"
            )

        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.drag_mode_start)
        mode_row.addWidget(self.drag_mode_end)
        pos_col.addWidget(mode_row_w)

        # Animation speed (walk-cycle frequency multiplier)
        speed_row_w = QWidget()
        speed_row = QHBoxLayout(speed_row_w)
        speed_row.setContentsMargins(0, 0, 0, 0)
        speed_row.setSpacing(8)

        speed_label = QLabel("🏃 Speed:")
        speed_label.setStyleSheet(
            f"background: transparent; color: {TEXT}; font-size: 12px;"
            f" {PANEL_LABEL_STYLE}"
        )
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 10.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setDecimals(1)
        self.speed_spin.setSuffix("x")
        self.speed_spin.setValue(1.0)
        self.speed_spin.valueChanged.connect(self._on_speed_spin_changed)
        self.speed_spin.editingFinished.connect(self._on_speed_commit)

        speed_row.addWidget(speed_label)
        speed_row.addWidget(self.speed_spin, 1)
        pos_col.addWidget(speed_row_w)

        # Position nudge buttons: arrows move the point per "Drag sets" mode
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
            button.setToolTip("Nudge point (follows Drag sets mode)")
            button.clicked.connect(
                lambda checked=False, d=direction: self._on_nudge_clicked(d)
            )
            nudge_row.addWidget(button)
        pos_col.addWidget(nudge_row_w)

        pos_col.addStretch()
        self.list.addItem(pos_item)
        self.list.setItemWidget(pos_item, pos_widget)

    def _build_flip_tool(self) -> None:
        flip_item = QListWidgetItem()
        flip_item.setSizeHint(QSize(0, 76))
        flip_widget = QWidget()
        flip_widget.setStyleSheet("background: transparent;")
        flip_col = QVBoxLayout(flip_widget)
        flip_col.setContentsMargins(8, 6, 8, 6)
        flip_col.setSpacing(6)

        flip_caption = QLabel("🪞 Flip")
        flip_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; {PANEL_LABEL_STYLE}"
        )
        flip_col.addWidget(flip_caption)

        flip_row = QHBoxLayout()
        flip_row.setContentsMargins(0, 0, 0, 0)
        flip_row.setSpacing(8)
        self.flip_h_btn = QPushButton("Flip H ↔")
        self.flip_v_btn = QPushButton("Flip V ↕")
        flip_style = BUTTON_STYLE + "QPushButton:checked { background-color: #1d4ed8; }"
        for button in (self.flip_h_btn, self.flip_v_btn):
            button.setCheckable(True)
            button.setEnabled(False)  # character-only; enabled on selection
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(flip_style)
            flip_row.addWidget(button)
        self.flip_h_btn.setToolTip("Mirror the selected character left/right")
        self.flip_v_btn.setToolTip("Mirror the selected character top/bottom")
        self.flip_h_btn.toggled.connect(self._on_flip_h_clicked)
        self.flip_v_btn.toggled.connect(self._on_flip_v_clicked)
        flip_col.addLayout(flip_row)
        flip_col.addStretch()

        self.list.addItem(flip_item)
        self.list.setItemWidget(flip_item, flip_widget)

    # ------------------------------------------------------------- actions
    def scene_range(self) -> tuple[str, float, float]:
        """(name, start, end) currently typed into the Save Scene form."""
        return (
            self.scene_name_input.text().strip(),
            float(self.scene_start_spin.value()),
            float(self.scene_end_spin.value()),
        )

    def set_scene_time_range(self, start: float, end: float) -> None:
        """Prefill the scene range (used when a project is loaded)."""
        for spin, value in (
            (self.scene_start_spin, start),
            (self.scene_end_spin, end),
        ):
            spin.blockSignals(True)
            spin.setValue(max(0.0, float(value)))
            spin.blockSignals(False)

    def _on_save_scene_clicked(self) -> None:
        callback = getattr(self, "on_save_scene", None)
        if callable(callback):
            callback(*self.scene_range())

    def _on_add_text_clicked(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        callback = getattr(self, "on_add_text", None)
        if callable(callback):
            callback(text)
        self.text_input.clear()

    def _on_scale_value_changed(self, value: int) -> None:
        self.scale_spin.blockSignals(True)
        self.scale_spin.setValue(value)
        self.scale_spin.blockSignals(False)
        callback = getattr(self, "on_scale_changed", None)
        if callable(callback):
            callback(value)

    def _on_scale_spin_changed(self, value: int) -> None:
        self.scale_slider.blockSignals(True)
        self.scale_slider.setValue(value)
        self.scale_slider.blockSignals(False)
        callback = getattr(self, "on_scale_changed", None)
        if callable(callback):
            callback(value)

    def _on_scale_released(self) -> None:
        callback = getattr(self, "on_scale_commit", None)
        if callable(callback):
            callback()

    def set_character_scale(self, percent: int) -> None:
        """Reflect the selected character's size on both controls (no callbacks)."""
        pct = max(
            MIN_CHARACTER_SIZE_PCT,
            min(MAX_CHARACTER_SIZE_PCT, int(percent)),
        )
        for widget in (self.scale_slider, self.scale_spin):
            widget.blockSignals(True)
            widget.setValue(pct)
            widget.blockSignals(False)

    def _on_position_spin_changed(self, point_key: str, value: int) -> None:
        callback = getattr(self, "on_position_changed", None)
        if callable(callback):
            callback(point_key, value)

    def _on_position_commit(self) -> None:
        callback = getattr(self, "on_position_commit", None)
        if callable(callback):
            callback()

    def set_character_positions(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> None:
        """Reflect the selected character's start/end positions (no callbacks)."""
        values = {
            "start_x": start_x,
            "start_y": start_y,
            "end_x": end_x,
            "end_y": end_y,
        }
        for key, spin in self._pos_spins.items():
            spin.blockSignals(True)
            spin.setValue(int(round(values[key])))
            spin.blockSignals(False)

    def drag_point_mode(self) -> str:
        """Which point the next stage-drag defines: "start" or "end"."""
        return "start" if self.drag_mode_start.isChecked() else "end"

    def _on_speed_spin_changed(self, value: float) -> None:
        callback = getattr(self, "on_speed_changed", None)
        if callable(callback):
            callback(value)

    def _on_speed_commit(self) -> None:
        callback = getattr(self, "on_speed_commit", None)
        if callable(callback):
            callback()

    def set_character_speed(self, value: float) -> None:
        """Reflect the selected character's animation speed (no callbacks)."""
        self.speed_spin.blockSignals(True)
        self.speed_spin.setValue(
            max(self.speed_spin.minimum(), min(self.speed_spin.maximum(), value))
        )
        self.speed_spin.blockSignals(False)

    def _on_flip_h_clicked(self, checked: bool) -> None:
        callback = getattr(self, "on_flip_h", None)
        if callable(callback):
            callback(checked)

    def _on_flip_v_clicked(self, checked: bool) -> None:
        callback = getattr(self, "on_flip_v", None)
        if callable(callback):
            callback(checked)

    def set_character_flip(self, flip_h: bool, flip_v: bool) -> None:
        """Reflect the selected clip's mirror flags (no callbacks)."""
        for button, value in (
            (self.flip_h_btn, flip_h),
            (self.flip_v_btn, flip_v),
        ):
            button.blockSignals(True)
            button.setChecked(bool(value))
            button.blockSignals(False)

    def _on_nudge_clicked(self, direction: str) -> None:
        callback = getattr(self, "on_nudge", None)
        if callable(callback):
            callback(direction)
