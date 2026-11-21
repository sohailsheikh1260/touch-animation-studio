"""Skeleton-animated character rendering for the timeline preview AND the
video export worker.

Characters with a skeleton render through the SAME model as the character
details tabs (screens.character_details.skeleton_loader): bones, bone
positions, bone-attached part images and the unified part draw order all
come from the shared loader, so the editor preview matches the Skeleton and
Animation tabs exactly. The walk-cycle animation (per-bone limb rotations +
vertical bob) is applied as bone rotation deltas on top of that model.

Characters without skeleton attachments fall back to the legacy assembled
body-part rendering.

Rendering uses QImage end-to-end: QImage (unlike QPixmap) is safe to paint
from non-GUI threads, so the export worker can render skeleton frames off
the UI thread. The preview wrapper converts the final QImage to QPixmap.
"""

import json
import math
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

import database
from screens.character import image_store as character_store
from screens.character_details.skeleton_loader import (
    load_character_skeleton_data,
    part_draw_key,
)
from screens.project_details.media_cache import AssetCache

CANVAS_SIZE = 2048  # native render size


def _wrap_angle(a: float) -> float:
    """Wrap an angle in radians to (-pi, pi]."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _angle_of(v: tuple[float, float]) -> float:
    """Angle of a direction vector."""
    return math.atan2(v[1], v[0])

# Skeleton hierarchy between assembled body parts (parents before children in
# DRAW_ORDER). torso is the root; limbs hang off it; head parts follow the head.
SKELETON_PARENT = {
    "torso": None,
    "head": "torso",
    "eyes": "head",
    "eyes-background": "head",
    "eyes-open": "head",
    "eye-close": "head",
    "eyebrow-1": "head",
    "eyebro-normal": "head",
    "eyebrow-angry": "head",
    "mouth-normal-4": "head",
    "mouth-talk-1": "head",
    "mouth-talk-2": "head",
    "mouth-talk-3": "head",
    "mouth-talk-4": "head",
    "mouth-angry-1": "head",
    "mouth-angry-2": "head",
    "mouth-angry-3": "head",
    "mouth-angry-4": "head",
    "mouth-smile-1": "head",
    "mouth-smile-2": "head",
    "mouth-smile-3": "head",
    "mouth-smile-4": "head",
    "left-arm": "torso",
    "left-forearm": "left-arm",
    "left-hand": "left-forearm",
    "left-hand-open": "left-forearm",
    "left-hand-close": "left-forearm",
    "left-hand-point": "left-forearm",
    "left-hand-grab": "left-forearm",
    "right-hand": "right-forearm",
    "right-hand-open": "right-forearm",
    "right-hand-close": "right-forearm",
    "right-hand-point": "right-forearm",
    "right-hand-grab": "right-forearm",
    "left-leg": "torso",
    "left-shin": "left-leg",
    "right-arm": "torso",
    "right-forearm": "right-arm",
    "right-hand": "right-forearm",
    "right-leg": "torso",
    "right-shin": "right-leg",
}

# Pivot point (as fraction of width/height from top-left) around which each
# part rotates. Limbs pivot at their top (joint to parent); torso at center;
# head at its bottom (neck); head-parts at center (follow the head).
PIVOT = {
    "torso": (0.5, 0.5),
    "head": (0.5, 1.0),
    "eyes-background": (0.5, 0.5),
    "eyes": (0.5, 0.5),
    "eyes-open": (0.5, 0.5),
    "eye-close": (0.5, 0.5),
    "eyebrow-1": (0.5, 0.5),
    "eyebro-normal": (0.5, 0.5),
    "eyebrow-angry": (0.5, 0.5),
    "mouth-normal-4": (0.5, 0.5),
    "mouth-talk-1": (0.5, 0.5),
    "mouth-talk-2": (0.5, 0.5),
    "mouth-talk-3": (0.5, 0.5),
    "mouth-talk-4": (0.5, 0.5),
    "mouth-angry-1": (0.5, 0.5),
    "mouth-angry-2": (0.5, 0.5),
    "mouth-angry-3": (0.5, 0.5),
    "mouth-angry-4": (0.5, 0.5),
    "mouth-smile-1": (0.5, 0.5),
    "mouth-smile-2": (0.5, 0.5),
    "mouth-smile-3": (0.5, 0.5),
    "mouth-smile-4": (0.5, 0.5),
    "left-arm": (0.5, 0.0),
    "left-forearm": (0.5, 0.0),
    "left-hand": (0.5, 0.0),
    "left-hand-open": (0.5, 0.0),
    "left-hand-close": (0.5, 0.0),
    "left-hand-point": (0.5, 0.0),
    "left-hand-grab": (0.5, 0.0),
    "right-hand": (0.5, 0.0),
    "right-hand-open": (0.5, 0.0),
    "right-hand-close": (0.5, 0.0),
    "right-hand-point": (0.5, 0.0),
    "right-hand-grab": (0.5, 0.0),
    "left-leg": (0.5, 0.0),
    "left-shin": (0.5, 0.0),
    "right-arm": (0.5, 0.0),
    "right-forearm": (0.5, 0.0),
    "right-hand": (0.5, 0.0),
    "right-leg": (0.5, 0.0),
    "right-shin": (0.5, 0.0),
}

# Draw order (parents before children).
DRAW_ORDER = [
    "torso",
    "head",
    "eyes-background",
    "eyes",
    "eyes-open",
    "eye-close",
    "eyebrow-1",
    "eyebro-normal",
    "eyebrow-angry",
    "mouth-normal-4",
    "mouth-talk-1",
    "mouth-talk-2",
    "mouth-talk-3",
    "mouth-talk-4",
    "mouth-angry-1",
    "mouth-angry-2",
    "mouth-angry-3",
    "mouth-angry-4",
    "mouth-smile-1",
    "mouth-smile-2",
    "mouth-smile-3",
    "mouth-smile-4",
    "left-arm",
    "left-forearm",
    "left-hand",
    "left-hand-open",
    "left-hand-close",
    "left-hand-point",
    "left-hand-grab",
    "left-leg",
    "left-shin",
    "right-arm",
    "right-forearm",
    "right-hand",
    "right-hand-open",
    "right-hand-close",
    "right-hand-point",
    "right-hand-grab",
    "right-leg",
    "right-shin",
]

_MOUTH_GROUPS_FOR_TYPE = {
    # "closed"/"open" are the new single-variant mouth part names
    # (mouth-closed, mouth-open); "normal"/"talk"/"smile"/"angry" are the
    # legacy indexed variant names (mouth-normal-4, mouth-talk-1, ...).
    "normal": {"talk", "normal", "closed"},
    "smile": {"smile"},
    "aggressive": {"angry"},
    "talking": {"talk", "open"},
}


def part_visible_for_anim(name: str, mouth_type: str, anim_name: str) -> bool:
    low = str(name).lower()
    if low.startswith("mouth-"):
        bits = low.split("-")
        group = bits[1] if len(bits) >= 2 else ""
        active = _MOUTH_GROUPS_FOR_TYPE.get(str(mouth_type).lower(), {"talk"})
        return group in active
    if low in ("eyes-open", "eye-open", "eyes-close", "eye-close"):
        closed = any(k in str(anim_name).lower() for k in ("blink", "sleep", "crying", "cry"))
        if "close" in low:
            return closed
        return not closed
    return True

# Short-TTL row cache: playback renders ~30 frames/second and each of the
# old lookups opened a brand-new SQLite connection; this keeps results for
# 2.5s (edits made elsewhere still appear within a couple of seconds).
# NOTE: this cache may be touched from both the GUI thread (preview) and
# the export worker; only atomic dict operations are used, so CPython
# keeps it consistent.
_row_cache = AssetCache()

_stage_cache: dict[int, tuple[float, QImage]] = {}  # character_id -> (mtime, img)
_crop_cache: dict[tuple, QImage] = {}  # (character_id, part_id, left, top, w, h) -> crop
_MAX_CROP_CACHE = 512


def _stage_image(character_id: int, image_path) -> QImage:
    """The character's full stage image (QImage), cached until the file
    changes. QImage decode is thread-safe; QPixmap is not."""
    path = character_store.absolute_path(image_path)
    if not image_path or not path.is_file():
        return QImage()
    try:
        mtime = os.stat(str(path)).st_mtime
    except OSError:
        mtime = 0.0
    cached = _stage_cache.get(character_id)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    img = QImage(str(path))
    _stage_cache[character_id] = (mtime, img)
    return img


def _bone_angle(name: str, t: float, leg_amplitude: float, arm_amplitude: float) -> float:
    """Per-bone rotation (degrees) for the walk cycle (see animation tab)."""
    nl = name.lower()
    leg = leg_amplitude * math.sin(t)
    arm = arm_amplitude * math.sin(t)
    if nl in ("left-arm",):
        return -arm
    if nl in ("right-arm",):
        return arm
    if nl in ("left-leg",):
        return leg
    if nl in ("right-leg",):
        return -leg
    return 0.0


def _pivot_specs(parts: dict) -> dict[str, tuple[float, float]]:
    """Rest-pose JOINT position of every part: top-left + pivot offset
    (the pivot fraction comes from the animation tab's PIVOT table).
    Limbs pivot at their top-center (the joint to their parent)."""
    specs: dict[str, tuple[float, float]] = {}
    for name, p in parts.items():
        w = p["crop"].width()
        h = p["crop"].height()
        fx, fy = PIVOT.get(name, (0.5, 0.5))
        specs[name] = (p["x"] + w * fx, p["y"] + h * fy)
    return specs


def _pivot_offset(parts: dict, name: str) -> tuple[float, float]:
    p = parts[name]
    w = p["crop"].width()
    h = p["crop"].height()
    fx, fy = PIVOT.get(name, (0.5, 0.5))
    return (w * fx, h * fy)


def _compute_transforms(parts: dict, t: float, leg_amplitude: float, arm_amplitude: float, bob: float) -> dict:
    """Hierarchical, JOINT-ANCHORED transforms.

    Each part is transformed so that its pivot (the joint printed in
    PIVOT/animation.py) stays attached where the skeleton says it is:

    - a part's world pivot = its parent's world pivot + the rest-pose
      pivot-to-pivot offset rotated by the parent's angle. Joints
      therefore never separate when a parent bone swings (the old
      top-left anchoring made knees/hips drift).
    - the returned (x, y) is the top-left the painter draws that places
      the crop so its pivot sits exactly on that world pivot; the paint
      step then rotates the crop around the same pivot, so pivot is
      invariant across the swing.
    """
    transforms: dict[str, tuple[float, float, float]] = {}
    if not parts:
        return transforms

    rest_piv = _pivot_specs(parts)
    world_piv: dict[str, tuple[float, float]] = {}
    angle: dict[str, float] = {}

    def own_angle(name: str) -> float:
        return _bone_angle(name, t, leg_amplitude, arm_amplitude)

    def place(name: str, piv: tuple[float, float], a: float) -> None:
        off_x, off_y = _pivot_offset(parts, name)
        transforms[name] = (piv[0] - off_x, piv[1] - off_y, a)

    # torso is the root; it carries the vertical bob
    if "torso" in parts:
        angle["torso"] = 0.0
        rp = rest_piv["torso"]
        world_piv["torso"] = (rp[0], rp[1] + bob)
        place("torso", world_piv["torso"], 0.0)

    # parents before children (DRAW_ORDER guarantees this)
    for name in DRAW_ORDER:
        if name == "torso" or name not in parts:
            continue
        parent = SKELETON_PARENT.get(name)
        if parent is not None and parent in world_piv:
            pa = angle[parent]
            ox = rest_piv[name][0] - rest_piv[parent][0]
            oy = rest_piv[name][1] - rest_piv[parent][1]
            rad = math.radians(pa)
            wx = world_piv[parent][0] + ox * math.cos(rad) - oy * math.sin(rad)
            wy = world_piv[parent][1] + ox * math.sin(rad) + oy * math.cos(rad)
        else:
            # no known/loaded parent -> root part: rest pose, no bob
            pa = 0.0
            wx, wy = rest_piv[name]
        a = pa + own_angle(name)
        angle[name] = a
        world_piv[name] = (wx, wy)
        place(name, (wx, wy), a)

    # Unknown part names (not in DRAW_ORDER) -> legacy corner-anchored
    # behaviour so custom parts still render.
    for name in parts:
        if name in transforms:
            continue
        transforms[name] = (
            parts[name]["x"],
            parts[name]["y"],
            own_angle(name),
        )
    return transforms


def _load_parts_parts(character_id: int, stage: QImage) -> dict[str, dict]:
    """Load + crop the visible body parts of a character from its stage
    image, cached by (character, part, source rect)."""
    parts: dict[str, dict] = {}
    try:
        rows = _row_cache.db(("parts", character_id), lambda: database.list_character_parts(character_id))
    except Exception:
        rows = []
    for row in rows:
        try:
            data = json.loads(row["payload"]) if row["payload"] else {}
        except Exception:
            data = {}
        if not data.get("visible", True):
            continue
        left = int(data.get("left") or data.get("x") or 0)
        top = int(data.get("top") or data.get("y") or 0)
        w = int(data.get("width") or 0)
        h = int(data.get("height") or 0)
        if w <= 0 or h <= 0:
            continue
        key = (character_id, row["id"], left, top, w, h)
        crop = _crop_cache.get(key)
        if crop is None:
            crop = stage.copy(left, top, w, h)
            if crop.isNull():
                continue
            if len(_crop_cache) >= _MAX_CROP_CACHE:
                _crop_cache.clear()
            _crop_cache[key] = crop
        part_key = "eyes" if row["part_name"] == "eys" else row["part_name"]
        parts[part_key] = {
            "crop": crop,
            # A part crop belongs at its own source rect position - that is
            # how the Mark tab places it and it reassembles the original
            # image exactly. The legacy payload x/y is a stale default
            # (200, 200) for parts created by newer flows and must not be
            # used for placement.
            "x": left,
            "y": top,
            "z": int(data.get("z", 0)),
        }
    return parts


def _drive_map(bones) -> dict[str, str]:
    """Rotation partner per bone: a bone with exactly one child rotates
    together with that child's segment (same rule as the Animation tab)."""
    children: dict[str, list[str]] = {b["bone_name"]: [] for b in bones}
    for bone in bones:
        parent = bone["parent_name"]
        if parent and parent in children:
            children[parent].append(bone["bone_name"])
    return {
        name: (kids[0] if len(kids) == 1 else name)
        for name, kids in children.items()
    }


def _bone_frames(
    bones, deltas: dict[str, float], root_offset: tuple[float, float] = (0.0, 0.0)
):
    """Bone joint positions and world rotations (radians), parents first.

    Identical forward kinematics to the Animation tab's
    ``_forward_kinematics``: each segment keeps the Skeleton tab's rest
    geometry (offset + angle + length) and is rotated rigidly around its
    parent joint by the accumulated deltas from the root down.
    """
    bone_map = {b["bone_name"]: b for b in bones}

    def depth(name: str) -> int:
        level, cur = 0, bone_map.get(name)
        while cur is not None and cur["parent_name"]:
            level += 1
            cur = bone_map.get(cur["parent_name"])
            if level > 50:
                break
        return level

    positions: dict[str, tuple[float, float]] = {}
    rots: dict[str, float] = {}
    for name in sorted(bone_map, key=lambda n: (depth(n), n)):
        bone = bone_map[name]
        parent = bone["parent_name"]
        delta = deltas.get(name, 0.0)
        if parent and parent in positions:
            base = positions[parent]
            w = rots[parent] + delta
        else:
            base = root_offset
            w = delta
        if parent:
            ang = math.radians(float(bone["angle"] or 0.0))
            length = float(bone["length"] or 0.0)
            ddx = float(bone["x_offset"] or 0.0) + math.sin(ang) * length
            ddy = float(bone["y_offset"] or 0.0) + math.cos(ang) * length
        else:
            # Root bone: the offset alone positions the joint (the root's
            # own segment is not drawn) - same as the Animation tab.
            ddx = float(bone["x_offset"] or 0.0)
            ddy = float(bone["y_offset"] or 0.0)
        c, s = math.cos(w), math.sin(w)
        positions[name] = (base[0] + c * ddx - s * ddy, base[1] + s * ddx + c * ddy)
        rots[name] = w
    return positions, rots


def _walk_deltas(
    bone_images: dict, t: float, leg_amplitude: float, arm_amplitude: float
) -> dict[str, float]:
    """Walk-cycle bone rotation deltas (radians).

    Each animated body part swings the bone its image is attached to, so
    the limb rotates around its attachment joint and everything connected
    further down the skeleton follows.
    """
    deltas: dict[str, float] = {}
    for bone_name, records in bone_images.items():
        for record in records:
            part = record.get("part")
            if not part:
                continue
            angle = _bone_angle(part, t, leg_amplitude, arm_amplitude)
            if angle:
                deltas[bone_name] = deltas.get(bone_name, 0.0) + math.radians(angle)
    return deltas


# ---------------------------------------------------------------
# IK keyframe animation frames (screens.character_details model)
# ---------------------------------------------------------------

def _ik_anim_field(anim, key: str, default=None):
    """Read a field from an animation row (plain dict or sqlite3.Row)."""
    try:
        value = anim[key]
    except Exception:
        return default
    return default if value is None else value


def _normalise_ik_keyframe(kf: dict) -> dict:
    """Coerce a stored keyframe into a safe working dict."""
    try:
        t = float(kf.get("t") or 0.0)
    except (TypeError, ValueError):
        t = 0.0
    bones: dict[str, float] = {}
    for name, deg in (kf.get("bones") or {}).items():
        try:
            bones[str(name)] = float(deg)
        except (TypeError, ValueError):
            continue
    effs: dict[str, list[float]] = {}
    for name, pos in (kf.get("effs") or {}).items():
        try:
            effs[str(name)] = [float(pos[0]), float(pos[1])]
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    root = kf.get("root") or (0.0, 0.0)
    try:
        root = [float(root[0]), float(root[1])]
    except (TypeError, ValueError, IndexError, KeyError):
        root = [0.0, 0.0]
    return {"t": t, "root": root, "bones": bones, "effs": effs}


def _lerp_ik_pose(a: dict, b: dict, f: float) -> dict:
    """Linear interpolation between two keyframe poses (same math as the
    Character Details Animation tab's playback sampler)."""
    ra, rb = a["root"], b["root"]
    out = {
        "t": a["t"] + (b["t"] - a["t"]) * f,
        "root": [ra[0] + (rb[0] - ra[0]) * f, ra[1] + (rb[1] - ra[1]) * f],
        "bones": {},
        "effs": {},
    }
    for name in set(a["bones"]) | set(b["bones"]):
        va = float(a["bones"].get(name, 0.0))
        vb = float(b["bones"].get(name, 0.0))
        out["bones"][name] = va + (vb - va) * f
    for name in set(a["effs"]) | set(b["effs"]):
        pa = a["effs"].get(name)
        pb = b["effs"].get(name)
        if pa is None or pb is None:
            continue
        out["effs"][name] = [pa[0] + (pb[0] - pa[0]) * f, pa[1] + (pb[1] - pa[1]) * f]
    return out


def _sample_ik_pose(
    kfs: list, t_seconds: float, duration: float, loop: bool
) -> dict | None:
    """Sample a keyframe list at ``t_seconds`` (seconds into the animation),
    interpolating between neighbouring keys - mirrors the Animation tab's
    playback sampler (loop wrap + linear interp)."""
    pts = sorted((_normalise_ik_keyframe(k) for k in kfs or []), key=lambda k: k["t"])
    if not pts:
        return None
    if len(pts) == 1:
        return pts[0]
    t0 = pts[0]["t"]
    period = float(duration) if float(duration) > 1e-6 else max(pts[-1]["t"] - t0, 1e-6)
    t = float(t_seconds)
    if loop:
        t = t0 + ((t - t0) % period)
    t = min(max(t, t0), t0 + period)
    sample_pts = pts
    if loop and pts[-1]["t"] < t0 + period - 1e-9:
        sample_pts = pts + [dict(pts[0], t=t0 + period)]
    idx = 0
    for i in range(len(sample_pts) - 1):
        if sample_pts[i]["t"] <= t < sample_pts[i + 1]["t"]:
            idx = i
            break
    else:
        idx = max(0, len(sample_pts) - 2)
    a, b = sample_pts[idx], sample_pts[idx + 1]
    seg = b["t"] - a["t"]
    f = 0.0 if seg <= 1e-9 else (t - a["t"]) / seg
    f = max(0.0, min(1.0, f))
    return _lerp_ik_pose(a, b, f)


def _ik_frame_pose(anim, t_seconds: float, speed_mul: float):
    """Resolve a saved IK keyframe animation to the pose to paint at
    ``t_seconds``.

    Returns ``(pose, meta)``: ``pose`` is the keyframe dict (with "root",
    "bones" deg-deltas and "effs") or None when there is nothing to paint;
    ``meta`` carries the animation type / name used for the mouth & eye swap
    rules. Non-IK animation rows resolve to (None, None) - callers fall back
    to the procedural walk-cycle renderer.
    """
    if not isinstance(anim, dict) or "payload" not in anim:
        return None, None
    try:
        payload = (
            json.loads(anim["payload"])
            if isinstance(anim.get("payload"), str)
            else (anim.get("payload") or {})
        )
    except (ValueError, TypeError):
        payload = {}
    kfs = payload.get("keyframes") if isinstance(payload, dict) else None
    if not kfs:
        return None, None
    duration = float(_ik_anim_field(anim, "duration", 2.0) or 2.0)
    loop = bool(_ik_anim_field(anim, "loop", True))
    speed = float(_ik_anim_field(anim, "speed", 1.0) or 1.0)
    t = float(t_seconds) * speed * max(0.05, float(speed_mul or 1.0))
    pose = _sample_ik_pose(kfs, t, duration, loop)
    meta = {
        "mouth_type": str(_ik_anim_field(anim, "anim_type", "normal") or "normal"),
        "name": str(_ik_anim_field(anim, "name", "") or ""),
    }
    return pose, meta


def _ik_chain_ancestors(bone_map: dict, bone_name: str) -> list[str]:
    """Ancestor bones from the end joint up to (and excluding) the root."""
    ancestors: list[str] = []
    cur = bone_map.get(bone_name)
    while cur is not None and cur["parent_name"]:
        ancestors.append(cur["bone_name"])
        cur = bone_map.get(cur["parent_name"])
    return ancestors


def _solve_ik_chain(
    bone_map: dict,
    rest_dir: dict,
    seg_len: dict,
    positions: dict,
    rots: dict,
    end: str,
    seg_b: str,
    seg_a: str | None,
    pivot: str | None,
    bend_sign: float,
    target: tuple[float, float],
    assigned_target: tuple[float, float] | None = None,
    rest_sign: float = 1.0,
    rest_end: tuple | None = None,
) -> dict[str, float]:
    """Two-bone or one-bone IK -> bone rotation deltas (radians).

    Mirrors the Animation tab's ``IKChain`` solve so timeline frames produce
    exactly the same poses the character's own animation canvas produces.
    """
    result: dict[str, float] = {}
    if seg_a:
        pivot_pos = positions.get(pivot)
        if pivot_pos is None:
            return result
        d_a = rest_dir.get(seg_a, (0.0, 1.0))
        d_b = rest_dir.get(seg_b, (0.0, 1.0))
        l1 = seg_len.get(seg_a, 0.0)
        l2 = seg_len.get(seg_b, 0.0)
        dx, dy = target[0] - pivot_pos[0], target[1] - pivot_pos[1]
        raw = math.hypot(dx, dy)
        if raw < 1e-6:
            return result
        ux, uy = dx / raw, dy / raw
        dist = min(max(raw, abs(l1 - l2) + 1e-3), l1 + l2 - 1e-3)
        cos_a = (l1 * l1 + dist * dist - l2 * l2) / (2.0 * l1 * dist)
        alpha = math.acos(max(-1.0, min(1.0, cos_a)))
        s = bend_sign
        if (
            rest_end is not None
            and assigned_target is not None
            and math.hypot(assigned_target[0] - rest_end[0], assigned_target[1] - rest_end[1]) < 2.0
        ):
            # Target sits at the rest end -> keep the rest-pose branch so the
            # rest pose stays an exact fixed point (idle chains never drift).
            s = rest_sign
        c, sn = math.cos(s * alpha), math.sin(s * alpha)
        ax = ux * c - uy * sn
        ay = ux * sn + uy * c
        mid = (pivot_pos[0] + ax * l1, pivot_pos[1] + ay * l1)
        endp = (pivot_pos[0] + ux * dist, pivot_pos[1] + uy * dist)
        bx = (endp[0] - mid[0]) / l2
        by = (endp[1] - mid[1]) / l2
        result[seg_a] = _wrap_angle(math.atan2(ay, ax) - _angle_of(d_a))
        parent_delta = result.get(seg_a, 0.0)
        result[seg_b] = _wrap_angle(math.atan2(by, bx) - _angle_of(d_b) - parent_delta)
    else:
        parent_name = bone_map.get(end)
        end_pos = positions.get(parent_name["parent_name"]) if parent_name else None
        d_rest = rest_dir.get(end)
        if end_pos is None or d_rest is None:
            return result
        dx, dy = target[0] - end_pos[0], target[1] - end_pos[1]
        raw = math.hypot(dx, dy)
        if raw < 1e-6:
            return result
        delta = _wrap_angle(math.atan2(dy, dx) - _angle_of(d_rest))
        parent_name = bone_map.get(end)
        parent_rot = rots.get(parent_name["parent_name"], 0.0) if parent_name else 0.0
        delta = _wrap_angle(delta - parent_rot)
        limit = math.radians(35.0) if ("head" in end.lower() or "neck" in end.lower()) else math.radians(80.0)
        result[end] = max(-limit, min(limit, delta))
    return result


def _pose_ik_deltas(
    bones: list,
    bone_map: dict,
    rest_dir: dict,
    seg_len: dict,
    positions: dict,
    rots: dict,
    pose: dict,
    rest_pos: dict,
) -> dict[str, float]:
    """Bone deltas for a sampled IK pose, re-solving chains from the
    effector targets (generated animations author targets, not raw deltas)."""
    deltas: dict[str, float] = {}
    effs = pose.get("effs") or {}
    if not effs:
        return deltas
    keywords = ("wrist", "hand", "palm", "ankle", "foot", "toe", "head", "neck")
    for bone in bones:
        name = bone["bone_name"]
        parent = bone["parent_name"]
        low = name.lower()
        if not parent or not any(k in low for k in keywords):
            continue
        ancestors = _ik_chain_ancestors(bone_map, name)
        solved: dict[str, float] = {}
        if len(ancestors) >= 3:
            end, seg_b, seg_a, pivot = ancestors[0], ancestors[0], ancestors[1], ancestors[2]
            if end not in effs:
                continue
            d_a = rest_dir.get(seg_a, (0.0, 1.0))
            d_b = rest_dir.get(seg_b, (0.0, 1.0))
            cross = (d_a[0] + d_b[0]) * d_a[1] - (d_a[1] + d_b[1]) * d_a[0]
            rest_sign = 1.0 if cross >= 0 else -1.0
            posed_sign = rest_sign
            if "left" in end.lower() and any(k in end.lower() for k in ("ankle", "foot", "toe")):
                posed_sign = -rest_sign
            tgt = effs.get(end) or (0.0, 0.0)
            tgt_pos = (float(tgt[0]), float(tgt[1]))
            sol = _solve_ik_chain(
                bone_map, rest_dir, seg_len, positions, rots,
                end, seg_b, seg_a, pivot, posed_sign,
                tgt_pos, assigned_target=tgt_pos, rest_sign=rest_sign,
                rest_end=rest_pos.get(end),
            )
            solved.update(sol)
        elif ancestors:
            end = ancestors[0]
            if end not in effs:
                continue
            pivot = bone_map[ancestors[0]]["parent_name"]
            tgt = effs.get(end) or (0.0, 0.0)
            tgt_pos = (float(tgt[0]), float(tgt[1]))
            sol = _solve_ik_chain(
                bone_map, rest_dir, seg_len, positions, rots,
                end, end, None, pivot, 1.0,
                tgt_pos, assigned_target=tgt_pos,
            )
            solved.update(sol)
        deltas.update(solved)
    return deltas


def _paint_skeleton_model(
    painter: QPainter,
    character_id: int,
    character,
    t: float,
    leg_amplitude: float,
    arm_amplitude: float,
    bob: float,
    mouth_type: str,
    anim_name: str,
    ik_pose: dict | None = None,
    ik_meta: dict | None = None,
) -> bool:
    """Paint the character through the shared skeleton model.

    Bones, bone positions, attached part images and the unified draw order
    come from ``load_character_skeleton_data`` - the exact model the
    Skeleton and Animation tabs render, so the editor preview matches them.
    Walk-cycle rotations are applied as bone deltas.

    Returns True when the character has a usable skeleton (the character
    was painted, even if every part is currently hidden). Returns False
    when there is no skeleton/attachment data, so the caller can fall back
    to the legacy assembled-parts rendering.
    """
    data = _row_cache.db(
        ("skeldata", character_id),
        lambda: load_character_skeleton_data(dict(character), as_image=True),
    )
    bones = data.get("bones") or []
    bone_images = data.get("bone_images") or {}
    part_crops = data.get("part_crops") or {}
    part_visible = data.get("part_visible") or {}
    if not bones:
        return False

    entries = [
        (bone_name, record)
        for bone_name, records in bone_images.items()
        for record in records
    ]
    if not entries:
        return False
    entries.sort(key=lambda item: part_draw_key(data.get("part_layers") or {}, item))

    # Rest-pose frame (zero deltas) for the framing box.
    rest_pos, _rest_rots = _bone_frames(bones, {})
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    framed = False
    for bone_name, record in entries:
        part = record.get("part")
        crop = part_crops.get(part) if part else None
        if crop is None or crop.isNull():
            continue
        pos = rest_pos.get(bone_name)
        if pos is None:
            continue
        ax = pos[0] + float(record.get("dx", 0.0))
        ay = pos[1] + float(record.get("dy", 0.0))
        half_w, half_h = crop.width() / 2.0, crop.height() / 2.0
        min_x, max_x = min(min_x, ax - half_w), max(max_x, ax + half_w)
        min_y, max_y = min(min_y, ay - half_h), max(max_y, ay + half_h)
        framed = True
    if not framed:
        return False

    # Fit the character into the render canvas (the caller scales the whole
    # canvas to the clip height, so the character must fill it like the
    # legacy assembled rendering did).
    box_w = max(1.0, max_x - min_x)
    box_h = max(1.0, max_y - min_y)
    model_scale = min((CANVAS_SIZE * 0.92) / box_w, (CANVAS_SIZE * 0.92) / box_h)
    model_scale = max(0.02, min(4.0, model_scale))
    off_x = CANVAS_SIZE / 2.0 - model_scale * (min_x + max_x) / 2.0
    off_y = CANVAS_SIZE / 2.0 - model_scale * (min_y + max_y) / 2.0

    drive = _drive_map(bones)
    bone_map = {b["bone_name"]: b for b in bones}
    rest_dir: dict[str, tuple[float, float]] = {}
    seg_len: dict[str, float] = {}
    for b in bones:
        name = b["bone_name"]
        parent = b["parent_name"]
        if parent:
            ang = math.radians(float(b["angle"]) or 0.0)
            length = float(b["length"] or 0.0)
            d = (
                float(b["x_offset"]) + math.sin(ang) * length,
                float(b["y_offset"]) + math.cos(ang) * length,
            )
        else:
            d = (float(b["x_offset"]), float(b["y_offset"]))
        rest_dir[name] = d
        seg_len[name] = math.hypot(d[0], d[1])
    if ik_pose is not None:
        # IK keyframe pose (Character Details Animation tab): bake the sampled
        # pose straight into bone deltas + root offset, exactly like the
        # Animation tab's canvas does, so the frame is the posed character.
        # Chains re-solved from the sampled effector targets (generated
        # animations author targets, not raw bone deltas).
        deltas = {
            str(name): math.radians(float(deg))
            for name, deg in (ik_pose.get("bones") or {}).items()
        }
        root_val = ik_pose.get("root") or (0.0, 0.0)
        root_off = (float(root_val[0]), float(root_val[1]))
        positions, rots = _bone_frames(bones, deltas, root_offset=root_off)
        solved = _pose_ik_deltas(bones, bone_map, rest_dir, seg_len, positions, rots, ik_pose, rest_pos)
        if solved:
            deltas.update(solved)
        positions, rots = _bone_frames(bones, deltas, root_offset=root_off)
    else:
        deltas = _walk_deltas(bone_images, t, leg_amplitude, arm_amplitude)
        positions, rots = _bone_frames(bones, deltas, root_offset=(0.0, bob))

    # Mouth / eye swap rules: IK poses carry their own animation type / name.
    part_mouth = str(mouth_type or "normal")
    part_anim_name = str(anim_name or "")
    if ik_meta is not None:
        part_mouth = str(ik_meta.get("mouth_type") or part_mouth)
        part_anim_name = str(ik_meta.get("name") or part_anim_name)

    painter.save()
    painter.translate(off_x, off_y)
    painter.scale(model_scale, model_scale)
    for bone_name, record in entries:
        part = record.get("part")
        if not part:
            continue
        # Hide/show flag shared with the Mark/Skeleton tabs...
        if not part_visible.get(part, True):
            continue
        # ...plus the animation's mouth/eye swap rules.
        if not part_visible_for_anim(part, part_mouth, part_anim_name):
            continue
        crop = part_crops.get(part)
        if crop is None or crop.isNull():
            continue
        pos = positions.get(bone_name)
        if pos is None:
            continue

        # The image is anchored to its bone's joint (with the Skeleton
        # tab's offset) and rotated with the bone segment it belongs to -
        # same math as the Animation tab's _draw_body_parts.
        rotation = rots.get(drive.get(bone_name, bone_name), 0.0)
        dx, dy = float(record.get("dx", 0.0)), float(record.get("dy", 0.0))
        c, s = math.cos(rotation), math.sin(rotation)
        anchor_x = pos[0] + c * dx - s * dy
        anchor_y = pos[1] + s * dx + c * dy

        painter.save()
        painter.translate(anchor_x, anchor_y)
        painter.rotate(math.degrees(rotation))
        painter.drawImage(
            int(-crop.width() / 2), int(-crop.height() / 2), crop
        )
        painter.restore()
    painter.restore()
    return True


def _paint_legacy_parts(
    painter: QPainter,
    parts: dict,
    t: float,
    leg_amplitude: float,
    arm_amplitude: float,
    bob: float,
    mouth_type: str,
    anim_name: str,
) -> bool:
    """Legacy assembled-body-part rendering (characters without skeleton
    attachments). Returns True when at least one part was drawn."""
    if not parts:
        return False
    transforms = _compute_transforms(parts, t, leg_amplitude, arm_amplitude, bob)
    draw_names = sorted(
        [n for n in parts if n in transforms and part_visible_for_anim(n, mouth_type, anim_name)],
        key=lambda n: (
            parts[n]["z"],
            DRAW_ORDER.index(n) if n in DRAW_ORDER else 99,
        ),
    )
    painted = False
    for name in draw_names:
        part = parts[name]
        px = int(round(transforms[name][0]))
        py = int(round(transforms[name][1]))
        angle = transforms[name][2]
        crop = part["crop"]

        fx, fy = PIVOT.get(name, (0.5, 0.5))
        piv_x = px + crop.width() * fx
        piv_y = py + crop.height() * fy

        if angle == 0.0:
            painter.drawImage(px, py, crop)
        else:
            painter.save()
            painter.translate(piv_x, piv_y)
            painter.rotate(angle)
            painter.translate(-piv_x, -piv_y)
            painter.drawImage(px, py, crop)
            painter.restore()
        painted = True
    return painted


def _paint_skeleton(
    character_id: int,
    anim,
    t_seconds: float,
    speed_mul: float,
    render_scale: float,
) -> QImage:
    """Paint the animated character onto a transparent QImage canvas."""
    character = _row_cache.db(("character", character_id), lambda: database.get_character(character_id))
    if character is None:
        return QImage()
    stage = _stage_image(character_id, character["image_path"])
    if stage.isNull():
        return QImage()

    # Animation parameters (same phase mapping as the animation tab:
    # speed units per 33 ms tick -> speed * 30 per second). The clip's
    # speed_mul multiplies the whole walk-cycle frequency.
    speed = float(_ik_anim_field(anim, "speed", 0.03)) if anim is not None else 0.03
    leg_amp = float(_ik_anim_field(anim, "leg_amplitude", 0.0))
    arm_amp = float(_ik_anim_field(anim, "arm_amplitude", 0.0))
    bob_amt = float(_ik_anim_field(anim, "bob_amount", 0.0))
    bob_freq = float(_ik_anim_field(anim, "bob_frequency", 1.0))
    mouth_type = str(_ik_anim_field(anim, "mouth_type", "normal") or "normal")
    anim_name = str(_ik_anim_field(anim, "name", "") or "")

    t = t_seconds * (speed * 30.0 * max(0.05, speed_mul))
    bob = bob_amt * abs(math.sin(t * bob_freq))

    scale = min(1.0, max(0.05, float(render_scale)))
    canvas = QImage(
        max(64, int(CANVAS_SIZE * scale)), max(64, int(CANVAS_SIZE * scale)),
        QImage.Format_ARGB32_Premultiplied,
    )
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    if scale < 1.0:
        # All skeleton coordinates/pivots stay in 2048-space; the scaled
        # painter maps them onto the smaller canvas in one pass.
        painter.scale(scale, scale)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)

    # 1) Shared skeleton model - the same bones/bone positions/attached
    #    images/draw order the Skeleton and Animation tabs render. Saved IK
    #    keyframe animations (the Character Details Animation tab) are sampled
    #    to a pose at the current time and painted through the same model, so
    #    timeline/export frames show the character's own animation.
    skeleton_handled = False
    ik_pose, ik_meta = _ik_frame_pose(anim, t_seconds, speed_mul)
    if ik_pose is not None:
        skeleton_handled = _paint_skeleton_model(
            painter, character_id, character,
            t, 0.0, 0.0, 0.0,
            str((ik_meta or {}).get("mouth_type") or mouth_type),
            str((ik_meta or {}).get("name") or anim_name),
            ik_pose=ik_pose,
            ik_meta=ik_meta,
        )
    if not skeleton_handled:
        skeleton_handled = _paint_skeleton_model(
            painter, character_id, character,
            t, leg_amp, arm_amp, bob, mouth_type, anim_name,
        )
    # 2) Fallback: legacy assembled body parts (no skeleton attachments).
    if not skeleton_handled:
        parts = _load_parts_parts(character_id, stage)
        painted = _paint_legacy_parts(
            painter, parts, t, leg_amp, arm_amp, bob, mouth_type, anim_name
        )
        if not painted:
            painter.end()
            return QImage()  # null -> caller falls back to the whole image

    painter.end()
    return canvas


