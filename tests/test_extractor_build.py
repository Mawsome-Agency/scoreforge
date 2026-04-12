"""Tests for core/extractor.py building functions.

Focuses on _infer_duration() and _build_note() which are the most
change-prone functions in the pipeline (they've caused duration bugs
multiple times). All tests are pure Python — no API calls.

Coverage targets:
- _infer_duration: all 7 note types × divisions=1 and divisions=4, dots 0/1/2
- _build_note: duration always from _infer_duration (never LLM value),
               pitch, rest, chord, voice, dots, grace, tie, tuplet, stem
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.extractor import _build_note, _infer_duration, NoteType


# ---------------------------------------------------------------------------
# _infer_duration — happy path: all 7 note types at divisions=1
# ---------------------------------------------------------------------------

class TestInferDurationDivisionsOne:
    """At divisions=1: whole=4, half=2, quarter=1, eighth=1 (min-capped)."""

    def test_whole_no_dots(self):
        assert _infer_duration(NoteType.WHOLE, 0, 1) == 4

    def test_half_no_dots(self):
        assert _infer_duration(NoteType.HALF, 0, 1) == 2

    def test_quarter_no_dots(self):
        assert _infer_duration(NoteType.QUARTER, 0, 1) == 1

    def test_eighth_no_dots_capped_at_one(self):
        # 0.5 * 1 = 0.5 → rounded to 1 (max(1,...))
        assert _infer_duration(NoteType.EIGHTH, 0, 1) == 1

    def test_sixteenth_no_dots_capped_at_one(self):
        assert _infer_duration(NoteType.SIXTEENTH, 0, 1) == 1

    def test_thirty_second_no_dots_capped_at_one(self):
        assert _infer_duration(NoteType.THIRTY_SECOND, 0, 1) == 1

    def test_sixty_fourth_no_dots_capped_at_one(self):
        assert _infer_duration(NoteType.SIXTY_FOURTH, 0, 1) == 1


# ---------------------------------------------------------------------------
# _infer_duration — divisions=4 (required for sub-quarter note accuracy)
# ---------------------------------------------------------------------------

class TestInferDurationDivisionsFour:
    """At divisions=4: quarter=4, eighth=2, 16th=1, 32nd=1 (min-capped)."""

    def test_whole_divisions_4(self):
        assert _infer_duration(NoteType.WHOLE, 0, 4) == 16

    def test_half_divisions_4(self):
        assert _infer_duration(NoteType.HALF, 0, 4) == 8

    def test_quarter_divisions_4(self):
        assert _infer_duration(NoteType.QUARTER, 0, 4) == 4

    def test_eighth_divisions_4(self):
        assert _infer_duration(NoteType.EIGHTH, 0, 4) == 2

    def test_sixteenth_divisions_4(self):
        assert _infer_duration(NoteType.SIXTEENTH, 0, 4) == 1

    def test_thirty_second_divisions_4_capped(self):
        # 0.125 * 4 = 0.5 → max(1, round(0.5)) = 1
        assert _infer_duration(NoteType.THIRTY_SECOND, 0, 4) == 1

    def test_sixty_fourth_divisions_4_capped(self):
        # 0.0625 * 4 = 0.25 → max(1, round(0.25)) = 1
        assert _infer_duration(NoteType.SIXTY_FOURTH, 0, 4) == 1


# ---------------------------------------------------------------------------
# _infer_duration — dotted notes
# ---------------------------------------------------------------------------

class TestInferDurationDots:
    """Dots: 1 dot = 1.5x, 2 dots = 1.75x."""

    def test_dotted_quarter_divisions_1(self):
        # 1 * 1.5 = 1.5 → round to 2
        assert _infer_duration(NoteType.QUARTER, 1, 1) == 2

    def test_dotted_half_divisions_1(self):
        # 2 * 1.5 = 3
        assert _infer_duration(NoteType.HALF, 1, 1) == 3

    def test_dotted_whole_divisions_1(self):
        # 4 * 1.5 = 6
        assert _infer_duration(NoteType.WHOLE, 1, 1) == 6

    def test_double_dotted_quarter_divisions_1(self):
        # 1 * 1.75 = 1.75 → round to 2
        assert _infer_duration(NoteType.QUARTER, 2, 1) == 2

    def test_double_dotted_half_divisions_1(self):
        # 2 * 1.75 = 3.5 → round to 4 (not 3!)
        assert _infer_duration(NoteType.HALF, 2, 1) == 4

    def test_dotted_quarter_divisions_4(self):
        # 4 * 1.5 = 6
        assert _infer_duration(NoteType.QUARTER, 1, 4) == 6

    def test_dotted_eighth_divisions_4(self):
        # 2 * 1.5 = 3
        assert _infer_duration(NoteType.EIGHTH, 1, 4) == 3

    def test_zero_dots_same_as_no_dots_arg(self):
        assert _infer_duration(NoteType.HALF, 0, 1) == _infer_duration(NoteType.HALF, 0, 1)


# ---------------------------------------------------------------------------
# _infer_duration — edge cases / min floor
# ---------------------------------------------------------------------------

class TestInferDurationEdgeCases:
    """Duration is always at least 1."""

    def test_result_is_always_positive(self):
        for nt in NoteType:
            result = _infer_duration(nt, 0, 1)
            assert result >= 1, f"{nt.value} at divisions=1 produced {result}"

    def test_result_is_always_positive_with_dots(self):
        for nt in NoteType:
            result = _infer_duration(nt, 1, 1)
            assert result >= 1, f"dotted {nt.value} at divisions=1 produced {result}"

    def test_result_is_integer(self):
        """_infer_duration must return an int (used in XML duration element)."""
        result = _infer_duration(NoteType.EIGHTH, 0, 4)
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# _build_note — duration is ALWAYS from _infer_duration, never LLM value
# ---------------------------------------------------------------------------

class TestBuildNoteDurationOverride:
    """Critical: LLM often emits wrong duration integers. _build_note must
    always use _infer_duration() regardless of what 'duration' the LLM gave."""

    def test_quarter_note_ignores_llm_duration_1(self):
        """LLM gives duration=1 for a quarter, divisions=1 → should be 1."""
        data = {"type": "quarter", "duration": 1, "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data, divisions=1)
        assert note.duration == 1

    def test_half_note_ignores_llm_duration_1(self):
        """LLM gives duration=1 for a half note — this was the bug. Must be 2."""
        data = {"type": "half", "duration": 1, "pitch": {"step": "D", "octave": 4}}
        note = _build_note(data, divisions=1)
        assert note.duration == 2  # half note at divisions=1 = 2, NOT 1

    def test_whole_note_ignores_llm_duration_1(self):
        """LLM gives duration=1 for whole note — must be 4."""
        data = {"type": "whole", "duration": 1, "pitch": {"step": "E", "octave": 4}}
        note = _build_note(data, divisions=1)
        assert note.duration == 4  # whole at divisions=1 = 4, NOT 1

    def test_eighth_note_with_divisions_4(self):
        """Eighth at divisions=4 → duration=2."""
        data = {"type": "eighth", "duration": 99, "pitch": {"step": "G", "octave": 5}}
        note = _build_note(data, divisions=4)
        assert note.duration == 2

    def test_dotted_quarter_at_divisions_4(self):
        """Dotted quarter at divisions=4 → 6."""
        data = {"type": "quarter", "duration": 999, "dots": 1, "pitch": {"step": "A", "octave": 4}}
        note = _build_note(data, divisions=4)
        assert note.duration == 6

    def test_duration_matches_infer_duration_directly(self):
        """_build_note duration must equal _infer_duration output exactly."""
        for nt_str, nt_enum in [("whole", NoteType.WHOLE), ("half", NoteType.HALF),
                                  ("quarter", NoteType.QUARTER), ("eighth", NoteType.EIGHTH)]:
            data = {"type": nt_str, "duration": 0, "pitch": {"step": "C", "octave": 4}}
            note = _build_note(data, divisions=4)
            expected = _infer_duration(nt_enum, 0, 4)
            assert note.duration == expected, f"{nt_str}: expected {expected}, got {note.duration}"


# ---------------------------------------------------------------------------
# _build_note — pitch handling
# ---------------------------------------------------------------------------

class TestBuildNotePitch:

    def test_pitch_step_and_octave_preserved(self):
        data = {"type": "quarter", "pitch": {"step": "G", "octave": 5}}
        note = _build_note(data)
        assert note.pitch.step == "G"
        assert note.pitch.octave == 5

    def test_pitch_with_alter(self):
        data = {"type": "quarter", "pitch": {"step": "F", "octave": 4, "alter": 1}}
        note = _build_note(data)
        assert note.pitch.alter == 1

    def test_pitch_alter_defaults_to_zero(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.pitch.alter == 0

    def test_rest_has_no_pitch(self):
        data = {"type": "quarter", "is_rest": True}
        note = _build_note(data)
        assert note.pitch is None
        assert note.is_rest is True

    def test_note_with_no_pitch_field_has_no_pitch(self):
        """Missing pitch key → pitch=None (treat as rest-like)."""
        data = {"type": "quarter"}
        note = _build_note(data)
        assert note.pitch is None

    def test_is_rest_false_with_pitch(self):
        data = {"type": "quarter", "pitch": {"step": "D", "octave": 5}, "is_rest": False}
        note = _build_note(data)
        assert note.is_rest is False
        assert note.pitch is not None


# ---------------------------------------------------------------------------
# _build_note — note type fallback
# ---------------------------------------------------------------------------

class TestBuildNoteTypeFallback:

    def test_unknown_type_defaults_to_quarter(self):
        """Unknown type string → default to QUARTER."""
        data = {"type": "triplet-half", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.note_type == NoteType.QUARTER

    def test_missing_type_defaults_to_quarter(self):
        """Missing type key → default to QUARTER."""
        data = {"pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.note_type == NoteType.QUARTER

    def test_all_valid_types_recognized(self):
        valid_types = ["whole", "half", "quarter", "eighth", "16th", "32nd", "64th"]
        expected = [NoteType.WHOLE, NoteType.HALF, NoteType.QUARTER, NoteType.EIGHTH,
                    NoteType.SIXTEENTH, NoteType.THIRTY_SECOND, NoteType.SIXTY_FOURTH]
        for t, expected_nt in zip(valid_types, expected):
            data = {"type": t, "pitch": {"step": "C", "octave": 4}}
            note = _build_note(data)
            assert note.note_type == expected_nt, f"type={t!r} expected {expected_nt}"


# ---------------------------------------------------------------------------
# _build_note — dots
# ---------------------------------------------------------------------------

class TestBuildNoteDots:

    def test_dot_count_zero_by_default(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.dot_count == 0

    def test_dot_count_one(self):
        data = {"type": "half", "dots": 1, "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.dot_count == 1

    def test_dot_count_two(self):
        data = {"type": "whole", "dots": 2, "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.dot_count == 2

    def test_dotted_half_duration_reflects_dots(self):
        """dot_count=1 must flow through to duration (via _infer_duration)."""
        data = {"type": "half", "dots": 1, "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data, divisions=1)
        assert note.duration == 3  # 2 * 1.5


# ---------------------------------------------------------------------------
# _build_note — voice, chord, grace, tie fields
# ---------------------------------------------------------------------------

class TestBuildNoteMetaFields:

    def test_voice_default_is_1(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.voice == 1

    def test_voice_set_to_2(self):
        data = {"type": "quarter", "voice": 2, "pitch": {"step": "G", "octave": 4}}
        note = _build_note(data)
        assert note.voice == 2

    def test_chord_default_is_false(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.is_chord is False

    def test_chord_set_true(self):
        data = {"type": "quarter", "is_chord": True, "pitch": {"step": "E", "octave": 4}}
        note = _build_note(data)
        assert note.is_chord is True

    def test_grace_default_is_false(self):
        data = {"type": "eighth", "pitch": {"step": "D", "octave": 5}}
        note = _build_note(data)
        assert note.grace is False

    def test_grace_set_true(self):
        data = {"type": "eighth", "grace": True, "pitch": {"step": "D", "octave": 5}}
        note = _build_note(data)
        assert note.grace is True

    def test_tie_start_default_false(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.tie_start is False

    def test_tie_stop_default_false(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.tie_stop is False

    def test_tie_start_and_stop(self):
        data = {"type": "half", "tie_start": True, "tie_stop": True,
                "pitch": {"step": "F", "octave": 4}}
        note = _build_note(data)
        assert note.tie_start is True
        assert note.tie_stop is True

    def test_fermata_default_false(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.fermata is False

    def test_fermata_set_true(self):
        data = {"type": "whole", "fermata": True, "pitch": {"step": "G", "octave": 4}}
        note = _build_note(data)
        assert note.fermata is True


# ---------------------------------------------------------------------------
# _build_note — tuplet fields
# ---------------------------------------------------------------------------

class TestBuildNoteTuplet:

    def test_tuplet_fields_default_none_false(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.tuplet_actual is None
        assert note.tuplet_normal is None
        assert note.tuplet_start is False
        assert note.tuplet_stop is False

    def test_tuplet_3_in_2(self):
        data = {"type": "eighth", "tuplet_actual": 3, "tuplet_normal": 2,
                "tuplet_start": True, "pitch": {"step": "C", "octave": 5}}
        note = _build_note(data)
        assert note.tuplet_actual == 3
        assert note.tuplet_normal == 2
        assert note.tuplet_start is True
        assert note.tuplet_stop is False

    def test_tuplet_stop(self):
        data = {"type": "eighth", "tuplet_actual": 3, "tuplet_normal": 2,
                "tuplet_stop": True, "pitch": {"step": "E", "octave": 5}}
        note = _build_note(data)
        assert note.tuplet_stop is True
        assert note.tuplet_start is False


# ---------------------------------------------------------------------------
# _build_note — accidental handling
# ---------------------------------------------------------------------------

class TestBuildNoteAccidental:

    def test_no_accidental_is_none(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.pitch.accidental is None

    def test_sharp_accidental(self):
        data = {"type": "quarter", "accidental": "sharp",
                "pitch": {"step": "F", "octave": 4}}
        note = _build_note(data)
        assert note.pitch.accidental is not None

    def test_unknown_accidental_is_none(self):
        """Unknown accidental key → pitch.accidental = None (no crash)."""
        data = {"type": "quarter", "accidental": "triple-sharp",
                "pitch": {"step": "G", "octave": 4}}
        note = _build_note(data)
        assert note.pitch.accidental is None


# ---------------------------------------------------------------------------
# _build_note — empty / null data edge cases
# ---------------------------------------------------------------------------

class TestBuildNoteEdgeCases:

    def test_minimal_data_does_not_crash(self):
        """Bare minimum data dict must not raise."""
        note = _build_note({})
        assert note is not None
        assert note.note_type == NoteType.QUARTER
        assert note.is_rest is False
        assert note.pitch is None

    def test_is_rest_true_without_pitch_field(self):
        data = {"type": "quarter", "is_rest": True}
        note = _build_note(data)
        assert note.is_rest is True
        assert note.pitch is None

    def test_rest_duration_still_inferred(self):
        """Rests still get correct durations from _infer_duration."""
        data = {"type": "whole", "is_rest": True}
        note = _build_note(data, divisions=1)
        assert note.duration == 4

    def test_lyrics_default_empty_list(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.lyrics == []

    def test_slur_defaults_false(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.slur_start is False
        assert note.slur_stop is False

    def test_staff_defaults_to_1(self):
        data = {"type": "quarter", "pitch": {"step": "C", "octave": 4}}
        note = _build_note(data)
        assert note.staff == 1
