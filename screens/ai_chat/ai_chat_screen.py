"""AI Chat module screen with a project/session sidebar."""

import json

import database

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from screens.ai_chat.agent import AIChatAgent
from screens.theme import BACK_BUTTON_STYLE, BG, CARD_BG, MUTED, TEXT

ICON = "💬"
NAME = "AI Chat"
DESC = "Chat with an AI assistant"
INFO = (ICON, NAME, DESC)


SIDEBAR_STYLE = (
    f"QFrame#Sidebar {{ background-color: {CARD_BG};"
    " border-right: 1px solid #334155; }"
)
MAIN_STYLE = f"QFrame#MainPanel {{ background-color: {BG}; }}"
GROUP_STYLE = (
    f"QGroupBox {{ background-color: {BG}; color: {TEXT};"
    " border: 1px solid #334155; border-radius: 10px;"
    " margin-top: 10px; padding: 12px 8px 10px 8px; font-weight: bold; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
)
COMBO_STYLE = (
    f"QComboBox {{ background-color: {BG}; color: {TEXT};"
    " border: 1px solid #334155; border-radius: 8px;"
    " padding: 7px 9px; font-size: 13px; }"
    "QComboBox QAbstractItemView { background-color: #1e293b; color: #e2e8f0;"
    " selection-background-color: #334155; }"
)
LIST_STYLE = (
    f"QListWidget {{ background-color: {BG}; color: {TEXT};"
    " border: 1px solid #334155; border-radius: 10px; padding: 5px; font-size: 13px; }"
    "QListWidget::item { padding: 9px 7px; border-radius: 6px; }"
    "QListWidget::item:hover { background-color: #1e293b; }"
    "QListWidget::item:selected { background-color: #334155; color: #ffffff; }"
)
CREATE_BUTTON_STYLE = (
    "QPushButton { background-color: #1d4ed8; color: #e2e8f0;"
    " border: none; border-radius: 8px; padding: 9px 12px;"
    " font-size: 13px; font-weight: bold; }"
    "QPushButton:hover { background-color: #2563eb; }"
    "QPushButton:disabled { background-color: #334155; color: #64748b; }"
)


