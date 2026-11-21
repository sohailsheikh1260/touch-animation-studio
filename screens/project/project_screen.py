"""Project module screen - CRUD with drawer + a details page (SQLite-backed).

- Grid page: boxes of projects (name + description), "＋ Create Project" button.
- Clicking a box opens the **Project Details page** (description, info, Edit
  and Delete actions).
- The drawer still slides in from the right for create/edit/delete forms.
"""

from PySide6.QtCore import QEvent, QPropertyAnimation, QEasingCurve, Qt, QPoint
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import database
from screens.audio import audio_store
from screens.project_details.project_editor import ProjectEditorPage
from screens.theme import BG, CARD_BG, MUTED, TEXT

ICON = "📂"
NAME = "Project"
DESC = "Create, open and manage your projects"
INFO = (ICON, NAME, DESC)

DRAWER_WIDTH = 340
CARD_W, CARD_H = 180, 216
GRID_COLUMNS = 3

CARD_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    f"  border: 2px solid {CARD_BG}; border-radius: 14px; }}"
    "QFrame:hover { border-color: #38bdf8; }"
)
CARD_LABEL_STYLE = "background-color: transparent; border: none;"

TOP_BUTTON_STYLE = (
    f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px; }"
    "QPushButton:hover { background-color: #334155; }"
)

CREATE_BUTTON_STYLE = (
    "QPushButton { background-color: #1d4ed8; color: #e2e8f0;"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 20px; font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #2563eb; }"
)

EDIT_BUTTON_STYLE = (
    "QPushButton { background-color: #1d4ed8; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px 24px;"
    "  font-size: 15px; font-weight: bold; }"
    "QPushButton:hover { background-color: #2563eb; }"
)

DELETE_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
    "  border: none; border-radius: 8px; padding: 10px 24px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
)

