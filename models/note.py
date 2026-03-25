"""Note and rest data models."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NoteType(Enum):
    WHOLE = "whole"
    HALF = "half"
    QUARTER = "quarter"
    EIGHTH = "eighth"
    SIXTEENTH = "16th"
    THIRTY_SECOND = "32nd"
    SIXTY_FOURTH = "64th"


class Accidental(Enum):
    SHARP = "sharp"
    FLAT = "flat"
    NATURAL = "natural"
    DOUBLE_SHARP = "double-sharp"
    DOUBLE_FLAT = "double-flat"


class ClefType(Enum):
    TREBLE = "G"
    BASS = "F"
    ALTO = "C"
    TENOR = "C"  # same sign, different line


@dataclass
class Pitch:
    step: str  # A-G
    octave: int  # 0-9
    alter: Optional[int] = None  # -2 to 2 (flats/sharps)
    accidental: Optional[Accidental] = None

    def __str__(self):
        acc = ""
        if self.accidental:
            acc = self.accidental.value
        return f"{self.step}{acc}{self.octave}"


@dataclass
class Note:
    """Represents a single note or rest."""
    note_type: NoteType
    duration: int  # in divisions
    is_rest: bool = False
    pitch: Optional[Pitch] = None
    dot_count: int = 0
    is_chord: bool = False  # stacked with previous note
    voice: int = 1
    staff: int = 1
    beam: Optional[str] = None  # begin, continue, end
    tie_start: bool = False
    tie_stop: bool = False
    slur_start: bool = False
    slur_stop: bool = False
    dynamic: Optional[str] = None  # pp, p, mp, mf, f, ff, etc.
    articulation: Optional[str] = None  # staccato, accent, tenuto, etc.
    tuplet_actual: Optional[int] = None  # e.g., 3 for triplet
    tuplet_normal: Optional[int] = None  # e.g., 2 for triplet
    lyrics: list[str] = field(default_factory=list)
    fermata: bool = False
    grace: bool = False

    def __str__(self):
        if self.is_rest:
            return f"Rest({self.note_type.value})"
        return f"Note({self.pitch}, {self.note_type.value})"
