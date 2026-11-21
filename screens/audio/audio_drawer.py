"""Reusable slide-in drawer for adding/editing audio records.

Used by both the Audio module screen and the project editor, so the add-audio
form and its file handling exist in exactly one place.
"""

import os
import sys
import tempfile
import time

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QProcess,
    QUrl,
    Qt,
    Signal,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import database
from screens.audio import audio_store
from screens.audio.tts_worker import finalize_wav_header, list_local_voices
from screens.theme import BG, CARD_BG, MUTED, TEXT
from screens.image_store import PROJECT_ROOT

try:
    import pyttsx3

    _PYTTSX3_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the local environment
    pyttsx3 = None
    _PYTTSX3_AVAILABLE = False

try:
    import edge_tts  # noqa: F401 - only needed inside the worker process

    _EDGE_TTS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the local environment
    _EDGE_TTS_AVAILABLE = False

from .audio_shared import (
    AUDIO_FILTER,
    AUDIO_TYPE_LABELS,
    CARD_LABEL_STYLE,
    COMBO_STYLE,
    DANGER_BUTTON_STYLE,
    DRAWER_WIDTH,
    EDGE_TTS_VOICES,
    GLOBAL_SCOPE,
    INPUT_STYLE,
    MODEL_EDGE,
    MODEL_LABELS,
    MODEL_LOCAL,
    PLAY_BUTTON_STYLE,
    PROJECT_SCOPE,
    SAVE_BUTTON_STYLE,
    TOP_BUTTON_STYLE,
)


