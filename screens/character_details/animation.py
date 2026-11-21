"""Animation tab - interactive 2D Inverse Kinematics (IK) animation.

Replaces the old walk-cycle preview tab. The tab now implements a bone-based
IK engine that shares the Skeleton tab's data source (single source of truth)
via skeleton_loader.load_character_skeleton_data:

- skeleton master bones: name, parent, offsets, length, angle, z_order
- body part crops cropped from the character's image (character_parts)
- bone-attached images with per-image offsets (dx/dy) and draw index
- locked bones / images

IK features:
- Two-bone IK chains for arms (shoulder -> elbow -> wrist) and legs
  (hip -> knee -> ankle); one-bone IK for the head; the torso root can be
  dragged to move the whole character.
- Dragging a hand, foot or head (its joint or its body-part image) poses the
  limb: the end follows the cursor, the elbow/knee bends on the natural side
  (derived from the rest pose), the upper segment rotates, and the pivot stays
  connected to its parent bone.
- Segment lengths stay fixed (the bone lengths configured in the Skeleton
  tab), targets are clamped to the reachable ring, so nothing stretches or
  separates.
- Bones and their attached body-part images rotate together - images are
  never moved independently of their bones.
- All motion is smoothed (exponential interpolation at ~30 fps), so poses
  never snap.

On top of the IK engine sits an animation library:

- "Animation List" sidebar tab: saved keyframe animations per character
  (Walking, Running, Dancing, ... or Custom) with play / edit / delete.
  Clicking an animation plays it on the current character; starting another
  one stops the previous playback.
- "Create Animation" sidebar tab: keyframe editor. Poses are captured from
  the live IK canvas (or generated from a per-type template), and the
  animation previews in real time before being saved.

Saved animations are stored per character in the database
(character_ik_animations) as JSON keyframe payloads and survive restarts.
Playback only drives the existing IK targets (end effectors, root offset and
bone deltas), so the skeleton stays connected and proportions are preserved.
"""

import json
import math
import random

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import database
from screens.character_details.skeleton_loader import (
    load_character_skeleton_data,
    part_draw_key,
)
from screens.theme import BG, CARD_BG, MUTED, TEXT

TICK_MS = 33  # animation tick (~30 fps)

# Animation types offered by the Create Animation workspace.
ANIMATION_TYPES = (
    "Walking",
    "Running",
    "Dancing",
    "Crying",
    "Talking",
    "Handshake",
    "Jumping",
    "Sitting",
    "Waving",
    "Custom",
)

# type -> (default duration s, default fps, default loop)
TYPE_DEFAULTS = {
    "Walking": (2.0, 30.0, True),
    "Running": (1.0, 30.0, True),
    "Dancing": (3.0, 30.0, True),
    "Crying": (2.5, 30.0, True),
    "Talking": (2.0, 30.0, True),
    "Handshake": (2.5, 30.0, True),
    "Jumping": (1.5, 30.0, True),
    "Sitting": (3.0, 30.0, False),
    "Waving": (2.0, 30.0, True),
    "Custom": (2.0, 30.0, False),
}

MAIN_STYLE = (
    f"QWidget {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px; }}"
)

SIDEBAR_STYLE = (
    f"QWidget {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px; }}"
)

TOGGLE_STYLE = (
    "QPushButton { background-color: #334155; color: #e2e8f0;"
    "  border: 1px solid #475569; border-radius: 8px; padding: 8px 10px; font-size: 12px; }"
    "QPushButton:hover { background-color: #475569; }"
    "QPushButton:checked { background-color: #0e7490; color: #ffffff; border-color: #0e7490; }"
)

SLIDER_STYLE = (
    "QSlider::groove:horizontal { background: #334155; height: 6px; border-radius: 3px; }"
    "QSlider::sub-page:horizontal { background: #0891b2; border-radius: 3px; }"
    "QSlider::handle:horizontal { background: #0e7490; width: 14px; margin: -5px 0;"
    "  border-radius: 7px; }"
    "QSlider::handle:horizontal:hover { background: #0891b2; }"
)

SPIN_STYLE = (
    "QDoubleSpinBox { background-color: #334155; color: #e2e8f0;"
    "  border: 1px solid #475569; border-radius: 4px; padding: 4px 6px; font-size: 12px; }"
    "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {"
    "  background-color: #475569; border: none; width: 16px; }"
)

COMBO_STYLE = (
    "QComboBox { background-color: #334155; color: #e2e8f0;"
    "  border: 1px solid #475569; border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
    "QComboBox::drop-down { border: none; }"
    "QComboBox QAbstractItemView { background-color: #1e293b; color: #e2e8f0;"
    "  selection-background-color: #0e7490; }"
)

LINE_STYLE = (
    "QLineEdit { background-color: #334155; color: #e2e8f0;"
    "  border: 1px solid #475569; border-radius: 4px; padding: 5px 8px; font-size: 12px; }"
    "QLineEdit:focus { border-color: #0e7490; }"
)

CHECK_STYLE = (
    "QCheckBox { color: #e2e8f0; font-size: 12px; }"
    "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px;"
    "  border: 1px solid #475569; background: #334155; }"
    "QCheckBox::indicator:checked { background: #0e7490; border-color: #0891b2; }"
)

SCROLL_STYLE = (
    "QScrollArea { border: none; background: transparent; }"
    "QScrollArea > QWidget > QWidget { background: transparent; }"
    "QScrollBar:vertical { background: #1e293b; width: 8px; border-radius: 4px; margin: 0; }"
    "QScrollBar::handle:vertical { background: #475569; border-radius: 4px; min-height: 30px; }"
    "QScrollBar::handle:vertical:hover { background: #0e7490; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
)

TAB_STYLE = (
    "QTabWidget::pane { border: none; top: -1px; }"
    "QTabBar::tab { background: #334155; color: #94a3b8; padding: 6px 10px;"
    "  font-size: 12px; border: 1px solid #475569; border-bottom: none;"
    "  border-top-left-radius: 6px; border-top-right-radius: 6px; }"
    "QTabBar::tab:selected { background: #0e7490; color: #ffffff; border-color: #0891b2; }"
    "QTabBar::tab:!selected { margin-top: 2px; }"
)

ROW_STYLE = "background-color: #1e293b; border-radius: 6px;"
ROW_SELECTED_STYLE = "background-color: #0e7490; border: 1px solid #0891b2; border-radius: 6px;"

ICON_BTN_STYLE = (
    "QPushButton { background-color: #334155; color: #e2e8f0;"
    "  border: 1px solid #475569; border-radius: 6px; font-size: 11px; }"
    "QPushButton:hover { background-color: #475569; }"
    "QPushButton:disabled { color: #64748b; background-color: #293548; }"
)


