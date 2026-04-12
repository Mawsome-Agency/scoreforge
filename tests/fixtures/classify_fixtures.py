#!/usr/bin/env python3
"""
ScoreForge Fixture Complexity Classifier

Analyzes all .musicxml fixtures in tests/fixtures/ across 5 dimensions:
  1. Note density     (notes per measure)
  2. Voice count      (max simultaneous voices in a single part)
  3. Rhythm complexity (tuplets, mixed meters, dotted rhythms)
  4. Notation complexity (ornaments, dynamics, lyrics, repeats, grace notes)
  5. Staff count      (single, grand staff, multi-part)

Outputs: tests/fixtures/complexity.json

Usage:
  python classify_fixtures.py               # generate complexity.json
  python classify_fixtures.py --report      # also print rich table
  python classify_fixtures.py --tier simple # filter to a specific tier
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

FIXTURE_DIR = Path(__file__).parent
OUTPUT_PATH = FIXTURE_DIR / "complexity.json"
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# XML namespace stripping helper
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    """Return local name without XML namespace prefix."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _iter_local(elem, local_tag: str):
    """Iterate over direct children with local_tag (ignoring namespace)."""
    for child in elem:
        if _strip_ns(child.tag) == local_tag:
            yield child


def _find_local(elem, local_tag: str):
    """Return first child with local_tag (ignoring namespace), or None."""
    for child in elem:
        if _strip_ns(child.tag) == local_tag:
            return child
    return None


def _find_all_recursive(elem, local_tag: str):
    """Recursively find all elements with local_tag."""
    results = []
    for child in elem.iter():
        if _strip_ns(child.tag) == local_tag:
            results.append(child)
    return results


# ---------------------------------------------------------------------------
# Per-dimension analyzers
# ---------------------------------------------------------------------------

def analyze_note_density(root) -> dict:
    """Compute notes per measure and rating."""
    parts = _find_all_recursive(root, "part")
    total_notes = 0
    total_measures = 0

    for part in parts:
        measures = _find_all_recursive(part, "measure")
        total_measures += len(measures)
        for measure in measures:
            for note in _find_all_recursive(measure, "note"):
                # Count all note elements (including rests and unpitched)
                total_notes += 1
                # Don't count whole-measure rests toward density
                rest_elem = _find_local(note, "rest")
                if rest_elem is not None and rest_elem.get("measure") == "yes":
                    total_notes -= 1

    notes_per_measure = total_notes / total_measures if total_measures > 0 else 0.0

    if notes_per_measure <= 4:
        rating = "low"
    elif notes_per_measure <= 8:
        rating = "medium"
    else:
        rating = "high"

    return {
        "notes_per_measure": round(notes_per_measure, 2),
        "rating": rating,
    }


def analyze_voice_count(root) -> dict:
    """
    Compute max simultaneous voices within a single part and total part count.
    Voice count = max number of distinct <voice> elements found in any single part.
    """
    parts = _find_all_recursive(root, "part")
    part_count = len(parts)
    max_voices_in_part = 0

    for part in parts:
        voices_in_part = set()
        for note in _find_all_recursive(part, "note"):
            voice_elem = _find_local(note, "voice")
            if voice_elem is not None and voice_elem.text:
                voices_in_part.add(voice_elem.text.strip())
        v = len(voices_in_part)
        if v > max_voices_in_part:
            max_voices_in_part = v

    # Default to 1 if no explicit voice elements found
    if max_voices_in_part == 0:
        max_voices_in_part = 1

    if max_voices_in_part <= 1:
        rating = "1"
    elif max_voices_in_part == 2:
        rating = "2"
    elif max_voices_in_part == 3:
        rating = "3"
    else:
        rating = "4+"

    return {
        "max_voices_in_part": max_voices_in_part,
        "part_count": part_count,
        "rating": rating,
    }


def analyze_rhythm_complexity(root) -> dict:
    """Detect tuplets, mixed meters, and dotted rhythms."""
    has_tuplets = False
    has_mixed_meters = False
    has_dotted_rhythms = False

    # Detect tuplets via <time-modification> or <tuplet> notations
    if _find_all_recursive(root, "time-modification"):
        has_tuplets = True
    if _find_all_recursive(root, "tuplet"):
        has_tuplets = True

    # Detect mixed meters: look for multiple distinct time signatures
    time_sigs = set()
    for time_elem in _find_all_recursive(root, "time"):
        beats_elem = _find_local(time_elem, "beats")
        beat_type_elem = _find_local(time_elem, "beat-type")
        if beats_elem is not None and beat_type_elem is not None:
            time_sigs.add((beats_elem.text, beat_type_elem.text))
    if len(time_sigs) > 1:
        has_mixed_meters = True

    # Detect dotted rhythms via <dot> elements
    if _find_all_recursive(root, "dot"):
        has_dotted_rhythms = True

    # Rating
    if has_tuplets:
        rating = "complex"
    elif has_mixed_meters or has_dotted_rhythms:
        rating = "compound"
    else:
        rating = "simple"

    return {
        "has_tuplets": has_tuplets,
        "has_mixed_meters": has_mixed_meters,
        "has_dotted_rhythms": has_dotted_rhythms,
        "rating": rating,
    }


