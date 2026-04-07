"""Instrument range validation for extracted MusicXML scores.

Checks notes in each part against standard playable ranges for common
instruments. Returns violations that the fixer can use as targeted hints.
"""
from __future__ import annotations
from typing import Optional

from models.score import Score, Part
from models.note import Pitch


# ---------------------------------------------------------------------------
# MIDI pitch helpers
# ---------------------------------------------------------------------------

_STEP_TO_SEMITONE = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}


def _pitch_to_midi(pitch: Pitch) -> int:
    """Convert a Pitch object to a MIDI note number (middle C = 60)."""
    semitone = _STEP_TO_SEMITONE.get(pitch.step.upper(), 0)
    alter = int(pitch.alter or 0)
    return (pitch.octave + 1) * 12 + semitone + alter


def _midi_to_str(midi: int) -> str:
    """Format a MIDI number as a human-readable pitch string."""
    steps = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
    octave = (midi // 12) - 1
    step = steps[midi % 12]
    return f"{step}{octave}"


def _pitch_str(pitch: Pitch) -> str:
    accidental_map = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
    alter = int(pitch.alter or 0)
    acc = accidental_map.get(alter, "")
    return f"{pitch.step}{acc}{pitch.octave}"


# ---------------------------------------------------------------------------
# Instrument ranges (MIDI note numbers, inclusive)
# Keys are lowercase keywords that appear in part names.
# ---------------------------------------------------------------------------

# (low, high) in MIDI
_INSTRUMENT_RANGES: list[tuple[list[str], int, int]] = [
    # Piano / keyboard
    (["piano", "keyboard", "harpsichord", "organ", "celesta"], 21, 108),
    # Strings
    (["violin", "fiddle"], 55, 103),
    (["viola"], 48, 93),
    (["cello", "violoncello"], 36, 84),
    (["bass", "contrabass", "double bass"], 28, 67),
    # Woodwinds
    (["flute", "piccolo"], 60, 108),
    (["oboe"], 58, 91),
    (["clarinet"], 50, 94),
    (["bassoon"], 34, 75),
    (["saxophone", "alto sax", "tenor sax", "soprano sax"], 44, 93),
    # Brass
    (["trumpet", "cornet"], 55, 82),
    (["horn", "french horn"], 34, 77),
    (["trombone"], 34, 72),
    (["tuba"], 22, 58),
    # Voice
    (["soprano", "sop."], 60, 81),
    (["mezzo", "ms."], 55, 79),
    (["alto", "contralto"], 53, 77),
    (["tenor", "ten."], 48, 72),
    (["baritone", "bar."], 43, 67),
    (["bass voice", "bass voc"], 40, 64),
    # Generic fallback — very wide range
    (["voice", "vocal"], 40, 84),
]

# Absolute safe bounds: anything outside C0–C9 is definitely wrong
_ABSOLUTE_LOW = 12   # C0
_ABSOLUTE_HIGH = 120  # C9


def _get_range(part_name: str) -> tuple[int, int]:
    """Return (low_midi, high_midi) for the given part name string."""
    name_lower = part_name.lower()
    for keywords, low, high in _INSTRUMENT_RANGES:
        if any(kw in name_lower for kw in keywords):
            return low, high
    # Default: generous range covering most pitched instruments
    return _ABSOLUTE_LOW, _ABSOLUTE_HIGH


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_out_of_range_notes(score: Score) -> list[dict]:
    """Find notes in *score* that fall outside standard instrument ranges.

    Args:
        score: Parsed Score object (from extractor or proxy).

    Returns:
        List of violation dicts, each with keys:
            part_name  – name of the part
            measure    – measure number (int)
            pitch_str  – human-readable pitch string
            midi       – MIDI note number
            low        – expected low bound (MIDI)
            high       – expected high bound (MIDI)
    """
    violations: list[dict] = []

    if score is None:
        return violations

    for part in (score.parts or []):
        part_name = getattr(part, "name", "") or getattr(part, "id", "Part")
        low, high = _get_range(part_name)

        for measure in (part.measures or []):
            m_num = getattr(measure, "number", 0)
            for note in (measure.notes or []):
                pitch = getattr(note, "pitch", None)
                if pitch is None:
                    continue  # rest or chord continuation
                try:
                    midi = _pitch_to_midi(pitch)
                except Exception:
                    continue

                if midi < low or midi > high:
                    violations.append({
                        "part_name": part_name,
                        "measure": m_num,
                        "pitch_str": _pitch_str(pitch),
                        "midi": midi,
                        "low": low,
                        "high": high,
                    })

    return violations


def format_range_hint(violation: dict) -> str:
    """Format a single range violation as a fixer hint string.

    Args:
        violation: Dict returned by find_out_of_range_notes.

    Returns:
        Human-readable string suitable for inclusion in a fixer prompt.
    """
    part = violation.get("part_name", "Unknown")
    measure = violation.get("measure", "?")
    pitch = violation.get("pitch_str", "?")
    low = violation.get("low", 0)
    high = violation.get("high", 127)
    midi = violation.get("midi", 0)

    low_str = _midi_to_str(low)
    high_str = _midi_to_str(high)

    return (
        f"{part} m.{measure}: {pitch} (MIDI {midi}) is out of range "
        f"[{low_str}–{high_str}]. Check ledger lines / octave transposition."
    )
