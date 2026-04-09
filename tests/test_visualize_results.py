#!/usr/bin/env python3
"""
Comprehensive tests for visualize_results.py.

Tests cover:
- Happy paths: all main functions with valid data
- Edge cases: empty data, missing files, malformed JSON
- Error handling: file not found, invalid data types
- Boundary conditions: single data point, max values
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from visualize_results import (
    AccuracyMetric,
    FixtureData,
    ResultReader,
    TrendAnalyzer,
    AsciiChart,
    HtmlReport,
    Visualizer,
    Colors,
)


# ==================== Fixtures ====================

@pytest.fixture
def sample_comparison_json():
    """Sample comparison.json content."""
    return {
        "scores": {
            "overall": 87.5,
            "pitch_accuracy": 92.3,
            "rhythm_accuracy": 95.0,
            "note_accuracy": 88.1,
            "measure_accuracy": 91.2,
        },
        "total_notes_gt": 100,
        "total_notes_matched": 87,
    }


@pytest.fixture
def sample_metric():
    """Sample AccuracyMetric."""
    return AccuracyMetric(
        timestamp="20260409_120000",
        overall_accuracy=87.5,
        pitch_accuracy=92.3,
        rhythm_accuracy=95.0,
        note_accuracy=88.1,
        measure_accuracy=91.2,
    )


@pytest.fixture
def sample_fixture_data():
    """Sample FixtureData with multiple metrics."""
    metrics = [
        AccuracyMetric("20260401_100000", 80.0, 85.0, 90.0, 82.0, 88.0),
        AccuracyMetric("20260402_100000", 85.0, 87.0, 92.0, 84.0, 90.0),
        AccuracyMetric("20260403_100000", 87.5, 90.0, 95.0, 86.0, 91.0),
    ]
    return FixtureData(
        name="test_fixture",
        metrics=metrics,
        latest_accuracy=87.5,
        trend="improving",
    )


@pytest.fixture
def temp_results_dir():
    """Create temporary results directory with sample data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir) / "results"
        results_dir.mkdir()

        # Create fixture with multiple timestamped runs
        fixture_dir = results_dir / "fixture_1"
        fixture_dir.mkdir()

        for i, accuracy in enumerate([80.0, 85.0, 87.5]):
            timestamp_dir = fixture_dir / f"2026040{i+1}_120000"
            timestamp_dir.mkdir()
            comparison_data = {
                "scores": {
                    "overall": accuracy,
                    "pitch_accuracy": accuracy + 5,
                    "rhythm_accuracy": accuracy + 8,
                    "note_accuracy": accuracy + 2,
                    "measure_accuracy": accuracy + 4,
                }
            }
            with open(timestamp_dir / "comparison.json", "w") as f:
                json.dump(comparison_data, f)

        # Create fixture below target
        fixture_dir_2 = results_dir / "fixture_2"
        fixture_dir_2.mkdir()
        timestamp_dir_2 = fixture_dir_2 / "20260401_120000"
        timestamp_dir_2.mkdir()
        comparison_data_2 = {
            "scores": {
                "overall": 65.0,
                "pitch_accuracy": 70.0,
                "rhythm_accuracy": 75.0,
                "note_accuracy": 68.0,
                "measure_accuracy": 72.0,
            }
        }
        with open(timestamp_dir_2 / "comparison.json", "w") as f:
            json.dump(comparison_data_2, f)

        # Create fixture above target
        fixture_dir_3 = results_dir / "fixture_3"
        fixture_dir_3.mkdir()
        timestamp_dir_3 = fixture_dir_3 / "20260401_120000"
        timestamp_dir_3.mkdir()
        comparison_data_3 = {
            "scores": {
                "overall": 98.5,
                "pitch_accuracy": 99.0,
                "rhythm_accuracy": 99.5,
                "note_accuracy": 98.0,
                "measure_accuracy": 99.0,
            }
        }
        with open(timestamp_dir_3 / "comparison.json", "w") as f:
            json.dump(comparison_data_3, f)

        yield results_dir


