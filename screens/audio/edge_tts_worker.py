"""Standalone edge-tts (online neural TTS) worker, process-isolated.

Run as a script:
    python edge_tts_worker.py <text_file> <out_path> [voice_id] [rate] [pitch]

Generates speech via Microsoft's neural TTS web service (needs internet) and
exits 0 on success. Runs in a child process on purpose: any native/COM crash
or network failure is contained and surfaces as a normal exit code/stderr
that the GUI reports, instead of taking the app down.
"""

import asyncio
import sys

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_AUDIO = 2


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "usage: edge_tts_worker.py <text_file> <out_path> "
            "[voice_id] [rate] [pitch]",
            file=sys.stderr,
        )
        return EXIT_ERROR

    text_path, out_path = argv[1], argv[2]
    voice = argv[3] if len(argv) > 3 and argv[3] else None
    rate = argv[4] if len(argv) > 4 and argv[4] else "+0%"
    pitch = argv[5] if len(argv) > 5 and argv[5] else "+0Hz"

    try:
        with open(text_path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        print(f"Cannot read text file: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        import edge_tts

        async def generate() -> None:
            communicate = edge_tts.Communicate(
                text,
                voice or "hi-IN-MadhurNeural",
                rate=rate,
                pitch=pitch,
            )
            await communicate.save(out_path)

        asyncio.run(generate())
    except BaseException:
        import traceback

        traceback.print_exc()
        return EXIT_ERROR

    if not (out_path and __import__("os").path.getsize(out_path) > 0):
        print("Text-to-Speech did not produce an audio file.", file=sys.stderr)
        return EXIT_NO_AUDIO

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
