#!/usr/bin/env python3
"""Generate PNG fixtures for all MusicXML test fixtures.

Iterates over every .musicxml file in tests/fixtures/ and renders a PNG
alongside it using core.renderer.render_musicxml_to_image(). Skips files
that already have a PNG (idempotent). Logs progress and errors clearly.

Usage:
    python tests/generate_fixture_pngs.py
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `core` is importable.
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.renderer import render_musicxml_to_image  # noqa: E402
from PIL import Image  # noqa: E402


FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


def generate_all_pngs() -> tuple[int, int, int]:
    """Generate PNGs for all MusicXML fixtures.

    Returns:
        (generated, skipped, total) counts.
    """
    musicxml_files = sorted(FIXTURES_DIR.glob("*.musicxml"))

    if not musicxml_files:
        print(f"ERROR: No .musicxml files found in {FIXTURES_DIR}", file=sys.stderr)
        return 0, 0, 0

    total = len(musicxml_files)
    generated = 0
    skipped = 0
    errors = []

    print(f"Found {total} MusicXML fixture(s) in {FIXTURES_DIR}")
    print()

    for musicxml_path in musicxml_files:
        png_path = musicxml_path.with_suffix(".png")
        stem = musicxml_path.stem

        if png_path.exists():
            print(f"  [SKIP]   {stem}.png already exists")
            skipped += 1
            continue

        print(f"  [RENDER] {stem}.musicxml → {stem}.png ...", end=" ", flush=True)
        try:
            render_musicxml_to_image(str(musicxml_path), str(png_path))

            # Validate the output is a non-empty, valid image.
            if not png_path.exists() or png_path.stat().st_size == 0:
                raise RuntimeError("Output PNG is missing or empty after render.")

            with Image.open(png_path) as img:
                img.verify()  # raises if the image is corrupt

            generated += 1
            print("OK")
        except Exception as exc:
            print(f"ERROR: {exc}")
            errors.append((stem, exc))
            # Remove partial output so re-runs don't skip a broken file.
            png_path.unlink(missing_ok=True)

    print()
    print(
        f"Generated {generated}/{total} PNG fixtures  "
        f"(skipped {skipped} already present, {len(errors)} error(s))"
    )

    if errors:
        print("\nErrors:")
        for name, exc in errors:
            print(f"  {name}: {exc}")

    return generated, skipped, total


def smoke_test_comparator() -> bool:
    """Self-comparison smoke test: compare simple_melody.musicxml to itself.

    A file compared to itself must return 1.0 on all accuracy metrics.
    This validates the comparator without needing the Claude API.
    """
    from core.comparator import compare_musicxml_semantic

    fixture = FIXTURES_DIR / "simple_melody.musicxml"
    if not fixture.exists():
        print(f"\nSMOKE TEST SKIPPED: {fixture} not found", file=sys.stderr)
        return False

    print("\n--- Smoke test: self-comparison of simple_melody.musicxml ---")
    result = compare_musicxml_semantic(str(fixture), str(fixture))
    scores = result.get("scores", {})

    note_acc = scores.get("note_accuracy", None)
    pitch_acc = scores.get("pitch_accuracy", None)
    rhythm_acc = scores.get("rhythm_accuracy", None)

    print(f"  note_accuracy   = {note_acc}")
    print(f"  pitch_accuracy  = {pitch_acc}")
    print(f"  rhythm_accuracy = {rhythm_acc}")

    # comparator._pct() returns values in [0, 100], so perfect = 100.0
    passed = note_acc == 100.0 and pitch_acc == 100.0 and rhythm_acc == 100.0

    if passed:
        print("  SMOKE TEST PASSED")
    else:
        print("  SMOKE TEST FAILED — expected all metrics = 100.0")

    return passed


if __name__ == "__main__":
    generated, skipped, total = generate_all_pngs()
    smoke_ok = smoke_test_comparator()

    all_present = (generated + skipped) == total
    exit_code = 0 if (all_present and smoke_ok) else 1
    sys.exit(exit_code)
