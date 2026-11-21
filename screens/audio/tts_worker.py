"""Standalone Text-to-Speech worker (process-isolated from the GUI).

Run as a script with two arguments:
    python tts_worker.py <text_file> <wav_out_path>

It reads the text file, generates speech with pyttsx3 (SAPI5 on Windows),
and exits 0 on success.

Why a separate process? pyttsx3/SAPI uses COM, and its engine teardown can
abort natively. Inside the Qt process that means the whole app dies with no
Python traceback. In this child process, such a crash is contained: the GUI
process survives and just reports the failure from the exit status.
"""

import struct
import sys

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_AUDIO = 2


def finalize_wav_header(path: str) -> bool:
    """Repair the WAV RIFF/data chunk sizes, which pyttsx3/SAPI5 can leave
    unfinalized (header sizes stale or zero -> "Duration: N/A" / "file may
    be invalid" in players).

    Idempotent: consistent files are left byte-for-byte unchanged.

    Returns True when the file is a known-consistent WAV afterwards.
    """
    if not path:
        return False
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return False

    if len(raw) < 44 or raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        return False

    def data_offset_and_size(buffer: bytes) -> tuple[int, int] | None:
        # Walk the chunk list; fall back to scanning if the walk breaks.
        pos = 12
        while pos + 8 <= len(buffer):
            chunk_id = buffer[pos:pos + 4]
            chunk_size = struct.unpack("<I", buffer[pos + 4:pos + 8])[0]
            if chunk_id == b"data":
                return pos, chunk_size
            end = pos + 8 + chunk_size + (chunk_size % 2)
            if chunk_size == 0 or end > len(buffer):
                index = buffer.find(b"data", 12)
                if index < 0 or index + 8 > len(buffer):
                    return None
                return index, struct.unpack("<I", buffer[index + 4:index + 8])[0]
            pos = end
        return None

    found = data_offset_and_size(raw)
    if found is None:
        return False
    pos, declared = found
    actual = len(raw) - (pos + 8)

    riff_ok = struct.unpack("<I", raw[4:8])[0] == len(raw) - 8
    if riff_ok and declared == actual:
        return True  # already valid, nothing to write

    with open(path, "r+b") as handle:
        handle.seek(4)
        handle.write(struct.pack("<I", len(raw) - 8))  # RIFF size
        handle.seek(pos + 4)
        handle.write(struct.pack("<I", actual))        # data chunk size
    return True


def list_local_voices() -> list[tuple[str, str]]:
    """Windows SAPI voice tokens straight from the registry.

    Reads HKLM without touching COM, so it is safe to call from the GUI
    process; pyttsx3 voice IDs on Windows are exactly these token names.
    """
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows keeps offline TTS
        return []

    voices: list[tuple[str, str]] = []
    for key_path in (
        r"SOFTWARE\Microsoft\Speech\Voices\Tokens",
        r"SOFTWARE\WOW6432Node\Microsoft\Speech\Voices\Tokens",
    ):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        except OSError:
            continue
        try:
            index = 0
            while True:
                try:
                    token = winreg.EnumKey(key, index)
                except OSError:
                    break
                label = token.replace("_", " ").strip()
                label = " ".join(part for part in label.split(" ") if part)
                voices.append((token, label))
                index += 1
        finally:
            winreg.CloseKey(key)
        if voices:
            break  # first successful hive view wins
    return voices


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: tts_worker.py <text_file> <wav_out_path> [voice_id]", file=sys.stderr)
        return EXIT_ERROR

    text_path, out_path = argv[1], argv[2]
    voice_id = argv[3] if len(argv) > 3 and argv[3] else None
    try:
        with open(text_path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        print(f"Cannot read text file: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        import pyttsx3

        engine = pyttsx3.init()
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.save_to_file(text, out_path)
        engine.runAndWait()
    except SystemExit:
        return EXIT_ERROR
    except BaseException:
        # The full traceback goes to stderr; the parent process logs it.
        import traceback

        traceback.print_exc()
        return EXIT_ERROR

    if not (out_path and __import__("os").path.getsize(out_path) > 0):
        print("Text-to-Speech did not produce an audio file.", file=sys.stderr)
        return EXIT_NO_AUDIO

    # SAPI can leave the RIFF/data sizes unfinalized (players then report
    # "Duration: N/A" / "file may be invalid"). Finalize them before exiting.
    if not finalize_wav_header(out_path):
        print("Generated file is not a readable WAV.", file=sys.stderr)
        return EXIT_NO_AUDIO

    try:
        import wave

        with wave.open(out_path) as wav:
            if wav.getnframes() <= 0 or wav.getnchannels() <= 0:
                print("Generated WAV has no audible frames.", file=sys.stderr)
                return EXIT_NO_AUDIO
    except BaseException:
        import traceback

        traceback.print_exc()
        return EXIT_NO_AUDIO

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
