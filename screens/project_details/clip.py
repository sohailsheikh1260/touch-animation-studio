"""Timeline clip model used by the project video editor timeline."""

# Shared positive bounds for scene-clip size controls (characters/backgrounds).
MIN_CHARACTER_SIZE_PCT = 20
MAX_CHARACTER_SIZE_PCT = 300


class Clip:
    """A block on the timeline (session-local)."""

    _next_uid = 1

    def __init__(self, start: float, duration: float, name: str, kind: str, data=None, track: int = 0, animation: str = "idle", x_offset: float = 0.0, y_offset: float = 0.0, size_scale: float = 1.0, x_end: float | None = None, y_end: float | None = None, anim_speed: float = 1.0, zoom_start: float = 1.0, zoom_end: float | None = None, text: str = "", flip_h: bool = False, flip_v: bool = False) -> None:
        self.uid = Clip._next_uid
        Clip._next_uid += 1
        self.start = start
        self.duration = duration
        self.name = name
        self.kind = kind  # "scene" | "audio"
        self.data = data  # (asset_kind, db id) for previews/playback
        self.track = track  # scene track index (0-based); audio always track -1
        self.animation = animation  # animation name for character clips (default 'idle')
        self.x_offset = x_offset  # stage-space X offset (scene clips)
        self.y_offset = y_offset  # stage-space Y offset (scene clips)
        self.size_scale = size_scale  # character size multiplier (1.0 = default)
        self.x_end = x_end  # endpoint X offset (None = no motion: stays at start)
        self.y_end = y_end  # endpoint Y offset (None = no motion: stays at start)
        self.anim_speed = anim_speed  # walk-cycle speed multiplier (1.0 = as authored)
        self.zoom_start = zoom_start  # whole-frame camera zoom at clip start (1.0 = none)
        self.zoom_end = zoom_end  # camera zoom at clip end (None = uses start)
        self.text = text  # text overlay content (asset_kind "text")
        self.flip_h = bool(flip_h)  # mirror the clip horizontally
        self.flip_v = bool(flip_v)  # mirror the clip vertically