def _wrap_angle(a: float) -> float:
    """Wrap an angle in radians to (-pi, pi]."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _angle_of(v: tuple[float, float]) -> float:
    """Angle of a direction vector."""
    return math.atan2(v[1], v[0])


class IKChain:
    """An inverse-kinematics chain built from the Skeleton tab bone hierarchy.

    kind "two": pivot -> seg_a -> seg_b (seg_b's joint is the dragged end).
    kind "one": parent(end) -> end, a single rotatable segment (e.g. head).
    """

    def __init__(
        self,
        end: str,
        seg_b: str,
        seg_a: str | None,
        pivot: str | None,
        label: str,
    ) -> None:
        self.end = end          # bone whose joint is the dragged end effector
        self.seg_b = seg_b      # segment closest to the end effector
        self.seg_a = seg_a      # second segment (two-bone chains), else None
        self.pivot = pivot      # anchor bone of the chain
        self.kind = "two" if seg_a else "one"
        self.label = label
        self.bend_sign = 1.0        # elbow/knee bend side while posing
                                    # (flipped for mirrored limbs, e.g. left knee)
        self.rest_bend_sign = 1.0   # rest-pose-derived branch, used when the
                                    # chain's target sits at its rest end so
                                    # the rest pose stays an exact fixed point
        self.draggable = True

    def bones(self) -> list[str]:
        """Bones whose rotation this chain drives (for lock checks)."""
        return [b for b in (self.end, self.seg_a, self.seg_b) if b]


class IKCanvas(QLabel):
    """Canvas widget that forwards mouse/wheel events to the page."""

    def __init__(self, page: "AnimationPage", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = page
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(500, 500)
        self.setStyleSheet(f"background-color: {BG}; border-radius: 8px;")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_press(event.position(), event.button())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_move(event.position())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_release(event.button())

    def wheelEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_wheel(event.angleDelta().y(), event.position())

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._page._on_canvas_leave()
        super().leaveEvent(event)


class AnimationPage(QWidget):
    """Animation tab: interactive IK posing of the character's skeleton."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._character = None

        # ---- Skeleton data (loaded via shared skeleton loader) ----
        self._bones: list = []
        self._bone_map: dict = {}
        self._part_crops: dict[str, QPixmap] = {}
        self._bone_images: dict[str, list[dict]] = {}
        self._locked_bones: set[str] = set()
        self._part_layers: dict[str, int] = {}  # unified part draw order
        self._part_locks: dict[str, bool] = {}  # unified part lock state
        self._part_visible: dict[str, bool] = {}  # hide/show (Mark tab's flag)

        # ---- IK model (derived from the skeleton data) ----
        self._order: list[str] = []             # bones sorted parent-first
        self._children: dict[str, list[str]] = {}
        self._rest_dir: dict[str, tuple[float, float]] = {}   # rest segment vectors
        self._seg_len: dict[str, float] = {}    # fixed joint-to-joint lengths
        self._rest_pos: dict[str, tuple[float, float]] = {}   # FK at zero deltas
        self._drive: dict[str, str] = {}        # image bone -> bone it rotates with
        self._image_entries: list[tuple[str, dict]] = []      # draw-ordered images
        self._chains: list[IKChain] = []
        self._chain_ends: dict[str, IKChain] = {}

        # ---- IK state ----
        self._deltas: dict[str, float] = {}          # current bone rotation deltas
        self._target_deltas: dict[str, float] = {}   # IK solution targets
        self._eff: dict[str, tuple[float, float]] = {}        # end effector (local)
        self._eff_target: dict[str, tuple[float, float]] = {}
        self._root_offset: tuple[float, float] = (0.0, 0.0)   # torso drag offset
        self._root_offset_target: tuple[float, float] = (0.0, 0.0)
        self._smoothness = 65  # 0 = instant, 100 = very smooth

        # ---- Drag / interaction state ----
        self._drag_chain: IKChain | None = None
        self._drag_root = False
        self._drag_root_start_mouse: tuple[float, float] | None = None
        self._drag_root_start_offset: tuple[float, float] | None = None
        self._hover_end: str | None = None
        self._highlight_end: str | None = None
        self._needs_frames = False

        # ---- Cached FK results ----
        self._positions: dict[str, tuple[float, float]] = {}
        self._rots: dict[str, float] = {}

        # ---- View state: zoom + pan ----
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._panning = False
        self._pan_start_mouse: tuple[float, float] | None = None
        self._pan_start: tuple[float, float] | None = None
        self._world_pad = 800

        # ---- Eye blink (uses the Skeleton tab's attached eye images) ----
        self._eye_blink_enabled = False
        self._eye_blink_interval = 4000
        self._eye_blink_timer = 0.0
        self._eye_blink_state = "open"

        # ---- Animation library / keyframe editor state ----
        self._kf: list[dict] = []            # Create-tab keyframes
        self._editing_id: int | None = None  # DB id being edited (None = new)
        self._playing_id: int | None = None  # DB id currently playing
        self._playing_kf: list[dict] | None = None  # keyframes being played
        self._playing_meta: dict | None = None      # duration/loop/speed/name
        self._play_time = 0.0                # playback clock (seconds)
        self._manual_deltas: dict[str, float] = {}  # keyframe bone deltas (rad)

        # ---- Visibility toggles ----
        self._show_skeleton = True
        self._show_body_parts = True
        self._preview_pixmap: QPixmap | None = None

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(TICK_MS)
        self._tick_timer.timeout.connect(self._on_tick)

        self._build_ui()

    # ============================================================ UI setup
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)

        # ---- Main area (80%): IK canvas ----
        main_widget = QWidget()
        main_widget.setStyleSheet(MAIN_STYLE)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(12)

        self.preview_canvas = IKCanvas(self)
        main_layout.addWidget(self.preview_canvas, 1)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.reset_pose_btn = QPushButton("↺ Reset Pose")
        self.reset_pose_btn.setToolTip("Return all bones to the Skeleton tab's rest pose")
        self.reset_pose_btn.setCursor(Qt.PointingHandCursor)
        self.reset_pose_btn.setStyleSheet(TOGGLE_STYLE)
        self.reset_pose_btn.clicked.connect(self._on_reset_pose)
        controls.addWidget(self.reset_pose_btn)

        self.show_skeleton_btn = QPushButton("🦴 Skeleton: Show")
        self.show_skeleton_btn.setCheckable(True)
        self.show_skeleton_btn.setChecked(True)
        self.show_skeleton_btn.setToolTip("Show or hide the skeleton bones and joints")
        self.show_skeleton_btn.setStyleSheet(TOGGLE_STYLE)
        self.show_skeleton_btn.toggled.connect(self._on_show_skeleton_toggled)
        controls.addWidget(self.show_skeleton_btn)

        self.show_parts_btn = QPushButton("🖼 Parts: Show")
        self.show_parts_btn.setCheckable(True)
        self.show_parts_btn.setChecked(True)
        self.show_parts_btn.setToolTip("Show or hide the body part images")
        self.show_parts_btn.setStyleSheet(TOGGLE_STYLE)
        self.show_parts_btn.toggled.connect(self._on_show_parts_toggled)
        controls.addWidget(self.show_parts_btn)

        self.reset_view_btn = QPushButton("🔍 Reset View")
        self.reset_view_btn.setToolTip("Reset preview zoom to fit")
        self.reset_view_btn.setCursor(Qt.PointingHandCursor)
        self.reset_view_btn.setStyleSheet(TOGGLE_STYLE)
        self.reset_view_btn.clicked.connect(self._reset_view)
        controls.addWidget(self.reset_view_btn)

        tip = QLabel("💡 Drag a hand, foot or head to pose • Scroll to zoom • Right-drag to pan")
        tip.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        controls.addWidget(tip, 1)
        main_layout.addLayout(controls)

        root.addWidget(main_widget, 7)

        # ---- Sidebar (20%): Animation List / Create Animation tabs ----
        sidebar = QWidget()
        sidebar.setStyleSheet(SIDEBAR_STYLE)
        sidebar.setMinimumWidth(260)
        sidebar.setMaximumWidth(340)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(10)

        title = QLabel("IK Animation")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: bold;")
        sidebar_layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        self.status_label.setWordWrap(True)
        self.status_label.setHidden(True)
        sidebar_layout.addWidget(self.status_label)

        self.info_label = QLabel("No skeleton loaded")
        self.info_label.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        self.info_label.setWordWrap(True)
        sidebar_layout.addWidget(self.info_label)

        self.sidebar_tabs = QTabWidget()
        self.sidebar_tabs.setStyleSheet(TAB_STYLE)
        self.sidebar_tabs.addTab(self._build_list_tab(), "📋 List")
        self.sidebar_tabs.addTab(self._build_create_tab(), "✨ Create")
        sidebar_layout.addWidget(self.sidebar_tabs, 1)

        ### IK smoothness (shared below the tabs)
        smooth_caption = QLabel("IK Smoothness")
        smooth_caption.setToolTip("How smoothly bone rotations follow targets")
        smooth_caption.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        sidebar_layout.addWidget(smooth_caption)

        self.smooth_slider = QSlider(Qt.Horizontal)
        self.smooth_slider.setRange(0, 100)
        self.smooth_slider.setValue(self._smoothness)
        self.smooth_slider.setStyleSheet(SLIDER_STYLE)
        self.smooth_slider.valueChanged.connect(self._on_smoothness_changed)
        sidebar_layout.addWidget(self.smooth_slider)

        ### Eye blink (shared below the tabs)
        blink_row = QHBoxLayout()
        blink_row.setSpacing(8)
        blink_label = QLabel("👁 Eye Blink")
        blink_label.setStyleSheet(f"color: {TEXT}; font-size: 12px;")
        blink_label.setFixedWidth(80)
        blink_row.addWidget(blink_label)

        self.eye_blink_btn = QPushButton("OFF")
        self.eye_blink_btn.setCheckable(True)
        self.eye_blink_btn.setChecked(False)
        self.eye_blink_btn.setFixedWidth(70)
        self.eye_blink_btn.setToolTip("Toggle automatic eye blinking animation")
        self.eye_blink_btn.setStyleSheet(TOGGLE_STYLE)
        self.eye_blink_btn.toggled.connect(self._on_eye_blink_toggled)
        blink_row.addWidget(self.eye_blink_btn)

        self.blink_interval_spin = QDoubleSpinBox()
        self.blink_interval_spin.setRange(1000, 10000)
        self.blink_interval_spin.setSingleStep(500)
        self.blink_interval_spin.setValue(4000)
        self.blink_interval_spin.setSuffix(" ms")
        self.blink_interval_spin.setStyleSheet(SPIN_STYLE)
        self.blink_interval_spin.setFixedWidth(110)
        self.blink_interval_spin.valueChanged.connect(self._on_blink_interval_changed)
        blink_row.addWidget(self.blink_interval_spin)
        blink_row.addStretch()
        sidebar_layout.addLayout(blink_row)

        root.addWidget(sidebar, 3)

    def _build_list_tab(self) -> QWidget:
        """Sidebar tab listing saved animations with play / edit / delete."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self.playing_label = QLabel("")
        self.playing_label.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; font-weight: bold;"
        )
        self.playing_label.setWordWrap(True)
        self.playing_label.setHidden(True)
        layout.addWidget(self.playing_label)

        self.stop_btn = QPushButton("⏹ Stop Animation")
        self.stop_btn.setToolTip("Stop the playing animation and ease back to rest")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setStyleSheet(TOGGLE_STYLE)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setHidden(True)
        layout.addWidget(self.stop_btn)

        self.anim_scroll = QScrollArea()
        self.anim_scroll.setWidgetResizable(True)
        self.anim_scroll.setStyleSheet(SCROLL_STYLE)
        self.anim_list = QWidget()
        self.anim_list_layout = QVBoxLayout(self.anim_list)
        self.anim_list_layout.setContentsMargins(0, 0, 0, 0)
        self.anim_list_layout.setSpacing(6)
        self.anim_scroll.setWidget(self.anim_list)
        layout.addWidget(self.anim_scroll, 1)

        hint = QLabel("Click an animation to play it")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(hint)
        return page

    def _build_create_tab(self) -> QWidget:
        """Sidebar tab with the keyframe animation editor."""
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_STYLE)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        def caption(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {TEXT}; font-size: 12px; font-weight: bold;")
            return lbl

        # ---- Name & type ----
        layout.addWidget(caption("Name"))
        self.anim_name_edit = QLineEdit("My Animation")
        self.anim_name_edit.setStyleSheet(LINE_STYLE)
        self.anim_name_edit.setPlaceholderText("Animation name")
        layout.addWidget(self.anim_name_edit)

        layout.addWidget(caption("Animation type"))
        self.anim_type_combo = QComboBox()
        self.anim_type_combo.addItems(ANIMATION_TYPES)
        self.anim_type_combo.setStyleSheet(COMBO_STYLE)
        self.anim_type_combo.currentTextChanged.connect(self._on_type_changed)
        layout.addWidget(self.anim_type_combo)

        # ---- Playback settings ----
        layout.addWidget(caption("Playback settings"))
        grid = QHBoxLayout()
        grid.setSpacing(6)
        col_a = QVBoxLayout()
        col_a.setSpacing(3)
        dur_lbl = QLabel("Duration (s)")
        dur_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        col_a.addWidget(dur_lbl)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.2, 60.0)
        self.duration_spin.setSingleStep(0.5)
        self.duration_spin.setValue(2.0)
        self.duration_spin.setDecimals(2)
        self.duration_spin.setStyleSheet(SPIN_STYLE)
        self.duration_spin.valueChanged.connect(self._on_duration_changed)
        col_a.addWidget(self.duration_spin)
        grid.addLayout(col_a)

        col_b = QVBoxLayout()
        col_b.setSpacing(3)
        fps_lbl = QLabel("FPS")
        fps_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        col_b.addWidget(fps_lbl)
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 60.0)
        self.fps_spin.setSingleStep(1.0)
        self.fps_spin.setValue(30.0)
        self.fps_spin.setDecimals(0)
        self.fps_spin.setStyleSheet(SPIN_STYLE)
        col_b.addWidget(self.fps_spin)
        grid.addLayout(col_b)

        col_c = QVBoxLayout()
        col_c.setSpacing(3)
        speed_lbl = QLabel("Speed ×")
        speed_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        col_c.addWidget(speed_lbl)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.1, 4.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setStyleSheet(SPIN_STYLE)
        col_c.addWidget(self.speed_spin)
        grid.addLayout(col_c)
        layout.addLayout(grid)

        self.loop_check = QCheckBox("Loop / repeat")
        self.loop_check.setChecked(True)
        self.loop_check.setStyleSheet(CHECK_STYLE)
        layout.addWidget(self.loop_check)

        # ---- Timeline / keyframes ----
        layout.addWidget(caption("Keyframes"))

        time_row = QHBoxLayout()
        time_row.setSpacing(6)
        time_lbl = QLabel("Time (s)")
        time_lbl.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        time_row.addWidget(time_lbl)
        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0.0, 2.0)
        self.time_spin.setSingleStep(0.1)
        self.time_spin.setDecimals(2)
        self.time_spin.setStyleSheet(SPIN_STYLE)
        time_row.addWidget(self.time_spin, 1)
        layout.addLayout(time_row)

        gen_row = QHBoxLayout()
        gen_row.setSpacing(6)
        self.generate_btn = QPushButton("⚡ Generate")
        self.generate_btn.setToolTip(
            "Fill the timeline with keyframes for the selected type"
        )
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.setStyleSheet(TOGGLE_STYLE)
        self.generate_btn.clicked.connect(self._on_generate_keyframes)
        gen_row.addWidget(self.generate_btn, 1)

        self.add_kf_btn = QPushButton("📷 Add Keyframe")
        self.add_kf_btn.setToolTip("Capture the current canvas pose as a keyframe")
        self.add_kf_btn.setCursor(Qt.PointingHandCursor)
        self.add_kf_btn.setStyleSheet(TOGGLE_STYLE)
        self.add_kf_btn.clicked.connect(self._on_add_keyframe)
        gen_row.addWidget(self.add_kf_btn, 1)
        layout.addLayout(gen_row)

        self.kf_scroll = QScrollArea()
        self.kf_scroll.setWidgetResizable(True)
        self.kf_scroll.setStyleSheet(SCROLL_STYLE)
        self.kf_scroll.setMinimumHeight(120)
        self.kf_list = QWidget()
        self.kf_rows_layout = QVBoxLayout(self.kf_list)
        self.kf_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.kf_rows_layout.setSpacing(4)
        self.kf_scroll.setWidget(self.kf_list)
        layout.addWidget(self.kf_scroll, 1)

        # ---- Preview / save / new ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.preview_btn = QPushButton("▶ Preview")
        self.preview_btn.setToolTip("Play the workspace keyframes without saving")
        self.preview_btn.setCursor(Qt.PointingHandCursor)
        self.preview_btn.setStyleSheet(TOGGLE_STYLE)
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        btn_row.addWidget(self.preview_btn, 1)

        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setToolTip("Save this animation to the library")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(TOGGLE_STYLE)
        self.save_btn.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self.save_btn, 1)

        self.new_btn = QPushButton("🆕 New")
        self.new_btn.setToolTip("Clear the workspace and start a new animation")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setStyleSheet(TOGGLE_STYLE)
        self.new_btn.clicked.connect(self._on_new_animation)
        btn_row.addWidget(self.new_btn, 1)
        layout.addLayout(btn_row)

        # ---- Draggable chains overview ----
        layout.addSpacing(4)
        chains_caption = QLabel("Draggable parts (Inverse Kinematics)")
        chains_caption.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; font-weight: bold;"
        )
        chains_caption.setWordWrap(True)
        layout.addWidget(chains_caption)

        self.chains_list = QWidget()
        self.chains_list_layout = QVBoxLayout(self.chains_list)
        self.chains_list_layout.setContentsMargins(0, 0, 0, 0)
        self.chains_list_layout.setSpacing(4)
        self.chains_list.setStyleSheet("background: transparent;")
        layout.addWidget(self.chains_list)

        layout.addStretch()
        scroll.setWidget(page)
        outer_layout.addWidget(scroll)
        return outer

    # ============================================================ Public API
    def set_character(self, character) -> None:
        """Remember the character, load its skeleton and refresh everything."""
        if hasattr(character, "keys"):
            self._character = dict(character)
        else:
            self._character = character
        self._refresh_status("")
        self._reset_drag_state()
        self._deltas.clear()
        self._target_deltas.clear()

        # Stop any playback and clear the animation workspace.
        self._stop_playback(ease=False)
        self._playing_meta = None
        self._playing_id = None
        self._kf = []
        self._editing_id = None
        self._manual_deltas = {}
        self._reset_create_form()
        self._refresh_kf_list()

        # Shared loader - single source of truth, same data as the Skeleton tab
        data = load_character_skeleton_data(self._character or {})
        self._bones = data["bones"]
        self._bone_map = data["bone_map"]
        self._part_crops = data["part_crops"]
        self._bone_images = data["bone_images"]
        self._locked_bones = data["locked_bones"]
        self._part_layers = data.get("part_layers", {})
        self._part_locks = data.get("part_locks", {})
        self._part_visible = data.get("part_visible", {})

        self._build_model()
        self._refresh_chain_list()
        self._refresh_animation_list()
        self._needs_frames = True
        self._update_timer_running()
        self._refresh_preview()

    # ============================================================ IK model
    def _build_model(self) -> None:
        """Derive the IK model from the Skeleton tab's bone data.

        No new skeleton mapping is created here: bones, parent-child links,
        offsets, lengths and image attachments come straight from the shared
        skeleton loader.
        """
        self._children = {b["bone_name"]: [] for b in self._bones}
        root_name = None

        for bone in self._bones:
            name = bone["bone_name"]
            parent = bone["parent_name"]

            # Rest segment vector of this bone (parent joint -> own joint).
            # Matches the Skeleton tab's forward kinematics exactly:
            #   child = parent + (x_off, y_off) + rotate(angle) * (0, length)
            # For root bones the offset alone positions the joint.
            if parent:
                ang = math.radians(float(bone["angle"]))
                length = float(bone["length"])
                d = (
                    float(bone["x_offset"]) + math.sin(ang) * length,
                    float(bone["y_offset"]) + math.cos(ang) * length,
                )
                if parent in self._children:
                    self._children[parent].append(name)
            else:
                d = (float(bone["x_offset"]), float(bone["y_offset"]))
                if root_name is None:
                    root_name = name

            self._rest_dir[name] = d
            self._seg_len[name] = math.hypot(d[0], d[1])

        self._root_name = root_name

        # Bones sorted so parents are processed before their children.
        def depth(name: str) -> int:
            level, cur = 0, self._bone_map.get(name)
            while cur is not None and cur["parent_name"]:
                level += 1
                cur = self._bone_map.get(cur["parent_name"])
                if level > 50:
                    break
            return level

        self._order = sorted(
            (b["bone_name"] for b in self._bones),
            key=lambda n: (depth(n), n),
        )

        # Forward kinematics at zero deltas = the Skeleton tab's rest pose.
        self._rest_pos, _ = self._forward_kinematics({})

        # The Animation tab centers the view on the root bone's rest position
        # (like the old preview), so characters with large root offsets stay
        # centered in the canvas.
        self._root_shift = (
            -self._rest_pos[root_name][0] if root_name else 0.0,
            -self._rest_pos[root_name][1] if root_name else 0.0,
        )

        # Rotation partner for each bone-attached image: an image attached at
        # a joint rotates together with the body part extending from that
        # joint. If the bone has exactly one child, the image belongs to that
        # child's segment (e.g. the upper-arm image at the shoulder follows
        # the elbow segment); otherwise it follows the bone itself (e.g. the
        # hand at the wrist, the head at its joint, the torso image).
        self._drive = {
            b["bone_name"]: (
                self._children[b["bone_name"]][0]
                if len(self._children.get(b["bone_name"], [])) == 1
                else b["bone_name"]
            )
            for b in self._bones
        }

        # Draw-ordered attached images. Primary key: the part's unified layer
        # index (the same index the Mark Character tab edits), then the
        # bone-image index as tiebreaker - identical to the Skeleton tab.
        self._image_entries = sorted(
            (
                (bone_name, record)
                for bone_name, records in self._bone_images.items()
                for record in records
            ),
            key=lambda item: part_draw_key(self._part_layers, item),
        )

        self._build_chains()

        # IK state: effectors start at their rest positions, no rotations.
        self._deltas = {}
        self._target_deltas = {}
        self._eff = {ch.end: self._rest_pos.get(ch.end, (0.0, 0.0)) for ch in self._chains}
        self._eff_target = dict(self._eff)
        self._root_offset = (0.0, 0.0)
        self._root_offset_target = (0.0, 0.0)

        n_draggable = sum(1 for ch in self._chains if ch.draggable)
        if self._bones:
            self.info_label.setText(
                f"Bones: {len(self._bones)}\n"
                f"IK chains: {n_draggable} of {len(self._chains)}\n"
                "Drag hands, feet or head on the canvas."
            )
        else:
            self.info_label.setText("No skeleton loaded")

    def _build_chains(self) -> None:
        """Find two-bone IK chains (arms/legs) and one-bone chains (head)."""
        self._chains = []
        self._chain_ends = {}
        keywords = ("wrist", "hand", "palm", "ankle", "foot", "toe", "head", "neck")

        for bone in self._bones:
            name = bone["bone_name"]
            parent = bone["parent_name"]
            low = name.lower()
            if not parent or not any(k in low for k in keywords):
                continue

            # Ancestors between this bone and the root.
            ancestors = []
            cur = self._bone_map.get(name)
            while cur is not None and cur["parent_name"]:
                ancestors.append(cur["bone_name"])
                cur = self._bone_map.get(cur["parent_name"])
            # ancestors[0] = end bone, ancestors[-1] = bone closest to root.

            if len(ancestors) >= 3:
                # Two-bone chain: pivot -> seg_a -> seg_b(end).
                chain = IKChain(
                    end=ancestors[0],
                    seg_b=ancestors[0],
                    seg_a=ancestors[1],
                    pivot=ancestors[2],
                    label=self._chain_label(ancestors[0]),
                )
                # Natural bend side from the rest pose: which side of the
                # pivot->target line the middle joint lies on, so that a
                # rest-pose target reproduces the Skeleton tab's pose exactly.
                d_a = self._rest_dir.get(chain.seg_a, (0.0, 1.0))
                d_b = self._rest_dir.get(chain.seg_b, (0.0, 1.0))
                # sign of rest rotation from (d_a + d_b) to d_a
                cross = (d_a[0] + d_b[0]) * d_a[1] - (d_a[1] + d_b[1]) * d_a[0]
                derived = 1.0 if cross >= 0 else -1.0
                chain.rest_bend_sign = derived
                chain.bend_sign = derived
                # Left-side LEG chains: the rest-pose-derived side makes the
                # left knee bend toward the right during motion, which looks
                # broken on a front-facing character (the right knee and both
                # arms all bend toward the same side). Flip left legs so the
                # knee bends toward the left, like the right knee's natural
                # bending behavior. Right legs keep their derived sign.
                # Only active posing uses the flipped side: when a chain's
                # target sits at its rest end position the solver falls back
                # to rest_bend_sign, so the rest pose is still reproduced
                # exactly (idle legs never drift, reset eases back precisely).
                end_low = chain.end.lower()
                if "left" in end_low and any(
                    k in end_low for k in ("ankle", "foot", "toe")
                ):
                    chain.bend_sign = -chain.bend_sign
            elif ancestors:
                # Single segment ending at the end bone (neck/head-like).
                chain = IKChain(
                    end=ancestors[0],
                    seg_b=ancestors[0],
                    seg_a=None,
                    pivot=self._bone_map[ancestors[0]]["parent_name"],
                    label=self._chain_label(ancestors[0]),
                )
            else:
                continue

            # Locked bones disable dragging for the whole chain.
            if any(b in self._locked_bones for b in chain.bones()) or any(
                self._seg_len.get(b, 0.0) < 1e-6
                for b in (chain.seg_a, chain.seg_b) if b
            ):
                chain.draggable = False

            if chain.end not in self._chain_ends:
                self._chains.append(chain)
                self._chain_ends[chain.end] = chain

    def _chain_label(self, bone_name: str) -> str:
        """Human-readable label for a chain end bone."""
        low = bone_name.lower()
        side = "Left" if "left" in low else "Right" if "right" in low else ""
        if "wrist" in low or "hand" in low or "palm" in low:
            part = "Hand"
        elif "ankle" in low or "foot" in low or "toe" in low:
            part = "Foot"
        elif "head" in low or "neck" in low:
            part = "Head"
        else:
            part = bone_name.replace("_", " ").title()
        return f"{side} {part}".strip()

    def _chain_for_bone(self, bone_name: str | None) -> IKChain | None:
        """Chain to drive when the user grabs a body-part image on `bone_name`."""
        if bone_name is None:
            return None
        for chain in self._chains:
            if not chain.draggable:
                continue
            if chain.end == bone_name or chain.seg_a == bone_name or chain.seg_b == bone_name:
                return chain
            # Grabbing an image on the pivot (e.g. the upper-arm image on the
            # shoulder) also poses the chain.
            if chain.pivot == bone_name:
                return chain
        return None

    # ============================================================ Kinematics
    def _forward_kinematics(
        self, deltas: dict[str, float]
    ) -> tuple[dict[str, tuple[float, float]], dict[str, float]]:
        """Bone joint positions (root-local) and world rotation per bone.

        Each bone segment is rotated rigidly around its parent joint by the
        accumulated rotation of the chain from the root down to that bone,
        keeping the Skeleton tab's rest geometry (offsets + lengths) intact.
        """
        positions: dict[str, tuple[float, float]] = {}
        rots: dict[str, float] = {}
        for name in self._order:
            bone = self._bone_map.get(name)
            if bone is None:
                continue
            parent = bone["parent_name"]
            delta = deltas.get(name, 0.0)
            if parent and parent in positions:
                base = positions[parent]
                w = rots[parent] + delta
            else:
                base = (0.0, 0.0)
                w = delta
            dx, dy = self._rest_dir.get(name, (0.0, 0.0))
            c, s = math.cos(w), math.sin(w)
            positions[name] = (base[0] + c * dx - s * dy, base[1] + s * dx + c * dy)
            rots[name] = w
        return positions, rots

    def _solve_chain(
        self,
        chain: IKChain,
        target: tuple[float, float],
        assigned_target: tuple[float, float] | None = None,
    ) -> dict[str, float]:
        """Solve IK for one chain and return target rotation deltas per bone.

        Two-bone IK keeps both segment lengths fixed (nothing stretches, no
        joint separation); the target is clamped to the reachable annulus.

        ``assigned_target`` is the chain's raw target before end-effector
        smoothing; the bend side is chosen from it so a chain whose target
        sits at its rest end position solves with the rest-pose branch
        (``rest_bend_sign``) and reproduces the rest pose exactly.
        """
        result: dict[str, float] = {}
        if chain.kind == "two":
            pivot_pos = self._positions.get(chain.pivot)
            if pivot_pos is None:
                return result
            d_a = self._rest_dir[chain.seg_a]
            d_b = self._rest_dir[chain.seg_b]
            l1 = self._seg_len[chain.seg_a]
            l2 = self._seg_len[chain.seg_b]

            dx, dy = target[0] - pivot_pos[0], target[1] - pivot_pos[1]
            raw = math.hypot(dx, dy)
            if raw < 1e-6:
                return result
            ux, uy = dx / raw, dy / raw

            # Clamp the reach so the chain can never stretch: the target is
            # projected into [|L1 - L2| + eps, L1 + L2 - eps].
            dist = min(max(raw, abs(l1 - l2) + 1e-3), l1 + l2 - 1e-3)
            cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
            alpha = math.acos(max(-1.0, min(1.0, cos_a)))

            s = chain.bend_sign
            # Mirrored limbs pose with a flipped bend side (the left knee
            # bends toward the left), but a chain whose assigned target sits
            # at its rest end position solves with the rest-pose branch: the
            # rest pose stays an exact fixed point of the solver, so idle
            # chains never drift and reset eases all the way back to the
            # Skeleton tab's pose.
            rest_end = self._rest_pos.get(chain.end)
            ref = target if assigned_target is None else assigned_target
            if (
                rest_end is not None
                and math.hypot(ref[0] - rest_end[0], ref[1] - rest_end[1]) < 2.0
            ):
                s = chain.rest_bend_sign
            c, sn = math.cos(s * alpha), math.sin(s * alpha)
            # Segment A direction = rotate(dir, s * alpha)
            ax = ux * c - uy * sn
            ay = ux * sn + uy * c
            mid = (pivot_pos[0] + ax * l1, pivot_pos[1] + ay * l1)
            end = (pivot_pos[0] + ux * dist, pivot_pos[1] + uy * dist)
            bx = (end[0] - mid[0]) / l2
            by = (end[1] - mid[1]) / l2

            result[chain.seg_a] = _wrap_angle(math.atan2(ay, ax) - _angle_of(d_a))
            # Segment B's world rotation also carries segment A's delta
            # (the forearm inherits the upper arm's rotation), so the child
            # delta is relative to the already-applied parent rotation.
            parent_delta = result.get(chain.seg_a, 0.0)
            result[chain.seg_b] = _wrap_angle(
                math.atan2(by, bx) - _angle_of(d_b) - parent_delta
            )
        else:
            parent_name = self._bone_map.get(chain.end, None)
            end_pos = self._positions.get(parent_name["parent_name"]) if parent_name else None
            d_rest = self._rest_dir.get(chain.end)
            if end_pos is None or d_rest is None:
                return result
            dx, dy = target[0] - end_pos[0], target[1] - end_pos[1]
            raw = math.hypot(dx, dy)
            if raw < 1e-6:
                return result
            delta = _wrap_angle(math.atan2(dy, dx) - _angle_of(d_rest))
            # Subtract the accumulated parent rotation so the target angle
            # is the bone's own rotation delta, not its world angle.
            parent_name = self._bone_map.get(chain.end)
            parent_rot = self._rots.get(
                parent_name["parent_name"], 0.0
            ) if parent_name else 0.0
            delta = _wrap_angle(delta - parent_rot)
            # Natural neck/head rotation limits.
            chain_any = "head" in chain.end.lower() or "neck" in chain.end.lower()
            limit = math.radians(35.0) if chain_any else math.radians(80.0)
            result[chain.end] = max(-limit, min(limit, delta))
        return result

    # ============================================================ Animation loop
    def _on_tick(self) -> None:
        """Advance smoothing, resolve IK, and redraw one frame."""
        dt = float(TICK_MS)

        # Keyframe playback: advance the clock and drive the IK targets from
        # the sampled pose. Playback reuses the exact same smoothing + IK
        # solve pipeline as manual dragging.
        playing = self._playing_kf is not None
        if playing:
            self._advance_playback(dt)
            playing = self._playing_kf is not None

        # Smooth the torso (root) drag offset.
        ro = self._root_offset
        rt = self._root_offset_target
        k_root = self._smoothing_factor(dt, self._tau_ms() * 0.5)
        self._root_offset = (
            ro[0] + (rt[0] - ro[0]) * k_root,
            ro[1] + (rt[1] - ro[1]) * k_root,
        )

        k_eff = self._smoothing_factor(dt, self._tau_ms())

        # Bone-delta targets start from the keyframe/manual deltas (bones not
        # driven by an IK chain, e.g. locked chains); chain solutions below
        # override the chain bones themselves.
        self._target_deltas = dict(self._manual_deltas)
        settled = not self._drag_chain and not self._drag_root
        for chain in self._chains:
            if not chain.draggable:
                continue
            cur = self._eff.get(chain.end)
            tgt = self._eff_target.get(chain.end)
            if cur is None or tgt is None:
                continue
            # Smooth the end effector toward its target (cursor pose).
            new_eff = (
                cur[0] + (tgt[0] - cur[0]) * k_eff,
                cur[1] + (tgt[1] - cur[1]) * k_eff,
            )
            self._eff[chain.end] = new_eff
            solution = self._solve_chain(chain, new_eff, tgt)
            self._target_deltas.update(solution)
            settled = settled and math.hypot(tgt[0] - new_eff[0], tgt[1] - new_eff[1]) < 0.5

        # Smooth bone rotations: exponential interpolation, no snapping.
        k_delta = self._smoothing_factor(dt, 70.0)
        for bone_name, target_delta in self._target_deltas.items():
            current = self._deltas.get(bone_name, 0.0)
            self._deltas[bone_name] = current + (target_delta - current) * k_delta
            settled = settled and abs(target_delta - self._deltas[bone_name]) < 0.005

        settled = settled and math.hypot(
            self._root_offset_target[0] - self._root_offset[0],
            self._root_offset_target[1] - self._root_offset[1],
        ) < 0.5

        # A playing animation never settles - the clock keeps advancing.
        if playing:
            settled = False
            self._needs_frames = True

        # Eye blink (runs even while paused).
        blink_running = False
        if self._eye_blink_enabled:
            self._eye_blink_timer += dt
            if self._eye_blink_state == "open":
                if self._eye_blink_timer >= self._eye_blink_interval:
                    self._eye_blink_state = "closed"
                    self._eye_blink_timer = 0.0
            else:
                if self._eye_blink_timer >= 150.0:
                    self._eye_blink_state = "open"
                    self._eye_blink_timer = 0.0
            blink_running = True

        self._refresh_preview()

        if settled and not blink_running:
            self._needs_frames = False
            self._update_timer_running()

    def _tau_ms(self) -> float:
        """Effector smoothing time constant from the smoothness slider."""
        return 40.0 + (100.0 - self._smoothness) * 2.6

    def _smoothing_factor(self, dt_ms: float, tau_ms: float) -> float:
        """Exponential smoothing factor for a tick, with tau in ms."""
        if tau_ms <= 0:
            return 1.0
        return 1.0 - math.exp(-dt_ms / tau_ms)

    def _update_timer_running(self) -> None:
        should_run = self.isVisible() and bool(self._bones) and self._needs_frames
        if should_run:
            self._tick_timer.start()
        else:
            self._tick_timer.stop()

    # ============================================================ Rendering
    def _refresh_preview(self) -> None:
        """Render one frame: body parts rotated with bones + skeleton overlay."""
        if not self._bones:
            self._preview_pixmap = None
            self.preview_canvas.setText(
                "No skeleton assigned to this character"
                if self._character
                else "No character loaded"
            )
            return

        w = max(500, self.preview_canvas.width())
        h = max(500, self.preview_canvas.height())
        pad = self._world_pad
        pw, ph = w + 2 * pad, h + 2 * pad
        cx, cy = pw // 2, ph // 2

        pm = QPixmap(pw, ph)
        pm.fill(QColor(BG))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)

        self._positions, self._rots = self._forward_kinematics(self._deltas)
        rox, roy = self._root_offset
        sx, sy = self._root_shift
        world = {
            name: (cx + sx + rox + x, cy + sy + roy + y)
            for name, (x, y) in self._positions.items()
        }

        if self._show_body_parts:
            self._draw_body_parts(painter, world)
        if self._show_skeleton:
            self._draw_bone_lines(painter, world)
            self._draw_joints(painter, world)

        painter.end()
        self._preview_pixmap = pm
        self._update_canvas()

    def _draw_body_parts(self, painter: QPainter, world: dict) -> None:
        """Draw bone-attached body part images, rotated with their bones.

        Images are never rendered independently: each image is anchored to
        its bone's joint (with the Skeleton tab's offset) and rotated by the
        same angle as the bone segment it belongs to, so the character always
        stays connected with no gaps.
        """
        for bone_name, record in self._image_entries:
            part = record.get("part")
            # Hidden parts (the Mark/Skeleton hide-show flag) are not drawn
            if part and not self._part_visible.get(part, True):
                continue
            crop = self._part_crops.get(part)
            if crop is None or crop.isNull():
                continue
            pos = world.get(bone_name)
            if pos is None:
                continue

            # Eye blink swap (images attached to the head bone).
            if part == "eyes-open" and self._eye_blink_enabled and self._eye_blink_state == "closed":
                continue
            if part == "eye-close" and not (
                self._eye_blink_enabled and self._eye_blink_state == "closed"
            ):
                continue

            rotation = self._rots.get(self._drive.get(bone_name, bone_name), 0.0)
            dx, dy = float(record.get("dx", 0.0)), float(record.get("dy", 0.0))
            c, s = math.cos(rotation), math.sin(rotation)
            img_cx = pos[0] + c * dx - s * dy
            img_cy = pos[1] + s * dx + c * dy

            painter.save()
            painter.translate(img_cx, img_cy)
            painter.rotate(math.degrees(rotation))
            painter.drawPixmap(
                int(-crop.width() / 2), int(-crop.height() / 2), crop
            )
            painter.restore()

    def _draw_bone_lines(self, painter: QPainter, world: dict) -> None:
        """Skeleton bones as connected lines (same style as the Skeleton tab)."""
        pen = painter.pen()
        pen.setColor(QColor("#38bdf8"))
        pen.setWidth(4)
        painter.setPen(pen)
        for bone in self._bones:
            parent = bone["parent_name"]
            if parent and parent in world:
                x1, y1 = world[parent]
                x2, y2 = world[bone["bone_name"]]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _draw_joints(self, painter: QPainter, world: dict) -> None:
        """Joints, IK end-effector rings and bone names."""
        highlight = (
            self._drag_chain.end if self._drag_chain else self._hover_end
        )
        pen = painter.pen()
        for bone_name, (x, y) in world.items():
            if bone_name == highlight:
                pen.setColor(QColor("#4ade80"))
                pen.setWidth(14)
            elif bone_name in self._locked_bones:
                pen.setColor(QColor("#94a3b8"))
                pen.setWidth(10)
            else:
                pen.setColor(QColor("#facc15"))
                pen.setWidth(10)
            painter.setPen(pen)
            painter.drawPoint(int(x), int(y))

        # Effector rings: draggable IK targets.
        painter.setBrush(Qt.NoBrush)
        for chain in self._chains:
            if not chain.draggable:
                continue
            pos = world.get(chain.end)
            if pos is None:
                continue
            active = chain.end in (highlight, self._highlight_end)
            pen = painter.pen()
            pen.setColor(QColor("#4ade80") if active else QColor(56, 189, 248, 130))
            pen.setWidth(2 if active else 1)
            painter.setPen(pen)
            painter.drawEllipse(QPointF(pos[0], pos[1]), 8.0, 8.0)

        # Bone names
        painter.setPen(QColor(TEXT))
        for bone_name, (x, y) in world.items():
            painter.drawText(int(x) + 12, int(y) + 4, bone_name)

    def _update_canvas(self) -> None:
        """Composite the world pixmap onto the canvas at the current zoom/pan."""
        pm = self._preview_pixmap
        if pm is None or pm.isNull():
            return
        canvas = self.preview_canvas
        cw, ch = canvas.width(), canvas.height()
        if cw <= 0 or ch <= 0:
            return
        _, _, _, _, scale, ox, oy = self._view_params()
        out = QPixmap(cw, ch)
        out.fill(QColor(BG))
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(
            int(round(ox)),
            int(round(oy)),
            max(1, int(pm.width() * scale)),
            max(1, int(pm.height() * scale)),
            pm,
        )
        p.end()
        canvas.setPixmap(out)

    def _view_params(self) -> tuple[float, float, float, float, float, float, float]:
        """Current canvas view: (w, h, center_x, center_y, scale, ox, oy)."""
        w = max(500, self.preview_canvas.width())
        h = max(500, self.preview_canvas.height())
        cw, ch = self.preview_canvas.width(), self.preview_canvas.height()
        pad = self._world_pad
        pw, ph = w + 2 * pad, h + 2 * pad
        scale = (min(cw / w, ch / h) if cw > 0 and ch > 0 else 1.0) * self._zoom
        ox = cw / 2 - (pw / 2) * scale + self._pan_x
        oy = ch / 2 - (ph / 2) * scale + self._pan_y
        return w, h, pw // 2, ph // 2, scale, ox, oy

    # ============================================================ Interaction
    def _start_pan(self, wpos) -> None:
        self._panning = True
        self._pan_start_mouse = (wpos.x(), wpos.y())
        self._pan_start = (self._pan_x, self._pan_y)
        self.preview_canvas.setCursor(Qt.ClosedHandCursor)

    def _start_chain_drag(self, chain: IKChain) -> None:
        # Manual posing takes over: stop any playing animation.
        self._stop_playback(ease=False)
        self._drag_chain = chain
        # Target starts at the current animated position so grabbing never
        # snaps the pose; it then glides toward the cursor.
        self._eff_target[chain.end] = self._eff.get(
            chain.end, self._rest_pos.get(chain.end, (0.0, 0.0))
        )
        self._hover_end = chain.end
        self.preview_canvas.setCursor(Qt.ClosedHandCursor)
        self._needs_frames = True
        self._update_timer_running()

    def _start_root_drag(self, mouse_world: tuple[float, float]) -> None:
        # Manual posing takes over: stop any playing animation.
        self._stop_playback(ease=False)
        self._drag_root = True
        self._drag_root_start_mouse = mouse_world
        self._drag_root_start_offset = self._root_offset_target
        self.preview_canvas.setCursor(Qt.ClosedHandCursor)
        self._needs_frames = True
        self._update_timer_running()

    def _on_canvas_press(self, wpos, button=Qt.LeftButton) -> None:
        if button != Qt.LeftButton or not self._bones:
            self._start_pan(wpos)
            return

        _, _, cx, cy, scale, ox, oy = self._view_params()
        mouse_world = ((wpos.x() - ox) / scale, (wpos.y() - oy) / scale)
        # Root-local coordinates (the IK solver works in this space).
        rox, roy = self._root_offset
        sx, sy = self._root_shift
        lx = mouse_world[0] - cx - sx - rox
        ly = mouse_world[1] - cy - sy - roy

        # 1) IK end joints (hands, feet, head).
        radius = 18.0 / scale
        best_chain = None
        best_d2 = radius * radius
        for chain in self._chains:
            if not chain.draggable:
                continue
            pos = self._positions.get(chain.end)
            if pos is None:
                continue
            dx, dy = lx - pos[0], ly - pos[1]
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best_chain = chain
        if best_chain is not None:
            self._start_chain_drag(best_chain)
            return

        # 2) The torso root joint moves the whole character.
        root_locked = self._root_name in self._locked_bones
        root_pos = self._positions.get(self._root_name)
        if not root_locked and root_pos is not None:
            dx, dy = lx - root_pos[0], ly - root_pos[1]
            if dx * dx + dy * dy <= radius * radius:
                self._start_root_drag(mouse_world)
                return

        # 3) Body part images map onto their bones' chains.
        hit = self._hit_test_image(lx, ly, scale)
        if hit is not None:
            bone_name, _record = hit
            if bone_name == self._root_name and not root_locked:
                self._start_root_drag(mouse_world)
                return
            chain = self._chain_for_bone(bone_name)
            if chain is not None:
                self._start_chain_drag(chain)
                return

        # 4) Empty space pans the view.
        self._start_pan(wpos)

    def _on_canvas_move(self, wpos) -> None:
        if self._panning and self._pan_start_mouse is not None:
            self._pan_x = self._pan_start[0] + (wpos.x() - self._pan_start_mouse[0])
            self._pan_y = self._pan_start[1] + (wpos.y() - self._pan_start_mouse[1])
            self._update_canvas()
            return
        if not self._bones:
            return

        _, _, cx, cy, scale, ox, oy = self._view_params()
        mouse_world = ((wpos.x() - ox) / scale, (wpos.y() - oy) / scale)
        rox, roy = self._root_offset
        sx, sy = self._root_shift
        lx = mouse_world[0] - cx - sx - rox
        ly = mouse_world[1] - cy - sy - roy

        if self._drag_chain is not None:
            # Target follows the cursor; IK runs in real time on the tick.
            self._eff_target[self._drag_chain.end] = (lx, ly)
            self._needs_frames = True
            self._update_timer_running()
            return

        if self._drag_root:
            sx, sy = self._drag_root_start_mouse
            start = self._drag_root_start_offset or (0.0, 0.0)
            self._root_offset_target = (
                start[0] + (mouse_world[0] - sx),
                start[1] + (mouse_world[1] - sy),
            )
            self._needs_frames = True
            self._update_timer_running()
            return

        # Hover: highlight the nearest draggable IK joint.
        radius = 18.0 / scale
        hover = None
        best = radius * radius
        for chain in self._chains:
            if not chain.draggable:
                continue
            pos = self._positions.get(chain.end)
            if pos is None:
                continue
            dx, dy = lx - pos[0], ly - pos[1]
            d2 = dx * dx + dy * dy
            if d2 < best:
                best = d2
                hover = chain.end
        if hover != self._hover_end:
            self._hover_end = hover
            self.preview_canvas.setCursor(
                Qt.PointingHandCursor if hover else Qt.OpenHandCursor
            )
            self._refresh_preview()

    def _on_canvas_release(self, button=Qt.LeftButton) -> None:
        if self._panning:
            self._panning = False
            self._pan_start_mouse = None
            self._pan_start = None
            self.preview_canvas.setCursor(Qt.OpenHandCursor)
            return
        if self._drag_chain is not None:
            # Keep the posed position; the effector target stays where
            # released so the pose holds.
            self._drag_chain = None
            self.preview_canvas.setCursor(Qt.OpenHandCursor)
            self._needs_frames = True
            self._update_timer_running()
        if self._drag_root:
            self._drag_root = False
            self._drag_root_start_mouse = None
            self._drag_root_start_offset = None
            self.preview_canvas.setCursor(Qt.OpenHandCursor)
            self._needs_frames = True
            self._update_timer_running()

    def _on_canvas_wheel(self, delta_y: int, wpos) -> None:
        """Zoom in/out, keeping the world point under the cursor fixed."""
        _, _, _, _, old_scale, ox, oy = self._view_params()
        cw, ch = self.preview_canvas.width(), self.preview_canvas.height()
        pad = self._world_pad
        world_x = (wpos.x() - ox) / old_scale
        world_y = (wpos.y() - oy) / old_scale

        factor = 1.15 if delta_y > 0 else 1 / 1.15
        new_zoom = min(5.0, max(0.3, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        self._zoom = new_zoom
        _, _, _, _, new_scale, _, _ = self._view_params()
        pw, ph = (max(500, self.preview_canvas.width()) + 2 * pad,
                  max(500, self.preview_canvas.height()) + 2 * pad)
        self._pan_x = wpos.x() - world_x * new_scale - cw / 2 + (pw / 2) * new_scale
        self._pan_y = wpos.y() - world_y * new_scale - ch / 2 + (ph / 2) * new_scale
        self._update_canvas()

    def _on_canvas_leave(self) -> None:
        if self._panning:
            self._panning = False
            self._pan_start_mouse = None
            self._pan_start = None
            self.preview_canvas.setCursor(Qt.OpenHandCursor)
            self._update_canvas()
            return
        if self._drag_chain is not None:
            # Keep the pose; just stop dragging.
            self._drag_chain = None
        if self._drag_root:
            self._drag_root = False
        self._drag_root_start_mouse = None
        self._drag_root_start_offset = None
        self.preview_canvas.setCursor(Qt.OpenHandCursor)
        if self._hover_end is not None:
            self._hover_end = None
            self._refresh_preview()

    def _hit_test_image(
        self, lx: float, ly: float, scale: float
    ) -> tuple[str, dict] | None:
        """Return the (bone, record) of the top-most image under local coords."""
        margin = 6.0 / scale
        # Top-most (highest index) matches first.
        for bone_name, record in reversed(self._image_entries):
            part = record.get("part")
            crop = self._part_crops.get(part)
            if crop is None or crop.isNull():
                continue
            pos = self._positions.get(bone_name)
            if pos is None:
                continue
            rotation = self._rots.get(self._drive.get(bone_name, bone_name), 0.0)
            dx, dy = float(record.get("dx", 0.0)), float(record.get("dy", 0.0))
            c, s = math.cos(rotation), math.sin(rotation)
            icx = pos[0] + c * dx - s * dy
            icy = pos[1] + s * dx + c * dy
            rr = math.hypot(crop.width(), crop.height()) / 2 + margin
            if (lx - icx) ** 2 + (ly - icy) ** 2 <= rr * rr:
                return bone_name, record
        return None

    def _reset_drag_state(self) -> None:
        self._drag_chain = None
        self._drag_root = False
        self._drag_root_start_mouse = None
        self._drag_root_start_offset = None
        self._hover_end = None
        self._highlight_end = None
        self._panning = False
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

    # ============================================================ Handlers
    def _on_reset_pose(self) -> None:
        """Ease all bones back to the Skeleton tab's rest pose."""
        self._stop_playback(ease=False)
        self._manual_deltas = {}
        self._root_offset_target = (0.0, 0.0)
        for chain in self._chains:
            if chain.draggable:
                self._eff_target[chain.end] = self._rest_pos.get(
                    chain.end, self._eff.get(chain.end, (0.0, 0.0))
                )
        self._needs_frames = True
        self._update_timer_running()
        self._refresh_status("Pose reset")

    def _on_smoothness_changed(self, value: int) -> None:
        self._smoothness = int(value)

    def _on_show_skeleton_toggled(self, checked: bool) -> None:
        self._show_skeleton = bool(checked)
        self.show_skeleton_btn.setText(
            "🦴 Skeleton: Show" if checked else "🦴 Skeleton: Hide"
        )
        self._refresh_preview()

    # ============================================================ Animation library
    # Saved keyframe animations are stored per character in the
    # character_ik_animations table (via the database module). Each payload is
    # {"version": 1, "speed": float, "keyframes": [{"t": seconds,
    #  "root": [x, y], "bones": {bone: deg}, "effs": {chain_end: [x, y]}}]}.
    # effs are root-local IK end-effector targets; bones are degree deltas.

    def _parse_payload(self, text: str) -> dict:
        """Decode an animation payload JSON string."""
        try:
            data = json.loads(text or "{}")
        except (ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _normalise_keyframe(self, kf: dict) -> dict:
        """Coerce a stored keyframe into a safe working dict."""
        try:
            t = float(kf.get("t", 0.0))
        except (TypeError, ValueError):
            t = 0.0
        bones: dict[str, float] = {}
        for name, deg in (kf.get("bones") or {}).items():
            try:
                bones[str(name)] = float(deg)
            except (TypeError, ValueError):
                continue
        effs: dict[str, list[float]] = {}
        for name, pos in (kf.get("effs") or {}).items():
            try:
                effs[str(name)] = [float(pos[0]), float(pos[1])]
            except (TypeError, ValueError, IndexError):
                continue
        root = kf.get("root") or (0.0, 0.0)
        try:
            root = [float(root[0]), float(root[1])]
        except (TypeError, ValueError, IndexError):
            root = [0.0, 0.0]
        return {"t": t, "root": root, "bones": bones, "effs": effs}

    # ------------------------------------------------- playback engine
    def _start_playback(
        self, kf_list: list[dict], meta: dict, anim_id: int | None = None
    ) -> None:
        """Play a keyframe list (saved animation or workspace preview).

        Starting a playback always replaces the previous one, so only one
        animation plays at a time.
        """
        if not kf_list or not self._bones:
            return
        self._drag_chain = None
        self._drag_root = False
        self._playing_kf = [self._normalise_keyframe(k) for k in kf_list]
        self._playing_meta = dict(meta or {})
        self._playing_id = anim_id
        self._play_time = 0.0
        self._manual_deltas = {}
        # Reset every IK target to rest first, then the keyframes drive the
        # chains they contain; untouched chains ease back to rest instead of
        # holding a stale manual pose.
        self._root_offset_target = (0.0, 0.0)
        for chain in self._chains:
            if chain.draggable:
                self._eff_target[chain.end] = self._rest_pos.get(
                    chain.end, self._eff.get(chain.end, (0.0, 0.0))
                )
        self._needs_frames = True
        self._update_playback_widgets()
        self._refresh_animation_list()
        self._update_timer_running()

    def _stop_playback(self, ease: bool = True) -> None:
        """Stop the playing animation. ease=True returns the pose to rest."""
        was_playing = self._playing_kf is not None
        self._playing_kf = None
        self._playing_meta = None
        self._playing_id = None
        self._play_time = 0.0
        self._update_playback_widgets()
        if was_playing:
            self._refresh_animation_list()
        if ease and self._bones:
            self._manual_deltas = {}
            self._root_offset_target = (0.0, 0.0)
            for chain in self._chains:
                if chain.draggable:
                    self._eff_target[chain.end] = self._rest_pos.get(
                        chain.end, self._eff.get(chain.end, (0.0, 0.0))
                    )
            self._needs_frames = True
            self._update_timer_running()

    def _on_stop_clicked(self) -> None:
        self._stop_playback(ease=True)
        self._refresh_status("Animation stopped")

    def _advance_playback(self, dt_ms: float) -> None:
        """Advance the playback clock and drive the IK targets from the pose."""
        meta = self._playing_meta or {}
        duration = max(0.05, float(meta.get("duration", 2.0)))
        loop = bool(meta.get("loop", True))
        speed = float(meta.get("speed", 1.0) or 1.0)
        self._play_time += (dt_ms / 1000.0) * speed
        pose = self._sample_pose(self._playing_kf or [], self._play_time, duration, loop)
        if pose is None:
            self._stop_playback(ease=True)
            return
        root = pose.get("root") or (0.0, 0.0)
        self._root_offset_target = (float(root[0]), float(root[1]))
        # Non-chain bones (and bones of locked chains) come from the keyframe;
        # draggable chain bones are re-solved from the effector targets below.
        self._manual_deltas = {
            name: math.radians(float(deg))
            for name, deg in (pose.get("bones") or {}).items()
        }
        for end, pos in (pose.get("effs") or {}).items():
            self._eff_target[end] = (float(pos[0]), float(pos[1]))

    def _sample_pose(
        self, kfs: list[dict], time_s: float, duration: float, loop: bool
    ) -> dict | None:
        """Sample the keyframe list at `time_s`, interpolating between keys."""
        if not kfs:
            return None
        pts = sorted((self._normalise_keyframe(k) for k in kfs), key=lambda k: k["t"])
        if len(pts) == 1:
            return pts[0]
        t0 = pts[0]["t"]
        period = duration if duration > 1e-6 else max(pts[-1]["t"] - t0, 1e-6)
        t = float(time_s)
        if loop:
            t = t0 + ((t - t0) % period)
        else:
            t = min(max(t, t0), t0 + period)
        sample_pts = pts
        if loop and pts[-1]["t"] < t0 + period - 1e-9:
            # Virtual keyframe so the wrap last -> first key is interpolated
            # instead of snapping.
            sample_pts = pts + [dict(pts[0], t=t0 + period)]
        idx = 0
        for i in range(len(sample_pts) - 1):
            if sample_pts[i]["t"] <= t < sample_pts[i + 1]["t"]:
                idx = i
                break
        else:
            idx = max(0, len(sample_pts) - 2)
        a, b = sample_pts[idx], sample_pts[idx + 1]
        seg = b["t"] - a["t"]
        f = 0.0 if seg <= 1e-9 else (t - a["t"]) / seg
        f = max(0.0, min(1.0, f))
        return self._lerp_pose(a, b, f)

    def _lerp_pose(self, a: dict, b: dict, f: float) -> dict:
        """Linear interpolation between two keyframe poses."""
        ra, rb = a["root"], b["root"]
        out = {
            "t": a["t"] + (b["t"] - a["t"]) * f,
            "root": [ra[0] + (rb[0] - ra[0]) * f, ra[1] + (rb[1] - ra[1]) * f],
            "bones": {},
            "effs": {},
        }
        ba, bb = a["bones"], b["bones"]
        for name in set(ba) | set(bb):
            va = float(ba.get(name, 0.0))
            vb = float(bb.get(name, 0.0))
            out["bones"][name] = va + (vb - va) * f
        ea, eb = a["effs"], b["effs"]
        for name in set(ea) | set(eb):
            pa = ea.get(name, eb.get(name))
            pb = eb.get(name, ea.get(name))
            if pa is None or pb is None:
                continue
            out["effs"][name] = [
                pa[0] + (pb[0] - pa[0]) * f,
                pa[1] + (pb[1] - pa[1]) * f,
            ]
        return out

    def _update_playback_widgets(self) -> None:
        playing = self._playing_kf is not None
        if playing:
            name = (self._playing_meta or {}).get("name", "")
            self.playing_label.setText(
                f"▶ Now playing: {name}" if name else "▶ Playing animation"
            )
            self.playing_label.setHidden(False)
            self.stop_btn.setHidden(False)
        else:
            self.playing_label.setHidden(True)
            self.stop_btn.setHidden(True)

    # ------------------------------------------------- animation list tab
    def _refresh_animation_list(self) -> None:
        """Rebuild the saved-animation rows for the current character."""
        while self.anim_list_layout.count():
            item = self.anim_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        character_id = (self._character or {}).get("id") if self._character else None
        rows: list = []
        if character_id is not None:
            rows = list(database.list_character_ik_animations(int(character_id)))
        if not rows:
            empty = QLabel(
                "No saved animations yet.\nCreate one in the ✨ Create tab."
                if self._character
                else "No character selected."
            )
            empty.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
            empty.setWordWrap(True)
            self.anim_list_layout.addWidget(empty)
            self.anim_list_layout.addStretch()
            return

        for row in rows:
            self.anim_list_layout.addWidget(self._build_anim_row(row))
        self.anim_list_layout.addStretch()

    def _build_anim_row(self, row) -> QFrame:
        """One library row: name, play button, edit and delete options."""
        anim_id = int(row["id"])
        playing = anim_id == self._playing_id
        frame = QFrame()
        frame.setStyleSheet(ROW_SELECTED_STYLE if playing else ROW_STYLE)
        frame.setCursor(Qt.PointingHandCursor)
        frame.setToolTip(f"Play '{row['name']}'")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 5, 6, 5)
        layout.setSpacing(4)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        name_lbl = QLabel(str(row["name"]))
        name_lbl.setStyleSheet(
            f"color: {TEXT}; font-size: 12px;"
            + (" font-weight: bold;" if playing else "")
        )
        type_lbl = QLabel(
            f"{row['anim_type']} • {float(row['duration']):.1f}s"
            + (" 🔁" if bool(row["loop"]) else "")
        )
        type_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        text_col.addWidget(name_lbl)
        text_col.addWidget(type_lbl)
        layout.addLayout(text_col, 1)

        def icon_button(text: str, tooltip: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setFixedSize(26, 24)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(ICON_BTN_STYLE)
            return btn

        play_btn = icon_button("▶", "Play this animation")
        play_btn.clicked.connect(lambda _=False, r=row: self._play_animation_row(r))
        layout.addWidget(play_btn)

        edit_btn = icon_button("✏", "Edit this animation")
        edit_btn.clicked.connect(lambda _=False, r=row: self._on_anim_edit_clicked(r))
        layout.addWidget(edit_btn)

        del_btn = icon_button("🗑", "Delete this animation")
        del_btn.clicked.connect(
            lambda _=False, r=row: self._on_anim_delete_clicked(r)
        )
        layout.addWidget(del_btn)

        # Clicking the row itself plays the animation.
        frame.mousePressEvent = (  # type: ignore[method-assign]
            lambda event, r=row: self._play_animation_row(r)
        )
        return frame

    def _play_animation_row(self, row) -> None:
        """Load and play a saved animation (stops any previous playback)."""
        payload = self._parse_payload(row["payload"])
        kfs = payload.get("keyframes")
        if not kfs:
            self._refresh_status(f"'{row['name']}' has no keyframes")
            return
        meta = {
            "duration": float(row["duration"]),
            "loop": bool(row["loop"]),
            "speed": float(row["speed"]) or 1.0,
            "name": str(row["name"]),
        }
        self._start_playback(kfs, meta, anim_id=int(row["id"]))
        self._refresh_status(f"Playing '{row['name']}'")

    def _on_anim_edit_clicked(self, row) -> None:
        """Load a saved animation into the Create Animation workspace."""
        self._stop_playback(ease=True)
        payload = self._parse_payload(row["payload"])
        kfs = payload.get("keyframes") or []
        self._editing_id = int(row["id"])
        self.anim_name_edit.setText(str(row["name"]))
        self.anim_type_combo.blockSignals(True)
        idx = self.anim_type_combo.findText(str(row["anim_type"]))
        self.anim_type_combo.setCurrentIndex(
            idx if idx >= 0 else ANIMATION_TYPES.index("Custom")
        )
        self.anim_type_combo.blockSignals(False)
        self.duration_spin.setValue(float(row["duration"]))
        self.fps_spin.setValue(float(row["fps"]))
        self.speed_spin.setValue(float(row["speed"]) or 1.0)
        self.loop_check.setChecked(bool(row["loop"]))
        self._kf = [self._normalise_keyframe(k) for k in kfs]
        if not self._kf:
            self._kf = [self._capture_current_pose(0.0)]
        self._refresh_kf_list()
        self.sidebar_tabs.setCurrentIndex(1)
        self._apply_keyframe_to_targets(self._kf[0])
        self._refresh_status(f"Editing '{row['name']}'")

    def _on_anim_delete_clicked(self, row) -> None:
        anim_id = int(row["id"])
        if self._playing_id == anim_id:
            self._stop_playback(ease=False)
        if self._editing_id == anim_id:
            self._editing_id = None
        database.delete_character_ik_animation(anim_id)
        self._refresh_animation_list()
        self._refresh_status(f"Deleted '{row['name']}'")

    # ------------------------------------------------- create animation tab
    def _reset_create_form(self) -> None:
        """Reset the Create Animation workspace to a fresh state."""
        self.anim_name_edit.setText("My Animation")
        self.anim_type_combo.blockSignals(True)
        self.anim_type_combo.setCurrentIndex(0)
        self.anim_type_combo.blockSignals(False)
        duration, fps, loop = TYPE_DEFAULTS[ANIMATION_TYPES[0]]
        self.duration_spin.setValue(duration)
        self.fps_spin.setValue(fps)
        self.loop_check.setChecked(loop)
        self.speed_spin.setValue(1.0)
        self.time_spin.setValue(0.0)

    def _workspace_meta(self) -> dict:
        return {
            "name": self.anim_name_edit.text().strip() or "My Animation",
            "type": self.anim_type_combo.currentText(),
            "duration": float(self.duration_spin.value()),
            "fps": float(self.fps_spin.value()),
            "loop": self.loop_check.isChecked(),
            "speed": float(self.speed_spin.value()) or 1.0,
        }

    def _on_type_changed(self, type_name: str) -> None:
        """Apply the default duration/fps/loop for the chosen type."""
        duration, fps, loop = TYPE_DEFAULTS.get(type_name, (2.0, 30.0, False))
        self.duration_spin.setValue(duration)
        self.fps_spin.setValue(fps)
        self.loop_check.setChecked(loop)

    def _on_duration_changed(self, value: float) -> None:
        self.time_spin.setMaximum(max(0.0, float(value)))

    def _on_generate_keyframes(self) -> None:
        """Fill the workspace with a procedural template for the type.

        Generating starts fresh content: saving afterwards creates a new
        animation instead of overwriting the one being edited.
        """
        if not self._bones:
            self._refresh_status("Load a character with a skeleton first")
            return
        anim_type = self.anim_type_combo.currentText()
        duration = float(self.duration_spin.value())
        self._kf = self._generate_type_keyframes(anim_type, duration)
        self._editing_id = None
        self._refresh_kf_list()
        if self._kf:
            self._apply_keyframe_to_targets(self._kf[0])
        self._refresh_status(f"Generated {len(self._kf)} keyframes for {anim_type}")

    def _on_add_keyframe(self) -> None:
        """Capture the current canvas pose as a keyframe at the chosen time."""
        if not self._bones:
            self._refresh_status("Load a character with a skeleton first")
            return
        t = float(self.time_spin.value())
        # Capturing at an existing keyframe's time replaces it.
        self._kf = [k for k in self._kf if abs(float(k["t"]) - t) > 1e-3]
        self._kf.append(self._capture_current_pose(t))
        self._refresh_kf_list()
        self._refresh_status(f"Keyframe captured at {t:.2f}s")

    def _on_preview_clicked(self) -> None:
        """Play the workspace keyframes without saving."""
        if not self._bones:
            self._refresh_status("Load a character with a skeleton first")
            return
        if not self._kf:
            self._kf = [self._capture_current_pose(0.0)]
            self._refresh_kf_list()
        meta = self._workspace_meta()
        self._start_playback(self._kf, dict(meta, name=f"{meta['name']} (preview)"))
        self._refresh_status("Previewing workspace animation")

    def _on_save_clicked(self) -> None:
        """Save (or update) the workspace animation in the database."""
        character_id = (self._character or {}).get("id") if self._character else None
        if character_id is None:
            self._refresh_status("Select a character first")
            return
        if not self._bones:
            self._refresh_status("Load a character with a skeleton first")
            return
        if not self._kf:
            self._kf = [self._capture_current_pose(0.0)]
            self._refresh_kf_list()
        self._kf.sort(key=lambda k: float(k["t"]))
        meta = self._workspace_meta()
        payload = {"version": 1, "speed": meta["speed"], "keyframes": self._kf}
        anim_id: int | None = None
        if self._editing_id is not None:
            existing = database.get_character_ik_animation(int(self._editing_id))
            if existing is not None:
                database.update_character_ik_animation(
                    int(self._editing_id),
                    meta["name"],
                    meta["type"],
                    meta["duration"],
                    meta["fps"],
                    meta["loop"],
                    meta["speed"],
                    payload,
                )
                anim_id = int(self._editing_id)
                self._refresh_status(f"Updated '{meta['name']}'")
            else:
                self._editing_id = None
        if anim_id is None:
            anim_id = database.create_character_ik_animation(
                int(character_id),
                meta["name"],
                meta["type"],
                meta["duration"],
                meta["fps"],
                meta["loop"],
                meta["speed"],
                payload,
            )
            self._editing_id = anim_id
            self._refresh_status(f"Saved '{meta['name']}'")
        self._refresh_animation_list()
        self.sidebar_tabs.setCurrentIndex(0)
        saved = database.get_character_ik_animation(int(anim_id))
        if saved is not None:
            self._play_animation_row(saved)

    def _on_new_animation(self) -> None:
        """Clear the workspace and start a new animation."""
        self._stop_playback(ease=True)
        self._editing_id = None
        self._kf = []
        self._reset_create_form()
        self._refresh_kf_list()
        self.sidebar_tabs.setCurrentIndex(1)
        self._refresh_status("New animation - pose the character and add keyframes")

    def _refresh_kf_list(self) -> None:
        """Rebuild the workspace keyframe rows."""
        self._kf.sort(key=lambda k: float(k["t"]))
        while self.kf_rows_layout.count():
            item = self.kf_rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not self._kf:
            empty = QLabel(
                "No keyframes yet.\nPose the character on the canvas and click"
                " 📷 Add Keyframe, or ⚡ Generate."
            )
            empty.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            empty.setWordWrap(True)
            self.kf_rows_layout.addWidget(empty)
            return
        for i, kf in enumerate(self._kf):
            self.kf_rows_layout.addWidget(self._build_kf_row(i, kf))

    def _build_kf_row(self, idx: int, kf: dict) -> QFrame:
        """One keyframe row: jump / re-capture / delete."""
        frame = QFrame()
        frame.setStyleSheet(ROW_STYLE)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 3, 6, 3)
        layout.setSpacing(4)
        label = QLabel(f"#{idx + 1}  @{float(kf['t']):.2f}s")
        label.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
        layout.addWidget(label, 1)

        def icon_button(text: str, tooltip: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setFixedSize(26, 22)
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(ICON_BTN_STYLE)
            return btn

        jump_btn = icon_button("⏩", "Jump to this keyframe on the canvas")
        jump_btn.clicked.connect(lambda _=False, i=idx: self._on_kf_jump(i))
        layout.addWidget(jump_btn)

        cap_btn = icon_button("📷", "Overwrite with the current canvas pose")
        cap_btn.clicked.connect(lambda _=False, i=idx: self._on_kf_capture(i))
        layout.addWidget(cap_btn)

        del_btn = icon_button("🗑", "Delete this keyframe")
        del_btn.setEnabled(len(self._kf) > 1)
        del_btn.clicked.connect(lambda _=False, i=idx: self._on_kf_delete(i))
        layout.addWidget(del_btn)
        return frame

    def _on_kf_jump(self, idx: int) -> None:
        if not (0 <= idx < len(self._kf)):
            return
        kf = self._kf[idx]
        self.time_spin.setValue(float(kf["t"]))
        self._apply_keyframe_to_targets(kf)

    def _on_kf_capture(self, idx: int) -> None:
        if not (0 <= idx < len(self._kf)):
            return
        t = float(self._kf[idx]["t"])
        self._kf[idx] = self._capture_current_pose(t)
        self._refresh_kf_list()
        self._refresh_status(f"Keyframe @{t:.2f}s updated")

    def _on_kf_delete(self, idx: int) -> None:
        if len(self._kf) <= 1 or not (0 <= idx < len(self._kf)):
            return
        self._kf.pop(idx)
        self._refresh_kf_list()

    def _capture_current_pose(self, t: float) -> dict:
        """Snapshot the live IK pose (deltas, effectors, root offset)."""
        bones = {}
        for name, delta in self._deltas.items():
            deg = math.degrees(delta)
            if abs(deg) > 0.05:
                bones[name] = round(deg, 2)
        effs = {
            end: [round(pos[0], 2), round(pos[1], 2)]
            for end, pos in self._eff.items()
        }
        return {
            "t": round(float(t), 3),
            "root": [
                round(self._root_offset[0], 2),
                round(self._root_offset[1], 2),
            ],
            "bones": bones,
            "effs": effs,
        }

    def _apply_keyframe_to_targets(self, kf: dict) -> None:
        """Ease the canvas toward a keyframe's pose (used when editing)."""
        root = kf.get("root") or (0.0, 0.0)
        self._root_offset_target = (float(root[0]), float(root[1]))
        self._manual_deltas = {
            name: math.radians(float(deg))
            for name, deg in (kf.get("bones") or {}).items()
        }
        for end, pos in (kf.get("effs") or {}).items():
            self._eff_target[end] = (float(pos[0]), float(pos[1]))
        self._needs_frames = True
        self._update_timer_running()

    # ------------------------------------------------- pose generators
    def _limb(self, side: str, part: str) -> IKChain | None:
        """First IK chain matching a side ('left'/'right'/'') and part name."""
        part_l = part.lower()
        for chain in self._chains:
            label = chain.label.lower()
            if part_l not in label:
                continue
            if side:
                if side.lower() not in label:
                    continue
            elif "left" in label or "right" in label:
                continue
            return chain
        return None

    def _pose_scale(self) -> float:
        """Amplitude scale derived from the character's limb lengths."""
        chain = self._limb("left", "hand") or self._limb("left", "foot")
        if chain is not None and chain.seg_a:
            total = self._seg_len.get(chain.seg_a, 0.0) + self._seg_len.get(
                chain.seg_b, 0.0
            )
            if total > 1e-3:
                return max(0.4, min(4.0, total / 60.0))
        return 1.0

    def _blank_pose(self, t: float) -> dict:
        """A keyframe at rest pose."""
        return {"t": round(float(t), 3), "root": [0.0, 0.0], "bones": {}, "effs": {}}

    def _eff_at(self, chain: IKChain, dx: float, dy: float) -> list[float]:
        """Root-local effector target at the chain's rest position + offset.

        dy is negative for up (screen space). Offsets scale with the
        character's limb lengths so proportions stay natural.
        """
        rest = self._rest_pos.get(chain.end, (0.0, 0.0))
        return [round(rest[0] + dx, 2), round(rest[1] + dy, 2)]

    def _generate_type_keyframes(self, anim_type: str, duration: float) -> list[dict]:
        """Procedural keyframe template for an animation type."""
        k = self._pose_scale()
        if anim_type == "Walking":
            return self._gen_walk_like(duration, 16 * k, 14 * k, 4 * k, 9 * k)
        if anim_type == "Running":
            return self._gen_walk_like(duration, 26 * k, 22 * k, 7 * k, 16 * k)
        if anim_type == "Dancing":
            return self._gen_dancing(duration, k)
        if anim_type == "Crying":
            return self._gen_crying(duration, k)
        if anim_type == "Talking":
            return self._gen_talking(duration, k)
        if anim_type == "Handshake":
            return self._gen_handshake(duration, k)
        if anim_type == "Jumping":
            return self._gen_jumping(duration, k)
        if anim_type == "Sitting":
            return self._gen_sitting(duration, k)
        if anim_type == "Waving":
            return self._gen_waving(duration, k)
        # Custom (and fallback): a single rest-pose keyframe to build on.
        return [self._blank_pose(0.0)]

    def _gen_walk_like(
        self, duration: float, arm_amp: float, foot_amp: float, bob: float, lift: float
    ) -> list[dict]:
        """Walk/run cycle: opposite arm/leg swings with a body bob.

        The loop wrap (last -> first keyframe) is interpolated by the
        playback sampler, so no duplicate final keyframe is needed.
        """
        keys = []
        n = 4
        left_hand = self._limb("left", "hand")
        right_hand = self._limb("right", "hand")
        left_foot = self._limb("left", "foot")
        right_foot = self._limb("right", "foot")
        for i in range(n):
            p = self._blank_pose(duration * i / n)
            ph = 2.0 * math.pi * i / n
            s = math.sin(ph)
            root_dy = bob * math.cos(2.0 * ph)
            if left_hand is not None:
                p["effs"][left_hand.end] = self._eff_at(
                    left_hand, s * arm_amp, -2.0 - abs(math.cos(ph)) * 2.0
                )
            if right_hand is not None:
                p["effs"][right_hand.end] = self._eff_at(
                    right_hand, -s * arm_amp, -2.0 - abs(math.cos(ph)) * 2.0
                )
            # Feet stay planted in world space: cancel the root bob in the
            # root-local target (-root_dy), and lift while swinging forward.
            if left_foot is not None:
                p["effs"][left_foot.end] = self._eff_at(
                    left_foot, -s * foot_amp, -root_dy - lift * max(0.0, -s)
                )
            if right_foot is not None:
                p["effs"][right_foot.end] = self._eff_at(
                    right_foot, s * foot_amp, -root_dy - lift * max(0.0, s)
                )
            p["root"] = [0.0, round(root_dy, 2)]
            keys.append(p)
        return keys

    def _gen_dancing(self, duration: float, k: float) -> list[dict]:
        """Side-to-side sway with alternating raised arms and head tilt."""
        keys = []
        n = 6
        left_hand = self._limb("left", "hand")
        right_hand = self._limb("right", "hand")
        head = self._limb("", "head")
        raise_ = 42.0 * k
        sway = 12.0 * k
        for i in range(n):
            p = self._blank_pose(duration * i / n)
            ph = 2.0 * math.pi * i / n
            s = math.sin(ph)
            if left_hand is not None:
                p["effs"][left_hand.end] = self._eff_at(
                    left_hand, s * 8.0 * k, -raise_ * max(0.0, s)
                )
            if right_hand is not None:
                p["effs"][right_hand.end] = self._eff_at(
                    right_hand, s * 8.0 * k, -raise_ * max(0.0, -s)
                )
            if head is not None:
                p["effs"][head.end] = self._eff_at(head, 10.0 * k * s, 0.0)
            p["root"] = [round(sway * s, 2), 0.0]
            keys.append(p)
        return keys

    def _gen_crying(self, duration: float, k: float) -> list[dict]:
        """Hands up at the face, head bowed, trembling."""
        keys = []
        n = 4
        left_hand = self._limb("left", "hand")
        right_hand = self._limb("right", "hand")
        head = self._limb("", "head")
        head_rest = self._rest_pos.get(head.end, (0.0, 0.0)) if head else (0.0, 0.0)
        for i in range(n):
            p = self._blank_pose(duration * i / n)
            ph = 2.0 * math.pi * i / n
            tremble = math.sin(ph) * 2.0 * k
            if left_hand is not None:
                p["effs"][left_hand.end] = [
                    round(head_rest[0] - 12.0 * k + tremble, 2),
                    round(head_rest[1] + 16.0 * k, 2),
                ]
            if right_hand is not None:
                p["effs"][right_hand.end] = [
                    round(head_rest[0] + 12.0 * k - tremble, 2),
                    round(head_rest[1] + 16.0 * k, 2),
                ]
            if head is not None:
                p["effs"][head.end] = self._eff_at(head, tremble * 0.5, 5.0 * k)
            keys.append(p)
        return keys

    def _gen_talking(self, duration: float, k: float) -> list[dict]:
        """Gesturing hand with small head nods."""
        keys = []
        n = 4
        hand = self._limb("right", "hand") or self._limb("left", "hand")
        head = self._limb("", "head")
        for i in range(n):
            p = self._blank_pose(duration * i / n)
            ph = 2.0 * math.pi * i / n
            s = math.sin(ph)
            if hand is not None:
                p["effs"][hand.end] = self._eff_at(
                    hand, 12.0 * k * s, -10.0 * k - 4.0 * k * math.cos(ph)
                )
            if head is not None:
                p["effs"][head.end] = self._eff_at(head, 3.0 * k * s, 2.0 * k * math.cos(ph))
            keys.append(p)
        return keys

    def _gen_handshake(self, duration: float, k: float) -> list[dict]:
        """Extended hand performing the handshake shake."""
        keys = []
        n = 4
        hand = self._limb("right", "hand") or self._limb("left", "hand")
        for i in range(n):
            p = self._blank_pose(duration * i / n)
            ph = 2.0 * math.pi * i / n
            shake = 3.0 * k * math.sin(2.0 * ph)
            if hand is not None:
                p["effs"][hand.end] = self._eff_at(hand, 34.0 * k, 8.0 * k + shake)
            keys.append(p)
        return keys

    def _gen_jumping(self, duration: float, k: float) -> list[dict]:
        """Crouch -> launch -> apex -> landing, arms swing overhead."""
        left_hand = self._limb("left", "hand")
        right_hand = self._limb("right", "hand")
        poses = [
            (14.0, 6.0, 10.0),     # crouch, arms low
            (-30.0, -10.0, -34.0),  # launch, arms swing up
            (-40.0, -14.0, -52.0),  # apex, arms high
            (10.0, 4.0, 8.0),      # landing, arms settle
        ]
        keys = []
        for i, (root_dy, hand_dx, hand_dy) in enumerate(poses):
            p = self._blank_pose(duration * i / len(poses))
            p["root"] = [0.0, round(root_dy * k, 2)]
            if left_hand is not None:
                p["effs"][left_hand.end] = self._eff_at(
                    left_hand, hand_dx * k, hand_dy * k
                )
            if right_hand is not None:
                p["effs"][right_hand.end] = self._eff_at(
                    right_hand, -hand_dx * k, hand_dy * k
                )
            keys.append(p)
        return keys

    def _gen_sitting(self, duration: float, k: float) -> list[dict]:
        """Seated hold: body lowered, knees bent forward, hands in lap."""
        left_hand = self._limb("left", "hand")
        right_hand = self._limb("right", "hand")
        left_foot = self._limb("left", "foot")
        right_foot = self._limb("right", "foot")
        root_dy = 20.0 * k
        p = self._blank_pose(0.0)
        p["root"] = [0.0, round(root_dy, 2)]
        # Feet stay at ground level in world space: cancel the root offset.
        if left_foot is not None:
            p["effs"][left_foot.end] = self._eff_at(left_foot, -10.0 * k, -root_dy)
        if right_foot is not None:
            p["effs"][right_foot.end] = self._eff_at(right_foot, 10.0 * k, -root_dy)
        if left_hand is not None:
            p["effs"][left_hand.end] = self._eff_at(left_hand, 6.0 * k, 10.0 * k)
        if right_hand is not None:
            p["effs"][right_hand.end] = self._eff_at(right_hand, -6.0 * k, 10.0 * k)
        hold = self._blank_pose(duration)
        hold["root"] = list(p["root"])
        hold["effs"] = {name: list(pos) for name, pos in p["effs"].items()}
        return [p, hold]

    def _gen_waving(self, duration: float, k: float) -> list[dict]:
        """Raised hand waving side to side."""
        keys = []
        n = 4
        hand = self._limb("right", "hand") or self._limb("left", "hand")
        head = self._limb("", "head")
        for i in range(n):
            p = self._blank_pose(duration * i / n)
            ph = 2.0 * math.pi * i / n
            s = math.sin(ph)
            if hand is not None:
                p["effs"][hand.end] = self._eff_at(hand, 12.0 * k * s, -44.0 * k)
            if head is not None:
                p["effs"][head.end] = self._eff_at(head, 4.0 * k * s, -2.0 * k)
            keys.append(p)
        return keys

    def _on_show_parts_toggled(self, checked: bool) -> None:
        self._show_body_parts = bool(checked)
        self.show_parts_btn.setText("🖼 Parts: Show" if checked else "🖼 Parts: Hide")
        self._refresh_preview()

    def _reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_canvas()

    def _on_eye_blink_toggled(self, checked: bool) -> None:
        self._eye_blink_enabled = bool(checked)
        self.eye_blink_btn.setText("ON" if checked else "OFF")
        if not checked:
            self._eye_blink_state = "open"
            self._eye_blink_timer = 0.0
        else:
            self._eye_blink_timer = random.uniform(0, self._eye_blink_interval)
        self._needs_frames = self._needs_frames or checked
        self._update_timer_running()
        self._refresh_preview()

    def _on_blink_interval_changed(self, value: float) -> None:
        self._eye_blink_interval = float(value)

    def _refresh_chain_list(self) -> None:
        """Rebuild the draggable-parts overview in the sidebar."""
        while self.chains_list_layout.count():
            item = self.chains_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self._chains:
            empty = QLabel("No IK chains found")
            empty.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
            empty.setWordWrap(True)
            self.chains_list_layout.addWidget(empty)
            return

        for chain in self._chains:
            row = QFrame()
            icon = "✋" if "hand" in chain.label.lower() else (
                "🦶" if "foot" in chain.label.lower() else "🙂"
            )
            if not chain.draggable:
                text = f"🔒 {chain.label}"
                row.setToolTip("Locked in the Skeleton tab")
                row.setStyleSheet(ROW_STYLE)
            else:
                text = f"{icon} {chain.label}"
                selected = chain.end == self._highlight_end
                row.setStyleSheet(ROW_SELECTED_STYLE if selected else ROW_STYLE)
                row.setCursor(Qt.PointingHandCursor)
                row.setToolTip(f"Drag {chain.label} on the canvas to pose it")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 5, 8, 5)
            label = QLabel(text)
            label.setStyleSheet(
                f"color: {'#94a3b8' if not chain.draggable else TEXT}; font-size: 13px;"
            )
            layout.addWidget(label)
            layout.addStretch()
            hint = QLabel("drag" if chain.draggable else "locked")
            hint.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            layout.addWidget(hint)
            row.mousePressEvent = (  # type: ignore[method-assign]
                lambda event, ch=chain: self._on_chain_row_clicked(ch)
            )
            self.chains_list_layout.addWidget(row)

    def _on_chain_row_clicked(self, chain: IKChain) -> None:
        self._highlight_end = None if chain.end == self._highlight_end else chain.end
        self._refresh_chain_list()
        self._refresh_preview()

    def _refresh_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setHidden(not message)

    # ============================================================ Qt events
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_preview()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._needs_frames = True
        self._update_timer_running()
        self._refresh_preview()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._update_timer_running()
