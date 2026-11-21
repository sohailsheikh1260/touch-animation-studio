"""Groq-powered chat panel for the editor sidebar ("Chat" tab).

A simple AI-assistant chat: the user types a message, the Groq API
(OpenAI-compatible endpoint) answers, and conversation context is kept
and trimmed automatically so the model remembers the recent chat.

API key priority: `config.py` (GROQ_API_KEY) -> GROQ_API_KEY environment
variable -> GROQ_API_KEY line in `.env` -> saved key in `groq_api_key.txt`
(project root). A key can also be pasted into the panel.
"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import config

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from screens.theme import BG, MUTED, TEXT

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
MAX_MESSAGES_IN_CONTEXT = 16
MAX_TOOL_ROUNDS = 4

KEY_FILE = Path(__file__).resolve().parents[2] / "groq_api_key.txt"

SYSTEM_PROMPT = (
    "You are a friendly assistant inside 'touch-animation', a Python/PySide6 "
    "app for building small animated videos: a project editor with a media "
    "library (characters, backgrounds, audio, animations), a multi-row "
    "timeline with clips, per-clip character motion (start/end points), size, "
    "walk-cycle animations (idle/walk/talk...), character size and speed, "
    "camera zoom effects, and MP4 export. Answer briefly and helpfully."
)


def _from_env_file() -> str:
    """Optional GROQ_API_KEY line in a `.env` file (project root)."""
    path = Path(__file__).resolve().parents[2] / ".env"
    try:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GROQ_API_KEY"):
                    value = line.split("=", 1)[1].strip().strip("'\"")
                    if value:
                        return value
    except Exception:
        pass
    return ""


def load_api_key() -> str:
    """Key priority: config.py -> environment variable -> .env -> key file."""
    try:
        config_key = (config.GROQ_API_KEY or "").strip()
    except Exception:
        config_key = ""
    for key in (
        config_key,
        os.environ.get("GROQ_API_KEY", "").strip(),
        _from_env_file(),
    ):
        if key:
            return key
    try:
        if KEY_FILE.is_file():
            key = KEY_FILE.read_text(encoding="utf-8").strip()
            if key:
                return key
    except Exception:
        pass
    return ""


class ChatWorker(QThread):
    """Off-UI thread performing a Groq chat completion request."""

    replied = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        api_key: str,
        messages: list[dict],
        parent=None,
        tools: list[dict] | None = None,
        tool_handlers: dict[str, Callable] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("groq-chat-worker")
        self._api_key = api_key
        self._messages = messages
        self._tools = list(tools or [])
        self._tool_handlers = dict(tool_handlers or {})

    def run(self) -> None:  # noqa: D102 (thread entry point)
        try:
            reply = self._request()
            self.replied.emit(reply)
        except Exception as exc:  # noqa: BLE001 (report any failure in-chat)
            self.failed.emit(str(exc))

    def _request(self) -> str:
        messages = [dict(message) for message in self._messages]

        for _round_index in range(MAX_TOOL_ROUNDS):
            message = self._response_message(self._post(messages))
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                reply = (message.get("content") or "").strip()
                print(f"[AI Chat] assistant: {reply}", flush=True)
                return reply

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name", "")
                raw_arguments = function.get("arguments") or "{}"
                print(f"[AI Chat] tool call: {name}({raw_arguments})", flush=True)

                try:
                    arguments = (
                        json.loads(raw_arguments)
                        if isinstance(raw_arguments, str)
                        else raw_arguments
                    )
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be a JSON object.")
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    result: object = {"error": f"Invalid tool arguments: {exc}"}
                else:
                    handler = self._tool_handlers.get(name)
                    if handler is None:
                        result = {"error": f"Unknown tool '{name}'."}
                    else:
                        try:
                            result = handler(**arguments)
                        except Exception as exc:  # noqa: BLE001
                            result = {"error": str(exc)}

                tool_content = (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False)
                )
                print(f"[AI Chat] tool result: {tool_content}", flush=True)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "name": name,
                        "content": tool_content,
                    }
                )

        # Ask for a final text answer without allowing another tool round.
        message = self._response_message(self._post(messages, include_tools=False))
        reply = (message.get("content") or "").strip()
        print(f"[AI Chat] assistant: {reply}", flush=True)
        return reply

    def _post(self, messages: list[dict], include_tools: bool = True) -> dict:
        request_data: dict = {
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.7,
        }
        if include_tools and self._tools:
            request_data["tools"] = self._tools
            request_data["tool_choice"] = "auto"

        print("\n[AI Chat] --- API request ---", flush=True)
        if include_tools and self._tools:
            print(f"[AI Chat] tools: {self._tools}", flush=True)
        for message in messages:
            content = message.get("content")
            if content:
                print(f"[AI Chat] {message.get('role', '?')}: {content}", flush=True)
            if message.get("tool_calls"):
                print(
                    f"[AI Chat] {message.get('role', '?')}: tool_calls="
                    f"{message['tool_calls']}",
                    flush=True,
                )

        payload = json.dumps(request_data).encode("utf-8")
        req = urllib.request.Request(
            GROQ_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                # Cloudflare (403 error 1010) blocks the default
                # "Python-urllib/x.y" User-Agent; send a normal one.
                "User-Agent": "Mozilla/5.0 (touch-animation chat)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            raise RuntimeError(f"HTTP {exc.code}: {detail[:300]}") from exc

    @staticmethod
    def _response_message(result: dict) -> dict:
        try:
            return result["choices"][0]["message"]
        except Exception as exc:  # unexpected response shape
            raise RuntimeError(f"Unexpected response: {str(result)[:300]}") from exc


class ChatPanel(QWidget):
    """Chat UI: log, input row and API-key row; keeps conversation context."""

    history_changed = Signal(object)
    busy_changed = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        system_prompt: str | None = None,
        tools: list[dict] | None = None,
        tool_handlers: dict[str, Callable] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"QWidget {{ background-color: {BG}; border: 1px solid #334155;"
            "  border-radius: 8px; }"
        )
        self._history: list[dict] = []
        self._worker: ChatWorker | None = None
        self._system_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
        self._tools = list(tools or [])
        self._tool_handlers = dict(tool_handlers or {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {BG}; color: {TEXT};"
            "  border: none; font-size: 12px; }"
        )
        self.log.setPlaceholderText("💬 Ask anything about your project…")
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log, 1)

        # API key row (hidden when a key is available)
        self.key_row = QHBoxLayout()
        key_label = QLineEdit()
        key_label.setEchoMode(QLineEdit.Password)
        key_label.setPlaceholderText("Paste Groq API key…")
        key_label.setStyleSheet(
            f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 6px;"
            "  padding: 4px 6px; font-size: 12px; }"
        )
        key_save = QPushButton("🔑")
        key_save.setFixedWidth(30)
        key_save.setCursor(Qt.PointingHandCursor)
        key_save.setStyleSheet(
            f"QPushButton {{ background-color: #334155; color: {TEXT};"
            "  border: none; border-radius: 6px; padding: 4px; }"
        )
        key_save.clicked.connect(lambda: self._save_key(key_label.text()))
        self.key_row.addWidget(key_label, 1)
        self.key_row.addWidget(key_save)
        layout.addLayout(self.key_row)
        has_key = bool(load_api_key())
        self.key_row.itemAt(0).widget().setEnabled(not has_key)

        # Input row
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message…")
        self.input.setStyleSheet(
            f"QLineEdit {{ background-color: {BG}; color: {TEXT};"
            "  border: 1px solid #334155; border-radius: 6px;"
            "  padding: 5px 8px; font-size: 12px; }"
        )
        self.input.returnPressed.connect(self._on_send)
        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(30, 26)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background-color: #1d4ed8; color: {TEXT};"
            "  border: none; border-radius: 6px; padding: 2px; }"
            "QPushButton:disabled { background-color: #334155; color: #64748b; }"
        )
        self.send_btn.clicked.connect(self._on_send)
        self.clear_btn = QPushButton("🧹")
        self.clear_btn.setFixedSize(30, 26)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setToolTip("Clear the conversation (context too)")
        self.clear_btn.setStyleSheet(
            f"QPushButton {{ background-color: #334155; color: {TEXT};"
            "  border: none; border-radius: 6px; padding: 2px; }"
        )
        self.clear_btn.clicked.connect(self._clear_chat)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_btn)
        input_row.addWidget(self.clear_btn)
        layout.addLayout(input_row)

        if not has_key:
            self.log.setPlaceholderText(
                "💬 Chat (paste your Groq API key above, then ask anything…)"
            )

    @property
    def history(self) -> list[dict]:
        return [dict(message) for message in self._history]

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt.strip()

    def set_history(self, messages: list[dict]) -> None:
        """Replace the visible conversation and its model context."""
        self._history = [
            {
                "role": str(message.get("role", "")),
                "content": str(message.get("content", "")),
            }
            for message in messages
            if isinstance(message, dict)
        ]
        self.log.clear()
        self.log.setPlaceholderText("💬 Ask anything about your project…")
        for message in self._history:
            prefix = "🧑 " if message["role"] == "user" else "🤖 "
            self._append(prefix + message["content"])

    # ------------------------------------------------------------ actions
    def _on_send(self) -> None:
        text = self.input.text().strip()
        if not text or self._worker is not None:
            return
        api_key = load_api_key()
        if not api_key:
            self.log.appendPlainText("⚠️ Set a Groq API key first.")
            return
        self._append("🧑 " + text)
        self.input.clear()
        self._history.append({"role": "user", "content": text})
        self.history_changed.emit(self.history)
        self._start_worker(api_key)

    def _start_worker(self, api_key: str) -> None:
        self.send_btn.setEnabled(False)
        self._worker = ChatWorker(
            api_key,
            self._context_messages(),
            self,
            tools=self._tools,
            tool_handlers=self._tool_handlers,
        )
        self._worker.replied.connect(self._on_reply)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self.busy_changed.emit(True)

    def _on_reply(self, text: str) -> None:
        self._worker_done()
        text = (text or "").strip() or "(empty reply)"
        self._history.append({"role": "assistant", "content": text})
        self._append("🤖 " + text)
        self.history_changed.emit(self.history)

    def _on_failed(self, message: str) -> None:
        self._worker_done()
        self.log.appendPlainText(f"⚠️ Chat error: {message}")

    def _worker_done(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
            self.send_btn.setEnabled(True)
            self.busy_changed.emit(False)

    def _clear_chat(self) -> None:
        self._history.clear()
        self.log.clear()
        self.log.setPlaceholderText("💬 Ask anything… (context cleared)")
        self.history_changed.emit(self.history)

    # ------------------------------------------------------------ context
    def _context_messages(self) -> list[dict]:
        """System prompt + the last MAX_MESSAGES_IN_CONTEXT chat messages."""
        return [{"role": "system", "content": self._system_prompt}] + [
            {"role": m["role"], "content": m["content"]}
            for m in self._history[-MAX_MESSAGES_IN_CONTEXT:]
        ]

    # ------------------------------------------------------------ key
    def _save_key(self, key: str) -> None:
        key = key.strip()
        if not key:
            self.log.appendPlainText("⚠️ Key is empty — nothing saved.")
            return
        try:
            KEY_FILE.write_text(key, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self.log.appendPlainText(f"⚠️ Could not save key: {exc}")
            return
        self.log.appendPlainText("🔑 Groq API key saved.")
        self.key_row.itemAt(0).widget().setEnabled(False)

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)
        scroll = self.log.verticalScrollBar()
        scroll.setValue(scroll.maximum())