# ==================== AccuracyMetric Tests ====================

class TestAccuracyMetric:
    """Tests for AccuracyMetric dataclass."""

    def test_create_metric(self, sample_metric):
        """Test creating an AccuracyMetric with valid data."""
        assert sample_metric.timestamp == "20260409_120000"
        assert sample_metric.overall_accuracy == 87.5
        assert sample_metric.pitch_accuracy == 92.3
        assert sample_metric.rhythm_accuracy == 95.0
        assert sample_metric.note_accuracy == 88.1
        assert sample_metric.measure_accuracy == 91.2

    def test_create_metric_with_zero_accuracy(self):
        """Test creating metric with zero accuracy."""
        metric = AccuracyMetric("20260409_120000", 0.0, 0.0, 0.0, 0.0, 0.0)
        assert metric.overall_accuracy == 0.0
        assert metric.pitch_accuracy == 0.0

    def test_create_metric_with_max_accuracy(self):
        """Test creating metric with 100% accuracy."""
        metric = AccuracyMetric("20260409_120000", 100.0, 100.0, 100.0, 100.0, 100.0)
        assert metric.overall_accuracy == 100.0

    def test_create_metric_with_float_accuracy(self):
        """Test creating metric with floating point accuracy."""
        metric = AccuracyMetric("20260409_120000", 87.53, 92.37, 95.01, 88.19, 91.24)
        assert metric.overall_accuracy == 87.53
        assert metric.pitch_accuracy == 92.37


# ==================== FixtureData Tests ====================

class TestFixtureData:
    """Tests for FixtureData dataclass."""

    def test_create_fixture_data(self):
        """Test creating FixtureData."""
        metrics = [AccuracyMetric("20260409_120000", 87.5, 92.3, 95.0, 88.1, 91.2)]
        data = FixtureData("test_fixture", metrics, 87.5, "improving")
        assert data.name == "test_fixture"
        assert len(data.metrics) == 1
        assert data.latest_accuracy == 87.5
        assert data.trend == "improving"

    def test_empty_metrics_list(self):
        """Test FixtureData with empty metrics list."""
        data = FixtureData("empty_fixture", [], 0.0, "stable")
        assert data.metrics == []
        assert data.latest_accuracy == 0.0

    def test_trend_values(self):
        """Test all valid trend values."""
        trends = ["improving", "declining", "stable"]
        for trend in trends:
            data = FixtureData("fixture", [], 0.0, trend)
            assert data.trend == trend


# ==================== ResultReader Tests ====================

