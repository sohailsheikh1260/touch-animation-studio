"""Audio pieces of the project editor: player, drawer, clips and export data."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

import database
from screens.audio import audio_store
from screens.audio.audio_drawer import AudioDrawer
from screens.audio.audio_shared import PROJECT_SCOPE
from screens.project_details.clip import Clip

DEFAULT_AUDIO_SEC = 5


class AudioEditorMixin:
    """Audio methods for ProjectEditorPage; the page owns the widgets/timeline."""

    def _init_audio(self) -> None:
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)
        self._playing_audio_uid = None
        # Qt ignores a seek until the source is loaded, so hold it briefly.
        self._pending_seek_ms = 0
        self._player.mediaStatusChanged.connect(self._on_audio_media_status)

    def _setup_audio_drawer(self) -> None:
        self.audio_drawer = AudioDrawer(self)
        self.audio_drawer.audio_saved.connect(self._on_audio_added)
        self.audio_drawer.audio_deleted.connect(self._on_audio_added)
        self.audio_drawer.status_changed.connect(self.status_label.setText)

    def _resize_audio_drawer(self) -> None:
        drawer = getattr(self, "audio_drawer", None)
        if drawer is not None:
            drawer.setGeometry(self.rect())

    def _hide_audio_drawer(self) -> None:
        drawer = getattr(self, "audio_drawer", None)
        if drawer is not None:
            drawer.hide_drawer()

    def _stop_audio_drawer_playback(self) -> None:
        drawer = getattr(self, "audio_drawer", None)
        if drawer is not None:
            drawer.stop_playback()

    def _build_audio_track_delete_row(self) -> QWidget | None:
        """Delete button for the selected audio clip, or None when unused."""
        if not self.timeline.audio_clips:
            return None
        row = QWidget()
        row.setFixedHeight(self.timeline.TRACK_H - 4)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        btn = QPushButton("✕")
        btn.setFixedSize(24, self.timeline.TRACK_H - 4)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: #7f1d1d; color: #ffffff; border: none; "
            "border-radius: 4px; padding: 0; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #991b1b; }"
        )
        btn.setToolTip("Delete the selected audio clip")
        btn.clicked.connect(self._delete_selected_audio)
        layout.addWidget(btn)
        return row

    def _delete_selected_audio(self) -> None:
        """✕ on the audio lane: remove the currently selected audio clip."""
        clip = None
        uid = self.timeline.selected_uid
        if uid is not None:
            for c in self.timeline.audio_clips:
                if c.uid == uid:
                    clip = c
                    break
        if clip is None:
            self.status_label.setText(
                "Select an audio clip on the audio track first."
            )
            return
        self.timeline.audio_clips.remove(clip)
        self.timeline.selected_uid = None
        self.timeline._refresh_size()
        self._fit_timeline_height()
        self._on_timeline_change()
        self.status_label.setText(f"Audio clip removed ({clip.name}).")

    def _open_add_audio(self) -> None:
        """Audio tab "+": open the Add Audio drawer inside this editor page."""
        self._stop_playback()
        self._flush_deferred()  # persist any pending clip edits first
        project_id = getattr(self, "project_id", None)
        if project_id is not None:
            self.audio_drawer.open_drawer(
                scope=PROJECT_SCOPE, project_id=project_id
            )
        else:
            self.audio_drawer.open_drawer()

    def _on_audio_added(self, message: str) -> None:
        """Refresh the sidebar audio list after the drawer saves/deletes."""
        self.left_sidebar.audio_tab.refresh()
        self.status_label.setText(message)

    def _add_audio_clip_to_timeline(self, audio_id: int) -> None:
        name = self._audio_display_name(audio_id)
        clip = Clip(
            0.0,
            self._audio_duration_for(audio_id),
            f"🎵 {name}",
            "audio",
            ("audio", audio_id),
            track=-1,
        )
        # add_clip appends audio clips at the end of the audio track automatically.
        self.timeline.add_clip(clip)
        self.status_label.setText(f"Added audio '{name}' to the timeline.")

    def _audio_duration_for(self, audio_id: int) -> float:
        """Duration of an audio file in seconds (falls back to the default)."""
        default_dur = float(DEFAULT_AUDIO_SEC)
        try:
            audio = database.get_audio(int(audio_id))
            path = audio_store.absolute_path(audio["audio_path"]) if audio else None
            if path is None or not path.is_file():
                return default_dur
            player = QMediaPlayer()
            try:
                player.setSource(QUrl.fromLocalFile(str(path)))
                dur = float(player.duration() or 0.0)
            finally:
                player.stop()
                try:
                    player.setSource(QUrl())
                except Exception:
                    pass
            if dur > 0.0:
                return dur
        except Exception:
            pass
        return default_dur

    def _audio_display_name(self, audio_id: int) -> str:
        try:
            return database.get_audio(audio_id)["name"]
        except Exception:
            return f"Audio {audio_id}"

    def _audio_clip_rows(self) -> list[tuple]:
        rows = []
        for clip in self.timeline.audio_clips:
            asset_kind, asset_id = clip.data[:2]
            rows.append(("audio", asset_kind, asset_id, clip.start, clip.duration, 0, "idle"))
        return rows

    def _pause_audio(self) -> None:
        self._player.stop()
        self._playing_audio_uid = None
        self._pending_seek_ms = 0

    def _stop_audio_playback(self) -> None:
        self._pause_audio()
        # Release the decoder so QMediaPlayer's internal threads wind down
        # now, not during app teardown (which would abort: "QThread:
        # Destroyed while thread is still running").
        self._player.setSource(QUrl())

    def _sync_audio_playback(self, audio_clip) -> None:
        if audio_clip is not None and self._playing_audio_uid != audio_clip.uid:
            self._play_clip_audio(audio_clip)
        elif audio_clip is None and self._playing_audio_uid is not None:
            self._pause_audio()

    def _play_clip_audio(self, clip: Clip) -> None:
        kind, asset_id = clip.data
        audio = database.get_audio(asset_id)
        if not audio["audio_path"]:
            return
        path = audio_store.absolute_path(audio["audio_path"])
        if not path.is_file():
            return
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        # Seek to the playhead position inside the clip. Qt ignores seeks set
        # before LoadedMedia, so _on_audio_media_status applies it later.
        self._pending_seek_ms = int(max(0.0, self.timeline.playhead - clip.start) * 1000)
        self._player.play()
        self._playing_audio_uid = clip.uid

    def _on_audio_media_status(self, status) -> None:
        """Apply the pending playhead offset once the audio source is loaded."""
        pending = self._pending_seek_ms
        if pending <= 0 or status != QMediaPlayer.MediaStatus.LoadedMedia:
            return
        self._pending_seek_ms = 0
        self._player.setPosition(pending)

    def _audio_export_data(self, timeline) -> list[dict]:
        data = []
        for clip in timeline.audio_clips:
            _kind, asset_id = clip.data
            audio = database.get_audio(asset_id)
            path = (
                audio_store.absolute_path(audio["audio_path"])
                if audio["audio_path"] else None
            )
            data.append(
                {
                    "start": clip.start,
                    "duration": clip.duration,
                    "path": str(path) if path and path.is_file() else "",
                    "name": audio["name"],
                }
            )
        return data
