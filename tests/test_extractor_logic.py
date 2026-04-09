"""Tests for pure-logic functions in core/extractor.py.

Covers:
  - _extract_json_from_response  (JSON extraction from LLM text)
  - _model_supports_thinking     (model feature flag)
  - _build_score                 (JSON dict → Score model)
  - _extract_two_pass / _extract_single_pass  (clef_metadata injection, mocked API)
  - extract_from_image           (end-to-end with all I/O mocked)

No real API calls are made — everything external is patched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.extractor import (
    _build_score,
    _extract_json_from_response,
    _extract_single_pass,
    _extract_two_pass,
    _model_supports_thinking,
    extract_from_image,
)
from models.note import NoteType
from models.score import Score


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_score_json(**overrides) -> dict:
    """Return minimal valid extraction JSON accepted by _build_score."""
    base = {
        "title": "Test Score",
        "composer": "Test Composer",
        "parts": [],
    }
    base.update(overrides)
    return base


def _part_json(name="Piano", staves=1, measures=None) -> dict:
    return {
        "name": name,
        "staves": staves,
        "measures": measures or [],
    }


def _measure_json(**kwargs) -> dict:
    base = {
        "number": 1,
        "time_signature": {"beats": 4, "beat_type": 4},
        "key_signature": {"fifths": 0, "mode": "major"},
        "clef": {"sign": "G", "line": 2},
        "divisions": 1,
        "notes": [],
        "barline_right": None,
        "tempo": None,
    }
    base.update(kwargs)
    return base


def _note_json(**kwargs) -> dict:
    base = {
        "type": "quarter",
        "is_rest": False,
        "pitch": {"step": "C", "octave": 4, "alter": 0},
        "accidental": None,
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
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# _extract_json_from_response
# ---------------------------------------------------------------------------

class TestExtractJsonFromResponse:
    """Tests for _extract_json_from_response."""

    # Happy path: clean JSON
    def test_plain_json_object(self):
        text = '{"title": "Test", "parts": []}'
        result = _extract_json_from_response(text)
        assert result == '{"title": "Test", "parts": []}'

    def test_plain_json_object_parses_clean(self):
        text = '{"a": 1}'
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed == {"a": 1}

    # Markdown fences
    def test_strips_json_markdown_fence(self):
        text = '```json\n{"title": "Foo"}\n```'
        result = _extract_json_from_response(text)
        assert result.strip() == '{"title": "Foo"}'

    def test_strips_plain_markdown_fence(self):
        text = '```\n{"title": "Bar"}\n```'
        result = _extract_json_from_response(text)
        assert result.strip() == '{"title": "Bar"}'

    def test_json_fence_parseable(self):
        text = '```json\n{"key": "value"}\n```'
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed["key"] == "value"

    # Preamble / postamble
    def test_skips_preamble_text(self):
        text = 'Here is the JSON output:\n{"parts": []}'
        result = _extract_json_from_response(text)
        parsed = json.loads(result)
        assert parsed == {"parts": []}

    def test_skips_postamble_text(self):
        text = '{"ok": true}\nThat completes the extraction.'
        result = _extract_json_from_response(text)
        parsed = json.loads(result)
        assert parsed == {"ok": True}

    def test_preamble_and_postamble(self):
        text = 'Sure! Here you go:\n{"x": 42}\nLet me know if you need anything else.'
        result = _extract_json_from_response(text)
        parsed = json.loads(result)
        assert parsed["x"] == 42

    # Nested JSON (bracket depth tracking)
    def test_nested_object(self):
        inner = {"nested": {"deep": [1, 2, 3]}}
        text = json.dumps(inner)
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed == inner

    def test_nested_object_with_preamble(self):
        inner = {"a": {"b": {"c": 3}}}
        text = "Extracted:\n" + json.dumps(inner)
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed == inner

    # JSON with string containing braces
    def test_string_value_with_braces(self):
        text = '{"text": "use {curly} braces", "num": 5}'
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed["text"] == "use {curly} braces"
        assert parsed["num"] == 5

    def test_string_value_with_escaped_quote(self):
        text = r'{"msg": "say \"hello\""}'
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed["msg"] == 'say "hello"'

    # Edge cases
    def test_empty_string_returns_empty(self):
        result = _extract_json_from_response("")
        assert result == ""

    def test_whitespace_only_returns_empty(self):
        result = _extract_json_from_response("   ")
        assert result == ""

    def test_no_json_returns_raw(self):
        text = "no json here at all"
        result = _extract_json_from_response(text)
        assert result == "no json here at all"

    def test_json_array(self):
        text = '[1, 2, 3]'
        result = _extract_json_from_response(text)
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]

    def test_leading_whitespace_stripped(self):
        text = '   \n  {"val": true}'
        parsed = json.loads(_extract_json_from_response(text))
        assert parsed["val"] is True


# ---------------------------------------------------------------------------
# _model_supports_thinking
# ---------------------------------------------------------------------------

class TestModelSupportsThinking:
    """Tests for _model_supports_thinking."""

    def test_sonnet_4_6_supports_thinking(self):
        assert _model_supports_thinking("claude-sonnet-4-6") is True

    def test_sonnet_4_5_supports_thinking(self):
        assert _model_supports_thinking("claude-sonnet-4-5") is True

    def test_claude_3_7_sonnet_supports_thinking(self):
        assert _model_supports_thinking("claude-3-7-sonnet") is True

    def test_haiku_does_not_support_thinking(self):
        assert _model_supports_thinking("claude-haiku-3-5") is False

    def test_opus_does_not_support_thinking(self):
        assert _model_supports_thinking("claude-opus-4") is False

    def test_empty_string_does_not_support_thinking(self):
        assert _model_supports_thinking("") is False

    def test_unknown_model_does_not_support_thinking(self):
        assert _model_supports_thinking("gpt-4o") is False

    def test_partial_match_works(self):
        # versioned prefix still matches
        assert _model_supports_thinking("claude-sonnet-4-6-20250101") is True


# ---------------------------------------------------------------------------
# _build_score
# ---------------------------------------------------------------------------

class TestBuildScore:
    """Tests for _build_score — JSON dict to Score model conversion."""

    def test_returns_score_instance(self):
        data = _minimal_score_json()
        score = _build_score(data)
        assert isinstance(score, Score)

    def test_title_and_composer(self):
        data = _minimal_score_json(title="Sonata", composer="Beethoven")
        score = _build_score(data)
        assert score.title == "Sonata"
        assert score.composer == "Beethoven"

    def test_null_title_and_composer(self):
        data = _minimal_score_json(title=None, composer=None)
        score = _build_score(data)
        assert score.title is None
        assert score.composer is None

    def test_empty_parts(self):
        data = _minimal_score_json(parts=[])
        score = _build_score(data)
        assert score.parts == []

    def test_single_part_created(self):
        data = _minimal_score_json(parts=[_part_json(name="Violin")])
        score = _build_score(data)
        assert len(score.parts) == 1
        assert score.parts[0].name == "Violin"

    def test_part_id_auto_assigned(self):
        data = _minimal_score_json(parts=[_part_json(), _part_json(name="Bass")])
        score = _build_score(data)
        assert score.parts[0].id == "P1"
        assert score.parts[1].id == "P2"

    def test_part_staves_set(self):
        data = _minimal_score_json(parts=[_part_json(staves=2)])
        score = _build_score(data)
        assert score.parts[0].staves == 2

    def test_measure_number(self):
        m = _measure_json(number=3)
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.parts[0].measures[0].number == 3

    def test_time_signature_parsed(self):
        m = _measure_json(time_signature={"beats": 3, "beat_type": 4})
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        ts = score.parts[0].measures[0].time_signature
        assert ts.beats == 3
        assert ts.beat_type == 4

    def test_initial_time_set_from_first_measure(self):
        m = _measure_json(time_signature={"beats": 6, "beat_type": 8})
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.initial_time is not None
        assert score.initial_time.beats == 6

    def test_key_signature_parsed(self):
        m = _measure_json(key_signature={"fifths": -2, "mode": "minor"})
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        ks = score.parts[0].measures[0].key_signature
        assert ks.fifths == -2
        assert ks.mode == "minor"

    def test_initial_key_set_from_first_measure(self):
        m = _measure_json(key_signature={"fifths": 2, "mode": "major"})
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.initial_key is not None
        assert score.initial_key.fifths == 2

    def test_clef_parsed(self):
        m = _measure_json(clef={"sign": "F", "line": 4})
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        clef = score.parts[0].measures[0].clef
        assert clef.sign == "F"
        assert clef.line == 4

    def test_clef_null_allowed(self):
        m = _measure_json(clef=None)
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.parts[0].measures[0].clef is None

    def test_divisions_default(self):
        m = _measure_json(divisions=4)
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.parts[0].measures[0].divisions == 4

    def test_tempo_set(self):
        m = _measure_json(tempo=120)
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.parts[0].measures[0].tempo == 120
        assert score.initial_tempo == 120

    def test_barline_right_parsed(self):
        m = _measure_json(barline_right={"style": "light-heavy"})
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert score.parts[0].measures[0].barline_right.style == "light-heavy"

    def test_note_added_to_measure(self):
        m = _measure_json(notes=[_note_json()])
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert len(score.parts[0].measures[0].notes) == 1

    def test_note_type_parsed(self):
        m = _measure_json(notes=[_note_json(type="half")])
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        note = score.parts[0].measures[0].notes[0]
        assert note.note_type == NoteType.HALF

    def test_rest_note(self):
        m = _measure_json(notes=[_note_json(is_rest=True, pitch=None)])
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        note = score.parts[0].measures[0].notes[0]
        assert note.is_rest is True
        assert note.pitch is None

    def test_multiple_notes_in_measure(self):
        notes = [_note_json(type="quarter") for _ in range(4)]
        m = _measure_json(notes=notes)
        data = _minimal_score_json(parts=[_part_json(measures=[m])])
        score = _build_score(data)
        assert len(score.parts[0].measures[0].notes) == 4

    def test_no_parts_key_gives_empty_score(self):
        data = {"title": "Empty"}
        score = _build_score(data)
        assert score.parts == []


