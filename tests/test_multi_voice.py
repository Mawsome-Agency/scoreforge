"""Tests for multi-voice extraction logic and stem sanitization."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.extractor import _build_note, _sanitize_stem
from models.note import NoteType


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _note(overrides: dict = None):
    """Return a minimal valid note data dict, merged with overrides."""
    base = {
        "type": "quarter",
        "is_rest": False,
        "pitch": {"step": "C", "octave": 4, "alter": 0},
        "dots": 0,
        "is_chord": False,
        "voice": 1,
        "staff": 1,
        "stem": "up",
        "tie_start": False,
        "tie_stop": False,
        "slur_start": False,
        "slur_stop": False,
        "beam": None,
        "dynamic": None,
        "articulation": None,
        "lyrics": [],
        "fermata": False,
        "grace": False,
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestSanitizeStem — _sanitize_stem unit tests
# ---------------------------------------------------------------------------

class TestSanitizeStem:
    """Tests for the _sanitize_stem helper."""

    # Valid values — should pass through (already lowercase)
    def test_valid_up(self):
        assert _sanitize_stem("up") == "up"

    def test_valid_down(self):
        assert _sanitize_stem("down") == "down"

    def test_valid_none_string(self):
        assert _sanitize_stem("none") == "none"

    def test_valid_double(self):
        assert _sanitize_stem("double") == "double"

    # Uppercase / mixed case — should be normalized and accepted
    def test_uppercase_up(self):
        assert _sanitize_stem("UP") == "up"

    def test_uppercase_down(self):
        assert _sanitize_stem("DOWN") == "down"

    def test_mixed_case_up(self):
        assert _sanitize_stem("Up") == "up"

    def test_mixed_case_down(self):
        assert _sanitize_stem("Down") == "down"

    def test_mixed_case_none(self):
        assert _sanitize_stem("None") == "none"

    def test_mixed_case_double(self):
        assert _sanitize_stem("Double") == "double"

    # Whitespace padding — should be stripped and accepted if valid
    def test_up_with_whitespace(self):
        assert _sanitize_stem("  up  ") == "up"

    def test_down_with_whitespace(self):
        assert _sanitize_stem("\tdown\n") == "down"

    # Invalid values — must return None
    def test_invalid_upward(self):
        assert _sanitize_stem("upward") is None

    def test_invalid_downward(self):
        assert _sanitize_stem("downward") is None

    def test_invalid_northward(self):
        assert _sanitize_stem("northward") is None

    def test_invalid_arrow_up(self):
        assert _sanitize_stem("↑") is None

    def test_invalid_arrow_down(self):
        assert _sanitize_stem("↓") is None

    def test_invalid_stem_up_phrase(self):
        assert _sanitize_stem("stem up") is None

    def test_invalid_stem_down_phrase(self):
        assert _sanitize_stem("stem down") is None

    def test_invalid_above(self):
        assert _sanitize_stem("above") is None

    def test_invalid_below(self):
        assert _sanitize_stem("below") is None

    def test_invalid_random_string(self):
        assert _sanitize_stem("foobar") is None

    def test_invalid_numeric(self):
        assert _sanitize_stem("1") is None

    # Falsy / None input
    def test_none_input(self):
        assert _sanitize_stem(None) is None

    def test_empty_string(self):
        assert _sanitize_stem("") is None

    def test_whitespace_only(self):
        assert _sanitize_stem("   ") is None


# ---------------------------------------------------------------------------
# TestExtractorBuildNoteStem — _build_note stem field behaviour
# ---------------------------------------------------------------------------

class TestExtractorBuildNoteStem:
    """Tests for stem field handling in _build_note."""

    def test_stem_up_stored(self):
        note = _build_note(_note({"stem": "up"}))
        assert note.stem == "up"

    def test_stem_down_stored(self):
        note = _build_note(_note({"stem": "down"}))
        assert note.stem == "down"

    def test_stem_none_string_stored(self):
        note = _build_note(_note({"stem": "none"}))
        assert note.stem == "none"

    def test_stem_double_stored(self):
        note = _build_note(_note({"stem": "double"}))
        assert note.stem == "double"

    def test_stem_null_json(self):
        note = _build_note(_note({"stem": None}))
        assert note.stem is None

    def test_stem_absent_key(self):
        data = _note()
        del data["stem"]
        note = _build_note(data)
        assert note.stem is None

    def test_stem_uppercase_normalised(self):
        note = _build_note(_note({"stem": "UP"}))
        assert note.stem == "up"

    # NEW TEST — required by acceptance criteria
    def test_invalid_stem_sanitized_to_none(self):
        """Stem value 'upward' is an LLM hallucination and must be discarded (→ None)."""
        note = _build_note(_note({"stem": "upward"}))
        assert note.stem is None

    def test_invalid_stem_northward_to_none(self):
        note = _build_note(_note({"stem": "northward"}))
        assert note.stem is None

    def test_invalid_stem_arrow_to_none(self):
        note = _build_note(_note({"stem": "↑"}))
        assert note.stem is None


# ---------------------------------------------------------------------------
# TestBuildNoteVoice — voice field behaviour in _build_note
# ---------------------------------------------------------------------------

class TestBuildNoteVoice:
    """Tests for voice field handling in _build_note."""

    def test_voice_1_default(self):
        data = _note()
        del data["voice"]
        note = _build_note(data)
        assert note.voice == 1

    def test_voice_1_explicit(self):
        note = _build_note(_note({"voice": 1}))
        assert note.voice == 1

    def test_voice_2_explicit(self):
        note = _build_note(_note({"voice": 2}))
        assert note.voice == 2

    def test_voice_3_explicit(self):
        note = _build_note(_note({"voice": 3}))
        assert note.voice == 3

    def test_stem_up_voice_1_pair(self):
        note = _build_note(_note({"stem": "up", "voice": 1}))
        assert note.stem == "up"
        assert note.voice == 1

    def test_stem_down_voice_2_pair(self):
        note = _build_note(_note({"stem": "down", "voice": 2}))
        assert note.stem == "down"
        assert note.voice == 2


# ---------------------------------------------------------------------------
# TestBuildNoteBasic — general _build_note correctness
# ---------------------------------------------------------------------------

class TestBuildNoteBasic:
    """Basic _build_note field mapping tests."""

    def test_note_type_quarter(self):
        note = _build_note(_note({"type": "quarter"}))
        assert note.note_type == NoteType.QUARTER

    def test_note_type_half(self):
        note = _build_note(_note({"type": "half"}))
        assert note.note_type == NoteType.HALF

    def test_note_type_whole(self):
        note = _build_note(_note({"type": "whole"}))
        assert note.note_type == NoteType.WHOLE

    def test_note_type_eighth(self):
        note = _build_note(_note({"type": "eighth"}))
        assert note.note_type == NoteType.EIGHTH

    def test_note_type_sixteenth(self):
        note = _build_note(_note({"type": "16th"}))
        assert note.note_type == NoteType.SIXTEENTH

    def test_pitch_step_and_octave(self):
        note = _build_note(_note({"pitch": {"step": "G", "octave": 5, "alter": 0}}))
        assert note.pitch.step == "G"
        assert note.pitch.octave == 5

    def test_rest_has_no_pitch(self):
        note = _build_note(_note({"is_rest": True, "pitch": None}))
        assert note.is_rest is True
        assert note.pitch is None

    def test_is_chord_false_default(self):
        note = _build_note(_note())
        assert note.is_chord is False

    def test_is_chord_true(self):
        note = _build_note(_note({"is_chord": True}))
        assert note.is_chord is True

    def test_tie_start(self):
        note = _build_note(_note({"tie_start": True}))
        assert note.tie_start is True

    def test_tie_stop(self):
        note = _build_note(_note({"tie_stop": True}))
        assert note.tie_stop is True

    def test_dots(self):
        note = _build_note(_note({"dots": 1}))
        assert note.dot_count == 1

    def test_staff_2(self):
        note = _build_note(_note({"staff": 2}))
        assert note.staff == 2

    def test_fermata(self):
        note = _build_note(_note({"fermata": True}))
        assert note.fermata is True

    def test_grace(self):
        note = _build_note(_note({"grace": True}))
        assert note.grace is True

    def test_beam_begin(self):
        note = _build_note(_note({"beam": "begin"}))
        assert note.beam == "begin"

    def test_beam_end(self):
        note = _build_note(_note({"beam": "end"}))
        assert note.beam == "end"
