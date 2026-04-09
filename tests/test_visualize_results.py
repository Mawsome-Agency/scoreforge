#!/usr/bin/env python3
"""Tests for visualize_results.py visualization tool."""
import json
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from visualize_results import (
    FixtureDataPoint,
    FixtureTrend,
    parse_timestamp,
    extract_accuracy_from_comparison,
    extract_accuracy_from_summary,
    calculate_trend,
    render_ascii_chart,
    build_fixture_trend,
    calculate_summary,
    VisualizationSummary,
)


class TestParseTimestamp:
    """Test timestamp parsing from directory names."""
    
    def test_valid_timestamp(self):
        """Parse valid timestamp format."""
        result = parse_timestamp("20260326_113438")
        assert result == datetime(2026, 3, 26, 11, 34, 38)
    
    def test_invalid_timestamp_format(self):
        """Return None for invalid format."""
        result = parse_timestamp("invalid_format")
        assert result is None
    
    def test_partial_timestamp(self):
        """Return None for partial timestamp."""
        result = parse_timestamp("20260326")
        assert result is None
    
    def test_empty_string(self):
        """Handle empty string."""
        result = parse_timestamp("")
        assert result is None


class TestExtractAccuracyFromComparison:
    """Test accuracy extraction from comparison JSON structures."""
    
    def test_extract_from_scores_dict(self):
        """Extract from scores dict with overall key."""
        data = {"scores": {"overall": 87.5, "pitch_accuracy": 90.0}}
        result = extract_accuracy_from_comparison(data)
        assert result == 87.5
    
    def test_extract_missing_scores(self):
        """Return 0.0 when scores dict missing."""
        data = {"other_field": "value"}
        result = extract_accuracy_from_comparison(data)
        assert result == 0.0
    
    def test_extract_none_input(self):
        """Handle None input gracefully."""
        result = extract_accuracy_from_comparison(None)
        assert result == 0.0
    
    def test_extract_empty_dict(self):
        """Handle empty dict."""
        data = {}
        result = extract_accuracy_from_comparison(data)
        assert result == 0.0


class TestExtractAccuracyFromSummary:
    """Test accuracy extraction from summary JSON structures."""
    
    def test_extract_from_best_score(self):
        """Extract from best_score field."""
        data = {"best_score": 92.3}
        result = extract_accuracy_from_summary(data)
        assert result == 92.3
    
    def test_extract_from_overall_accuracy(self):
        """Extract from overall_accuracy field."""
        data = {"overall_accuracy": 88.7}
        result = extract_accuracy_from_summary(data)
        assert result == 88.7
    
    def test_extract_none_input(self):
        """Handle None input gracefully."""
        result = extract_accuracy_from_summary(None)
        assert result == 0.0


class TestCalculateTrend:
    """Test trend calculation from data points."""
    
    def test_improving_trend(self):
        """Detect improving trend (increase > 2%)."""
        data_points = [
            FixtureDataPoint("test", "2026-03-26", 85.0),
            FixtureDataPoint("test", "2026-03-27", 88.0),
            FixtureDataPoint("test", "2026-03-28", 92.0),
        ]
        result = calculate_trend(data_points)
        assert result == "improving"
    
    def test_declining_trend(self):
        """Detect declining trend (decrease > 2%)."""
        data_points = [
            FixtureDataPoint("test", "2026-03-26", 92.0),
            FixtureDataPoint("test", "2026-03-27", 88.0),
            FixtureDataPoint("test", "2026-03-28", 85.0),
        ]
        result = calculate_trend(data_points)
        assert result == "declining"
    
    def test_stable_trend(self):
        """Detect stable trend (change < 2%)."""
        data_points = [
            FixtureDataPoint("test", "2026-03-26", 87.0),
            FixtureDataPoint("test", "2026-03-27", 88.0),
            FixtureDataPoint("test", "2026-03-28", 88.5),
        ]
        result = calculate_trend(data_points)
        assert result == "stable"
    
    def test_insufficient_data(self):
        """Return 'unknown' for insufficient data points."""
        data_points = [FixtureDataPoint("test", "2026-03-26", 85.0)]
        result = calculate_trend(data_points)
        assert result == "unknown"
    
    def test_empty_list(self):
        """Handle empty list."""
        result = calculate_trend([])
        assert result == "unknown"