def analyze_notation_complexity(root) -> dict:
    """Detect advanced notation features."""
    has_ornaments = bool(_find_all_recursive(root, "ornaments"))
    has_dynamics = bool(_find_all_recursive(root, "dynamics"))
    has_lyrics = bool(_find_all_recursive(root, "lyric"))
    has_grace_notes = bool(_find_all_recursive(root, "grace"))

    # Repeat barlines or segno/coda signs
    has_repeats = False
    for barline in _find_all_recursive(root, "barline"):
        repeat_elem = _find_local(barline, "repeat")
        if repeat_elem is not None:
            has_repeats = True
            break
    if not has_repeats:
        # Also check direction for segno/coda
        for direction_type in _find_all_recursive(root, "direction-type"):
            for child in direction_type:
                if _strip_ns(child.tag) in ("segno", "coda", "fine", "da-capo"):
                    has_repeats = True
                    break

    feature_count = sum([has_ornaments, has_dynamics, has_lyrics, has_repeats, has_grace_notes])

    if feature_count == 0:
        rating = "low"
    elif feature_count <= 2:
        rating = "medium"
    else:
        rating = "high"

    return {
        "has_ornaments": has_ornaments,
        "has_dynamics": has_dynamics,
        "has_lyrics": has_lyrics,
        "has_repeats": has_repeats,
        "has_grace_notes": has_grace_notes,
        "feature_count": feature_count,
        "rating": rating,
    }


def analyze_staff_count(root) -> dict:
    """Classify staff layout."""
    parts = _find_all_recursive(root, "part")
    part_count = len(parts)

    # Detect grand staff: a part with staves=2 attribute in attributes/staves
    has_grand_staff = False
    for staves_elem in _find_all_recursive(root, "staves"):
        try:
            if int(staves_elem.text or "0") >= 2:
                has_grand_staff = True
                break
        except ValueError:
            pass

    if part_count == 1 and not has_grand_staff:
        rating = "single"
    elif part_count == 1 and has_grand_staff:
        rating = "grand"
    elif part_count == 2 and has_grand_staff:
        rating = "grand"
    else:
        rating = "multi"

    return {
        "part_count": part_count,
        "has_grand_staff": has_grand_staff,
        "rating": rating,
    }


# ---------------------------------------------------------------------------
# Complexity tier computation
# ---------------------------------------------------------------------------

_EXPERT_FIXTURES = {"nested_tuplets", "full_orchestra"}


def compute_complexity_tier(name: str, nd: dict, vc: dict, rc: dict, nc: dict, sc: dict) -> str:
    """Compute overall complexity tier from dimension ratings."""
    # Expert overrides
    if name in _EXPERT_FIXTURES:
        return "expert"

    elevated = 0

    # Note density
    if nd["rating"] == "high":
        return "complex"  # any single high immediately complex
    if nd["rating"] == "medium":
        elevated += 1

    # Voice count
    voice_rating = vc["rating"]
    if voice_rating == "4+":
        return "complex"
    if voice_rating in ("2", "3"):
        elevated += 1

    # Rhythm
    if rc["rating"] == "complex":
        return "complex"
    if rc["rating"] == "compound":
        elevated += 1

    # Notation
    if nc["rating"] == "high":
        return "complex"
    if nc["rating"] == "medium":
        elevated += 1

    # Staff
    if sc["rating"] == "multi":
        elevated += 1
    elif sc["rating"] == "grand":
        elevated += 1

    if elevated == 0:
        return "simple"
    elif elevated <= 2:
        return "moderate"
    else:
        return "complex"


# ---------------------------------------------------------------------------
# Main classifier
# ---------------------------------------------------------------------------

