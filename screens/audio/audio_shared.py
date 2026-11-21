"""Shared constants and styles for the audio module and its drawer."""

from screens.theme import BG, CARD_BG, MUTED, TEXT

DRAWER_WIDTH = 340
CARD_W, CARD_H = 180, 232
GRID_COLUMNS = 3

AUDIO_TYPE_LABELS = {
    "effect": "Effect",
    "animal": "Animal",
    "vehicle": "Vehicle",
    "other": "Other",
    "voice": "Voice",
    "dialogs": "Dialogs",
}
AUDIO_TYPE_ICONS = {
    "effect": "✨",
    "animal": "🐾",
    "vehicle": "🚗",
    "other": "🎵",
    "voice": "🎙",
    "dialogs": "💬",
}
GLOBAL_SCOPE = "global"
PROJECT_SCOPE = "project"

# --- Text to Audio engines -------------------------------------------------
MODEL_LOCAL = "local"   # offline pyttsx3 (SAPI5)
MODEL_EDGE = "edge"     # online neural voices via edge-tts

MODEL_LABELS = {
    MODEL_LOCAL: "Local TTS (Offline)",
    MODEL_EDGE: "Edge TTS (Online Neural)",
}

# Curated neural voices (verified ShortNames from edge_tts.list_voices()).
EDGE_TTS_VOICES = [
    ("hi-IN-MadhurNeural", "Hindi – Madhur (Male)"),
    ("hi-IN-SwaraNeural", "Hindi – Swara (Female)"),
    ("en-IN-NeerjaNeural", "English (India) – Neerja (Female)"),
    ("en-US-GuyNeural", "English (US) – Guy (Male)"),
    ("en-US-AriaNeural", "English (US) – Aria (Female)"),
    ("en-GB-RyanNeural", "English (UK) – Ryan (Male)"),
    ("en-GB-SoniaNeural", "English (UK) – Sonia (Female)"),
]

CARD_STYLE = (
    f"QFrame {{ background-color: {CARD_BG};"
    f"  border: 2px solid {CARD_BG}; border-radius: 14px; }}"
    "QFrame:hover { border-color: #7c3aed; }"
)
CARD_LABEL_STYLE = "background-color: transparent; border: none;"
PLACEHOLDER_STYLE = f"color: {MUTED}; font-size: 12px; {CARD_LABEL_STYLE}"

TOP_BUTTON_STYLE = (
    f"QPushButton {{ background-color: {CARD_BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 16px; font-size: 14px; }"
    "QPushButton:hover { background-color: #334155; }"
)

CREATE_BUTTON_STYLE = (
    "QPushButton { background-color: #7c3aed; color: #e2e8f0;"
    "  border: none; border-radius: 8px;"
    "  padding: 8px 20px; font-size: 14px; font-weight: bold; }"
    "QPushButton:hover { background-color: #8b5cf6; }"
)

INPUT_STYLE = (
    f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 8px 12px; font-size: 14px; }"
)

COMBO_STYLE = (
    f"QComboBox {{ background-color: {BG}; color: {TEXT};"
    "  border: 1px solid #334155; border-radius: 8px;"
    "  padding: 6px 10px; font-size: 13px; }"
    "QComboBox QAbstractItemView { background-color: #1e293b; color: #e2e8f0;"
    "  selection-background-color: #334155; }"
)

SAVE_BUTTON_STYLE = (
    "QPushButton { background-color: #16a34a; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px;"
    "  font-size: 15px; font-weight: bold; }"
    "QPushButton:hover { background-color: #22c55e; }"
)

PLAY_BUTTON_STYLE = (
    "QPushButton { background-color: #0e7490; color: #e2e8f0;"
    "  border: none; border-radius: 8px; padding: 10px; font-size: 14px; }"
    "QPushButton:hover { background-color: #0891b2; }"
)

DANGER_BUTTON_STYLE = (
    f"QPushButton {{ background-color: #7f1d1d; color: {TEXT};"
    "  border: none; border-radius: 8px; padding: 10px; font-size: 14px; }"
    "QPushButton:hover { background-color: #991b1b; }"
    "QPushButton:disabled { color: #64748b; }"
)

AUDIO_FILTER = "Audio (*.mp3 *.wav *.ogg *.m4a *.flac *.aac *.opus)"
