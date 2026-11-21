"""Shared colors and widget styles for all screens."""

BG = "#0f172a"
HEADER_BG = "#1e293b"
CARD_BG = "#1e293b"
CARD_BG_HOVER = "#334155"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
ACCENT = "#38bdf8"

CARD_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    f"  border: 2px solid {CARD_BG};"
    "  border-radius: 16px;"
    "}"
    "QFrame:hover { border-color: #38bdf8; }"
)

CARD_LABEL_STYLE = "background-color: transparent; border: none;"

BACK_BUTTON_STYLE = (
    f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px;}"
    "QPushButton:hover { background-color: #334155; }"
)
