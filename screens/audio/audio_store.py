"""Audio storage for the audio screen (files in audios/)."""

from screens.image_store import AUDIO_EXTENSIONS, FileStore

_store = FileStore("audios", AUDIO_EXTENSIONS)

save_audio = _store.save_file
delete_audio = _store.delete_file
absolute_path = _store.absolute_path
