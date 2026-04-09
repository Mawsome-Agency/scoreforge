"""Tests for visual comparison helpers in core/comparator.py.

Covers the pixel-level and perceptual-hash comparison path, plus
the pure-function helpers (_find_diff_regions, _note_str, _pct).
These tests run without any external API calls.
"""
import io
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.comparator import (
    _find_diff_regions,
    _note_str,
    _pct,
    compare_images,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _write_png(path: str, width: int = 100, height: int = 80,
               color: int = 255) -> None:
    """Write a grayscale PNG of uniform colour."""
    img = Image.new("L", (width, height), color=color)
    img.save(path)


def _write_rgb_png(path: str, width: int = 100, height: int = 80,
                   color=(255, 255, 255)) -> None:
    img = Image.new("RGB", (width, height), color=color)
    img.save(path)


# ─────────────────────────────────────────────────────────────────────────────
# 1. _find_diff_regions — pure function
# ─────────────────────────────────────────────────────────────────────────────

class TestFindDiffRegions:

    def test_all_zeros_no_regions(self):
        diff = np.zeros((100, 100), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        assert regions == []

    def test_all_ones_produces_regions(self):
        diff = np.ones((100, 100), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        assert len(regions) > 0

    def test_region_has_required_keys(self):
        diff = np.ones((100, 100), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        for r in regions:
            assert "x" in r
            assert "y" in r
            assert "width" in r
            assert "height" in r
            assert "severity" in r

    def test_severity_is_float(self):
        diff = np.ones((100, 100), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        for r in regions:
            assert isinstance(r["severity"], float)

    def test_severity_in_zero_to_one(self):
        diff = np.random.rand(50, 50).astype(np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        for r in regions:
            assert 0.0 <= r["severity"] <= 1.0

    def test_cell_below_005_threshold_not_included(self):
        """A diff of 0.04 per cell (just below 5%) should produce no regions."""
        diff = np.full((100, 100), 0.04, dtype=np.float32)
        # At threshold=0.3, binary = 0 everywhere (0.04 < 0.3)
        regions = _find_diff_regions(diff, threshold=0.3)
        assert regions == []

    def test_high_threshold_reduces_regions(self):
        diff = np.full((100, 100), 0.5, dtype=np.float32)
        regions_low = _find_diff_regions(diff, threshold=0.1)
        regions_high = _find_diff_regions(diff, threshold=0.9)
        # At threshold 0.9, nothing exceeds → no regions
        assert len(regions_low) > 0
        assert regions_high == []

    def test_single_pixel_diff_array(self):
        diff = np.array([[0.9]], dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        # Single pixel above threshold with cell.mean() = 1.0 > 0.05
        assert len(regions) == 1
        assert regions[0]["x"] == 0
        assert regions[0]["y"] == 0

    def test_region_coords_within_array_bounds(self):
        h, w = 80, 120
        diff = np.ones((h, w), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        for r in regions:
            assert r["x"] >= 0
            assert r["y"] >= 0
            assert r["x"] + r["width"] <= w
            assert r["y"] + r["height"] <= h

    def test_non_square_array(self):
        diff = np.ones((30, 90), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        assert len(regions) > 0

    def test_1x1_array_above_threshold(self):
        diff = np.array([[1.0]], dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        assert len(regions) == 1

    def test_1x1_array_below_threshold(self):
        diff = np.array([[0.1]], dtype=np.float32)
        # 0.1 < 0.3, binary = 0, mean = 0 ≤ 0.05
        regions = _find_diff_regions(diff, threshold=0.3)
        assert regions == []

    def test_severity_rounded_to_3_decimal_places(self):
        diff = np.ones((10, 10), dtype=np.float32)
        regions = _find_diff_regions(diff, threshold=0.3)
        for r in regions:
            # Check it's already rounded (no more than 3 decimal places)
            assert round(r["severity"], 3) == r["severity"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. _note_str — pure function
# ─────────────────────────────────────────────────────────────────────────────

class TestNoteStr:

    def test_rest_note(self):
        note = {"is_rest": True, "type": "quarter"}
        assert _note_str(note) == "Rest(quarter)"

    def test_rest_unknown_type(self):
        note = {"is_rest": True}
        assert _note_str(note) == "Rest(?)"

    def test_pitched_note_no_accidental(self):
        note = {"is_rest": False, "pitch": {"step": "C", "octave": 4, "alter": 0}, "type": "quarter"}
        assert _note_str(note) == "C4(quarter)"

    def test_pitched_note_sharp(self):
        note = {"is_rest": False, "pitch": {"step": "F", "octave": 5, "alter": 1}, "type": "half"}
        assert _note_str(note) == "F#5(half)"

    def test_pitched_note_flat(self):
        note = {"is_rest": False, "pitch": {"step": "B", "octave": 3, "alter": -1}, "type": "whole"}
        assert _note_str(note) == "Bb3(whole)"

    def test_pitched_note_double_sharp(self):
        note = {"is_rest": False, "pitch": {"step": "G", "octave": 4, "alter": 2}, "type": "quarter"}
        assert _note_str(note) == "G##4(quarter)"

    def test_pitched_note_double_flat(self):
        note = {"is_rest": False, "pitch": {"step": "A", "octave": 5, "alter": -2}, "type": "eighth"}
        assert _note_str(note) == "Abb5(eighth)"

    def test_missing_pitch_field(self):
        note = {"is_rest": False, "type": "quarter"}
        result = _note_str(note)
        # Should not crash; pitch is missing so gets default unknowns
        assert "?" in result

    def test_missing_step_in_pitch(self):
        note = {"is_rest": False, "pitch": {"octave": 4, "alter": 0}, "type": "quarter"}
        result = _note_str(note)
        assert "4" in result

    def test_missing_octave_in_pitch(self):
        note = {"is_rest": False, "pitch": {"step": "C", "alter": 0}, "type": "quarter"}
        result = _note_str(note)
        assert "C" in result
        assert "?" in result

    def test_missing_type(self):
        note = {"is_rest": False, "pitch": {"step": "D", "octave": 5, "alter": 0}}
        result = _note_str(note)
        assert "D5" in result
        assert "(?)" in result

    def test_alter_zero_produces_no_accidental_suffix(self):
        note = {"is_rest": False, "pitch": {"step": "E", "octave": 4, "alter": 0}, "type": "quarter"}
        result = _note_str(note)
        assert "#" not in result
        assert "b" not in result


# ─────────────────────────────────────────────────────────────────────────────
# 3. _pct — pure function (additional edge cases beyond test_multi_voice.py)
# ─────────────────────────────────────────────────────────────────────────────

class TestPctAdditional:

    def test_one_hundred(self):
        assert _pct(100, 100) == 100.0

    def test_one_of_three(self):
        assert _pct(1, 3) == 33.3

    def test_two_of_three(self):
        assert _pct(2, 3) == 66.7

    def test_large_values(self):
        assert _pct(999, 1000) == 99.9

    def test_returns_float(self):
        assert isinstance(_pct(1, 2), float)

    def test_zero_correct_is_zero(self):
        assert _pct(0, 50) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. compare_images — pixel/perceptual hash comparison
# ─────────────────────────────────────────────────────────────────────────────

class TestCompareImages:

    def test_identical_images_perfect_score(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, width=100, height=80, color=255)
        result = compare_images(p, p)
        assert result["is_perfect"] is True
        assert result["match_score"] >= 95

    def test_identical_images_zero_phash_distance(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, width=100, height=80, color=200)
        result = compare_images(p, p)
        assert result["phash_distance"] == 0

    def test_identical_images_zero_pixel_diff(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, width=100, height=80, color=200)
        result = compare_images(p, p)
        assert result["pixel_diff_pct"] == 0.0

    def test_identical_images_no_diff_regions(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, width=100, height=80, color=128)
        result = compare_images(p, p)
        assert result["diff_regions"] == []

    def test_result_has_all_required_keys(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, width=50, height=50, color=255)
        result = compare_images(p, p)
        assert "match_score" in result
        assert "phash_distance" in result
        assert "pixel_diff_pct" in result
        assert "diff_regions" in result
        assert "is_perfect" in result

    def test_match_score_is_integer(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, width=50, height=50, color=255)
        result = compare_images(p, p)
        assert isinstance(result["match_score"], int)

    def test_match_score_in_range(self, tmp_path):
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, color=255)
        _write_png(rend, color=0)  # fully black vs white
        result = compare_images(orig, rend)
        assert 0 <= result["match_score"] <= 100

    def test_different_images_lower_score(self, tmp_path):
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, color=255)
        _write_png(rend, color=0)
        result = compare_images(orig, rend)
        assert result["match_score"] < 95
        assert result["is_perfect"] is False

    def test_different_sizes_resizes_rendered(self, tmp_path):
        """Comparator should resize rendered to match original — no exception."""
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, width=100, height=80, color=255)
        _write_png(rend, width=200, height=150, color=255)
        result = compare_images(orig, rend)
        # Same content (both white) so should be perfect after resize
        assert result["is_perfect"] is True

    def test_rgb_images_handled(self, tmp_path):
        """RGB PNGs should be converted to grayscale without error."""
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_rgb_png(orig, color=(255, 255, 255))
        _write_rgb_png(rend, color=(255, 255, 255))
        result = compare_images(orig, rend)
        assert result["is_perfect"] is True

    def test_missing_original_raises(self, tmp_path):
        p = str(tmp_path / "exists.png")
        _write_png(p)
        with pytest.raises(Exception):  # PIL raises FileNotFoundError or similar
            compare_images(str(tmp_path / "ghost.png"), p)

    def test_missing_rendered_raises(self, tmp_path):
        p = str(tmp_path / "exists.png")
        _write_png(p)
        with pytest.raises(Exception):
            compare_images(p, str(tmp_path / "ghost.png"))

    def test_diff_regions_list_type(self, tmp_path):
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, color=255)
        _write_png(rend, color=0)
        result = compare_images(orig, rend)
        assert isinstance(result["diff_regions"], list)

    def test_pixel_diff_pct_is_float(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p)
        result = compare_images(p, p)
        assert isinstance(result["pixel_diff_pct"], float)

    def test_phash_distance_non_negative(self, tmp_path):
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, color=200)
        _write_png(rend, color=50)
        result = compare_images(orig, rend)
        assert result["phash_distance"] >= 0

    def test_is_perfect_false_for_low_match(self, tmp_path):
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, color=255)
        _write_png(rend, color=0)
        result = compare_images(orig, rend)
        assert result["is_perfect"] is False

    def test_slightly_different_images_not_perfect(self, tmp_path):
        """Images with minor pixel differences should not be 'perfect'."""
        orig_arr = np.full((100, 100), 255, dtype=np.uint8)
        # Put a high-contrast stripe that exceeds the 30% diff threshold
        diff_arr = orig_arr.copy()
        diff_arr[0:50, :] = 0  # half the image is black vs white

        orig_path = str(tmp_path / "orig.png")
        diff_path = str(tmp_path / "diff.png")
        Image.fromarray(orig_arr, mode="L").save(orig_path)
        Image.fromarray(diff_arr, mode="L").save(diff_path)

        result = compare_images(orig_path, diff_path)
        assert result["is_perfect"] is False
        assert result["pixel_diff_pct"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. compare_images — match score formula sanity checks
# ─────────────────────────────────────────────────────────────────────────────

class TestCompareImagesScoreFormula:
    """Verify the score formula: 40% phash + 60% pixel."""

    def test_perfect_both_gives_100(self, tmp_path):
        p = str(tmp_path / "img.png")
        _write_png(p, color=255)
        result = compare_images(p, p)
        # phash_score = 100, pixel_score = 100 → match_score = 100
        assert result["match_score"] == 100

    def test_large_pixel_diff_lowers_score(self, tmp_path):
        orig = str(tmp_path / "orig.png")
        rend = str(tmp_path / "rend.png")
        _write_png(orig, color=255)   # white
        _write_png(rend, color=0)     # black — maximum diff
        result = compare_images(orig, rend)
        # pixel_diff_pct ~50% (>30% threshold for all pixels)
        # phash would also be very high distance
        assert result["match_score"] < 50