class TestResultReader:
    """Tests for ResultReader."""

    def test_read_result_existing_file(self, temp_results_dir):
        """Test reading an existing result file."""
        comparison_path = temp_results_dir / "fixture_1" / "20260401_120000" / "comparison.json"
        result = ResultReader.read_result(comparison_path)
        assert result is not None
        assert "scores" in result

    def test_read_result_nonexistent_file(self):
        """Test reading a non-existent file."""
        result = ResultReader.read_result(Path("/nonexistent/file.json"))
        assert result is None

    def test_read_result_malformed_json(self, tmp_path):
        """Test reading a malformed JSON file."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json")
        result = ResultReader.read_result(bad_file)
        assert result is None

    def test_parse_comparison_json_valid(self, sample_comparison_json):
        """Test parsing valid comparison JSON."""
        metric = ResultReader.parse_comparison_json(sample_comparison_json, "20260409_120000")
        assert metric is not None
        assert metric.overall_accuracy == 87.5
        assert metric.pitch_accuracy == 92.3
        assert metric.rhythm_accuracy == 95.0

    def test_parse_comparison_json_missing_scores(self):
        """Test parsing comparison JSON with missing scores."""
        metric = ResultReader.parse_comparison_json({}, "20260409_120000")
        assert metric is None

    def test_parse_comparison_json_empty_scores(self):
        """Test parsing comparison JSON with empty scores."""
        metric = ResultReader.parse_comparison_json({"scores": {}}, "20260409_120000")
        assert metric is None

    def test_parse_comparison_json_partial_scores(self):
        """Test parsing comparison JSON with partial scores."""
        data = {"scores": {"overall": 87.5}}
        metric = ResultReader.parse_comparison_json(data, "20260409_120000")
        assert metric is not None
        assert metric.overall_accuracy == 87.5
        assert metric.pitch_accuracy == 0.0

    def test_discover_fixture_results(self, temp_results_dir):
        """Test discovering fixture results."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = ResultReader.discover_fixture_results()
            assert len(fixtures) == 3
            assert "fixture_1" in fixtures
            assert "fixture_2" in fixtures
            assert "fixture_3" in fixtures
            assert len(fixtures["fixture_1"]) == 3  # Three runs
            assert len(fixtures["fixture_2"]) == 1

    def test_discover_fixture_results_no_directory(self):
        """Test discovering results when directory doesn't exist."""
        with patch.object(ResultReader, 'RESULT_DIR', Path("/nonexistent")):
            fixtures = ResultReader.discover_fixture_results()
            assert fixtures == {}

    def test_discover_fixture_results_empty_directory(self, tmp_path):
        """Test discovering results from empty directory."""
        with patch.object(ResultReader, 'RESULT_DIR', tmp_path):
            fixtures = ResultReader.discover_fixture_results()
            assert fixtures == {}

    def test_discover_fixture_results_sorts_by_timestamp(self, temp_results_dir):
        """Test that fixtures are sorted by timestamp."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = ResultReader.discover_fixture_results()
            timestamps = [t[0] for t in fixtures["fixture_1"]]
            assert timestamps == ["20260401_120000", "20260402_120000", "20260403_120000"]


# ==================== TrendAnalyzer Tests ====================

class TestTrendAnalyzer:
    """Tests for TrendAnalyzer."""

    def test_calculate_trend_improving(self):
        """Test trend calculation for improving metrics."""
        metrics = [
            AccuracyMetric("20260401", 80.0, 85.0, 90.0, 82.0, 88.0),
            AccuracyMetric("20260402", 85.0, 87.0, 92.0, 84.0, 90.0),
            AccuracyMetric("20260403", 90.0, 90.0, 95.0, 86.0, 91.0),
        ]
        trend = TrendAnalyzer.calculate_trend(metrics)
        assert trend == "improving"

    def test_calculate_trend_declining(self):
        """Test trend calculation for declining metrics."""
        metrics = [
            AccuracyMetric("20260401", 90.0, 90.0, 95.0, 86.0, 91.0),
            AccuracyMetric("20260402", 85.0, 87.0, 92.0, 84.0, 90.0),
            AccuracyMetric("20260403", 80.0, 85.0, 90.0, 82.0, 88.0),
        ]
        trend = TrendAnalyzer.calculate_trend(metrics)
        assert trend == "declining"

    def test_calculate_trend_stable(self):
        """Test trend calculation for stable metrics."""
        metrics = [
            AccuracyMetric("20260401", 85.0, 87.0, 92.0, 84.0, 90.0),
            AccuracyMetric("20260402", 85.5, 87.5, 92.0, 84.0, 90.0),
            AccuracyMetric("20260403", 85.0, 87.0, 92.0, 84.0, 90.0),
        ]
        trend = TrendAnalyzer.calculate_trend(metrics)
        assert trend == "stable"

    def test_calculate_trend_single_metric(self):
        """Test trend calculation with single metric."""
        metrics = [AccuracyMetric("20260401", 85.0, 87.0, 92.0, 84.0, 90.0)]
        trend = TrendAnalyzer.calculate_trend(metrics)
        assert trend == "stable"

    def test_calculate_trend_empty_list(self):
        """Test trend calculation with empty list."""
        trend = TrendAnalyzer.calculate_trend([])
        assert trend == "stable"

    def test_target_accuracy_constant(self):
        """Test that TARGET_ACCURACY is set correctly."""
        assert TrendAnalyzer.TARGET_ACCURACY == 95.0


# ==================== AsciiChart Tests ====================

class TestAsciiChart:
    """Tests for AsciiChart."""

    def test_draw_chart_with_data(self):
        """Test drawing chart with valid data."""
        metrics = [
            AccuracyMetric("20260401", 80.0, 85.0, 90.0, 82.0, 88.0),
            AccuracyMetric("20260402", 85.0, 87.0, 92.0, 84.0, 90.0),
            AccuracyMetric("20260403", 90.0, 90.0, 95.0, 86.0, 91.0),
        ]
        chart = AsciiChart.draw_chart(metrics, "Test Chart")
        assert "Test Chart" in chart
        assert "*" in chart  # Data points
        assert "%" in chart  # Percentages

    def test_draw_chart_empty_metrics(self):
        """Test drawing chart with empty metrics."""
        chart = AsciiChart.draw_chart([], "Empty Chart")
        assert "No data available" in chart

    def test_draw_chart_single_metric(self):
        """Test drawing chart with single metric."""
        metrics = [AccuracyMetric("20260401", 85.0, 87.0, 92.0, 84.0, 90.0)]
        chart = AsciiChart.draw_chart(metrics, "Single Point")
        assert "Single Point" in chart

    def test_draw_chart_includes_target_line(self):
        """Test that target line is included when within range."""
        metrics = [
            AccuracyMetric("20260401", 80.0, 85.0, 90.0, 82.0, 88.0),
            AccuracyMetric("20260402", 100.0, 100.0, 100.0, 100.0, 100.0),
        ]
        chart = AsciiChart.draw_chart(metrics, "Target Test")
        assert "=" in chart  # Target line

    def test_chart_width_constant(self):
        """Test that chart width is set correctly."""
        assert AsciiChart.WIDTH == 50

    def test_chart_height_constant(self):
        """Test that chart height is set correctly."""
        assert AsciiChart.HEIGHT == 10

    def test_draw_chart_with_all_same_values(self):
        """Test drawing chart when all values are the same."""
        metrics = [
            AccuracyMetric("20260401", 85.0, 87.0, 92.0, 84.0, 90.0),
            AccuracyMetric("20260402", 85.0, 87.0, 92.0, 84.0, 90.0),
            AccuracyMetric("20260403", 85.0, 87.0, 92.0, 84.0, 90.0),
        ]
        chart = AsciiChart.draw_chart(metrics, "Same Values")
        assert "Same Values" in chart


# ==================== HtmlReport Tests ====================

class TestHtmlReport:
    """Tests for HtmlReport."""

    def test_generate_html_with_fixtures(self, sample_fixture_data):
        """Test generating HTML report with fixtures."""
        fixtures = {"fixture_1": sample_fixture_data}
        html = HtmlReport.generate(fixtures)
        assert "<!DOCTYPE html>" in html
        assert "ScoreForge Test Results Visualization" in html
        assert "fixture_1" in html
        assert "87.5%" in html

    def test_generate_html_empty_fixtures(self):
        """Test generating HTML report with no fixtures."""
        html = HtmlReport.generate({})
        assert "<!DOCTYPE html>" in html
        assert "Total Fixtures" in html

    def test_generate_html_includes_summary(self, sample_fixture_data):
        """Test that HTML includes summary cards."""
        fixtures = {"fixture_1": sample_fixture_data}
        html = HtmlReport.generate(fixtures)
        assert "Total Fixtures" in html
        assert "Meeting 95% Goal" in html
        assert "Average Accuracy" in html

    def test_generate_html_includes_table(self, sample_fixture_data):
        """Test that HTML includes fixture table."""
        fixtures = {"fixture_1": sample_fixture_data}
        html = HtmlReport.generate(fixtures)
        assert "<table>" in html
        assert "<th>Fixture</th>" in html
        assert "<th>Latest Accuracy</th>" in html
        assert "<th>Trend</th>" in html

    def test_generate_html_includes_needs_improvement(self, sample_fixture_data):
        """Test that HTML includes needs improvement section."""
        fixtures = {"fixture_1": sample_fixture_data}
        html = HtmlReport.generate(fixtures)
        assert "Fixtures Needing Improvement" in html

    def test_generate_html_all_fixtures_pass(self):
        """Test HTML when all fixtures meet target."""
        metrics = [AccuracyMetric("20260401", 98.0, 99.0, 99.5, 98.0, 99.0)]
        data = FixtureData("passing", metrics, 98.0, "stable")
        fixtures = {"passing": data}
        html = HtmlReport.generate(fixtures)
        assert "All fixtures meet the 95% accuracy goal!" in html

    def test_generate_html_with_status_classes(self, sample_fixture_data):
        """Test that HTML includes proper status CSS classes."""
        fixtures = {"fixture_1": sample_fixture_data}
        html = HtmlReport.generate(fixtures)
        assert "metric-card" in html
        assert "pass" in html or "fail" in html

    def test_generate_html_with_trend_icons(self, sample_fixture_data):
        """Test that HTML includes trend icons."""
        fixtures = {"fixture_1": sample_fixture_data}
        html = HtmlReport.generate(fixtures)
        assert "↑" in html or "↓" in html or "→" in html


# ==================== Visualizer Tests ====================

class TestVisualizer:
    """Tests for Visualizer."""

    def test_load_fixture_data(self, temp_results_dir):
        """Test loading fixture data from results directory."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            assert len(fixtures) == 3
            assert "fixture_1" in fixtures
            assert "fixture_2" in fixtures
            assert "fixture_3" in fixtures

    def test_load_fixture_data_empty_directory(self, tmp_path):
        """Test loading data from empty directory."""
        with patch.object(ResultReader, 'RESULT_DIR', tmp_path):
            fixtures = Visualizer.load_fixture_data()
            assert fixtures == {}

    def test_load_fixture_data_calculates_latest_accuracy(self, temp_results_dir):
        """Test that latest accuracy is calculated correctly."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            assert fixtures["fixture_1"].latest_accuracy == 87.5
            assert fixtures["fixture_2"].latest_accuracy == 65.0
            assert fixtures["fixture_3"].latest_accuracy == 98.5

    def test_load_fixture_data_calculates_trends(self, temp_results_dir):
        """Test that trends are calculated correctly."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            assert fixtures["fixture_1"].trend == "improving"

    def test_print_ascii_report_empty_fixtures(self, capsys):
        """Test printing ASCII report with no fixtures."""
        Visualizer.print_ascii_report({})
        captured = capsys.readouterr()
        assert "No test results found" in captured.out

    def test_print_ascii_report_with_fixtures(self, temp_results_dir, capsys):
        """Test printing ASCII report with fixtures."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            Visualizer.print_ascii_report(fixtures)
            captured = capsys.readouterr()
            assert "ScoreForge Test Results Visualization" in captured.out
            assert "Total Fixtures: 3" in captured.out

    def test_print_ascii_report_shows_top_performers(self, temp_results_dir, capsys):
        """Test that ASCII report shows top performers."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            Visualizer.print_ascii_report(fixtures)
            captured = capsys.readouterr()
            assert "Top Performers" in captured.out
            assert "fixture_3" in captured.out  # Has highest accuracy

    def test_print_ascii_report_shows_needs_improvement(self, temp_results_dir, capsys):
        """Test that ASCII report shows fixtures needing improvement."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            Visualizer.print_ascii_report(fixtures)
            captured = capsys.readouterr()
            assert "Needs Improvement" in captured.out
            assert "fixture_2" in captured.out  # Below target

    def test_generate_html_report(self, temp_results_dir, tmp_path):
        """Test generating HTML report to file."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            output_path = tmp_path / "test_report.html"
            Visualizer.generate_html_report(fixtures, output_path)
            assert output_path.exists()

    def test_generate_html_report_creates_directory(self, tmp_path):
        """Test that HTML generation creates output directory."""
        output_path = tmp_path / "subdir" / "report.html"
        fixtures = {}
        Visualizer.generate_html_report(fixtures, output_path)
        assert output_path.exists()

    def test_generate_html_report_content(self, temp_results_dir, tmp_path):
        """Test that generated HTML has correct content."""
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()
            output_path = tmp_path / "test_report.html"
            Visualizer.generate_html_report(fixtures, output_path)
            with open(output_path, "r") as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "ScoreForge Test Results Visualization" in content


