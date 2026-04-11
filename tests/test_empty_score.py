"""Unit tests for empty-score edge case (HARNESS_GAPS.md Gap #6).

Tests the most common pipeline failure mode: extraction returns 0 notes.
This happens when Claude returns malformed JSON, a blank image is submitted,
or the score is truly empty.

Edge cases covered:
- build_musicxml() does not crash on a Score with 0 notes
- build_musicxml() produces valid (parseable) XML when given 0 notes
- comparator reports 0% recall when extracted score has 0 notes
- comparator does not crash when GT has notes and extracted has 0
- comparator does not crash when both GT and extracted have 0 notes
- empty_score.musicxml fixture is valid and parseable
- empty_score fixture has the expected structure (1 part, 1 measure, no pitched notes)
"""
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Make sure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EMPTY_SCORE_PATH = FIXTURES_DIR / "empty_score.musicxml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_empty_score():
    """Build a minimal Score dataclass with zero notes."""
    from models.measure import Clef, KeySignature, Measure, TimeSignature
    from models.score import Part, Score

    score = Score(title="Empty Test")
    part = Part(id="P1", name="Piano")
    measure = Measure(number=1)
    measure.divisions = 1
    measure.key_signature = KeySignature(fifths=0, mode="major")
    measure.time_signature = TimeSignature(beats=4, beat_type=4)
    measure.clef = Clef(sign="G", line=2)
    # No notes added — measure.notes stays []
    part.measures.append(measure)
    score.parts.append(part)
    return score


def _make_one_note_score():
    """Build a minimal Score with exactly 1 note (for comparator baseline)."""
    from models.measure import Clef, KeySignature, Measure, TimeSignature
    from models.note import Note, NoteType, Pitch
    from models.score import Part, Score

    score = Score(title="One Note")
    part = Part(id="P1", name="Piano")
    measure = Measure(number=1)
    measure.divisions = 1
    measure.key_signature = KeySignature(fifths=0, mode="major")
    measure.time_signature = TimeSignature(beats=4, beat_type=4)
    measure.clef = Clef(sign="G", line=2)
    measure.notes.append(
        Note(
            note_type=NoteType.QUARTER,
            duration=1,
            is_rest=False,
            pitch=Pitch(step="C", octave=4, alter=0),
        )
    )
    part.measures.append(measure)
    score.parts.append(part)
    return score


# ---------------------------------------------------------------------------
# A. Fixture file validation
# ---------------------------------------------------------------------------

class TestEmptyScoreFixture:
    """Verify the empty_score.musicxml fixture itself is well-formed."""

    def test_fixture_exists(self):
        """empty_score.musicxml exists on disk."""
        assert EMPTY_SCORE_PATH.exists(), (
            f"Fixture missing: {EMPTY_SCORE_PATH}. "
            "Run tests/fixtures/generate_fixtures.py to create it."
        )

    def test_fixture_is_valid_xml(self):
        """empty_score.musicxml parses without XML errors."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        assert root is not None

    def test_fixture_is_score_partwise(self):
        """Root element is score-partwise (standard MusicXML format)."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        assert root.tag == "score-partwise", (
            f"Expected 'score-partwise', got '{root.tag}'"
        )

    def test_fixture_has_one_part(self):
        """empty_score has exactly one part."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        parts = root.findall(".//part")
        assert len(parts) == 1, f"Expected 1 part, got {len(parts)}"

    def test_fixture_has_one_measure(self):
        """empty_score has exactly one measure."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        measures = root.findall(".//measure")
        assert len(measures) == 1, f"Expected 1 measure, got {len(measures)}"

    def test_fixture_has_no_pitched_notes(self):
        """empty_score has no pitched note elements (only rests or whole-measure rests)."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        pitched_notes = [
            n for n in root.findall(".//note")
            if n.find("rest") is None
        ]
        assert len(pitched_notes) == 0, (
            f"Expected 0 pitched notes in empty_score, found {len(pitched_notes)}"
        )

    def test_fixture_has_valid_key_signature(self):
        """empty_score has a key signature element."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        key = root.find(".//key")
        assert key is not None, "Missing <key> element in empty_score.musicxml"

    def test_fixture_has_valid_time_signature(self):
        """empty_score has a time signature element."""
        tree = ET.parse(EMPTY_SCORE_PATH)
        root = tree.getroot()
        time_sig = root.find(".//time")
        assert time_sig is not None, "Missing <time> element in empty_score.musicxml"