class TestCalculateSummary:
    """Test summary calculation from trends."""
    
    def test_calculate_summary_with_data(self):
        """Calculate summary with valid trend data."""
        trends = {
            "fixture1": FixtureTrend(
                fixture="fixture1",
                data_points=[
                    FixtureDataPoint("fixture1", "2026-03-26", 95.0),
                ],
                latest_accuracy=95.0,
                best_accuracy=95.0,
                first_accuracy=95.0,
                meets_target=True,
                needs_improvement=False
            ),
            "fixture2": FixtureTrend(
                fixture="fixture2",
                data_points=[
                    FixtureDataPoint("fixture2", "2026-03-26", 85.0),
                ],
                latest_accuracy=85.0,
                best_accuracy=85.0,
                first_accuracy=85.0,
                meets_target=False,
                needs_improvement=True
            ),
        }
        
        result = calculate_summary(trends)
        
        assert result.total_fixtures == 2
        assert result.fixtures_meeting_target == 1
        assert result.fixtures_needing_improvement == 1
        assert result.avg_accuracy == 90.0
        assert result.best_performing_fixture == "fixture1"
        assert result.worst_performing_fixture == "fixture2"
    
    def test_calculate_summary_empty(self):
        """Handle empty trends dict."""
        result = calculate_summary({})
        assert result.total_fixtures == 0
        assert result.fixtures_meeting_target == 0
        assert result.fixtures_needing_improvement == 0
    
    def test_calculate_summary_no_data_points(self):
        """Handle trends without data points."""
        trends = {
            "fixture1": FixtureTrend(fixture="fixture1", needs_improvement=False),
        }
        result = calculate_summary(trends)
        assert result.total_fixtures == 0


class TestRenderAsciiChart:
    """Test ASCII chart rendering."""
    
    def test_chart_with_sufficient_data(self):
        """Generate chart with 2+ data points."""
        data_points = [
            FixtureDataPoint("test", "2026-03-26", 80.0),
            FixtureDataPoint("test", "2026-03-27", 90.0),
            FixtureDataPoint("test", "2026-03-28", 95.0),
        ]
        result = render_ascii_chart(data_points, width=20)
        
        assert isinstance(result, str)
        assert "80.0%" in result
        assert "90.0%" in result
        assert "95.0%" in result
        assert "│" in result or "└" in result
    
    def test_chart_with_insufficient_data(self):
        """Handle case with less than 2 data points."""
        data_points = [FixtureDataPoint("test", "2026-03-26", 85.0)]
        result = render_ascii_chart(data_points)
        assert "insufficient data" in result


class TestFixtureTrendDataclass:
    """Test FixtureTrend dataclass."""
    
    def test_fixture_trend_defaults(self):
        """Verify default values."""
        trend = FixtureTrend(fixture="test_fixture")
        assert trend.fixture == "test_fixture"
        assert trend.data_points == []
        assert trend.latest_accuracy == 0.0
        assert trend.best_accuracy == 0.0
        assert trend.first_accuracy == 0.0
        assert trend.trend == "unknown"
        assert trend.meets_target is False
        assert trend.needs_improvement is True
    
    def test_fixture_trend_with_data(self):
        """Create trend with data."""
        data_point = FixtureDataPoint("test", "2026-03-26", 90.0)
        trend = FixtureTrend(
            fixture="test",
            data_points=[data_point],
            latest_accuracy=90.0,
            best_accuracy=92.0,
            first_accuracy=85.0,
            trend="improving",
            meets_target=False,
            needs_improvement=True
        )
        
        assert len(trend.data_points) == 1
        assert trend.trend == "improving"
        assert trend.meets_target is False



class TestIntegration:
    """Integration tests for the visualization tool."""
    
    def test_build_fixture_trend_from_directory(self):
        """Build trend from fixture directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "test_fixture"
            fixture_path.mkdir()
            
            # Create timestamped run directory
            run_dir = fixture_path / "20260326_113438"
            run_dir.mkdir()
            
            # Create comparison.json
            comparison_data = {"scores": {"overall": 87.5, "pitch_accuracy": 90.0}}
            comparison_file = run_dir / "comparison.json"
            with open(comparison_file, 'w') as f:
                json.dump(comparison_data, f)
            
            # Build trend
            trend = build_fixture_trend("test_fixture", fixture_path)
            
            assert trend.fixture == "test_fixture"
            assert len(trend.data_points) == 1
            assert trend.data_points[0].overall_accuracy == 87.5
            assert trend.latest_accuracy == 87.5
            assert trend.meets_target is False  # 87.5 < 95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
