"""Audio module screen - CRUD with audio files instead of images (SQLite-backed).

Grid of audio boxes (type icon + name + library), "＋ Create Audio" button
opens a drawer that slides in from the right with a name field, an audio type,
a global/project library selector, an audio-file picker and a Play button.
Clicking an existing box opens the drawer in edit mode. The Dialogs type also
gets a separate multi-file "Add Audio" option.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import database
from screens.audio.audio_drawer import AudioDrawer
from screens.audio.audio_shared import (
    AUDIO_TYPE_ICONS,
    AUDIO_TYPE_LABELS,
    CARD_H,
    CARD_LABEL_STYLE,
    CARD_STYLE,
    CARD_W,
    COMBO_STYLE,
    CREATE_BUTTON_STYLE,
    GLOBAL_SCOPE,
    GRID_COLUMNS,
    PROJECT_SCOPE,
    TOP_BUTTON_STYLE,
)
from screens.theme import BG, MUTED, TEXT

ICON = "🔊"
NAME = "Audio"
DESC = "Add music and sound effects"
INFO = (ICON, NAME, DESC)


class AudioScreen(QWidget):
    def __init__(self, go_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        database.init_db()

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(14)

        # ---- Top bar ----
        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(TOP_BUTTON_STYLE)
        back_btn.clicked.connect(self._on_leave)

        self.title = QLabel(f"{ICON}  Audio")
        self.title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")

        create_btn = QPushButton("＋ Create Audio")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.setStyleSheet(CREATE_BUTTON_STYLE)
        create_btn.clicked.connect(lambda: self.open_drawer())

        top_bar = QHBoxLayout()
        top_bar.addWidget(back_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.title)
        top_bar.addStretch()
        top_bar.addWidget(create_btn)
        root.addLayout(top_bar)

        # ---- Library filters (type + global/project) ----
        filters = QHBoxLayout()
        filters.setSpacing(8)
        type_label = QLabel("Type")
        type_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        self.type_filter = QComboBox()
        self.type_filter.setStyleSheet(COMBO_STYLE)
        self.type_filter.addItem("All types", "all")
        for audio_type in database.AUDIO_TYPES:
            self.type_filter.addItem(
                AUDIO_TYPE_LABELS.get(audio_type, audio_type.title()), audio_type
            )
        self.type_filter.currentIndexChanged.connect(self._on_filters_changed)
        filters.addWidget(type_label)
        filters.addWidget(self.type_filter)
        filters.addSpacing(14)

        library_label = QLabel("Library")
        library_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        self.project_filter = QComboBox()
        self.project_filter.setStyleSheet(COMBO_STYLE)
        self.project_filter.currentIndexChanged.connect(self._on_filters_changed)
        filters.addWidget(library_label)
        filters.addWidget(self.project_filter)
        filters.addStretch()
        root.addLayout(filters)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        root.addWidget(self.status_label, 0, Qt.AlignLeft)

        # ---- Audio boxes grid (scrollable) ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        self.empty_label = QLabel("No audio yet — click “＋ Create Audio”!")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
        root.addWidget(self.empty_label, 1)
        self.empty_label.hide()

        root.addWidget(self.scroll, 1)

        # ---- Slide-in drawer + overlay (shared reusable component) ----
        self.audio_drawer = AudioDrawer(self)
        self.audio_drawer.audio_saved.connect(self._on_drawer_saved)
        self.audio_drawer.audio_deleted.connect(self._on_drawer_saved)
        self.audio_drawer.status_changed.connect(self.status_label.setText)

        # Compatibility aliases for the old drawer attributes.
        self.overlay = self.audio_drawer.overlay
        self.drawer = self.audio_drawer.panel
        self._anim = self.audio_drawer._anim
        self._player = self.audio_drawer._player
        self._audio_output = self.audio_drawer._audio_output
        self.drawer_title = self.audio_drawer.drawer_title
        self.drawer_name = self.audio_drawer.drawer_name
        self.drawer_type = self.audio_drawer.drawer_type
        self.drawer_scope = self.audio_drawer.drawer_scope
        self.file_label = self.audio_drawer.file_label
        self.play_btn = self.audio_drawer.play_btn
        self.dialog_add_btn = self.audio_drawer.dialog_add_btn
        self.delete_btn = self.audio_drawer.delete_btn
        self.save_btn = self.audio_drawer.save_btn

        self.refresh()

    # -------------------------------------------------------- Filter bar
    def _populate_filters(self) -> None:
        """Refresh the project list (projects may be added/deleted elsewhere)."""
        current = self.project_filter.currentData()
        self.project_filter.blockSignals(True)
        self.project_filter.clear()
        self.project_filter.addItem("All audio", "all")
        self.project_filter.addItem("Global audio", GLOBAL_SCOPE)
        for project in database.list_projects():
            self.project_filter.addItem(f"Project: {project['name']}", project["id"])
        index = self.project_filter.findData(current)
        self.project_filter.setCurrentIndex(index if index >= 0 else 0)
        self.project_filter.blockSignals(False)

    def _on_filters_changed(self) -> None:
        self.refresh()

    def _filter_scope(self):
        """(scope, project_id) for the library filter combo."""
        value = self.project_filter.currentData()
        if value == GLOBAL_SCOPE:
            return GLOBAL_SCOPE, None
        if isinstance(value, int):
            return PROJECT_SCOPE, value
        return None, None

    # ------------------------------------------------------------ Drawer
    def open_drawer(self, audio_id: int | None = None) -> None:
        filter_scope, filter_project = self._filter_scope()
        self.audio_drawer.open_drawer(
            audio_id,
            scope=filter_scope or GLOBAL_SCOPE,
            project_id=filter_project,
            audio_type=self.type_filter.currentData(),
        )

    def close_drawer(self) -> None:
        self.audio_drawer.close_drawer()

    def _on_drawer_saved(self, message: str) -> None:
        self.refresh()
        self.status_label.setText(message)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        # Projects may have been created/deleted while this screen was hidden.
        self.refresh()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().hideEvent(event)
        if hasattr(self, "audio_drawer"):
            self.audio_drawer.hide_drawer()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if hasattr(self, "audio_drawer"):
            self.audio_drawer.setGeometry(self.rect())

    def _on_leave(self) -> None:
        self.audio_drawer.hide_drawer()
        window = self.window()
        if hasattr(window, "show_home"):
            window.show_home()

    def stop_playback(self) -> None:
        """Stop any playing audio (used for clean app shutdown)."""
        self.audio_drawer.stop_playback()

    # ------------------------------------------------------------ Grid list
    def refresh(self) -> None:
        self._populate_filters()
        scope, project_id = self._filter_scope()
        audio_type = self.type_filter.currentData() or "all"
        audios = database.list_audios(
            project_id=project_id, scope=scope, audio_type=audio_type
        )
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_items = bool(audios)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

        for i, audio in enumerate(audios):
            card = self._make_card(audio)
            row, col = divmod(i, GRID_COLUMNS)
            self.grid.addWidget(card, row, col)
        self.status_label.setText(
            f"{len(audios)} audio(s) · files stored in audios/ folder"
        )

    def _make_card(self, audio) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(CARD_W, CARD_H)
        card.setStyleSheet(CARD_STYLE)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(6)

        audio_type = audio["audio_type"] if "audio_type" in audio.keys() else "effect"
        icon = AUDIO_TYPE_ICONS.get(audio_type, "🎵")
        icon_label = QLabel(icon if audio["audio_path"] else "🔇")
        icon_label.setStyleSheet(
            f"font-size: 50px; background-color: {BG}; border: none; border-radius: 8px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedHeight(124)

        name_label = QLabel(audio["name"])
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: bold; {CARD_LABEL_STYLE}"
        )
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)

        type_label = AUDIO_TYPE_LABELS.get(audio_type, audio_type.title())
        scope = audio["scope"] if "scope" in audio.keys() else GLOBAL_SCOPE
        if scope == PROJECT_SCOPE:
            project_id = audio["project_id"] if "project_id" in audio.keys() else None
            project = database.get_project(project_id) if project_id else None
            where = project["name"] if project is not None else "Project"
        else:
            where = "Global"
        meta_label = QLabel(f"{type_label} · {where}")
        meta_label.setStyleSheet(f"color: {MUTED}; font-size: 11px; {CARD_LABEL_STYLE}")
        meta_label.setAlignment(Qt.AlignHCenter)
        meta_label.setWordWrap(True)

        inner.addWidget(icon_label)
        inner.addWidget(name_label)
        inner.addWidget(meta_label)

        def mousePressEvent(event, aid=audio["id"]):  # noqa: N802 (Qt naming)
            if event.button() == Qt.LeftButton:
                self.open_drawer(aid)

        card.mousePressEvent = mousePressEvent
        return card