# ==================== Colors Tests ====================

class TestColors:
    """Tests for ANSI color codes."""

    def test_color_constants_defined(self):
        """Test that all color constants are defined."""
        assert hasattr(Colors, 'RESET')
        assert hasattr(Colors, 'GREEN')
        assert hasattr(Colors, 'RED')
        assert hasattr(Colors, 'YELLOW')
        assert hasattr(Colors, 'BLUE')
        assert hasattr(Colors, 'MAGENTA')
        assert hasattr(Colors, 'CYAN')

    def test_color_values_are_strings(self):
        """Test that color values are strings."""
        assert isinstance(Colors.RESET, str)
        assert isinstance(Colors.GREEN, str)
        assert isinstance(Colors.RED, str)

    def test_color_values_contain_escape_sequence(self):
        """Test that color values contain ANSI escape sequences."""
        assert Colors.RESET.startswith("\033")
        assert Colors.GREEN.startswith("\033")
        assert Colors.RED.startswith("\033")


# ==================== Edge Case Tests ====================

class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_metric_with_negative_accuracy(self):
        """Test handling of negative accuracy (invalid but should not crash)."""
        metric = AccuracyMetric("20260409", -5.0, -5.0, -5.0, -5.0, -5.0)
        assert metric.overall_accuracy == -5.0

    def test_metric_with_accuracy_above_100(self):
        """Test handling of accuracy above 100% (invalid but should not crash)."""
        metric = AccuracyMetric("20260409", 150.0, 150.0, 150.0, 150.0, 150.0)
        assert metric.overall_accuracy == 150.0

    def test_metric_with_very_long_timestamp(self):
        """Test handling of very long timestamp."""
        long_timestamp = "a" * 1000
        metric = AccuracyMetric(long_timestamp, 85.0, 87.0, 92.0, 84.0, 90.0)
        assert metric.timestamp == long_timestamp

    def test_fixture_data_with_many_metrics(self):
        """Test fixture data with many metrics."""
        metrics = [
            AccuracyMetric(f"2026040{i:02d}_120000", 80.0 + i, 85.0 + i, 90.0 + i, 82.0 + i, 88.0 + i)
            for i in range(100)
        ]
        data = FixtureData("many_metrics", metrics, 100.0, "improving")
        assert len(data.metrics) == 100

    def test_parse_comparison_json_with_nested_structure(self):
        """Test parsing comparison with deeply nested structure."""
        data = {
            "scores": {
                "overall": 87.5,
                "nested": {
                    "deep": {
                        "value": 100.0
                    }
                }
            }
        }
        metric = ResultReader.parse_comparison_json(data, "20260409")
        assert metric is not None
        assert metric.overall_accuracy == 87.5

    def test_read_result_with_permission_denied(self, tmp_path):
        """Test reading file with permission denied."""
        file_path = tmp_path / "no_permission.json"
        file_path.write_text("{}")
        file_path.chmod(0o000)
        result = ResultReader.read_result(file_path)
        # Result should be None due to IOError
        file_path.chmod(0o644)  # Restore permissions for cleanup
        assert result is None

    def test_discover_fixture_with_subdirectories_only(self, tmp_path):
        """Test discovering fixtures with only subdirectories."""
        with patch.object(ResultReader, 'RESULT_DIR', tmp_path):
            fixtures = ResultReader.discover_fixture_results()
            assert fixtures == {}

    def test_generate_html_with_unicode_characters(self):
        """Test HTML generation with unicode in fixture names."""
        metrics = [AccuracyMetric("20260401", 85.0, 87.0, 92.0, 84.0, 90.0)]
        data = FixtureData("fixture_αβγ", metrics, 85.0, "stable")
        fixtures = {"fixture_αβγ": data}
        html = HtmlReport.generate(fixtures)
        assert "fixture_αβγ" in html

    def test_calculate_trend_with_large_numbers(self):
        """Test trend calculation with large accuracy values."""
        metrics = [
            AccuracyMetric("20260401", 1000.0, 1005.0, 1010.0, 1002.0, 1008.0),
            AccuracyMetric("20260402", 2000.0, 2005.0, 2010.0, 2002.0, 2008.0),
        ]
        trend = TrendAnalyzer.calculate_trend(metrics)
        assert trend == "improving"

    def test_calculate_trend_with_very_small_differences(self):
        """Test trend calculation with very small differences."""
        metrics = [
            AccuracyMetric("20260401", 85.001, 87.001, 92.001, 84.001, 90.001),
            AccuracyMetric("20260402", 85.002, 87.002, 92.002, 84.002, 90.002),
            AccuracyMetric("20260403", 85.003, 87.003, 92.003, 84.003, 90.003),
        ]
        trend = TrendAnalyzer.calculate_trend(metrics)
        assert trend == "stable"  # Differences too small


