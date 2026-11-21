"""Marker image storage (files in markers/)."""

from screens.image_store import ImageStore

_store = ImageStore("markers")

save_image = _store.save_image
delete_image = _store.delete_image
absolute_path = _store.absolute_path
