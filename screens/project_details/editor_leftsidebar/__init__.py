"""Left sidebar (media library) package for the project video editor."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .animation_tab import AnimationTab
from .audio_tab import AudioTab
from .background_tab import BackgroundTab
from .character_tab import CharacterTab
from .chat_tab import ChatTab
from .common import (
    BUTTON_STYLE,
    LIST_STYLE,
    PANEL_LABEL_STYLE,
    PANEL_STYLE,
)
from .effect_tab import EffectTab
from .tools_tab import ToolsTab

__all__ = [
    "EditorLeftSidebar",
    "BUTTON_STYLE",
    "LIST_STYLE",
    "PANEL_LABEL_STYLE",
    "PANEL_STYLE",
]


class EditorLeftSidebar(QFrame):
    """Left sidebar of the project editor: media library with category tabs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(PANEL_STYLE)
        self.setFixedWidth(300)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.project_id: int | None = None

        # ---- Callbacks (set by the project editor after construction) ----
        self.on_add_timeline_row = None      # callable()
        self.on_remove_selected = None       # callable()
        self.on_add_asset_to_timeline = None  # callable(kind: str, asset_id: int)
        self.on_edit_character = None        # callable(character_id: int)
        self.on_add_text = None              # callable(text: str)
        self.on_add_audio = None             # callable() - opens the Add Audio slider
        self.on_scale_changed = None         # callable(percent: int)
        self.on_scale_commit = None          # callable()
        self.on_position_changed = None      # callable(point_key, value: int)
        self.on_position_commit = None       # callable()
        self.on_flip_h = None                # callable(bool)
        self.on_flip_v = None                # callable(bool)
        self.on_speed_changed = None         # callable(value: float)
        self.on_speed_commit = None          # callable()
        self.on_nudge = None                 # callable(direction: str)
        self.on_zoom_changed = None          # callable(point_key: str, value: int)
        self.on_zoom_commit = None           # callable()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # ---- Add TimelineRow button (above the library tabs) ----
        add_timeline_row_btn = QPushButton("＋ Add Timeline Row")
        add_timeline_row_btn.setCursor(Qt.PointingHandCursor)
        add_timeline_row_btn.setStyleSheet(BUTTON_STYLE)
        add_timeline_row_btn.clicked.connect(self._on_add_timeline_row_clicked)
        layout.addWidget(add_timeline_row_btn)

        # ---- Category switcher buttons at top ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._lib_buttons = {}
        for key, label in (
            ("character", "Char"),
            ("background", "Bg"),
            ("audio", "Audio"),
            ("animation", "Anim"),
            ("tools", "Tools"),
            ("effect", "Effect"),
            ("chat", "Chat"),
        ):
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                BUTTON_STYLE
                # one more tab: tighter padding so all five fit
                + "QPushButton { padding: 8px 4px; font-size: 12px; }"
                + "QPushButton:checked { background-color: #1d4ed8; }"
            )
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, k=key: self._switch_library(k)
            )
            btn_row.addWidget(button)
            self._lib_buttons[key] = button
        layout.addLayout(btn_row)

        # ---- Tab widgets ----
        self.character_tab = CharacterTab()
        self.background_tab = BackgroundTab()
        self.audio_tab = AudioTab()
        self.animation_tab = AnimationTab()
        self.tools_tab = ToolsTab()
        self.effect_tab = EffectTab()
        self.chat_tab = ChatTab()

        self._tabs = {
            "character": self.character_tab,
            "background": self.background_tab,
            "audio": self.audio_tab,
            "animation": self.animation_tab,
            "tools": self.tools_tab,
            "effect": self.effect_tab,
            "chat": self.chat_tab,
        }
        for tab in self._tabs.values():
            layout.addWidget(tab)

        self._wire_callbacks()

        # ---- Compatibility aliases for the old flat-sidebar attributes ----
        self.character_list = self.character_tab.list
        self.background_list = self.background_tab.list
        self.audio_list = self.audio_tab.list
        self.animation_list = self.animation_tab.list
        self.tools_list = self.tools_tab.list
        self.effect_list = self.effect_tab.list
        self.chat_panel = self.chat_tab.panel

        self.text_input = self.tools_tab.text_input
        self.scale_value_label = self.tools_tab.scale_value_label
        self.scale_slider = self.tools_tab.scale_slider
        self.scale_spin = self.tools_tab.scale_spin
        self.speed_spin = self.tools_tab.speed_spin
        self.flip_h_btn = self.tools_tab.flip_h_btn
        self.flip_v_btn = self.tools_tab.flip_v_btn
        self.drag_mode_start = self.tools_tab.drag_mode_start
        self.drag_mode_end = self.tools_tab.drag_mode_end
        self._pos_spins = self.tools_tab._pos_spins
        self._zoom_spins = self.effect_tab._zoom_spins

        self._lib_lists = {
            key: getattr(tab, "list", getattr(tab, "panel", None))
            for key, tab in self._tabs.items()
        }
        self._lib_captions = {
            key: getattr(tab, "caption", None)
            for key, tab in self._tabs.items()
        }

        # Remember which library list the user clicked last + track selections
        self._last_media_list = None
        self._selected_character_id = None
        self._selected_animation_id = None
        for widget in self._lib_lists.values():
            if hasattr(widget, "itemClicked"):
                widget.itemClicked.connect(
                    lambda _item, w=widget: self._on_library_item_clicked(w)
                )

        remove_btn = QPushButton("✕ Remove Selected Clip")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(BUTTON_STYLE)
        remove_btn.clicked.connect(self._on_remove_clicked)
        layout.addWidget(remove_btn)

        # default view: show only character list
        self._switch_library("character")

    # ------------------------------------------------------------- wiring
    def _wire_callbacks(self) -> None:
        self.character_tab.on_add_asset = self._on_add_asset_clicked
        self.character_tab.on_edit_character = self._on_edit_character_clicked

        for tab in (
            self.background_tab,
            self.audio_tab,
            self.animation_tab,
        ):
            tab.on_add_asset = self._on_add_asset_clicked

        self.audio_tab.on_add_audio = (
            lambda: self._dispatch("on_add_audio")
        )

        self.tools_tab.on_add_text = (
            lambda text: self._dispatch("on_add_text", text)
        )
        self.tools_tab.on_scale_changed = (
            lambda value: self._dispatch("on_scale_changed", value)
        )
        self.tools_tab.on_scale_commit = (
            lambda: self._dispatch("on_scale_commit")
        )
        self.tools_tab.on_position_changed = (
            lambda key, value: self._dispatch("on_position_changed", key, value)
        )
        self.tools_tab.on_position_commit = (
            lambda: self._dispatch("on_position_commit")
        )
        self.tools_tab.on_flip_h = (
            lambda checked: self._dispatch("on_flip_h", checked)
        )
        self.tools_tab.on_flip_v = (
            lambda checked: self._dispatch("on_flip_v", checked)
        )
        self.tools_tab.on_speed_changed = (
            lambda value: self._dispatch("on_speed_changed", value)
        )
        self.tools_tab.on_speed_commit = (
            lambda: self._dispatch("on_speed_commit")
        )
        self.tools_tab.on_nudge = (
            lambda direction: self._dispatch("on_nudge", direction)
        )

        self.effect_tab.on_zoom_changed = (
            lambda key, value: self._dispatch("on_zoom_changed", key, value)
        )
        self.effect_tab.on_zoom_commit = (
            lambda: self._dispatch("on_zoom_commit")
        )
        self.effect_tab.on_nudge = (
            lambda direction: self._dispatch("on_nudge", direction)
        )

    def _dispatch(self, name: str, *args) -> None:
        callback = getattr(self, name, None)
        if callable(callback):
            callback(*args)

    # ------------------------------------------------------------- actions
    def _on_add_timeline_row_clicked(self) -> None:
        self._dispatch("on_add_timeline_row")

    def _on_add_asset_clicked(self, kind: str, asset_id: int) -> None:
        self._dispatch("on_add_asset_to_timeline", kind, asset_id)

    def _on_edit_character_clicked(self, character_id: int) -> None:
        self._dispatch("on_edit_character", character_id)

    def _on_remove_clicked(self) -> None:
        self._dispatch("on_remove_selected")

    def _switch_library(self, key: str) -> None:
        for k, button in self._lib_buttons.items():
            button.setChecked(k == key)
        for k, tab in self._tabs.items():
            tab.setVisible(k == key)

    # ------------------------------------------------------------- data
    def set_project(self, project_id: int | None) -> None:
        """Remember which project's library to show (global + this project)."""
        self.project_id = int(project_id) if project_id is not None else None
        self.audio_tab.set_project(self.project_id)

    def _refresh_media(self) -> None:
        self.character_tab.refresh()
        self.background_tab.refresh()
        self.audio_tab.set_project(self.project_id)
        self.audio_tab.refresh()
        self.refresh_animations()

    def refresh_animations(self) -> None:
        """Fill the Animations tab with only the selected character's animations."""
        self.animation_tab.refresh()

    def set_anim_character(self, character_id: int | None) -> None:
        """Filter the Animations tab to one character's animations."""
        self.animation_tab.set_character(character_id)

    @property
    def _anim_character_id(self) -> int | None:
        return self.animation_tab.character_id

    @_anim_character_id.setter
    def _anim_character_id(self, value: int | None) -> None:
        self.animation_tab.character_id = (
            int(value) if value is not None else None
        )

    def _on_library_item_clicked(self, widget) -> None:
        self._last_media_list = widget
        item = widget.currentItem()
        if item is None or item.data(Qt.UserRole) is None:
            return
        kind, asset_id = item.data(Qt.UserRole)
        if kind == "character":
            self._selected_character_id = asset_id
        elif kind == "animation":
            self._selected_animation_id = asset_id

    def _selected_media(self):
        """(kind, id) of the selected media item, from the list last clicked."""
        if getattr(self, "_last_media_list", None) is not None:
            item = self._last_media_list.currentItem()
            if item is not None and item.data(Qt.UserRole) is not None:
                return item.data(Qt.UserRole)
        # Fallback: any list that has a selection
        for widget in (
            self.character_list,
            self.background_list,
            self.audio_list,
            self.animation_list,
        ):
            item = widget.currentItem()
            if item is not None and item.data(Qt.UserRole) is not None:
                return item.data(Qt.UserRole)
        return None

    # ------------------------------------------------------------- delegates
    def set_character_scale(self, percent: int) -> None:
        """Reflect the selected character's size on the slider (no callbacks)."""
        self.tools_tab.set_character_scale(percent)

    def set_character_positions(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> None:
        """Reflect the selected character's start/end positions (no callbacks)."""
        self.tools_tab.set_character_positions(
            start_x, start_y, end_x, end_y
        )

    def drag_point_mode(self) -> str:
        """Which point the next stage-drag defines: "start" or "end"."""
        return self.tools_tab.drag_point_mode()

    def set_character_speed(self, value: float) -> None:
        """Reflect the selected character's animation speed (no callbacks)."""
        self.tools_tab.set_character_speed(value)

    def set_character_flip(self, flip_h: bool, flip_v: bool) -> None:
        """Reflect the selected character's mirror flags (no callbacks)."""
        self.tools_tab.set_character_flip(flip_h, flip_v)

    def set_clip_zoom(self, start_pct: int, end_pct: int) -> None:
        """Reflect the selected clip's frame zoom (no callbacks)."""
        self.effect_tab.set_clip_zoom(start_pct, end_pct)