def classify_fixture(path: Path) -> dict:
    """Classify a single .musicxml file."""
    name = path.stem

    # Handle empty_score edge case
    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except ET.ParseError as e:
        return {
            "note_density": {"notes_per_measure": 0.0, "rating": "low"},
            "voice_count": {"max_voices_in_part": 1, "part_count": 1, "rating": "1"},
            "rhythm_complexity": {"has_tuplets": False, "has_mixed_meters": False, "has_dotted_rhythms": False, "rating": "simple"},
            "notation_complexity": {"has_ornaments": False, "has_dynamics": False, "has_lyrics": False, "has_repeats": False, "has_grace_notes": False, "feature_count": 0, "rating": "low"},
            "staff_count": {"part_count": 1, "has_grand_staff": False, "rating": "single"},
            "complexity_tier": "simple",
            "is_edge_case": True,
            "notes": f"Parse error: {e}",
        }

    # Check if this is an empty score (all-rest or no notes)
    all_notes = _find_all_recursive(root, "note")
    real_notes = []
    for note in all_notes:
        rest_elem = _find_local(note, "rest")
        if rest_elem is None:
            real_notes.append(note)

    is_edge_case = name == "empty_score" or len(real_notes) == 0

    if is_edge_case:
        return {
            "note_density": {"notes_per_measure": 0.0, "rating": "low"},
            "voice_count": {"max_voices_in_part": 1, "part_count": 1, "rating": "1"},
            "rhythm_complexity": {"has_tuplets": False, "has_mixed_meters": False, "has_dotted_rhythms": False, "rating": "simple"},
            "notation_complexity": {"has_ornaments": False, "has_dynamics": False, "has_lyrics": False, "has_repeats": False, "has_grace_notes": False, "feature_count": 0, "rating": "low"},
            "staff_count": {"part_count": 1, "has_grand_staff": False, "rating": "single"},
            "complexity_tier": "simple",
            "is_edge_case": True,
            "notes": "Empty score — no pitched notes; classified at minimum complexity.",
        }

    nd = analyze_note_density(root)
    vc = analyze_voice_count(root)
    rc = analyze_rhythm_complexity(root)
    nc = analyze_notation_complexity(root)
    sc = analyze_staff_count(root)

    tier = compute_complexity_tier(name, nd, vc, rc, nc, sc)

    return {
        "note_density": nd,
        "voice_count": vc,
        "rhythm_complexity": rc,
        "notation_complexity": nc,
        "staff_count": sc,
        "complexity_tier": tier,
        "is_edge_case": False,
        "notes": "",
    }


def classify_all(fixture_dir: Path) -> dict:
    """Classify all .musicxml fixtures in the given directory."""
    fixtures = {}
    for path in sorted(fixture_dir.glob("*.musicxml")):
        name = path.stem
        fixtures[name] = classify_fixture(path)
    return fixtures


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def build_output(fixtures: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures": fixtures,
    }


def print_report(data: dict, tier_filter: str | None = None) -> None:
    """Print a rich table to terminal."""
    try:
        from rich.console import Console
        from rich.table import Table
        rich_available = True
    except ImportError:
        rich_available = False

    fixtures = data["fixtures"]
    rows = []
    for name, info in sorted(fixtures.items()):
        if tier_filter and info["complexity_tier"] != tier_filter:
            continue
        rows.append((
            name,
            info["complexity_tier"],
            info["note_density"]["rating"],
            info["voice_count"]["rating"],
            info["rhythm_complexity"]["rating"],
            info["notation_complexity"]["rating"],
            info["staff_count"]["rating"],
            "YES" if info["is_edge_case"] else "",
        ))

    if rich_available:
        console = Console()
        table = Table(title=f"Fixture Complexity Classification (schema v{data['schema_version']})")
        table.add_column("Fixture", style="bold")
        table.add_column("Tier", style="cyan")
        table.add_column("Note Density")
        table.add_column("Voices")
        table.add_column("Rhythm")
        table.add_column("Notation")
        table.add_column("Staff")
        table.add_column("Edge?", style="yellow")

        tier_colors = {
            "simple": "green",
            "moderate": "yellow",
            "complex": "orange1",
            "expert": "red",
        }

        for row in rows:
            name, tier, nd, vc, rc, nc, sc, edge = row
            color = tier_colors.get(tier, "white")
            table.add_row(name, f"[{color}]{tier}[/{color}]", nd, vc, rc, nc, sc, edge)

        console.print(table)
        console.print(f"\nGenerated at: {data['generated_at']}")
        console.print(f"Total fixtures: {len(data['fixtures'])}")
    else:
        # Fallback plain text
        header = f"{'Fixture':<35} {'Tier':<10} {'Density':<10} {'Voices':<8} {'Rhythm':<10} {'Notation':<10} {'Staff':<8} {'Edge'}"
        print(header)
        print("-" * len(header))
        for row in rows:
            name, tier, nd, vc, rc, nc, sc, edge = row
            print(f"{name:<35} {tier:<10} {nd:<10} {vc:<8} {rc:<10} {nc:<10} {sc:<8} {edge}")
        print(f"\nGenerated at: {data['generated_at']}")
        print(f"Total fixtures: {len(data['fixtures'])}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Classify MusicXML fixtures by complexity.")
    parser.add_argument("--report", action="store_true", help="Print rich table to terminal after writing JSON.")
    parser.add_argument("--tier", default=None, choices=["simple", "moderate", "complex", "expert"],
                        help="Filter report output to a specific complexity tier.")
    parser.add_argument("--fixture-dir", default=None,
                        help="Override path to fixtures directory.")
    parser.add_argument("--output", default=None,
                        help="Override output path for complexity.json.")
    args = parser.parse_args()

    fixture_dir = Path(args.fixture_dir) if args.fixture_dir else FIXTURE_DIR
    output_path = Path(args.output) if args.output else OUTPUT_PATH

    print(f"Scanning: {fixture_dir}")
    fixtures = classify_all(fixture_dir)
    data = build_output(fixtures)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Written: {output_path}")
    print(f"Classified {len(fixtures)} fixtures.")

    if args.report:
        print_report(data, tier_filter=args.tier)


if __name__ == "__main__":
    main()