# ---------------------------------------------------------------------------
# B. build_musicxml() with 0 notes
# ---------------------------------------------------------------------------

class TestBuildMusicxmlEmptyScore:
    """build_musicxml() must not crash when given a Score with 0 notes."""

    def test_build_does_not_raise_on_empty_score(self):
        """build_musicxml() completes without exception for a 0-note Score."""
        from core.musicxml_builder import build_musicxml
        score = _make_empty_score()
        # Must not raise any exception
        result = build_musicxml(score)
        assert result is not None

    def test_build_returns_string(self):
        """build_musicxml() returns a string for a 0-note Score."""
        from core.musicxml_builder import build_musicxml
        score = _make_empty_score()
        result = build_musicxml(score)
        assert isinstance(result, str), (
            f"Expected str, got {type(result)}"
        )

    def test_build_returns_nonempty_string(self):
        """build_musicxml() returns non-empty output even with 0 notes."""
        from core.musicxml_builder import build_musicxml
        score = _make_empty_score()
        result = build_musicxml(score)
        assert len(result) > 0, "build_musicxml() returned empty string for 0-note score"

    def test_build_output_is_valid_xml(self):
        """build_musicxml() output is well-formed XML for a 0-note Score."""
        from core.musicxml_builder import build_musicxml
        score = _make_empty_score()
        result = build_musicxml(score)
        try:
            root = ET.fromstring(result)
        except ET.ParseError as e:
            pytest.fail(f"build_musicxml() produced invalid XML for 0-note score: {e}")
        assert root is not None

    def test_build_output_contains_part(self):
        """build_musicxml() output contains at least one part element."""
        from core.musicxml_builder import build_musicxml
        score = _make_empty_score()
        result = build_musicxml(score)
        root = ET.fromstring(result)
        parts = root.findall(".//part")
        assert len(parts) >= 1, "build_musicxml() output missing <part> for 0-note score"

    def test_build_on_completely_empty_score(self):
        """build_musicxml() handles a Score with no parts at all."""
        from core.musicxml_builder import build_musicxml
        from models.score import Score
        score = Score(title="Totally Empty")
        # Must not raise; result may be minimal but valid
        try:
            result = build_musicxml(score)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(
                f"build_musicxml() raised {type(e).__name__} on Score with no parts: {e}"
            )

    def test_build_on_score_with_empty_part(self):
        """build_musicxml() handles a Part with no measures."""
        from core.musicxml_builder import build_musicxml
        from models.score import Part, Score
        score = Score(title="Empty Part")
        part = Part(id="P1", name="Piano")
        # No measures added
        score.parts.append(part)
        try:
            result = build_musicxml(score)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(
                f"build_musicxml() raised {type(e).__name__} on Part with no measures: {e}"
            )


# ---------------------------------------------------------------------------
# C. Comparator with 0-note extracted score
# ---------------------------------------------------------------------------

