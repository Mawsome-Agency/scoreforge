"""Unit tests for time signature pre-extraction module."""

import pytest
import numpy as np
from pathlib import Path

from core.timesig_extractor import (
    extract_time_signature,
    _is_valid_time_signature,
    _preprocess_for_ocr,
    _generate_time_sig_templates,
    inject_time_signature_constraint,
    TimeSignatureResult,
    HAS_PYTESSERACT,
)


class TestTimeSignatureValidation:
    """Test time signature validation logic."""

    def test_valid_time_signatures(self):
        """Common valid time signatures should pass."""
        assert _is_valid_time_signature(2, 4) is True
        assert _is_valid_time_signature(3, 4) is True
        assert _is_valid_time_signature(4, 4) is True
        assert _is_valid_time_signature(6, 8) is True
        assert _is_valid_time_signature(3, 8) is True

    def test_valid_beat_types(self):
        """All standard beat types should be valid."""
        for beat_type in [1, 2, 4, 8, 16, 32]:
            assert _is_valid_time_signature(4, beat_type) is True

    def test_invalid_beats(self):
        """Beat counts outside valid range should fail."""
        assert _is_valid_time_signature(0, 4) is False
        assert _is_valid_time_signature(17, 4) is False
        assert _is_valid_time_signature(-1, 4) is False
        assert _is_valid_time_signature(100, 4) is False

    def test_invalid_beat_types(self):
        """Non-standard beat types should fail."""
        assert _is_valid_time_signature(4, 3) is False
        assert _is_valid_time_signature(4, 5) is False
        assert _is_valid_time_signature(4, 64) is False


class TestTimeSignatureResult:
    """Test TimeSignatureResult named tuple."""

    def test_result_creation(self):
        """Create result with all fields."""
        result = TimeSignatureResult(
            beats=4,
            beat_type=4,
            confidence=0.85,
            method='ocr',
            raw_text='4/4'
        )
        assert result.beats == 4
        assert result.beat_type == 4
        assert result.confidence == 0.85
        assert result.method == 'ocr'
        assert result.raw_text == '4/4'


class TestPreprocessForOCR:
    """Test image preprocessing for OCR."""

    def test_returns_grayscale(self):
        """Should convert to grayscale."""
        # Create simple test image
        test_img = np.ones((100, 100, 3), dtype=np.uint8) * 255
        result = _preprocess_for_ocr(test_img)
        # Result should be single channel (grayscale)
        assert len(result.shape) == 2
        # Account for 2x upscale + 40px padding (20 on each side)
        expected_size = (100 * 2 + 40, 100 * 2 + 40)
        assert result.shape == expected_size

    def test_inverts_binary(self):
        """Should invert for tesseract (white text on black)."""
        # Create white background, black text
        test_img = np.zeros((100, 100, 3), dtype=np.uint8)
        test_img[:, :] = 255  # White
        test_img[30:70, 30:70, :] = 0  # Black box

        result = _preprocess_for_ocr(test_img)
        # Inverted: black becomes white, white becomes black
        # Check pixel inside the black box (not center)
        assert result[50, 50] == 0  # Should be black after inversion


class TestTemplateGeneration:
    """Test synthetic template generation."""

    def test_generates_templates(self):
        """Should generate templates for common time signatures."""
        shape = (100, 100, 3)
        templates = _generate_time_sig_templates(shape)

        # Check some expected time signatures
        assert "4/4" in templates
        assert "3/4" in templates
        assert "6/8" in templates
        assert "2/4" in templates

    def test_templates_are_binary(self):
        """Generated templates should be inverted (black on white)."""
        shape = (100, 100, 3)
        templates = _generate_time_sig_templates(shape)

        # All templates should be single channel
        for name, template in templates.items():
            assert len(template.shape) == 2
            # Template should be mostly black (0) with white (255) digits
            # after inversion, so most pixels should be 0
            mean_val = np.mean(template)
            assert mean_val < 50, f"Template {name} mean {mean_val} too high"


class TestConstraintInjection:
    """Test prompt modification for time signature injection."""

    def test_injects_constraint(self):
        """Should add explicit instruction to prompt."""
        base_prompt = "Extract the structure..."
        result = TimeSignatureResult(
            beats=3,
            beat_type=4,
            confidence=0.9,
            method='ocr',
            raw_text='3/4'
        )

        modified = inject_time_signature_constraint(base_prompt, result)

        assert "3/4" in modified
        assert "pre-detected" in modified.lower()
        assert "confidence" in modified.lower()
        assert base_prompt in modified  # Original prompt preserved

    def test_includes_method_and_confidence(self):
        """Should include detection method and confidence."""
        base_prompt = "Extract..."
        result = TimeSignatureResult(
            beats=6,
            beat_type=8,
            confidence=0.75,
            method='template_match',
            raw_text='6/8'
        )

        modified = inject_time_signature_constraint(base_prompt, result)

        assert "75.0%" in modified
        assert "template_match" in modified


class TestQuickCropRegion:
    """Test of quick-crop region configuration."""

    def test_region_percentages(self):
        """Crop region should be valid percentages."""
        from core.timesig_extractor import TIME_SIG_REGION

        assert 0 < TIME_SIG_REGION["x_start"] < 1
        assert 0 < TIME_SIG_REGION["x_end"] < 1
        assert TIME_SIG_REGION["x_start"] < TIME_SIG_REGION["x_end"]
        assert 0 < TIME_SIG_REGION["y_start"] < 1
        assert 0 < TIME_SIG_REGION["y_end"] < 1
        assert TIME_SIG_REGION["y_start"] < TIME_SIG_REGION["y_end"]

    def test_region_is_left_top(self):
        """Quick-crop should target left/top area of image."""
        from core.timesig_extractor import TIME_SIG_REGION

        # Time signature should be in first 25% of width (left side)
        assert TIME_SIG_REGION["x_end"] <= 0.25
        # Time signature should be in first 35% of height (top area)
        assert TIME_SIG_REGION["y_end"] <= 0.35


class TestExtractionSkip:
    """Test that extraction can be skipped."""

    def test_skip_returns_none(self):
        """With use_preextract=False, should return None."""
        result = extract_time_signature(
            "/tmp/nonexistent.png",
            use_preextract=False
        )
        assert result is None
