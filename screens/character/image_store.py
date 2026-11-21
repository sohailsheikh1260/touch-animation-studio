"""Character image storage (files in images/)."""

from screens.image_store import ImageStore

_store = ImageStore("images")

save_image = _store.save_image
delete_image = _store.delete_image
absolute_path = _store.absolute_path
