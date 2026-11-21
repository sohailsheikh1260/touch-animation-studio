"""AI agent system prompt, tools, and tool handlers."""

from pathlib import Path

import database
from screens.character_details.export import import_character_file
from screens.project_details.chat_option import ChatPanel

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SYSTEM_PROMPT = (
    "You are the AI agent inside Touch Animation Studio, a Python/PySide6 app "
    "for building animated videos. Help with projects, backgrounds, characters, "
    "animations, audio, timelines, and MP4 export. Keep answers clear and brief.\n\n"
    "Character import rules:\n"
    "- When the user explicitly asks to import a character, use the import_character tool.\n"
    "- If the target character name is unknown, call list_characters first.\n"
    "- Import into an existing character; never imply a character was imported "
    "until the tool result confirms success.\n"
    "- If the file path or target character is missing, ask the user for it."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_characters",
            "description": "List existing character names and IDs available for import.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_character",
            "description": (
                "Import character parts and animations from a JSON file into an "
                "existing character."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "character_name": {
                        "type": "string",
                        "description": "Name of the existing target character.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to the character JSON file.",
                    },
                },
                "required": ["character_name", "file_path"],
                "additionalProperties": False,
            },
        },
    },
]


def list_characters_tool() -> dict:
    """Return the characters available as import targets."""
    characters = [
        {"id": character["id"], "name": character["name"]}
        for character in database.list_characters()
    ]
    return {"characters": characters}


def import_character_tool(character_name: str, file_path: str) -> dict:
    """Import a character JSON file into an existing character."""
    requested_name = (character_name or "").strip()
    characters = database.list_characters()
    target = next(
        (
            character
            for character in characters
            if character["name"].casefold() == requested_name.casefold()
        ),
        None,
    )
    if target is None:
        available = ", ".join(character["name"] for character in characters) or "none"
        return {
            "ok": False,
            "error": f"Character '{requested_name}' does not exist. Available: {available}",
        }

    source = Path(file_path or "").expanduser()
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    if source.suffix.lower() != ".json":
        return {"ok": False, "error": "Character import requires a JSON file."}
    if not source.is_file():
        return {"ok": False, "error": f"Character JSON was not found: {source}"}

    try:
        result = import_character_file(target["id"], str(source))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "character_id": target["id"],
        "character_name": target["name"],
        "file_path": str(source),
        **result,
    }


class AIChatAgent(ChatPanel):
    """Chat panel configured with the project agent prompt and tools."""

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
            tool_handlers={
                "list_characters": list_characters_tool,
                "import_character": import_character_tool,
            },
        )
