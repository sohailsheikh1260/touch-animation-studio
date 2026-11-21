"""Video export for the project editor timeline.

Renders the timeline frame-by-frame with the SAME compositor semantics as
the live preview (`ProjectEditorPage._render_preview`):

- whole-frame camera zoom (zoom_start -> zoom_end interpolation)
- background drawn aspect-fill with per-clip size/offset
- one render item per covering character CLIP (duplicates move independently)
- skeleton animation via character_animator (walk cycles etc.)
- per-clip size_scale, anim_speed and start->end position motion
- idle bob for the static fallback
- stage-relative text overlays

Frames are painted into PNGs, then encoded with ffmpeg (from
imageio-ffmpeg) into an MP4 including the audio clips at their timeline
offsets. Runs in a QThread so the UI stays responsive.
"""

import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from screens.project_details import character_animator
from screens.project_details.clip import MAX_CHARACTER_SIZE_PCT, MIN_CHARACTER_SIZE_PCT

MUTED = "#94a3b8"

# Benign ffmpeg chatter on Windows: Media Foundation encoder-probe lines
# (av1_mf / h264_mf / hevc_mf ...) that appear while ffmpeg probes available
# encoders. They are NOT errors and must not surface to the user.
_FFMPEG_BENIGN_RE = re.compile(
    r"\[[^\]]*_mf @|could not find any MFT|could not create MFT|MFT name:"
)


def _clean_ffmpeg_err(err: str | None) -> str:
    """Drop harmless MFT probe lines from ffmpeg stderr before use."""
    lines = [
        ln
        for ln in (err or "").splitlines()
        if ln.strip() and not _FFMPEG_BENIGN_RE.search(ln)
    ]
    return "\n".join(lines)


