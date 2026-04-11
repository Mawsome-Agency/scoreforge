"""Generate PNG fixtures for all 18 MusicXML test fixtures.

Iterates over all .musicxml files in tests/fixtures/, renders each to PNG
using the verovio-python renderer, and validates the output with PIL.

Usage:
    python tests/generate_fixture_pngs.py

Idempotent: skips fixtures that already have a corresponding PNG.
"""
import sys
from pathlib import Path

# Add project root to path so we can import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image

from core.comparator import compare_musicxml_semantic
from core.renderer import render_musicxml_to_image

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TOTAL_FIXTURES = 18


def main() -> None:
    fixtures = sorted(FIXTURE_DIR.glob("*.musicxml"))

    if not fixtures:
        print("ERROR: No .musicxml files found in tests/fixtures/")
        sys.exit(1)

    generated = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    print(f"Found {len(fixtures)} .musicxml fixtures. Generating PNGs...\n")

    for i, musicxml_path in enumerate(fixtures, start=1):
        png_path = musicxml_path.with_suffix(".png")
        name = musicxml_path.stem

        if png_path.exists():
            print(f"[{i:2}/{len(fixtures)}] SKIP  {name} (PNG already exists)")
            skipped += 1
            continue

        print(f"[{i:2}/{len(fixtures)}] RENDER {name} ...", end=" ", flush=True)

        try:
            out_path = render_musicxml_to_image(str(musicxml_path))

            # Validate: non-zero size and PIL can open it
            out = Path(out_path)
            if not out.exists() or out.stat().st_size == 0:
                raise ValueError(f"Output file missing or empty: {out_path}")

            with Image.open(out_path) as img:
                w, h = img.size

            print(f"OK ({w}x{h}px)")
            generated += 1

        except Exception as exc:
            print(f"FAILED")
            msg = f"{name}: {exc}"
            errors.append(msg)
            print(f"         ERROR: {msg}")
            failed += 1

    # Summary line
    print(f"\nGenerated {generated}/{TOTAL_FIXTURES} PNG fixtures", end="")
    if skipped:
        print(f" ({skipped} skipped, already existed)", end="")
    if failed:
        print(f" ({failed} FAILED)", end="")
    print()

    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  - {e}")

    # --- Smoke test ---
    print("\n--- Smoke test: self-comparison of simple_melody ---")
    simple_melody = FIXTURE_DIR / "simple_melody.musicxml"
    if not simple_melody.exists():
        print("SKIP: simple_melody.musicxml not found")
    else:
        result = compare_musicxml_semantic(str(simple_melody), str(simple_melody))
        scores = result["scores"]
        note_acc = scores["note_accuracy"]
        pitch_acc = scores["pitch_accuracy"]
        rhythm_acc = scores["rhythm_accuracy"]

        print(f"  note_accuracy:   {note_acc}")
        print(f"  pitch_accuracy:  {pitch_acc}")
        print(f"  rhythm_accuracy: {rhythm_acc}")

        assert note_acc == 100.0, f"Expected note_accuracy=100.0, got {note_acc}"
        assert pitch_acc == 100.0, f"Expected pitch_accuracy=100.0, got {pitch_acc}"
        assert rhythm_acc == 100.0, f"Expected rhythm_accuracy=100.0, got {rhythm_acc}"

        print("  PASS: all metrics == 100.0")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