class AudioDrawer(QWidget):
    """Translucent overlay that hosts the Add/Edit Audio side panel.

    The widget fills its parent, dims the page behind it, and slides the same
    drawer panel used by the Audio module screen. It emits signals after a
    save/delete so the host can refresh its own audio list.
    """

    audio_saved = Signal(str)    # message after creating/updating audio
    audio_deleted = Signal(str)  # message after deleting audio
    status_changed = Signal(str)  # transient status text (e.g. play errors)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editing_id: int | None = None
        self._pending_audio: str | None = None
        self._pending_dialog_files: list[str] = []
        self._generated_audio_path: str | None = None
        self._tts_process: QProcess | None = None
        self._tts_text_file: str | None = None
        self._tts_generation: int = 0
        self._tts_current_model: str = MODEL_LOCAL
        self._tts_started_at: float = 0.0
        self._stale_processes: list[QProcess] = []
        self._tts_generating: bool = False
        self._tts_source_text: str = ""

        # Audio playback for previewing the chosen/saved file.
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.overlay.hide()
        self.overlay.installEventFilter(self)

        self.panel = QFrame(self)
        self.panel.setFixedWidth(DRAWER_WIDTH)
        self.panel.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG};"
            "  border-left: 2px solid #7c3aed; }"
        )
        self._build_panel(self.panel)

        self._anim = QPropertyAnimation(self.panel, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        self.hide()

    # --------------------------------------------------------------- UI
    def _build_panel(self, panel: QFrame) -> None:
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.drawer_title = QLabel("Create Audio")
        self.drawer_title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: bold;"
        )
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(TOP_BUTTON_STYLE)
        close_btn.clicked.connect(self.close_drawer)
        header.addWidget(self.drawer_title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        name_hint = QLabel("Audio name")
        name_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.drawer_name = QLineEdit()
        self.drawer_name.setPlaceholderText("e.g. Epic Battle Theme")
        self.drawer_name.setStyleSheet(INPUT_STYLE)
        layout.addWidget(name_hint)
        layout.addWidget(self.drawer_name)

        type_hint = QLabel("Audio type")
        type_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.drawer_type = QComboBox()
        self.drawer_type.setStyleSheet(COMBO_STYLE)
        for audio_type in database.AUDIO_TYPES:
            self.drawer_type.addItem(
                AUDIO_TYPE_LABELS.get(audio_type, audio_type.title()),
                audio_type,
            )
        self.drawer_type.currentIndexChanged.connect(self._on_drawer_type_changed)
        layout.addWidget(type_hint)
        layout.addWidget(self.drawer_type)

        scope_hint = QLabel("Add to")
        scope_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.drawer_scope = QComboBox()
        self.drawer_scope.setStyleSheet(COMBO_STYLE)
        layout.addWidget(scope_hint)
        layout.addWidget(self.drawer_scope)

        audio_hint = QLabel("Audio file")
        audio_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        choose_btn = QPushButton("🎵  Choose Audio File...")
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.setStyleSheet(TOP_BUTTON_STYLE)
        choose_btn.clicked.connect(self._on_choose_audio)

        self.file_label = QLabel("No audio file chosen")
        self.file_label.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.file_label.setWordWrap(True)

        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(PLAY_BUTTON_STYLE)
        self.play_btn.clicked.connect(self._on_play_toggle)
        self.play_btn.hide()  # only visible once a file is chosen/saved

        # Dialogs-only: add several dialog audio files in one go. Every other
        # audio type keeps the original single-file "Choose Audio File" flow.
        self.dialog_add_btn = QPushButton("＋ Add Audio (multiple)")
        self.dialog_add_btn.setCursor(Qt.PointingHandCursor)
        self.dialog_add_btn.setStyleSheet(TOP_BUTTON_STYLE)
        self.dialog_add_btn.setToolTip(
            "Choose several dialog audio files; each becomes its own entry"
        )
        self.dialog_add_btn.clicked.connect(self._on_add_dialog_audios)
        self.dialog_add_btn.hide()

        layout.addWidget(audio_hint)
        layout.addWidget(choose_btn)
        layout.addWidget(self.dialog_add_btn)
        layout.addWidget(self.file_label)
        layout.addWidget(self.play_btn)

        # ---- Text to Audio (offline TTS via pyttsx3) ----
        tts_hint = QLabel("Text to Audio")
        tts_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.tts_text = QPlainTextEdit()
        self.tts_text.setPlaceholderText("Enter or paste text to convert to speech...")
        self.tts_text.setFixedHeight(84)
        self.tts_text.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 8px;"
            "  padding: 8px 12px; font-size: 14px; }"
        )

        # ---- TTS model (engine) choice ----
        model_hint = QLabel("Model")
        model_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.tts_model_combo = QComboBox()
        self.tts_model_combo.setStyleSheet(COMBO_STYLE)
        self.tts_model_combo.currentIndexChanged.connect(
            self._on_tts_model_changed
        )

        # ---- Voice choice (per model) ----
        voice_hint = QLabel("Voice")
        voice_hint.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.setStyleSheet(COMBO_STYLE)

        self.generate_audio_btn = QPushButton("Generate Audio")
        self.generate_audio_btn.setCursor(Qt.PointingHandCursor)
        self.generate_audio_btn.setStyleSheet(TOP_BUTTON_STYLE)
        if not _PYTTSX3_AVAILABLE and not _EDGE_TTS_AVAILABLE:
            self.generate_audio_btn.setEnabled(False)
            self.generate_audio_btn.setToolTip("No TTS engine is installed")
        self.generate_audio_btn.clicked.connect(self._on_generate_audio)

        # Indeterminate progress bar shown while the TTS worker runs off-thread.
        self.tts_busy = QProgressBar()
        self.tts_busy.setRange(0, 0)  # indeterminate (busy) mode
        self.tts_busy.setTextVisible(False)
        self.tts_busy.setFixedHeight(6)
        self.tts_busy.setStyleSheet(
            f"QProgressBar {{ background-color: {BG}; border: none;"
            "  border-radius: 3px; }"
            "  QProgressBar::chunk { background-color: #7c3aed; border-radius: 3px; }"
        )
        self.tts_busy.hide()

        self.tts_status = QLabel("")
        self.tts_status.setStyleSheet(
            f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"
        )
        self.tts_status.setWordWrap(True)

        layout.addWidget(tts_hint)
        layout.addWidget(self.tts_text)
        layout.addWidget(model_hint)
        layout.addWidget(self.tts_model_combo)
        layout.addWidget(voice_hint)
        layout.addWidget(self.tts_voice_combo)
        layout.addWidget(self.generate_audio_btn)
        layout.addWidget(self.tts_busy)
        layout.addWidget(self.tts_status)
        layout.addStretch()

        self._populate_tts_models()

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾  Save Audio")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    # ---------------------------------------------------------- behavior
    def _fit_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())

    def _populate_scope_choices(
        self, scope: str = GLOBAL_SCOPE, project_id: int | None = None
    ) -> None:
        self.drawer_scope.blockSignals(True)
        self.drawer_scope.clear()
        self.drawer_scope.addItem("Global (all projects)", GLOBAL_SCOPE)
        for project in database.list_projects():
            self.drawer_scope.addItem(f"Project: {project['name']}", project["id"])
        if scope == PROJECT_SCOPE and project_id is not None:
            index = self.drawer_scope.findData(int(project_id))
            self.drawer_scope.setCurrentIndex(index if index >= 0 else 0)
        else:
            self.drawer_scope.setCurrentIndex(0)
        self.drawer_scope.blockSignals(False)

    def _drawer_scope(self) -> tuple[str, int | None]:
        value = self.drawer_scope.currentData()
        if isinstance(value, int):
            return PROJECT_SCOPE, value
        return GLOBAL_SCOPE, None

    def _on_drawer_type_changed(self) -> None:
        """Dialogs get the extra multi-file Add Audio option; others don't."""
        show = (
            self._editing_id is None
            and self.drawer_type.currentData() == "dialogs"
        )
        if not show and self._pending_dialog_files:
            self._pending_dialog_files = []
            self._show_file("")
        self.dialog_add_btn.setVisible(show)

    # --------------------------------------------------- TTS model/voice
    def _populate_tts_models(self) -> None:
        """Fill the model (engine) dropdown with every installed engine."""
        combo = self.tts_model_combo
        combo.blockSignals(True)
        combo.clear()
        for model, available in (
            (MODEL_EDGE, _EDGE_TTS_AVAILABLE),
            (MODEL_LOCAL, _PYTTSX3_AVAILABLE),
        ):
            label = MODEL_LABELS[model]
            if not available:
                label += " — not installed"
            combo.addItem(label, model)
            item = combo.model().item(combo.count() - 1)
            item.setEnabled(available)
            item.setToolTip(
                "" if available else f"{label.rsplit(' — ', 1)[0]} engine package is missing."
            )
        # Prefer Edge TTS when available (better voices), else Local.
        default = (
            MODEL_EDGE if _EDGE_TTS_AVAILABLE else MODEL_LOCAL
        )
        index = combo.findData(default)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)
        self._on_tts_model_changed()

    def _on_tts_model_changed(self) -> None:
        if self._tts_generating:
            return  # repopulated after generation ends
        self._populate_tts_voices()

    def _populate_tts_voices(self) -> None:
        """Fill the voice dropdown with the voices of the chosen model."""
        combo = self.tts_voice_combo
        combo.clear()
        if self.tts_model_combo.currentData() == MODEL_EDGE:
            for voice_id, label in EDGE_TTS_VOICES:
                combo.addItem(label, voice_id)
        else:
            local_voices = list_local_voices()
            if local_voices:
                for voice_id, label in local_voices:
                    combo.addItem(label, voice_id)
            else:
                # No registry lookup possible: let the worker pick the default.
                combo.addItem("Default system voice", "")
        index = combo.findData(EDGE_TTS_VOICES[0][0])
        if self.tts_model_combo.currentData() == MODEL_EDGE and index >= 0:
            combo.setCurrentIndex(0)

    def _set_tts_busy_state(self, busy: bool) -> None:
        """Enable/disable the TTS controls while a generation is running."""
        ready = (
            _EDGE_TTS_AVAILABLE if self.tts_model_combo.currentData() == MODEL_EDGE
            else _PYTTSX3_AVAILABLE
        )
        self._tts_generating = busy
        self.generate_audio_btn.setEnabled(not busy and ready)
        self.generate_audio_btn.setText("Generating..." if busy else "Generate Audio")
        self.tts_model_combo.setEnabled(not busy)
        self.tts_voice_combo.setEnabled(not busy)
        self.tts_busy.setVisible(busy)

    def open_drawer(
        self,
        audio_id: int | None = None,
        *,
        scope: str = GLOBAL_SCOPE,
        project_id: int | None = None,
        audio_type: str | None = None,
    ) -> None:
        """Open in create mode, or edit ``audio_id`` when one is given."""
        self._player.stop()
        self._editing_id = audio_id
        self._pending_audio = None
        self._pending_dialog_files = []

        if audio_id is None:
            self.drawer_title.setText("Create Audio")
            self.drawer_name.clear()
            self.file_label.setText("No audio file chosen")
            self.play_btn.hide()
            self.delete_btn.hide()
            # Preselect the type currently being browsed, if any.
            if audio_type is None:
                audio_type = self.drawer_type.currentData()
            index = self.drawer_type.findData(audio_type)
            self.drawer_type.setCurrentIndex(index if index >= 0 else 0)
            self._populate_scope_choices(scope, project_id)
        else:
            audio = database.get_audio(audio_id)
            if audio is None:
                return
            self.drawer_title.setText("Edit Audio")
            self.drawer_name.setText(audio["name"])
            audio_type = (
                audio["audio_type"] if "audio_type" in audio.keys() else "effect"
            )
            index = self.drawer_type.findData(audio_type)
            self.drawer_type.setCurrentIndex(index if index >= 0 else 0)
            saved_scope = (
                audio["scope"] if "scope" in audio.keys() else GLOBAL_SCOPE
            )
            saved_project_id = (
                audio["project_id"] if "project_id" in audio.keys() else None
            )
            self._populate_scope_choices(saved_scope, saved_project_id)
            self._show_file(audio["audio_path"])
            self.delete_btn.show()

        self._on_drawer_type_changed()
        self.tts_text.clear()
        self.tts_status.setText("")
        self._set_tts_busy_state(False)
        self.drawer_name.setFocus()
        self._fit_to_parent()
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        self.show()
        self.raise_()
        self.overlay.show()
        self.overlay.raise_()
        self.panel.setGeometry(self.width(), 0, DRAWER_WIDTH, self.height())
        self.panel.show()
        self.panel.raise_()
        self._anim.stop()
        self._anim.setStartValue(QPoint(self.width(), 0))
        self._anim.setEndValue(QPoint(self.width() - DRAWER_WIDTH, 0))
        self._anim.start()

    def _show_file(self, stored_path: str) -> None:
        """Update the drawer's file label + play button for a stored/pending file."""
        if self._pending_dialog_files:
            label = f"Selected: {len(self._pending_dialog_files)} dialog audio file(s)"
            has_file = True
        elif self._pending_audio:
            label = f"Selected: {os.path.basename(self._pending_audio)}"
            has_file = True
        elif stored_path and audio_store.absolute_path(stored_path).is_file():
            label = f"Stored: {os.path.basename(stored_path)}"
            has_file = True
        else:
            label = "No audio file" if stored_path else "No audio file chosen"
            has_file = False

        self.file_label.setText(label)
        self.play_btn.setVisible(has_file)
        self.play_btn.setText("▶  Play")

    def close_drawer(self) -> None:
        self._player.stop()
        self._anim.stop()
        self._anim.setStartValue(self.panel.pos())
        self._anim.setEndValue(QPoint(self.width(), 0))
        self._anim.start()

    def hide_drawer(self) -> None:
        """Close immediately (no animation), e.g. when leaving the page."""
        if self._generated_audio_path and self._pending_audio == self._generated_audio_path:
            self._pending_audio = None
            self._cleanup_generated_audio()
        # The TTS worker runs in a separate OS process (QProcess), so a native
        # SAPI/COM crash there can never take down the GUI. Detach first so
        # its finished handler can't touch the closing drawer, then kill it.
        if self._tts_process is not None:
            self._detach_tts_process()
        self._rmdir_text_file()
        # The finished handler was disconnected above, so it can't reset the
        # generation state anymore; do it here instead.
        self._set_tts_busy_state(False)
        self._player.stop()
        self._anim.stop()
        self.panel.hide()
        self.overlay.hide()
        self.hide()

    def _detach_tts_process(self) -> None:
        """Disconnect the current TTS process and kill it (safe for the GUI)."""
        process = self._tts_process
        self._tts_process = None
        if process is None:
            return
        try:
            process.finished.disconnect(self._on_tts_finished)
        except (RuntimeError, TypeError):
            pass
        try:
            process.errorOccurred.disconnect(self._on_tts_error)
        except (RuntimeError, TypeError):
            pass
        # Native cleanup for the QProcess object once its child is gone.
        process.finished.connect(process.deleteLater)
        if process.state() != QProcess.NotRunning:
            self._stale_processes.append(process)
            process.kill()

    def _rmdir_text_file(self) -> None:
        """Delete the temporary text file used for the TTS request, if any."""
        if self._tts_text_file:
            try:
                if os.path.isfile(self._tts_text_file):
                    os.remove(self._tts_text_file)
            except OSError:
                pass
            self._tts_text_file = None

    def _tts_log(self, message: str) -> None:
        """Append a timestamped line to tts_debug.log (diagnostics survive a crash)."""
        try:
            with open(PROJECT_ROOT / "tts_debug.log", "a", encoding="utf-8") as log:
                log.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
                )
        except OSError:
            pass

    def _after_anim(self) -> None:
        """After the slide-out finishes, stop the drawer & overlay from eating clicks."""
        if self._anim.endValue().x() >= self.width():
            self.panel.hide()
            self.overlay.hide()
            self.hide()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.hide_drawer()
        super().closeEvent(event)

    def __del__(self) -> None:
        try:
            process = getattr(self, "_tts_process", None)
            if process is not None and process.state() != QProcess.NotRunning:
                process.kill()
        except Exception:
            pass

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        if obj is self.overlay and event.type() == QEvent.MouseButtonPress:
            self.close_drawer()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        is_open = (
            self.panel.isVisible()
            and self._anim.state() != QPropertyAnimation.Running
        )
        x = self.width() - DRAWER_WIDTH if is_open else self.width()
        self.panel.setGeometry(x, 0, DRAWER_WIDTH, self.height())

    def stop_playback(self) -> None:
        """Stop any playing audio (used for clean app shutdown)."""
        self._player.stop()
        # Release the decoder: QMediaPlayer's internal threads must finish
        # now, not during teardown (fatal "QThread: Destroyed while running").
        self._player.setSource(QUrl())

    @property
    def editing_id(self) -> int | None:
        return self._editing_id

    # ----------------------------------------------------------- actions
    def _on_choose_audio(self) -> None:
        if self._generated_audio_path and self._pending_audio == self._generated_audio_path:
            self._pending_audio = None
            self._cleanup_generated_audio()
        source, _ = QFileDialog.getOpenFileName(
            self, "Choose audio file", "", AUDIO_FILTER
        )
        if not source:
            return
        self._pending_dialog_files = []
        self._pending_audio = source
        self._show_file("")

    def _on_add_dialog_audios(self) -> None:
        """Dialogs-only: queue several audio files for the next save."""
        if self._generated_audio_path and self._pending_audio == self._generated_audio_path:
            self._pending_audio = None
            self._cleanup_generated_audio()
        sources, _ = QFileDialog.getOpenFileNames(
            self, "Add dialog audio files", "", AUDIO_FILTER
        )
        if not sources:
            return
        self._pending_audio = None
        self._pending_dialog_files = list(sources)
        self._show_file("")

    def _on_play_toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.stop()
            self.play_btn.setText("▶  Play")
            return

        # Prefer the pending file while editing an unsaved pick
        if self._pending_dialog_files:
            source_path = self._pending_dialog_files[0]
        elif self._pending_audio:
            source_path = self._pending_audio
        elif self._editing_id is not None:
            audio = database.get_audio(self._editing_id)
            if audio is None or not audio["audio_path"]:
                self._flash("No audio file to play.")
                return
            source_path = str(
                audio_store.absolute_path(audio["audio_path"])
            )
            if not audio_store.absolute_path(audio["audio_path"]).is_file():
                self._flash("Audio file is missing on disk.")
                return
        else:
            self._flash("Choose an audio file first.")
            return

        self._player.setSource(QUrl.fromLocalFile(source_path))
        self._player.play()
        self.play_btn.setText("⏹  Stop")

    def _on_save(self) -> None:
        name = self.drawer_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter the audio name.")
            return

        audio_type = self.drawer_type.currentData() or "effect"
        scope, project_id = self._drawer_scope()

        # Dialogs-only batch add: one database row per chosen file.
        if self._editing_id is None and self._pending_dialog_files:
            if audio_type != "dialogs":
                QMessageBox.warning(
                    self,
                    "Dialog audio only",
                    "Multi-file Add Audio is only available for the Dialogs type.",
                )
                return
            files = list(self._pending_dialog_files)
            created: list[tuple] = []
            stored = ""
            try:
                for index, source in enumerate(files, 1):
                    stored = audio_store.save_audio(source)
                    item_name = name if len(files) == 1 else f"{name} ({index})"
                    audio = database.create_audio(
                        item_name,
                        stored,
                        audio_type=audio_type,
                        scope=scope,
                        project_id=project_id,
                    )
                    created.append((audio, stored))
                    stored = ""
            except (ValueError, OSError) as exc:
                if stored:
                    audio_store.delete_audio(stored)
                for audio, path in created:
                    database.delete_audio(audio["id"])
                    audio_store.delete_audio(path)
                QMessageBox.warning(self, "Cannot save audio", str(exc))
                return

            self._pending_dialog_files = []
            self._cleanup_generated_audio()
            self.close_drawer()
            self.audio_saved.emit(f"Created {len(created)} dialog audio(s).")
            return

        try:
            if (
                self._pending_audio
                and self._pending_audio == self._generated_audio_path
            ):
                # Make sure the temp TTS WAV's header is finalized (harmless
                # replay of the display-time fix) before it is copied over.
                finalize_wav_header(self._pending_audio)
            stored = (
                audio_store.save_audio(self._pending_audio)
                if self._pending_audio
                else None
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid audio", str(exc))
            return

        try:
            if self._editing_id is None:
                audio = database.create_audio(
                    name,
                    stored or "",
                    audio_type=audio_type,
                    scope=scope,
                    project_id=project_id,
                )
                message = f"Created '{audio['name']}'."
            else:
                old = database.get_audio(self._editing_id)
                database.update_audio(
                    self._editing_id,
                    name,
                    audio_type=audio_type,
                    scope=scope,
                    project_id=project_id,
                    audio_path=stored,
                )
                if stored:
                    audio_store.delete_audio(old["audio_path"])
                message = f"Saved '{name}'."
        except ValueError as exc:
            if stored:
                audio_store.delete_audio(stored)
            QMessageBox.warning(self, "Cannot save audio", str(exc))
            return

        if self._generated_audio_path is not None and self._pending_audio == self._generated_audio_path:
            self._cleanup_generated_audio()
        self._pending_audio = None
        self.close_drawer()
        self.audio_saved.emit(message)

    def _on_delete(self) -> None:
        if self._editing_id is None:
            return
        audio = database.get_audio(self._editing_id)
        if audio is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete audio",
            f"Delete audio '{audio['name']}'?\n\n"
            "This also deletes its audio file and cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        database.delete_audio(audio["id"])
        audio_store.delete_audio(audio["audio_path"])
        self.close_drawer()
        self.audio_deleted.emit(f"Deleted '{audio['name']}'.")

    def _on_generate_audio(self) -> None:
        text = self.tts_text.toPlainText().strip()
        if not text:
            self._flash("Enter text to generate audio.")
            return
        if self._tts_generating:
            return

        model = self.tts_model_combo.currentData() or MODEL_LOCAL
        if model == MODEL_EDGE and not _EDGE_TTS_AVAILABLE:
            message = "edge-tts is not installed."
            self._flash(message)
            self.tts_status.setText(message)
            return
        if model == MODEL_LOCAL and not _PYTTSX3_AVAILABLE:
            message = "pyttsx3 is not installed."
            self._flash(message)
            self.tts_status.setText(message)
            return

        if self._generated_audio_path and self._pending_audio == self._generated_audio_path:
            self._pending_audio = None
            self._cleanup_generated_audio()

        out_ext = ".mp3" if model == MODEL_EDGE else ".wav"
        fd, path = tempfile.mkstemp(suffix=out_ext, prefix="tts_")
        os.close(fd)
        try:
            os.remove(path)
        except OSError:
            pass

        self._generated_audio_path = path
        self._tts_source_text = text
        self._tts_current_model = model
        self._tts_generating = True

        # Write the text to a temp file so there is no command-line length
        # or quoting limit; the child reads it back.
        text_fd, text_path = tempfile.mkstemp(suffix=".txt", prefix="tts_text_")
        with os.fdopen(text_fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self._tts_text_file = text_path

        # Run TTS in a separate process: pyttsx3/SAPI teardown can abort
        # natively; isolated like this it can never take down the app.
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        script = os.path.join(
            scripts_dir,
            "edge_tts_worker.py" if model == MODEL_EDGE else "tts_worker.py",
        )
        voice = self.tts_voice_combo.currentData()
        args = [script, text_path, path]
        if model == MODEL_EDGE:
            args.append(voice or "hi-IN-MadhurNeural")
        elif voice:
            args.append(voice)

        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments(args)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        self._tts_generation += 1
        process.setProperty("generation", self._tts_generation)

        self._tts_process = process
        self._tts_started_at = time.monotonic()
        voice_log = voice or "default"
        self._tts_log(
            f"start: generation={self._tts_generation} model={model} "
            f"voice={voice_log} text={len(text)} chars out={path}"
        )

        process.finished.connect(self._on_tts_finished)
        process.errorOccurred.connect(self._on_tts_error)
        process.start()
        self._set_tts_busy_state(True)
        self.tts_status.setText("Generating audio...")

    def _on_tts_error(self, error: QProcess.ProcessError) -> None:
        process = self.sender()
        if process is not self._tts_process:
            return
        if error != QProcess.FailedToStart:
            return  # finishing/crashed cases are covered by `finished`
        process.deleteLater()
        self._tts_process = None
        self._display_tts_failure(
            "Could not start the Text-to-Speech worker "
            f"({sys.executable}). {process.errorString()}"
        )

    def _on_tts_finished(self, exit_code: int, status) -> None:
        process = self.sender()
        if process is not self._tts_process:
            return  # a stale/killed child from a closed drawer
        process.deleteLater()
        self._tts_process = None

        stderr = (
            bytes(process.readAllStandardError())
            .decode("utf-8", errors="replace")
            .strip()
        )
        elapsed = time.monotonic() - getattr(self, "_tts_started_at", 0.0)
        crashed = status != QProcess.NormalExit
        self._tts_log(
            f"finish: generation={self._tts_generation} exit={exit_code} "
            f"crashed={crashed} elapsed={elapsed:.1f}s"
            + (f"\n    stderr: {stderr}" if stderr else "")
        )
        if crashed and not stderr:
            stderr = "The Text-to-Speech worker crashed without output."

        path = self._generated_audio_path
        succeeded = (
            not crashed
            and exit_code == 0
            and bool(path)
            and os.path.isfile(path)
            and os.path.getsize(path) > 0
        )
        if succeeded and str(path).lower().endswith(".wav"):
            # Belt & braces: make sure the header is finalized before the
            # file is previewed or stored (pyttsx3/SAPI can leave it stale).
            if not finalize_wav_header(path):
                succeeded = False
                stderr = "Generated file is not a readable WAV."
        if succeeded:
            self._display_tts_result(path)
        else:
            self._display_tts_failure(
                stderr or f"Text-to-Speech worker exited with code {exit_code}."
            )

    def _display_tts_failure(self, message: str) -> None:
        self._rmdir_text_file()
        self._set_tts_busy_state(False)
        self._cleanup_generated_audio()
        message = f"Text-to-Speech failed: {message}"
        self._flash(message)
        self.tts_status.setText(message)

    def _display_tts_result(self, path: str) -> None:
        self._rmdir_text_file()
        self._set_tts_busy_state(False)

        if not self.isVisible():
            self._cleanup_generated_audio()
            return

        self._pending_dialog_files = []
        self._pending_audio = path
        self._show_file("")
        self.tts_status.setText("Generated audio ready. Preview or Save Audio.")
        if not self.drawer_name.text().strip():
            self.drawer_name.setText(self._tts_source_text[:40].strip() or "Generated Audio")

    def _cleanup_generated_audio(self) -> None:
        if self._generated_audio_path:
            try:
                if os.path.isfile(self._generated_audio_path):
                    os.remove(self._generated_audio_path)
            except OSError:
                pass
            self._generated_audio_path = None

    def _flash(self, message: str) -> None:
        self.status_changed.emit(message)