class TestComparatorEmptyScore:
    """comparator.compare_musicxml_semantic() must handle 0-note output gracefully."""

    def _write_empty_extracted(self, tmp_path: Path) -> str:
        """Write an empty extracted MusicXML to tmp_path and return path."""
        from core.musicxml_builder import build_musicxml
        score = _make_empty_score()
        xml = build_musicxml(score)
        out = tmp_path / "extracted_empty.musicxml"
        out.write_text(xml, encoding="utf-8")
        return str(out)

    def test_comparator_does_not_crash_empty_vs_nonempty(self, tmp_path):
        """compare_musicxml_semantic() does not raise when extracted has 0 notes but GT has notes."""
        from core.comparator import compare_musicxml_semantic
        gt_path = str(FIXTURES_DIR / "simple_melody.musicxml")
        extracted_path = self._write_empty_extracted(tmp_path)
        # Must not raise
        try:
            result = compare_musicxml_semantic(gt_path, extracted_path)
        except Exception as e:
            pytest.fail(
                f"compare_musicxml_semantic() raised {type(e).__name__} "
                f"when extracted score has 0 notes: {e}"
            )

    def test_comparator_zero_recall_on_empty_extraction(self, tmp_path):
        """When extracted score has 0 notes, overall accuracy should be very low.

        The overall may not be exactly 0% because key/time signature matching from
        the one extracted measure contributes slightly to the overall score. The
        important invariant is that the score is very low (< 15%) — never 100% or
        even 50%. All note-level scores (pitch, rhythm) must be 0%.
        """
        from core.comparator import compare_musicxml_semantic
        gt_path = str(FIXTURES_DIR / "simple_melody.musicxml")
        extracted_path = self._write_empty_extracted(tmp_path)
        result = compare_musicxml_semantic(gt_path, extracted_path)
        overall = result["scores"].get("overall", -1)
        # 0 notes extracted against a non-empty GT must score well below passing threshold.
        # Key/time sig match in the one extracted measure may contribute a few %, hence < 15%.
        assert overall < 15, (
            f"Expected < 15% overall when extracted score has 0 notes, got {overall}%"
        )
        # note and rhythm must be exactly 0% (no notes matched, no durations correct)
        assert result["scores"].get("note_accuracy", -1) == 0, "note_accuracy should be 0% for empty extraction"
        assert result["scores"].get("rhythm_accuracy", -1) == 0, "rhythm_accuracy should be 0% for empty extraction"

    def test_comparator_returns_dict_on_empty_extraction(self, tmp_path):
        """compare_musicxml_semantic() returns a dict even when extraction is empty."""
        from core.comparator import compare_musicxml_semantic
        gt_path = str(FIXTURES_DIR / "simple_melody.musicxml")
        extracted_path = self._write_empty_extracted(tmp_path)
        result = compare_musicxml_semantic(gt_path, extracted_path)
        assert isinstance(result, dict), (
            f"Expected dict, got {type(result)}"
        )
        assert "scores" in result, "Result dict missing 'scores' key"
        assert "is_perfect" in result, "Result dict missing 'is_perfect' key"

    def test_comparator_is_not_perfect_on_empty_extraction(self, tmp_path):
        """is_perfect must be False when extracted score has 0 notes."""
        from core.comparator import compare_musicxml_semantic
        gt_path = str(FIXTURES_DIR / "simple_melody.musicxml")
        extracted_path = self._write_empty_extracted(tmp_path)
        result = compare_musicxml_semantic(gt_path, extracted_path)
        assert result["is_perfect"] is False, (
            "is_perfect should be False when extracted score has 0 notes"
        )

    def test_comparator_empty_vs_empty_does_not_crash(self, tmp_path):
        """compare_musicxml_semantic() handles both GT and extracted being empty."""
        from core.comparator import compare_musicxml_semantic
        gt_path = str(EMPTY_SCORE_PATH)
        extracted_path = self._write_empty_extracted(tmp_path)
        try:
            result = compare_musicxml_semantic(gt_path, extracted_path)
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(
                f"compare_musicxml_semantic() raised {type(e).__name__} "
                f"on empty-vs-empty comparison: {e}"
            )

    def test_comparator_pitch_accuracy_zero_on_empty_extraction(self, tmp_path):
        """pitch_accuracy should be 0% when extracted score has 0 notes."""
        from core.comparator import compare_musicxml_semantic
        gt_path = str(FIXTURES_DIR / "simple_melody.musicxml")
        extracted_path = self._write_empty_extracted(tmp_path)
        result = compare_musicxml_semantic(gt_path, extracted_path)
        pitch_acc = result["scores"].get("pitch_accuracy", -1)
        assert pitch_acc == 0 or pitch_acc < 5, (
            f"Expected ~0% pitch_accuracy on empty extraction, got {pitch_acc}%"
        )


# ---------------------------------------------------------------------------
# D. test_harness integration — empty_score is in BUILT_IN_TESTS
# ---------------------------------------------------------------------------