# ==================== Integration Tests ====================

class TestIntegration:
    """Integration tests for the complete workflow."""

    def test_full_workflow(self, temp_results_dir, tmp_path, capsys):
        """Test complete workflow from loading to reporting."""
        # Load data
        with patch.object(ResultReader, 'RESULT_DIR', temp_results_dir):
            fixtures = Visualizer.load_fixture_data()

        # Generate ASCII report
        Visualizer.print_ascii_report(fixtures)
        ascii_output = capsys.readouterr().out

        # Generate HTML report
        output_path = tmp_path / "integration_report.html"
        Visualizer.generate_html_report(fixtures, output_path)

        # Verify ASCII output
        assert "ScoreForge Test Results Visualization" in ascii_output
        assert "Total Fixtures: 3" in ascii_output

        # Verify HTML file exists
        assert output_path.exists()

        # Verify HTML content
        with open(output_path, "r") as f:
            html_content = f.read()
        assert "<!DOCTYPE html>" in html_content
        assert "fixture_1" in html_content

    def test_workflow_with_no_results(self, tmp_path, capsys):
        """Test workflow when no results exist."""
        fixtures = {}

        Visualizer.print_ascii_report(fixtures)
        ascii_output = capsys.readouterr().out

        output_path = tmp_path / "no_results.html"
        Visualizer.generate_html_report(fixtures, output_path)

        assert "No test results found" in ascii_output
        assert output_path.exists()

    def test_workflow_with_single_result(self, tmp_path, capsys):
        """Test workflow with single result."""
        metrics = [AccuracyMetric("20260401_120000", 85.0, 87.0, 92.0, 84.0, 90.0)]
        fixtures = {
            "single_fixture": FixtureData("single_fixture", metrics, 85.0, "stable")
        }

        Visualizer.print_ascii_report(fixtures)
        ascii_output = capsys.readouterr().out

        output_path = tmp_path / "single_result.html"
        Visualizer.generate_html_report(fixtures, output_path)

        assert "single_fixture" in ascii_output
        assert output_path.exists()
