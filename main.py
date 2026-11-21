"""Touch Animation Studio - app launcher & home screen (PySide6).

Each module screen lives in its own folder under screens/.

Run with:  uv run main.py
"""

import os

# Qt 6.12 ships two multimedia backends. The default ffmpeg backend probes
# AV1/H.264/HEVC Media Foundation encoders whenever QMediaPlayer opens an MP3
# (e.g. pressing Play in the project editor) and dumps harmless
# "could not find any MFT" lines to the console. Force the native Windows
# Media Foundation backend and silence any ffmpeg-backend Qt logging before
# PySide6/Qt is imported.
os.environ.setdefault("QT_MEDIA_BACKEND", "windows")
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.multimedia.ffmpeg*=false",
)

import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from screens.ai_chat.ai_chat_screen import INFO as AI_CHAT_INFO, AIChatScreen
from screens.animation.animation_screen import INFO as ANIMATION_INFO, AnimationScreen
from screens.audio.audio_screen import INFO as AUDIO_INFO, AudioScreen
from screens.background.background_screen import INFO as BACKGROUND_INFO, BackgroundScreen
from screens.character.character_screen import INFO as CHARACTER_INFO, CharacterScreen
from screens.character_mask_master.character_mask_master_screen import (
    INFO as CHARACTER_MASK_MASTER_INFO,
    CharacterMaskMasterScreen,
)
from screens.knowledge.knowledge_screen import INFO as KNOWLEDGE_INFO, KnowledgeScreen
from screens.since.since_screen import INFO as SINCE_INFO, SinceScreen
from screens.project.project_screen import INFO as PROJECT_INFO, ProjectScreen
from screens.skeleton_master.skeleton_master_screen import INFO as SKELETON_MASTER_INFO, SkeletonMasterScreen
from screens.theme import BG, CARD_LABEL_STYLE, CARD_STYLE, MUTED, TEXT

# (icon, name, description, screen class) - one card per module
MODULES = [
    (*PROJECT_INFO, ProjectScreen),
    (*BACKGROUND_INFO, BackgroundScreen),
    (*CHARACTER_INFO, CharacterScreen),
    (*ANIMATION_INFO, AnimationScreen),
    (*AUDIO_INFO, AudioScreen),
    (*KNOWLEDGE_INFO, KnowledgeScreen),
    (*SINCE_INFO, SinceScreen),
    (*SKELETON_MASTER_INFO, SkeletonMasterScreen),
    (*CHARACTER_MASK_MASTER_INFO, CharacterMaskMasterScreen),
    (*AI_CHAT_INFO, AIChatScreen),
]


class HomeScreen(QWidget):
    """Home page with a grid of module cards."""

    def __init__(self, open_module, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.open_module = open_module

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 32)
        layout.setSpacing(24)

        title = QLabel("🏠 Touch Animation Studio")
        title.setStyleSheet(f"color: {TEXT}; font-size: 26px; font-weight: bold;")
        title.setAlignment(Qt.AlignHCenter)
        layout.addWidget(title)

        subtitle = QLabel("Pick a module to get started")
        subtitle.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        subtitle.setAlignment(Qt.AlignHCenter)
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(20)

        for i, (icon, name, desc, _screen_cls) in enumerate(MODULES):
            card = self._make_card(icon, name, desc, i)
            row, col = divmod(i, 3)
            grid.addWidget(card, row, col)

        layout.addLayout(grid)
        layout.addStretch()

    def _make_card(self, icon: str, name: str, desc: str, index: int) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card.setMinimumSize(220, 150)
        card.setStyleSheet(CARD_STYLE)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 20, 20, 20)
        inner.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 42px; {CARD_LABEL_STYLE}")
        icon_label.setAlignment(Qt.AlignHCenter)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: bold; {CARD_LABEL_STYLE}")
        name_label.setAlignment(Qt.AlignHCenter)

        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignHCenter)
        desc_label.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")

        inner.addStretch()
        inner.addWidget(icon_label)
        inner.addWidget(name_label)
        inner.addWidget(desc_label)
        inner.addStretch()

        def mousePressEvent(event, idx=index):  # noqa: N802 (Qt naming)
            if event.button() == Qt.LeftButton:
                self.open_module(idx)

        card.mousePressEvent = mousePressEvent
        return card


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Touch Animation Studio")
        self.setMinimumSize(900, 560)
        self.resize(1024, 640)

        self.setStyleSheet(
            f"QWidget {{ background-color: {BG}; color: {TEXT}; }}"
            # Message/information popups: white text on a dark panel
            "QMessageBox { background-color: #1e293b; }"
            "QMessageBox QLabel { color: #ffffff; }"
            "QMessageBox QPushButton {"
            "  background-color: #334155; color: #ffffff;"
            "  border: 1px solid #475569; border-radius: 8px;"
            "  min-width: 84px; padding: 6px 12px; font-size: 14px;"
            "}"
            "QMessageBox QPushButton:hover { background-color: #475569; }"
            "QInputDialog { background-color: #1e293b; }"
            "QInputDialog QLabel { color: #ffffff; }"
        )

        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)
        self.stack.addWidget(HomeScreen(self.open_module))  # index 0 = home

        # Add each module screen from its folder
        for _icon, _name, _desc, screen_cls in MODULES:
            self.stack.addWidget(screen_cls(self.show_home))

        self.stack.setCurrentIndex(0)

    def show_home(self) -> None:
        self.stack.setCurrentIndex(0)

    def open_module(self, index: int) -> None:
        self.stack.setCurrentIndex(index + 1)


    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        import time

        from PySide6.QtCore import qInfo

        # Stop every running media/export thread for a clean shutdown
        for i in range(self.stack.count()):
            widget = self.stack.widget(i)
            for method_name in ("stop_export", "stop_playback"):
                if hasattr(widget, method_name):
                    method = getattr(widget, method_name)
                    if callable(method):
                        method()
        qInfo("closeEvent[marker]: all screens stopped")

        # Give QMediaPlayer's internal decode threads a moment to wind down;
        # destroying them too early aborts the process (exit code 1).
        deadline = time.time() + 1.0
        try:
            while time.time() < deadline:
                QApplication.processEvents()
                time.sleep(0.05)
        except KeyboardInterrupt:
            # Ctrl+C during shutdown should close cleanly, not surface as a Qt
            # "Error calling Python override of QMainWindow::closeEvent".
            pass
        qInfo("closeEvent[marker]: teardown drain complete")
        event.accept()



def main() -> None:
    # Capture native crashes (thread teardown, Qt aborts) to a log file
    import faulthandler

    crash_log = open(
        Path(__file__).resolve().parent / "crash.log", "w", encoding="utf-8"
    )
    faulthandler.enable(crash_log, all_threads=True)
    crash_log.write(f"=== session start {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    crash_log.flush()

    def _log_unraisable(exc_type, exc_value, exc_tb, context=None) -> None:
        crash_log.write("\n=== UNRAISABLE ===\n")
        crash_log.write(f"while deleting: {exc_value!r}\n")
        crash_log.write(f"exception: {exc_value!r}\n")

    sys.unraisablehook = _log_unraisable

    from PySide6.QtCore import qInstallMessageHandler, QtMsgType

    def _qt_message(mode: QtMsgType, _context, message: str) -> None:
        crash_log.write(f"\n=== QT {mode.name} ===\n{message}\n")
        crash_log.flush()

    qInstallMessageHandler(_qt_message)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    faulthandler.disable()
    crash_log.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
