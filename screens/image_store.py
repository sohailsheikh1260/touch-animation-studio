"""Generic image storage used by screens that attach images to records.

Each store keeps files in its own folder at the project root (created on
demand) and the database only stores stable relative paths ("<folder>/<file>").
"""

import shutil
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus"}


class FileStore:
    """Stores picked files in their own folder at the project root."""

    def __init__(self, folder: str, allowed_extensions: set[str]) -> None:
        self.folder = folder  # e.g. "images", "backgrounds", "audios"
        self.allowed_extensions = allowed_extensions
        self.folder_path = PROJECT_ROOT / folder

    def save_file(self, source_path: str) -> str:
        """Copy a file into this store's folder; return its relative path."""
        source = Path(source_path)
        if not source.is_file():
            raise ValueError("Selected file does not exist.")
        if source.suffix.lower() not in self.allowed_extensions:
            allowed = ", ".join(sorted(self.allowed_extensions))
            raise ValueError(f"Unsupported file type. Allowed: {allowed}")

        self.folder_path.mkdir(exist_ok=True)
        suffix = source.suffix.lower().replace(".jpeg", ".jpg").replace(".m4a", ".m4a")
        filename = f"{uuid.uuid4().hex}{suffix}"
        shutil.copy2(source, self.folder_path / filename)
        return f"{self.folder}/{filename}"

    # Convenience alias (most stores handle images)
    save_image = save_file

    def delete_file(self, relative_path: str) -> None:
        """Remove a stored file; path-safe (only files inside this folder)."""
        if not relative_path:
            return
        path = self.absolute_path(relative_path)
        try:
            if (
                path.resolve().is_relative_to(self.folder_path.resolve())
                and path.is_file()
            ):
                path.unlink()
        except (OSError, ValueError):
            pass

    # Alias kept for the image-based screens
    delete_image = delete_file

    def absolute_path(self, relative_path: str) -> Path:
        return PROJECT_ROOT / relative_path


class ImageStore(FileStore):
    """FileStore for image files (used by character/background screens)."""

    def __init__(self, folder: str) -> None:
        super().__init__(folder, ALLOWED_EXTENSIONS)
