"""Measure data model."""
from dataclasses import dataclass, field
from typing import Optional
from .note import Note, ClefType


@dataclass
class TimeSignature:
    beats: int  # numerator (e.g., 4)
    beat_type: int  # denominator (e.g., 4)

    def __str__(self):
        return f"{self.beats}/{self.beat_type}"


@dataclass
class KeySignature:
    fifths: int  # -7 to 7 (negative=flats, positive=sharps)
    mode: str = "major"  # major or minor

    @property
    def name(self) -> str:
        major_keys = {
            -7: "Cb", -6: "Gb", -5: "Db", -4: "Ab", -3: "Eb",
            -2: "Bb", -1: "F", 0: "C", 1: "G", 2: "D",
            3: "A", 4: "E", 5: "B", 6: "F#", 7: "C#"
        }
        minor_keys = {
            -7: "Ab", -6: "Eb", -5: "Bb", -4: "F", -3: "C",
            -2: "G", -1: "D", 0: "A", 1: "E", 2: "B",
            3: "F#", 4: "C#", 5: "G#", 6: "D#", 7: "A#"
        }
        if self.mode == "minor":
            return minor_keys.get(self.fifths, "?")
        return major_keys.get(self.fifths, "?")


@dataclass
class Clef:
    sign: str  # G, F, C
    line: int  # staff line number
    clef_type: ClefType = ClefType.TREBLE


@dataclass
class Barline:
    style: str = "regular"  # regular, light-light, light-heavy, heavy-light, etc.
    repeat_direction: Optional[str] = None  # forward, backward


@dataclass
class Measure:
    """Represents a single measure of music."""
    number: int
    notes: list[Note] = field(default_factory=list)
    time_signature: Optional[TimeSignature] = None  # only if changed
    key_signature: Optional[KeySignature] = None  # only if changed
    clef: Optional[Clef] = None  # only if changed
    divisions: int = 1  # divisions per quarter note
    barline_left: Optional[Barline] = None
    barline_right: Optional[Barline] = None
    tempo: Optional[int] = None  # BPM if marked
    rehearsal_mark: Optional[str] = None
    is_pickup: bool = False  # anacrusis

    @property
    def note_count(self) -> int:
        return len([n for n in self.notes if not n.is_rest])

    @property
    def rest_count(self) -> int:
        return len([n for n in self.notes if n.is_rest])
