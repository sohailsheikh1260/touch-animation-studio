"""Audio library tab for the project editor sidebar."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

import database
from screens.audio import audio_store

from .common import BUTTON_STYLE, ListTab


class AudioTab(ListTab):
    """Global audio plus the current project's audio."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("🔊 Audio", parent=parent)
        self.project_id: int | None = None

        # Callback set by the sidebar: opens the existing Add Audio drawer.
        self.on_add_audio = None

        self.add_audio_btn = QPushButton("＋ Add Audio")
        self.add_audio_btn.setCursor(Qt.PointingHandCursor)
        self.add_audio_btn.setStyleSheet(BUTTON_STYLE)
        self.add_audio_btn.setToolTip("Open the Add Audio slider")
        self.add_audio_btn.clicked.connect(self._on_add_audio_clicked)
        self.layout().addWidget(self.add_audio_btn)

    def set_project(self, project_id: int | None) -> None:
        """Remember which project's audio library to show."""
        self.project_id = int(project_id) if project_id is not None else None

    def _on_add_audio_clicked(self) -> None:
        callback = getattr(self, "on_add_audio", None)
        if callable(callback):
            callback()

    def refresh(self) -> None:
        """Rebuild the audio list from the database."""
        self.list.clear()
        audios = (
            database.list_audios_for_project(self.project_id)
            if self.project_id is not None
            else database.list_audios()
        )
        for audio in audios:
            has_file = bool(audio["audio_path"]) and audio_store.absolute_path(
                audio["audio_path"]
            ).is_file()
            self.add_asset_row(
                ("🎵 " if has_file else "🔇 ") + audio["name"],
                "audio",
                audio["id"],
            )