class AIChatScreen(QWidget):
    def __init__(self, show_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        database.init_db()
        self.show_home = show_home
        self._current_session_id: int | None = None
        self._busy = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(220)
        self.sidebar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.sidebar.setStyleSheet(SIDEBAR_STYLE)
        self._build_sidebar()

        self.main_panel = QFrame()
        self.main_panel.setObjectName("MainPanel")
        self.main_panel.setMinimumWidth(500)
        self.main_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_panel.setStyleSheet(MAIN_STYLE)
        self._build_main_panel()

        root.addWidget(self.sidebar, 1)
        root.addWidget(self.main_panel, 4)

        self._refresh_projects()
        self._refresh_sessions()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._refresh_projects()
        if not self._busy:
            self._refresh_sessions()

    def _build_sidebar(self) -> None:
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(12)

        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.clicked.connect(self.show_home)
        layout.addWidget(back_btn)

        title = QLabel(f"{ICON} {NAME}")
        title.setStyleSheet(f"color: {TEXT}; font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        create_group = QGroupBox("Create Session")
        create_group.setStyleSheet(GROUP_STYLE)
        create_layout = QVBoxLayout(create_group)
        create_layout.setContentsMargins(8, 8, 8, 8)
        create_layout.setSpacing(8)

        project_label = QLabel("Project")
        project_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        self.project_combo = QComboBox()
        self.project_combo.setStyleSheet(COMBO_STYLE)
        create_layout.addWidget(project_label)
        create_layout.addWidget(self.project_combo)

        create_layout.addStretch()
        self.create_btn = QPushButton("＋ Create Session")
        self.create_btn.setCursor(Qt.PointingHandCursor)
        self.create_btn.setStyleSheet(CREATE_BUTTON_STYLE)
        self.create_btn.clicked.connect(self._create_session)
        create_layout.addWidget(self.create_btn)
        layout.addWidget(create_group)

        sessions_label = QLabel("Session List")
        sessions_label.setStyleSheet(f"color: {MUTED}; font-size: 12px; font-weight: bold;")
        layout.addWidget(sessions_label)

        self.session_list = QListWidget()
        self.session_list.setStyleSheet(LIST_STYLE)
        self.session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.session_list.setWordWrap(True)
        self.session_list.currentItemChanged.connect(self._on_session_changed)
        layout.addWidget(self.session_list, 1)

    def _build_main_panel(self) -> None:
        layout = QVBoxLayout(self.main_panel)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(f"{ICON} {NAME}")
        title.setStyleSheet(f"color: {TEXT}; font-size: 24px; font-weight: bold;")
        self.session_title = QLabel("No session selected")
        self.session_title.setStyleSheet(f"color: {MUTED}; font-size: 13px;")
        system_prompt_btn = QPushButton("⚙ System Prompt")
        system_prompt_btn.setCursor(Qt.PointingHandCursor)
        system_prompt_btn.setStyleSheet(BACK_BUTTON_STYLE)
        system_prompt_btn.clicked.connect(self._edit_system_prompt)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(system_prompt_btn)
        header.addWidget(self.session_title)
        layout.addLayout(header)

        self.chat = AIChatAgent()
        self.chat.history_changed.connect(self._save_history)
        self.chat.busy_changed.connect(self._on_busy_changed)
        layout.addWidget(self.chat, 1)

    def _edit_system_prompt(self) -> None:
        prompt, accepted = QInputDialog.getMultiLineText(
            self,
            "System Prompt",
            "Agent instructions:",
            self.chat.system_prompt,
        )
        if accepted:
            self.chat.set_system_prompt(prompt)
            print("[AI Chat] system prompt updated", flush=True)

    def _refresh_projects(self) -> None:
        projects = database.list_projects()
        selected_id = self.project_combo.currentData()

        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for project in projects:
            self.project_combo.addItem(project["name"], project["id"])
        if projects and selected_id is not None:
            index = self.project_combo.findData(selected_id)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
        self.project_combo.blockSignals(False)

        if not projects:
            self.project_combo.addItem("No projects available", None)
        self._update_create_button()

    def _refresh_sessions(self, select_id: int | None = None) -> None:
        sessions = database.list_chat_sessions()
        target_id = select_id or self._current_session_id
        target_item = None

        self.session_list.blockSignals(True)
        self.session_list.clear()
        for session in sessions:
            item = QListWidgetItem(f"{session['title']}  ·  {session['project_name']}")
            item.setData(Qt.UserRole, session["id"])
            item.setToolTip(f"{session['project_name']}\n{session['created_at']}")
            self.session_list.addItem(item)
            if session["id"] == target_id:
                target_item = item
        if target_item is None and self.session_list.count():
            target_item = self.session_list.item(0)
        if target_item is not None:
            self.session_list.setCurrentItem(target_item)
        self.session_list.blockSignals(False)

        if target_item is None:
            self._clear_current_session()
        else:
            self._load_session(int(target_item.data(Qt.UserRole)))

    def _create_session(self) -> None:
        project_id = self.project_combo.currentData()
        if project_id is None:
            return
        try:
            session = database.create_chat_session(int(project_id))
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot create session", str(exc))
            return
        self._refresh_sessions(session["id"])

    def _on_session_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._clear_current_session()
            return
        self._load_session(int(current.data(Qt.UserRole)))

    def _load_session(self, session_id: int) -> None:
        session = database.get_chat_session(session_id)
        if session is None:
            self._clear_current_session()
            return
        try:
            messages = json.loads(session["messages"] or "[]")
        except (json.JSONDecodeError, TypeError):
            messages = []
        if not isinstance(messages, list):
            messages = []

        self._current_session_id = session_id
        project_index = self.project_combo.findData(session["project_id"])
        if project_index >= 0:
            self.project_combo.setCurrentIndex(project_index)
        self.chat.set_history(messages)
        self.chat.setEnabled(True)
        self.session_title.setText(f"{session['title']}  ·  {session['project_name']}")

    def _clear_current_session(self) -> None:
        self._current_session_id = None
        self.chat.set_history([])
        self.chat.setEnabled(False)
        self.chat.log.setPlaceholderText("Select or create a session to start chatting…")
        self.session_title.setText("No session selected")

    def _save_history(self, messages: list[dict]) -> None:
        if self._current_session_id is not None:
            database.save_chat_session_messages(self._current_session_id, messages)

    def _on_busy_changed(self, busy: bool) -> None:
        self._busy = busy
        self.session_list.setEnabled(not busy)
        self._update_create_button()

    def _update_create_button(self) -> None:
        can_create = not self._busy and self.project_combo.currentData() is not None
        self.create_btn.setEnabled(can_create)
