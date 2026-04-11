"""Tests for the baseline validation pipeline.

Covers:
- discover_fixtures(): all 18 fixtures present
- run_fixture() in skip_api mode: self-comparison yields 100% accuracy
- run_all_fixtures() in skip_api mode: all fixtures pass
- calculate_summary(): aggregate metrics correct
- failure_modes: populated from comparison diffs
- generate_markdown_report(): required sections present
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.validate_baseline import (
    FixtureInfo,
    FixtureResult,
    BaselineSummary,
    discover_fixtures,
    run_fixture,
    run_all_fixtures,
    calculate_summary,
    generate_markdown_report,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
EXPECTED_FIXTURES = [
    "annotations", "clef_changes", "complex_rhythm", "dynamics_hairpins",
    "empty_score", "full_orchestra", "key_changes", "lyrics_verses",
    "marching_stickings", "mixed_meters", "multi_voice", "nested_tuplets",
    "ornaments", "piano_chords", "repeats_codas", "simple_melody",
    "solo_with_accompaniment", "title_metadata",
]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class TestDiscoverFixtures:
    def test_finds_all_18_fixtures(self):
        fixtures = discover_fixtures()
        assert len(fixtures) == 18

    def test_fixture_names_match_expected(self):
        fixtures = discover_fixtures()
        names = {f.name for f in fixtures}
        assert names == set(EXPECTED_FIXTURES)

    def test_all_fixture_paths_exist(self):
        fixtures = discover_fixtures()
        for f in fixtures:
            assert f.path.exists(), f"Fixture file missing: {f.path}"

    def test_fixture_paths_are_musicxml(self):
        fixtures = discover_fixtures()
        for f in fixtures:
            assert f.path.suffix == ".musicxml", f"Expected .musicxml, got {f.path.suffix}"


# ---------------------------------------------------------------------------
# Single fixture — skip_api (self-comparison)
# ---------------------------------------------------------------------------

class TestRunFixtureSkipApi:
    @pytest.fixture(scope="class")
    def simple_melody_result(self):
        fixtures = discover_fixtures()
        fixture = next(f for f in fixtures if f.name == "simple_melody")
        return run_fixture(fixture, skip_api=True)

    def test_render_ok(self, simple_melody_result):
        assert simple_melody_result.render_ok is True

    def test_extract_ok_in_skip_mode(self, simple_melody_result):
        assert simple_melody_result.extract_ok is True

    def test_build_ok_in_skip_mode(self, simple_melody_result):
        assert simple_melody_result.build_ok is True

    def test_compare_ok(self, simple_melody_result):
        assert simple_melody_result.compare_ok is True

    def test_self_comparison_passes(self, simple_melody_result):
        assert simple_melody_result.passed is True

    def test_no_error(self, simple_melody_result):
        assert simple_melody_result.error is None

    def test_overall_accuracy_100(self, simple_melody_result):
        assert simple_melody_result.overall_accuracy == 100.0

    def test_pitch_accuracy_100(self, simple_melody_result):
        assert simple_melody_result.pitch_accuracy == 100.0

    def test_rhythm_accuracy_100(self, simple_melody_result):
        assert simple_melody_result.rhythm_accuracy == 100.0

    def test_voice_accuracy_100(self, simple_melody_result):
        assert simple_melody_result.voice_accuracy == 100.0

    def test_failure_modes_empty_on_perfect(self, simple_melody_result):
        # Self-comparison: no diffs → no failure modes
        assert simple_melody_result.failure_modes == []

    def test_gt_note_count_nonzero(self, simple_melody_result):
        assert simple_melody_result.gt_note_count > 0

    def test_matched_notes_equals_gt(self, simple_melody_result):
        assert simple_melody_result.matched_note_count == simple_melody_result.gt_note_count


# ---------------------------------------------------------------------------
# Full 18-fixture run — skip_api
# ---------------------------------------------------------------------------

class TestRunAllFixturesSkipApi:
    @pytest.fixture(scope="class")
    def all_results(self):
        fixtures = discover_fixtures()
        return run_all_fixtures(fixtures, skip_api=True, verbose=False)

    def test_returns_18_results(self, all_results):
        assert len(all_results) == 18

    def test_all_fixtures_pass(self, all_results):
        failures = [r.fixture.name for r in all_results if not r.passed]
        assert failures == [], f"Fixtures failed self-comparison: {failures}"

    def test_no_errors(self, all_results):
        errors = [(r.fixture.name, r.error) for r in all_results if r.error]
        assert errors == [], f"Fixtures had errors: {errors}"

    def test_all_overall_accuracy_100(self, all_results):
        below = [r.fixture.name for r in all_results if r.overall_accuracy < 100.0]
        assert below == [], f"Fixtures below 100% overall: {below}"

    def test_result_names_match_expected(self, all_results):
        names = {r.fixture.name for r in all_results}
        assert names == set(EXPECTED_FIXTURES)


# ---------------------------------------------------------------------------
# Summary calculation
# ---------------------------------------------------------------------------

class TestCalculateSummary:
    @pytest.fixture(scope="class")
    def summary(self):
        fixtures = discover_fixtures()
        results = run_all_fixtures(fixtures, skip_api=True, verbose=False)
        return calculate_summary(results)

    def test_total_18(self, summary):
        assert summary.total_fixtures == 18

    def test_all_passed(self, summary):
        assert summary.passed == 18

    def test_no_failed(self, summary):
        assert summary.failed == 0

    def test_no_errors(self, summary):
        assert summary.errors == 0

    def test_avg_overall_100(self, summary):
        assert summary.avg_overall_accuracy == 100.0

    def test_avg_pitch_100(self, summary):
        assert summary.avg_pitch_accuracy == 100.0

    def test_avg_rhythm_100(self, summary):
        assert summary.avg_rhythm_accuracy == 100.0

    def test_avg_voice_100(self, summary):
        assert summary.avg_voice_accuracy == 100.0

    def test_target_met(self, summary):
        assert summary.target_95_percent_met is True

    def test_timestamp_set(self, summary):
        assert summary.timestamp != ""


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

class TestGenerateMarkdownReport:
    @pytest.fixture(scope="class")
    def report(self):
        fixtures = discover_fixtures()
        results = run_all_fixtures(fixtures, skip_api=True, verbose=False)
        summary = calculate_summary(results)
        return generate_markdown_report(results, summary, model="auto (skip-api)")

    def test_has_title(self, report):
        assert "# ScoreForge Baseline Accuracy Report" in report

    def test_has_summary_table(self, report):
        assert "## Summary" in report

    def test_has_per_fixture_table(self, report):
        assert "## Per-Fixture Results" in report

    def test_has_failure_modes_section(self, report):
        assert "## Top Failure Modes" in report

    def test_has_progress_tracking_section(self, report):
        assert "## Progress Tracking" in report

    def test_all_fixture_names_in_report(self, report):
        for name in EXPECTED_FIXTURES:
            assert name in report, f"Fixture '{name}' missing from report"

    def test_pass_status_shown(self, report):
        assert "✅ PASS" in report

    def test_95_target_met_shown(self, report):
        assert "95% target" in report.lower() or "≥95%" in report