class ExportWorker(QThread):
    progress = Signal(int)      # 0..100
    finished_ok = Signal(str)   # output path
    failed = Signal(str)        # error message

    FPS = 30
    RENDER_REPORTING_STEP = 5

    def __init__(
        self,
        out_path: str,
        width: int,
        height: int,
        scene_clips: list[dict],
        audio_clips: list[dict],
        stage_width: int | None = None,
        stage_height: int | None = None,
        parent=None,
    ) -> None:
        """Scene clip dicts carry everything the preview compositor needs:
        start, duration, kind, path, name, text, x_offset/y_offset (plus
        x_end/y_end), size_scale, anim_speed, zoom_start/zoom_end, plus for
        character clips: cid, animation, anims (rows), stage_path and parts
        (parsed payload rects)."""
        super().__init__(parent)
        self.setObjectName("export-worker")
        self.out_path = out_path
        self.width = width
        self.height = height
        self.stage_width = stage_width if stage_width else width
        self.stage_height = stage_height if stage_height else height
        self.scene_clips = scene_clips
        self.audio_clips = audio_clips
        self._cancel = False
        self._process: subprocess.Popen | None = None
        # Per-character stage image paths (crops of parts come from them).
        # Built in __init__ so headless _render_frame calls work too.
        self._stage_paths: dict[int, str] = {}
        for clip in scene_clips:
            cid = clip.get("cid")
            stage_path = clip.get("stage_path") or ""
            if cid is not None and stage_path:
                self._stage_paths[int(cid)] = stage_path
        # Worker-side asset caches (built once per export). QImage instead
        # of QPixmap: painting images off the GUI thread is safe, QPixmap
        # is not (native fail-fast abort otherwise).
        self._image_cache: dict[str, QImage | None] = {}
        self._assembly_cache: dict[tuple, QImage | None] = {}

    def cancel(self) -> None:
        """Stop the export: both the render loop and any running ffmpeg."""
        self._cancel = True
        process = self._process
        if process is not None and process.poll() is None:
            # Encode phase: the cancel flag can't interrupt subprocess.run,
            # so kill ffmpeg directly - communicate() then returns quickly.
            process.kill()

    def kill_process(self) -> None:
        """Last-resort: force-kill the ffmpeg subprocess if still running."""
        process = self._process
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
            self._process = None

    # ------------------------------------------------------- clip helpers
    def _covering(self, t: float, kind: str):
        """Scene clips of ``kind`` covering time ``t``, timeline order."""
        for clip in self.scene_clips:
            if clip.get("kind") != kind or not clip.get("path"):
                continue
            if clip["start"] <= t < clip["start"] + clip["duration"]:
                yield clip

    @staticmethod
    def _progress_at(clip: dict, t: float) -> float:
        """0..1 progress of a clip at time t (same as preview)."""
        duration = clip.get("duration", 0.0) or 0.0
        if duration <= 0:
            return 0.0
        p = (t - clip["start"]) / duration
        return max(0.0, min(1.0, p))

    @staticmethod
    def _position_at(clip: dict, t: float) -> tuple[float, float]:
        """Stage-space position of a character clip at time t (start->end)."""
        sx = float(clip.get("x_offset", 0.0) or 0.0)
        sy = float(clip.get("y_offset", 0.0) or 0.0)
        x_end = clip.get("x_end")
        y_end = clip.get("y_end")
        ex = sx if x_end is None else x_end
        ey = sy if y_end is None else y_end
        p = ExportWorker._progress_at(clip, t)
        return (sx + (ex - sx) * p, sy + (ey - sy) * p)

    def _scene_zoom_at(self, t: float) -> float:
        """Whole-frame camera zoom at time t (identical math to preview)."""
        values = []
        for clip in self.scene_clips:
            if not (clip["start"] <= t < clip["start"] + clip["duration"]):
                continue
            zs = float(clip.get("zoom_start", 1.0) or 1.0)
            ze = clip.get("zoom_end")
            if ze is None:
                if abs(zs - 1.0) > 0.005:
                    values.append(zs)
            else:
                z = zs + (ze - zs) * self._progress_at(clip, t)
                values.append(z)
        if not values:
            return 1.0
        ups = [v for v in values if v > 1.0]
        downs = [v for v in values if v < 1.0]
        if ups:
            return max(ups)
        if downs:
            return min(downs)
        return 1.0

    # --------------------------------------------------- asset resolution
    def _cached_image(self, path: str) -> QImage | None:
        """Decode once; the export re-uses the same decoded images."""
        if not path:
            return None
        if path not in self._image_cache:
            img = QImage(path)
            self._image_cache[path] = None if img.isNull() else img
        return self._image_cache[path]

    def _character_anim_for(self, clip: dict):
        """The animation row assigned to this character's clip (dict)."""
        anims = clip.get("anims") or []
        anim_name = clip.get("animation") or "idle"
        anim = None
        for candidate in anims:
            if candidate.get("name") == anim_name:
                anim = candidate
                break
        if anim is None and anims:
            anim = anims[0]
        return anim

    def _assembled_image(self, cid: int, asm_scale: float, parsed: list[dict]):
        """Compose the visible body parts once per (character, layout,
        scale) — same 1.4x display-height approach as the preview."""
        if not parsed:
            return None
        sig = tuple(
            (p["left"], p["top"], p["w"], p["h"], p["x"], p["y"]) for p in parsed
        )
        key = (cid, round(asm_scale, 3), sig)
        if key in self._assembly_cache:
            return self._assembly_cache[key]

        stage_path = self._stage_paths.get(cid)
        stage = self._cached_image(stage_path) if stage_path else None
        result: QImage | None = None
        if stage is not None and not stage.isNull():
            canvas_size = max(64, int(2048 * asm_scale))
            asm = QImage(
                canvas_size, canvas_size, QImage.Format_ARGB32_Premultiplied
            )
            asm.fill(Qt.transparent)
            painter = QPainter(asm)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.scale(asm_scale, asm_scale)
            for p in parsed:
                crop = stage.copy(p["left"], p["top"], p["w"], p["h"])
                if crop.isNull():
                    continue
                painter.drawImage(p["x"], p["y"], crop)
            painter.end()
            if not asm.isNull():
                result = asm
        self._assembly_cache[key] = result
        return result

    # --------------------------------------------------- per-character
    def _render_character(
        self, clip: dict, t: float, char_h: int
    ) -> tuple[QImage, int] | None:
        """Skeleton-animated frame if possible, then the static parts
        assembly, then the whole image. Returns (scaled_image, bob)."""
        cid = int(clip.get("cid") or 0)
        anim = self._character_anim_for(clip)

        image: QImage | None = None
        is_animated = False
        if anim is not None:
            speed_mul = clip.get("anim_speed", 1.0) or 1.0
            render_scale = min(1.0, max(0.3, (char_h * 1.5) / 2048.0))
            try:
                image = character_animator.render_character_anim_image(
                    cid, anim, t,
                    speed_mul=speed_mul,
                    render_scale=render_scale,
                )
            except Exception:
                image = None
            if image is not None and image.isNull():
                image = None
            is_animated = image is not None

        if image is None:
            parsed = clip.get("parts") or []
            asm_scale = min(1.0, max(0.3, (char_h * 1.4) / 2048.0))
            image = self._assembled_image(cid, asm_scale, parsed)
        if image is None or image.isNull():
            image = self._cached_image(clip.get("path") or "")
        if image is None or image.isNull():
            return None

        scaled = image.scaled(
            max(8, int(char_h * 0.8)), char_h,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        if scaled.isNull():
            return None
        flip_h = bool(clip.get("flip_h"))
        flip_v = bool(clip.get("flip_v"))
        if flip_h or flip_v:
            scaled = scaled.mirrored(flip_h, flip_v)

        # Idle bob for the static fallback (animated frames already carry
        # the full bob), identical math to the preview.
        bob_offset = 0
        if not is_animated and anim is not None:
            try:
                speed = float(anim["speed"])
                bob_amount = float(anim["bob_amount"])
                bob_freq = float(anim["bob_frequency"])
                phase = t * (speed * 30.0)
                bob = bob_amount * abs(math.sin(phase * bob_freq))
                bob_offset = int(bob * (char_h / 2048.0))
            except (KeyError, TypeError, ValueError):
                bob_offset = 0
        return scaled, bob_offset

    # -------------------------------------------------------- compositor
    def _render_frame(self, t: float) -> QImage:
        image = QImage(self.width, self.height, QImage.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        W, H = self.width, self.height
        zoom = self._scene_zoom_at(t)
        if abs(zoom - 1.0) > 0.005:
            # Bake the camera zoom into the painter (same as the preview).
            painter.translate(W / 2.0, H / 2.0)
            painter.scale(zoom, zoom)
            painter.translate(-W / 2.0, -H / 2.0)

        scale_x = W / max(1, self.stage_width)
        scale_y = H / max(1, self.stage_height)

        drawn = False

        # Background: LAST covering clip wins (same semantics as preview).
        background: dict | None = None
        for clip in self._covering(t, "background"):
            background = clip
        if background is not None:
            bg_source = self._cached_image(background["path"])
            if bg_source is not None:
                bg_pct = max(
                    MIN_CHARACTER_SIZE_PCT,
                    min(
                        MAX_CHARACTER_SIZE_PCT,
                        int(round(float(background.get("size_scale", 1.0) or 1.0) * 100)),
                    ),
                )
                bg_scale = bg_pct / 100.0
                scaled = bg_source.scaled(
                    max(1, int(W * bg_scale)), max(1, int(H * bg_scale)),
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                )
                pos_x, pos_y = self._position_at(background, t)
                off_x = int(pos_x * scale_x)
                off_y = int(pos_y * scale_y)
                painter.drawImage(
                    (W - scaled.width()) // 2 + off_x,
                    (H - scaled.height()) // 2 + off_y,
                    scaled,
                )
                drawn = True

        # Characters: ONE render item per covering character clip, so
        # duplicate characters (with their own positions) render separately.
        items = list(self._covering(t, "character"))
        n = len(items)
        for i, clip in enumerate(items):
            size_scale = float(clip.get("size_scale", 1.0) or 1.0)
            char_h = max(32, int(H * 0.6 * size_scale))

            try:
                result = self._render_character(clip, t, char_h)
            except Exception:
                result = None
            if result is None:
                continue
            scaled, bob_offset = result

            offset = (i - (n - 1) / 2.0) * (scaled.width() + 10)
            pos_x, pos_y = self._position_at(clip, t)
            off_x = int(pos_x * scale_x)
            off_y = int(pos_y * scale_y)
            target_x = int((W - scaled.width()) // 2 + offset) + off_x
            target_y = (
                H - scaled.height() - int(H * 0.04) - bob_offset + off_y
            )
            painter.drawImage(target_x, target_y, scaled)
            drawn = True

        # Text overlays covering this frame (drawn above characters).
        for clip in self.scene_clips:
            if clip.get("kind") != "text":
                continue
            if not (clip["start"] <= t < clip["start"] + clip["duration"]):
                continue
            content = clip.get("text") or ""
            if not content:
                continue
            font_px = max(8, int(H * 0.09 * float(clip.get("size_scale", 1.0) or 1.0)))
            font = QFont("Segoe UI", font_px)
            font.setBold(True)
            painter.setFont(font)
            fm = QFontMetrics(font)
            off_x = float(clip.get("x_offset", 0.0) or 0.0) * scale_x
            off_y = float(clip.get("y_offset", 0.0) or 0.0) * scale_y
            tx = int(W / 2 + off_x - fm.horizontalAdvance(content) / 2)
            ty = int(H / 2 + off_y - fm.height() / 2) + fm.ascent()
            painter.setPen(QColor(0, 0, 0, 180))
            painter.drawText(tx + 2, ty + 2, content)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(tx, ty, content)
            drawn = True

        if not drawn:
            painter.setPen(QColor(MUTED))
            painter.setFont(QFont("Segoe UI", max(12, H // 24)))
            painter.drawText(
                image.rect(), Qt.AlignCenter, "Empty scene placeholder"
            )

        painter.end()
        return image

    # ----------------------------------------------------------- main run
    def run(self) -> None:  # noqa: D102 (QThread override)
        try:
            self._run()
        except Exception as exc:  # surface any failure in the UI
            self.failed.emit(str(exc))

    def _run(self) -> None:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        # Clamp output dims to even numbers (H.264 requirement)
        width = self.width - (self.width % 2)
        height = self.height - (self.height % 2)

        total_sec = max(
            [c["start"] + c["duration"] for c in self.scene_clips + self.audio_clips]
            + [1.0]
        )
        total_frames = int(total_sec * self.FPS)

        frames_dir = tempfile.mkdtemp(prefix="touch_anim_export_")
        try:
            # ---- 1. Render frames (0-80%) ----
            for i in range(total_frames):
                if self._cancel:
                    self.failed.emit("Export cancelled.")
                    return
                t = i / self.FPS
                frame = self._render_frame(t)
                ok = frame.save(
                    str(Path(frames_dir) / f"f{i:06d}.png"), "PNG"
                )
                if not ok:
                    raise RuntimeError(f"Could not save frame {i}.")
                if i % max(1, total_frames // (100 // self.RENDER_REPORTING_STEP)) == 0:
                    self.progress.emit(int(80 * i / total_frames))

            # ---- 2. Encode with ffmpeg (80-100%) ----
            cmd = [ffmpeg, "-y", "-nostdin", "-framerate", str(self.FPS), "-i",
                   str(Path(frames_dir) / "f%06d.png")]

            filter_parts = []
            audio_inputs = []
            for idx, clip in enumerate(sorted(self.audio_clips, key=lambda c: c["start"])):
                if not clip["path"] or not Path(clip["path"]).is_file():
                    continue
                cmd += ["-i", clip["path"]]  # audio input must be registered
                stream_index = 1 + len(audio_inputs)
                audio_inputs.append(clip)
                delay_ms = int(clip["start"] * 1000)
                filter_parts.append(
                    f"[{stream_index}:a]adelay={delay_ms}|{delay_ms}[a{idx}]"
                )

            if audio_inputs:
                # mix all audio clips into one track
                mix_labels = "".join(f"[a{idx}]" for idx in range(len(audio_inputs)))
                filter_parts.append(
                    f"{mix_labels}amix=inputs={len(audio_inputs)}"
                    ":duration=longest:normalize=0[aout]"
                )
                cmd += ["-filter_complex", ";".join(filter_parts)]
                cmd += ["-map", "0:v", "-map", "[aout]"]
            else:
                cmd += ["-an"]

            if audio_inputs:
                # trim to the exported length (audio may be longer than timeline)
                cmd += ["-t", f"{total_sec:.3f}"]

            cmd += [
                "-c:v", "libx264",
                "-preset", "medium",
                "-pix_fmt", "yuv420p",
                "-r", str(self.FPS),
                self.out_path,
            ]

            self.progress.emit(80)
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,  # ffmpeg must never read stdin
                text=True,
            )
            try:
                _out, err = self._process.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.communicate()
                raise RuntimeError("ffmpeg timed out after 10 minutes.")

            self.progress.emit(95)
            if self._process.returncode != 0:
                cleaned = _clean_ffmpeg_err(err)
                tail = cleaned.strip().splitlines()[-1:] or ["unknown ffmpeg error"]
                raise RuntimeError(
                    f"ffmpeg failed: {tail[0][:300]} (code {self._process.returncode})"
                )

            if not os.path.isfile(self.out_path):
                raise RuntimeError("Export finished but the output file is missing.")

            self.progress.emit(100)
            self.finished_ok.emit(self.out_path)
        finally:
            shutil.rmtree(frames_dir, ignore_errors=True)
            self._process = None