INPUT_STYLE = (
    f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

DESCRIPTION_STYLE = (
    f"QTextEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

DETAIL_TEXT = f"color: {TEXT}; font-size: 14px;"
MUTED_TEXT = f"color: {MUTED}; font-size: 13px; {CARD_LABEL_STYLE}"


class ProjectScreen(QWidget):
    def __init__(self, go_home, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        database.init_db()
        self._editing_id: int | None = None
        self._details_id: int | None = None  # project shown on the details page

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._build_projects_page())  # index 0: grid
        self.editor = ProjectEditorPage(self)         # index 1: video-editor page
        stack.addWidget(self.editor)

        # ---- Slide-in drawer + overlay ----
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(2, 6, 23, 160);")
        self.overlay.hide()
        self.overlay.installEventFilter(self)

        self.drawer = QFrame(self)
        self.drawer.setFixedWidth(DRAWER_WIDTH)
        self.drawer.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; border-left: 2px solid #1d4ed8; }}"
        )
        self._build_drawer(self.drawer)

        self._anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)

        self.stack = stack
        self.refresh()

    # ==================================================== Page 0: projects
    def _build_projects_page(self) -> QWidget:
        page = QWidget()

        root = QVBoxLayout(page)
        root.setContentsMargins(32, 24, 32, 32)
        root.setSpacing(14)

        # ---- Top bar ----
        back_btn = QPushButton("← Back to Home")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFixedWidth(160)
        back_btn.setStyleSheet(TOP_BUTTON_STYLE)
        back_btn.clicked.connect(self.show_home)

        self.title = QLabel(f"{ICON}  Projects")
        self.title.setStyleSheet(f"color: {TEXT}; font-size: 22px; font-weight: bold;")

        create_btn = QPushButton("＋ Create Project")
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

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        root.addWidget(self.status_label, 0, Qt.AlignLeft)

        # ---- Project boxes grid (scrollable) ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(18)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)

        self.empty_label = QLabel("No projects yet — click “＋ Create Project”!")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {MUTED}; font-size: 15px;")
        root.addWidget(self.empty_label, 1)
        self.empty_label.hide()

        root.addWidget(self.scroll, 1)
        return page

    # =================================================== Page 1: video editor
    # (built by ProjectEditorPage; details/info + timeline live there)

    def stop_export(self) -> None:
        """Delegate to the editor page (clean shutdown hook)."""
        if hasattr(self, "editor"):
            self.editor.stop_export()

    def stop_playback(self) -> None:
        """Delegate to the editor page (clean shutdown hook)."""
        if hasattr(self, "editor"):
            self.editor.stop_playback()

    def show_projects(self) -> None:
        self._details_id = None
        self._stop_editor_playback()
        self.stack.setCurrentIndex(0)

    def show_home(self) -> None:
        self._details_id = None
        self._stop_editor_playback()
        window = self.window()
        if hasattr(window, "show_home"):
            window.show_home()

    def _stop_editor_playback(self) -> None:
        if hasattr(self, "editor"):
            self.editor._stop_playback()

    def show_details(self, project_id: int) -> None:
        project = database.get_project(project_id)
        if project is None:
            return
        self._details_id = project_id
        self.editor.load(project_id)
        self.stack.setCurrentIndex(1)

    def delete_current_project(self) -> None:
        """Called by the editor's Delete button."""
        if self._details_id is not None:
            self._delete_project(self._details_id)

    def _delete_project(self, project_id: int, close_drawer: bool = False) -> None:
        project = database.get_project(project_id)
        if project is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete project",
            f"Delete project '{project['name']}'?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._stop_editor_playback()
        self._delete_project_and_audio(project["id"])
        self.refresh()
        if self.stack.currentIndex() == 1:
            self.show_projects()
        if close_drawer:
            self.close_drawer()
        self.status_label.setText(f"Deleted '{project['name']}'.")

    def _delete_project_and_audio(self, project_id: int) -> None:
        """Delete a project plus its project-scoped audio records/files."""
        audios = database.delete_project(project_id) or []
        for audio in audios:
            audio_store.delete_audio(audio["audio_path"])

    # ------------------------------------------------------------ Grid list
    def refresh(self) -> None:
        projects = database.list_projects()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        has_items = bool(projects)
        self.scroll.setVisible(has_items)
        self.empty_label.setVisible(not has_items)

        for i, project in enumerate(projects):
            card = self._make_card(project)
            row, col = divmod(i, GRID_COLUMNS)
            self.grid.addWidget(card, row, col)
        self.status_label.setText(f"{len(projects)} project(s)")

    def _make_card(self, project) -> QFrame:
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(CARD_W, CARD_H)
        card.setStyleSheet(CARD_STYLE)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 14, 14, 14)
        inner.setSpacing(8)

        icon_label = QLabel(ICON)
        icon_label.setStyleSheet(
            f"font-size: 34px; background-color: {BG}; border: none; border-radius: 8px;"
        )
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedHeight(140)

        name_label = QLabel(project["name"])
        name_label.setStyleSheet(
            f"color: {TEXT}; font-size: 15px; font-weight: bold; {CARD_LABEL_STYLE}"
        )
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)

        desc_text = project["description"] or "No description"
        desc_label = QLabel(desc_text)
        desc_label.setStyleSheet(MUTED_TEXT)
        desc_label.setAlignment(Qt.AlignHCenter)
        desc_label.setWordWrap(True)

        inner.addWidget(icon_label)
        inner.addWidget(name_label)
        inner.addWidget(desc_label)

        delete_btn = QPushButton("🗑")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setToolTip(f"Delete project '{project['name']}'")
        delete_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #f87171; "
            "border: none; padding: 4px; font-size: 13px; }"
            "QPushButton:hover { color: #ef4444; }"
        )
        delete_btn.clicked.connect(
            lambda _checked=False, pid=project["id"]: self._delete_project(pid)
        )

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 8, 0, 0)
        bottom.addStretch()
        bottom.addWidget(delete_btn)
        inner.addLayout(bottom)

        def mousePressEvent(event, pid=project["id"]):  # noqa: N802 (Qt naming)
            if event.button() == Qt.LeftButton:
                self.show_details(pid)

        card.mousePressEvent = mousePressEvent
        return card

    # -------------------------------------------------------- Drawer UI
    def _build_drawer(self, drawer: QFrame) -> None:
        layout = QVBoxLayout(drawer)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.drawer_title = QLabel("Create Project")
        self.drawer_title.setStyleSheet(f"color: {TEXT}; font-size: 18px; font-weight: bold;")
        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet(TOP_BUTTON_STYLE)
        close_btn.clicked.connect(self.close_drawer)
        header.addWidget(self.drawer_title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        name_hint = QLabel("Project name")
        name_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_name = QLineEdit()
        self.drawer_name.setPlaceholderText("e.g. My First Toon")
        self.drawer_name.setStyleSheet(INPUT_STYLE)
        layout.addWidget(name_hint)
        layout.addWidget(self.drawer_name)

        desc_hint = QLabel("Project description")
        desc_hint.setStyleSheet(f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}")
        self.drawer_description = QTextEdit()
        self.drawer_description.setPlaceholderText("What is this project about?")
        self.drawer_description.setStyleSheet(DESCRIPTION_STYLE)
        self.drawer_description.setFixedHeight(140)
        layout.addWidget(desc_hint)
        layout.addWidget(self.drawer_description)

        layout.addStretch()

        self.delete_btn = QPushButton("🗑  Delete")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet(DELETE_BUTTON_STYLE)
        self.delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self.delete_btn)

        self.save_btn = QPushButton("💾  Save Project")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #16a34a; color: #e2e8f0;"
            "  border: none; border-radius: 8px; padding: 10px;"
            "  font-size: 15px; font-weight: bold; }"
            "QPushButton:hover { background-color: #22c55e; }"
        )
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    # ---------------------------------------------------- Drawer behavior
    def open_drawer(self, project_id: int | None = None) -> None:
        self._editing_id = project_id

        if project_id is None:
            self.drawer_title.setText("Create Project")
            self.drawer_name.clear()
            self.drawer_description.clear()
            self.delete_btn.hide()
        else:
            project = database.get_project(project_id)
            if project is None:
                return
            self.drawer_title.setText("Edit Project")
            self.drawer_name.setText(project["name"])
            self.drawer_description.setPlainText(project["description"])
            self.delete_btn.show()

        self.drawer_name.setFocus()

        # Slide in from the right edge
        h = self.height()
        self.overlay.setGeometry(0, 0, self.width(), h)
        self.overlay.show()
        self.overlay.raise_()
        self.drawer.setGeometry(self.width(), 0, DRAWER_WIDTH, h)
        self.drawer.show()
        self.drawer.raise_()
        self._anim.stop()
        self._anim.setStartValue(QPoint(self.width(), 0))
        self._anim.setEndValue(QPoint(self.width() - DRAWER_WIDTH, 0))
        self._anim.start()

    def close_drawer(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.drawer.pos())
        self._anim.setEndValue(QPoint(self.width(), 0))
        self._anim.start()

    def _after_anim(self) -> None:
        """After the slide-out finishes, stop the drawer & overlay from eating clicks."""
        if self._anim.endValue().x() >= self.width():
            self.drawer.hide()
            self.overlay.hide()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt naming)
        if obj is self.overlay and event.type() == QEvent.MouseButtonPress:
            self.close_drawer()
            return True
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())
        is_open = self.drawer.isVisible() and self._anim.state() != QPropertyAnimation.Running
        x = self.width() - DRAWER_WIDTH if is_open else self.width()
        self.drawer.setGeometry(x, 0, DRAWER_WIDTH, self.height())

    # ------------------------------------------------------------- Actions
    def _on_save(self) -> None:
        name = self.drawer_name.text().strip()
        description = self.drawer_description.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Enter the project name.")
            return

        try:
            if self._editing_id is None:
                project = database.create_project(name, description)
                message = f"Created '{project['name']}'."
                new_id = project["id"]
            else:
                database.update_project(self._editing_id, name, description)
                message = f"Saved '{name}'."
                new_id = self._editing_id
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot save project", str(exc))
            return

        self.refresh()
        # Keep the editor page in sync if the drawer was opened there
        if self.stack.currentIndex() == 1 and self._details_id is not None:
            updated = database.get_project(new_id)
            if updated is not None:
                if new_id != self._details_id:
                    self._details_id = new_id  # keep (names only change here)
                self.editor._refresh_header()
            else:
                self.show_projects()
        self.close_drawer()
        self.status_label.setText(message)

    def _on_delete(self) -> None:
        if self._editing_id is not None:
            self._delete_project(self._editing_id, close_drawer=True)