class TestHarnessEmptyScoreIntegration:
    """Verify test_harness.py registers empty_score correctly."""

    def test_empty_score_in_built_in_tests(self):
        """empty_score is registered in BUILT_IN_TESTS."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        names = [t.name for t in harness.BUILT_IN_TESTS]
        assert "empty_score" in names, (
            f"empty_score not found in BUILT_IN_TESTS. Found: {names}"
        )

    def test_empty_score_has_edge_case_tag(self):
        """empty_score fixture has 'edge_case' or 'zero_notes' tag."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        tc = next(t for t in harness.BUILT_IN_TESTS if t.name == "empty_score")
        assert "edge_case" in tc.tags or "zero_notes" in tc.tags, (
            f"empty_score tags should include 'edge_case' or 'zero_notes', got: {tc.tags}"
        )

    def test_empty_score_fixture_file_path_resolves(self):
        """empty_score.musicxml path in BUILT_IN_TESTS points to an existing file."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        tc = next(t for t in harness.BUILT_IN_TESTS if t.name == "empty_score")
        assert Path(tc.musicxml_path).exists(), (
            f"empty_score musicxml_path does not exist: {tc.musicxml_path}"
        )

    def test_all_18_fixtures_in_built_in_tests(self):
        """All 18 fixtures are registered in BUILT_IN_TESTS (no auto-discovery needed)."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        assert len(harness.BUILT_IN_TESTS) == 18, (
            f"Expected 18 fixtures in BUILT_IN_TESTS, got {len(harness.BUILT_IN_TESTS)}"
        )

    def test_no_duplicate_fixture_names(self):
        """No fixture name appears twice in BUILT_IN_TESTS."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        names = [t.name for t in harness.BUILT_IN_TESTS]
        duplicates = [n for n in set(names) if names.count(n) > 1]
        assert duplicates == [], f"Duplicate fixture names: {duplicates}"

    def test_discover_fixtures_returns_18_no_duplicates(self):
        """discover_fixtures() returns 18 tests with no duplicates after promotion."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        tests = harness.discover_fixtures()
        names = [t.name for t in tests]
        duplicates = [n for n in set(names) if names.count(n) > 1]
        assert duplicates == [], f"Duplicate fixture names after discover: {duplicates}"
        assert len(tests) == 18, f"Expected 18, got {len(tests)}"


# ---------------------------------------------------------------------------
# E. --no-api skip display (HARNESS_GAPS.md Gap #8)
# ---------------------------------------------------------------------------

class TestNoApiSkipDisplay:
    """TestResult.skipped flag must be set (not error) when skip_api=True."""

    def test_test_result_has_skipped_field(self):
        """TestResult dataclass has a 'skipped' boolean field."""
        import importlib.util
        import dataclasses
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        field_names = [f.name for f in dataclasses.fields(harness.TestResult)]
        assert "skipped" in field_names, (
            f"TestResult missing 'skipped' field. Fields: {field_names}"
        )

    def test_test_result_skipped_defaults_false(self):
        """TestResult.skipped defaults to False."""
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)
        r = harness.TestResult(test_name="test", passed=False)
        assert r.skipped is False

    def test_run_test_skip_api_sets_skipped_true(self):
        """run_test() with skip_api=True sets result.skipped=True."""
        import importlib.util
        from unittest.mock import patch, MagicMock
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)

        tc = harness.BUILT_IN_TESTS[0]  # simple_melody
        # Mock render to succeed (so we reach the skip_api check)
        with patch("core.renderer.render_musicxml_to_image", return_value=None):
            result = harness.run_test(tc, skip_api=True)

        assert result.skipped is True, (
            f"run_test() with skip_api=True should set result.skipped=True, got {result.skipped}"
        )

    def test_run_test_skip_api_clears_error(self):
        """run_test() with skip_api=True sets result.error=None (not 'Skipped (--no-api)')."""
        import importlib.util
        from unittest.mock import patch
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)

        tc = harness.BUILT_IN_TESTS[0]
        with patch("core.renderer.render_musicxml_to_image", return_value=None):
            result = harness.run_test(tc, skip_api=True)

        assert result.error is None, (
            f"run_test() with skip_api=True should set result.error=None, got {result.error!r}"
        )

    def test_run_test_skip_api_does_not_set_error_string(self):
        """run_test() with skip_api=True does not set the old 'Skipped (--no-api)' error string."""
        import importlib.util
        from unittest.mock import patch
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)

        tc = harness.BUILT_IN_TESTS[0]
        with patch("core.renderer.render_musicxml_to_image", return_value=None):
            result = harness.run_test(tc, skip_api=True)

        assert result.error != "Skipped (--no-api)", (
            "run_test() still sets the old error string 'Skipped (--no-api)' — fix not applied"
        )

    def test_harness_source_uses_skipped_flag(self):
        """test_harness.py source code sets result.skipped = True in the skip_api branch."""
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        source = harness_path.read_text()
        assert "result.skipped = True" in source, (
            "test_harness.py does not set result.skipped = True in skip_api branch"
        )

    def test_harness_source_clears_error_in_skip_branch(self):
        """test_harness.py source code sets result.error = None in the skip_api branch."""
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        source = harness_path.read_text()
        assert "result.error = None" in source, (
            "test_harness.py does not set result.error = None in skip_api branch"
        )