def render_character_anim_image(
    character_id: int,
    anim,
    t_seconds: float,
    speed_mul: float = 1.0,
    render_scale: float = 1.0,
) -> QImage:
    """Skeleton-rendered frame as a QImage — thread-safe (QImage only), so
    the video export worker can call this off the GUI thread.

    ``anim`` may be a procedural walk-cycle preset
    (character_animations) or a saved IK keyframe animation
    (character_ik_animations, the Character Details Animation tab) - the
    latter is sampled to a pose and painted through the shared skeleton
    model, exactly like the character's own animation canvas.
    """
    return _paint_skeleton(character_id, anim, t_seconds, speed_mul, render_scale)


def render_character_ik_image(
    character_id: int,
    anim,
    t_seconds: float,
    speed_mul: float = 1.0,
    render_scale: float = 1.0,
) -> QImage:
    """One frame of a saved IK keyframe animation as a QImage.

    Same pipeline as ``render_character_anim_image`` but always resolves the
    IK keyframe pose (walk-cycle presets have no "payload" and never reach
    this path - they use the procedural renderer).
    """
    return _paint_skeleton(character_id, anim, t_seconds, speed_mul, render_scale)


def render_character_anim(
    character_id: int,
    anim,
    t_seconds: float,
    speed_mul: float = 1.0,
    render_scale: float = 1.0,
) -> QPixmap:
    """Render the character animated at ``t_seconds`` on a transparent canvas.

    ``anim`` is a character_animations DB row (or None -> gentle idle).
    ``render_scale`` < 1 renders the whole skeleton pipeline at a smaller
    resolution (the preview only ever displays it a fraction of that
    size, so this cuts the per-frame cost by ``1/scale^2`` with no visible
    quality loss); the default 1.0 keeps the animation-tab behavior.
    Returns a null pixmap when the character has no usable body parts;
    callers should then fall back to the static image + idle bob.
    NOTE: GUI-thread only (QPixmap), use render_character_anim_image
    from background threads.
    """
    image = _paint_skeleton(character_id, anim, t_seconds, speed_mul, render_scale)
    if image.isNull():
        return QPixmap()
    return QPixmap.fromImage(image)
