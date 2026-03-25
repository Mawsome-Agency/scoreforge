"""Full score data model."""
from dataclasses import dataclass, field
from typing import Optional
from .measure import Measure, KeySignature, TimeSignature, Clef


@dataclass
class Part:
    """A single instrument part."""
    id: str
    name: str
    abbreviation: Optional[str] = None
    measures: list[Measure] = field(default_factory=list)
    staves: int = 1  # 2 for piano (treble + bass)
    midi_program: Optional[int] = None
    transpose_diatonic: Optional[int] = None
    transpose_chromatic: Optional[int] = None

    @property
    def measure_count(self) -> int:
        return len(self.measures)


@dataclass
class Score:
    """Complete musical score."""
    title: Optional[str] = None
    composer: Optional[str] = None
    arranger: Optional[str] = None
    parts: list[Part] = field(default_factory=list)
    initial_key: Optional[KeySignature] = None
    initial_time: Optional[TimeSignature] = None
    initial_tempo: Optional[int] = None

    @property
    def measure_count(self) -> int:
        if not self.parts:
            return 0
        return max(p.measure_count for p in self.parts)

    @property
    def part_count(self) -> int:
        return len(self.parts)

    def summary(self) -> str:
        lines = []
        if self.title:
            lines.append(f"Title: {self.title}")
        if self.composer:
            lines.append(f"Composer: {self.composer}")
        lines.append(f"Parts: {self.part_count}")
        lines.append(f"Measures: {self.measure_count}")
        if self.initial_key:
            lines.append(f"Key: {self.initial_key.name} {self.initial_key.mode}")
        if self.initial_time:
            lines.append(f"Time: {self.initial_time}")
        return "\n".join(lines)
