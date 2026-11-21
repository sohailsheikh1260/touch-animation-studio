"""Screen size presets for the editor preview stage (canvas aspect ratios)."""

SCREEN_PRESETS = [
    {"id": "youtube-hd", "name": "YouTube HD", "width": 1280, "height": 720, "category": "YouTube"},
    {"id": "youtube-full-hd", "name": "YouTube Full HD", "width": 1920, "height": 1080, "category": "YouTube"},
    {"id": "youtube-4k", "name": "YouTube 4K", "width": 3840, "height": 2160, "category": "YouTube"},
    {"id": "youtube-shorts", "name": "YouTube Shorts", "width": 1080, "height": 1920, "category": "Social Media"},
    {"id": "instagram-reels", "name": "Instagram Reels", "width": 1080, "height": 1920, "category": "Social Media"},
    {"id": "tiktok", "name": "TikTok", "width": 1080, "height": 1920, "category": "Social Media"},
    {"id": "instagram-square", "name": "Instagram Square", "width": 1080, "height": 1080, "category": "Social Media"},
    {"id": "instagram-portrait", "name": "Instagram Portrait", "width": 1080, "height": 1350, "category": "Social Media"},
    {"id": "facebook-post", "name": "Facebook Post", "width": 1200, "height": 630, "category": "Social Media"},
    {"id": "pinterest", "name": "Pinterest Pin", "width": 1000, "height": 1500, "category": "Social Media"},
    {"id": "snapchat", "name": "Snapchat Story", "width": 1080, "height": 1920, "category": "Social Media"},
    {"id": "cinema", "name": "Cinema", "width": 2048, "height": 858, "category": "Professional"},
    {"id": "custom", "name": "Custom Size", "width": 1920, "height": 1080, "category": "Custom"},
]

DEFAULT_PRESET_ID = "youtube-hd"


def preset_by_id(preset_id: str):
    for preset in SCREEN_PRESETS:
        if preset["id"] == preset_id:
            return preset
    return None
