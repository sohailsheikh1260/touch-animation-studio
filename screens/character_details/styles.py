"""Shared widget styles for the character-details tabs (same layout across tabs)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from screens.theme import BG, CARD_BG, MUTED, TEXT

CARD_LABEL_STYLE = "background-color: transparent; border: none;"
PLACEHOLDER_STYLE = f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"

TOP_BUTTON_STYLE = (
    f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px; }"
    "QPushButton:hover { background-color: #334155; }"
    "QPushButton:disabled { background-color: #0f172a; color: #64748b;"
    "  border-color: #1e293b; }"
)

# Destructive action (matches DELETE_BUTTON_STYLE used across the app).
DELETE_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
    "  border: 1px solid #991b1b; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
    "QPushButton:disabled { background-color: #0f172a; color: #64748b;"
    "  border-color: #1e293b; }"
)

INPUT_STYLE = (
    f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

IMAGE_PANEL_STYLE = (
    f"QLabel {{ background-color: {CARD_BG};"
    "  border: 1px solid #334155; border-radius: 12px;"
    f"  color: {MUTED}; font-size: 14px; }}"
)

MUTED_TEXT = f"color: {MUTED}; font-size: 13px;"
INFO_TEXT = f"color: {TEXT}; font-size: 14px;"
HEADING_STYLE = f"color: {TEXT}; font-size: 16px; font-weight: bold; {CARD_LABEL_STYLE}"

# The default body-part list lives in config.BODY_PARTS (single source of
# truth shared by the Mark tab, the Skeleton tab and the Marker module).


from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def make_delete_icon(size: int = 18):
    """Generate a simple red 'X' icon (renders reliably on all platforms)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#ef4444"))
    pen.setWidth(2)
    p.setPen(pen)
    m = 4
    p.drawLine(m, m, size - m, size - m)
    p.drawLine(size - m, m, m, size - m)
    p.end()
    return QIcon(pix)


def make_select_icon(size: int = 18):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#facc15"))
    pen.setWidth(2)
    p.setPen(pen)
    p.drawEllipse(2, 2, size - 4, size - 4)
    p.end()
    return QIcon(pix)


def make_edit_icon(size: int = 18):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#38bdf8"))
    pen.setWidth(2)
    p.setPen(pen)
    p.drawLine(2, size - 2, size - 2, 2)
    p.drawLine(size - 2, 2, size - 4, 2)
    p.drawLine(2, size - 2, 2, size - 4)
    p.end()
    return QIcon(pix)


def make_visible_icon(size: int = 18):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#22c55e"))
    pen.setWidth(2)
    p.setPen(pen)
    p.drawEllipse(2, size // 3, size - 4, size // 3)
    p.setBrush(QColor("#22c55e"))
    p.drawEllipse(size // 2 - 2, size // 2 - 2, 4, 4)
    p.end()
    return QIcon(pix)


def make_hidden_icon(size: int = 18):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#94a3b8"))
    pen.setWidth(2)
    p.setPen(pen)
    p.drawEllipse(2, size // 3, size - 4, size // 3)
    pen.setColor(QColor("#ef4444"))
    p.setPen(pen)
    p.drawLine(2, size - 2, size - 2, 2)
    p.end()
    return QIcon(pix)


def make_lock_icon(size: int = 18):
    """Closed padlock icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#ef4444"))
    pen.setWidth(2)
    p.setPen(pen)
    # shackle
    p.drawArc(4, 2, size - 8, size - 8, 0, 180 * 16)
    # body
    p.setBrush(QColor("#ef4444"))
    p.drawRect(3, size // 2, size - 6, size // 2 - 2)
    p.end()
    return QIcon(pix)


def make_unlock_icon(size: int = 18):
    """Open padlock icon."""
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = p.pen()
    pen.setColor(QColor("#22c55e"))
    pen.setWidth(2)
    p.setPen(pen)
    # open shackle
    p.drawArc(4, 2, size - 8, size - 8, 0, 120 * 16)
    p.drawLine(size - 4, 6, size - 4, 2)
    # body
    p.setBrush(QColor("#22c55e"))
    p.drawRect(3, size // 2, size - 6, size // 2 - 2)
    p.end()
    return QIcon(pix)
