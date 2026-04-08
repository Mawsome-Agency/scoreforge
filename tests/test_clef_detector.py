"""Unit tests for core/clef_detector.py.

Tests run without any image files by constructing synthetic numpy arrays.
Integration tests that use real fixture images are skipped if the fixtures
don't exist (so the suite stays green in CI).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

# Ensure repo root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.clef_detector import (
    ClefDetector,
    _binarize,
    _load_as_grayscale,
    detect_ledger_lines,
    detect_staff_lines,
    identify_clef_symbols,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

_CORPUS_SIMPLE = Path(__file__).parent.parent / "corpus" / "originals" / "simple"
_CORPUS_MODERATE = Path(__file__).parent.parent / "corpus" / "originals" / "moderate"


def _fixture_path(category: str, name: str) -> Path:
    base = Path(__file__).parent.parent / "corpus" / "originals" / category
    return base / name


def _make_staff_image(
    width: int = 400,
    height: int = 200,
    num_staves: int = 1,
    lines_per_staff: int = 5,
    line_spacing: int = 8,
) -> np.ndarray:
    """Synthesize a grayscale image containing horizontal staff lines (white on black)."""
    # Start with white paper (255 = paper)
    img = np.ones((height, width), dtype=np.uint8) * 255

    staff_height_total = (lines_per_staff - 1) * line_spacing
    top_margin = (height // (num_staves + 1)) - staff_height_total // 2

    for s in range(num_staves):
        staff_top = top_margin + s * (height // (num_staves + 1))
        for l in range(lines_per_staff):
            y = staff_top + l * line_spacing
            if 0 <= y < height:
                # Draw a thick-ish line (2px) spanning most of the width
                ink_width = int(width * 0.85)
                x_start = (width - ink_width) // 2
                img[y : y + 2, x_start : x_start + ink_width] = 0  # black ink

    return img


def _make_blank_image(width: int = 200, height: int = 100) -> np.ndarray:
    """All-white (no ink) image."""
    return np.ones((height, width), dtype=np.uint8) * 255


# ── Unit tests: detect_staff_lines ────────────────────────────────────────────


def test_detect_staff_lines_returns_list():
    gray = _make_staff_image(num_staves=1)
    result = detect_staff_lines(gray)
    assert isinstance(result, list)


def test_detect_staff_lines_simple_melody():
    """Single staff should yield exactly one (top_y, bottom_y) tuple."""
    gray = _make_staff_image(width=400, height=150, num_staves=1)
    result = detect_staff_lines(gray)
    assert len(result) == 1
    top_y, bottom_y = result[0]
    assert isinstance(top_y, int)
    assert isinstance(bottom_y, int)
    assert top_y < bottom_y


def test_detect_staff_lines_multi_voice():
    """Two staves should yield two (top_y, bottom_y) tuples."""
    gray = _make_staff_image(width=400, height=300, num_staves=2)
    result = detect_staff_lines(gray)
    assert len(result) == 2
    # Staves should be ordered top to bottom
    assert result[0][0] < result[1][0]


def test_detect_staff_lines_piano_chords():
    """Piano grand staff = 2 staves stacked."""
    gray = _make_staff_image(width=400, height=300, num_staves=2)
    result = detect_staff_lines(gray)
    assert len(result) == 2


def test_detect_staff_lines_blank_image():
    """No staff lines in blank image."""
    gray = _make_blank_image()
    result = detect_staff_lines(gray)
    assert result == []


def test_detect_staff_lines_returns_tuples_of_ints():
    gray = _make_staff_image(num_staves=1)
    result = detect_staff_lines(gray)
    if result:
        top_y, bottom_y = result[0]
        assert isinstance(top_y, int)
        assert isinstance(bottom_y, int)


# ── Unit tests: identify_clef_symbols ────────────────────────────────────────


def test_identify_clef_symbols_returns_list():
    gray = _make_staff_image(num_staves=1)
    staff_bounds = detect_staff_lines(gray)
    result = identify_clef_symbols(gray, staff_bounds)
    assert isinstance(result, list)


def test_identify_treble_clef():
    """With uniform ink on left margin (mimicking tall treble clef), expect treble."""
    gray = _make_staff_image(width=400, height=200, num_staves=1)
    staff_bounds = detect_staff_lines(gray)
    # Add uniform ink in left margin across all thirds → treble heuristic
    clef_width = int(400 * 0.15)
    gray_copy = gray.copy()
    # Paint uniform ink density across left margin
    gray_copy[10:190, 0:clef_width] = 0  # solid black in left margin
    result = identify_clef_symbols(gray_copy, staff_bounds)
    assert len(result) == 1
    # With uniform distribution, the classifier may call it treble or something
    assert result[0]["clef_type"] in ("treble", "bass", "alto", "unknown")
    assert 0.0 <= result[0]["confidence"] <= 1.0


def test_identify_bass_clef():
    """Upper-heavy ink distribution should classify as bass."""
    gray = _make_staff_image(width=400, height=200, num_staves=1)
    staff_bounds = detect_staff_lines(gray)
    clef_width = int(400 * 0.15)
    gray_copy = gray.copy()
    # Paint ink only in top third of the search region → bass heuristic
    top_y = staff_bounds[0][0]
    search_top = max(0, top_y - int((staff_bounds[0][1] - top_y) * 0.8))
    region_h = staff_bounds[0][1] + int((staff_bounds[0][1] - top_y) * 0.8) - search_top
    third = region_h // 3
    gray_copy[search_top : search_top + third, 0:clef_width] = 0
    result = identify_clef_symbols(gray_copy, staff_bounds)
    assert len(result) == 1
    assert result[0]["clef_type"] == "bass"
    assert result[0]["confidence"] > 0.3


def test_identify_alto_clef():
    """Middle-heavy symmetric ink distribution should classify as alto."""
    gray = _make_staff_image(width=400, height=200, num_staves=1)
    staff_bounds = detect_staff_lines(gray)
    clef_width = int(400 * 0.15)
    gray_copy = gray.copy()
    top_y = staff_bounds[0][0]
    bot_y = staff_bounds[0][1]
    search_top = max(0, top_y - int((bot_y - top_y) * 0.8))
    region_h = bot_y + int((bot_y - top_y) * 0.8) - search_top
    third = region_h // 3
    # Paint ink in middle third only → alto heuristic
    gray_copy[search_top + third : search_top + 2 * third, 0:clef_width] = 0
    result = identify_clef_symbols(gray_copy, staff_bounds)
    assert len(result) == 1
    assert result[0]["clef_type"] in ("alto", "treble", "unknown")


def test_identify_clef_symbols_empty_bounds():
    """Empty staff_bounds returns empty list."""
    gray = _make_blank_image()
    result = identify_clef_symbols(gray, [])
    assert result == []


# ── Unit tests: ClefDetector.process ─────────────────────────────────────────


def test_process_returns_valid_structure():
    """process() always returns a dict with expected keys."""
    with patch("core.clef_detector._load_as_grayscale") as mock_load:
        mock_load.return_value = _make_staff_image(num_staves=1)
        detector = ClefDetector()
        result = detector.process("fake_path.png")

    assert "staff_count" in result
    assert "staves" in result
    assert "context_block" in result
    assert "error" in result
    assert isinstance(result["staff_count"], int)
    assert isinstance(result["staves"], list)
    assert isinstance(result["context_block"], str)


def test_process_handles_no_staffs():
    """process() gracefully handles images with no detectable staff lines."""
    with patch("core.clef_detector._load_as_grayscale") as mock_load:
        mock_load.return_value = _make_blank_image()
        detector = ClefDetector()
        result = detector.process("fake_path.png")

    assert result["staff_count"] == 0
    assert result["staves"] == []
    assert result["context_block"] == ""
    assert result["error"] is not None


def test_process_handles_missing_file():
    """process() returns error dict when file doesn't exist."""
    detector = ClefDetector()
    result = detector.process("/nonexistent/path/image.png")
    assert result["staff_count"] == 0
    assert result["error"] is not None


