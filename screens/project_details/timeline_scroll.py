"""Scroll area that keeps the timeline content sized to the viewport."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QScrollArea, QWidget

from screens.project_details.timeline_widget import TimelineWidget


class TimelineScroll(QScrollArea):
    """Timeline scroll area that keeps its content widened to the viewport."""

    def __init__(self, timeline: TimelineWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._timeline = timeline

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        # Re-fit after the layout settles so we see the final viewport width
        QTimer.singleShot(0, self._timeline._refresh_size)
