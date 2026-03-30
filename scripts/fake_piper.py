from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path


def _write_wav(output_path: Path) -> None:
    sample_rate = 22050
    duration_seconds = 1
    frame_count = sample_rate * duration_seconds
    silence = b"\x00\x00" * frame_count

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(silence)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validation-only Piper stub for smoke tests.")
    parser.add_argument("-m", "--model", dest="model_path", required=False)
    parser.add_argument("-f", "--output-file", dest="output_file", required=True)
    args = parser.parse_args()

    _ = sys.stdin.read()
    _write_wav(Path(args.output_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