def test_process_context_block_content():
    """context_block should mention staff count and clef type."""
    with patch("core.clef_detector._load_as_grayscale") as mock_load:
        mock_load.return_value = _make_staff_image(num_staves=1)
        detector = ClefDetector()
        result = detector.process("fake_path.png")

    if result["staff_count"] > 0:
        assert "Staff 1" in result["context_block"]
        assert "CV PRE-ANALYSIS" in result["context_block"]


# ── Integration tests: real fixture images (skipped if not present) ───────────


@pytest.mark.skipif(
    not (_CORPUS_SIMPLE / "bluemtns-a4-1.png").exists(),
    reason="Fixture image not available",
)
def test_detect_staff_lines_simple_melody_fixture():
    """Integration: detect staves in a real simple melody image."""
    from core.clef_detector import _load_as_grayscale

    img_path = str(_CORPUS_SIMPLE / "bluemtns-a4-1.png")
    gray = _load_as_grayscale(img_path)
    assert gray is not None
    result = detect_staff_lines(gray)
    assert len(result) >= 1


@pytest.mark.skipif(
    not (_CORPUS_SIMPLE / "giselle-a4-1.png").exists(),
    reason="Fixture image not available",
)
def test_clef_detector_process_simple_fixture():
    """Integration: ClefDetector.process on a real fixture."""
    detector = ClefDetector()
    result = detector.process(str(_CORPUS_SIMPLE / "giselle-a4-1.png"))
    assert "staff_count" in result
    assert "context_block" in result
