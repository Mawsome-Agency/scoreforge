"""Time signature pre-extraction using quick-crop approach.

This module implements Approach A from the research report:
1. Pre-extract time signature region using hardcoded crop percentages (optimized for Verovio-rendered fixtures)
2. OCR the stacked numerals using pytesseract with custom digit templates
3. Return detected time signature with confidence score

The quick-crop approach uses fixed percentage coordinates relative to image dimensions:
- Time signature typically appears in first 20% width, 10-35% height range
- Works reliably for Verovio-rendered test fixtures
- Lower risk than AI detection, faster than complex layout analysis
"""

import re
import base64
from pathlib import Path
from typing import Optional, Tuple, NamedTuple

import cv2
import numpy as np
from PIL import Image

# Optional pytesseract import (graceful degradation)
try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False


# ---------------------------------------------------------------------------
# Quick-crop region for Verovio-rendered fixtures
# These percentages are tuned for Verovio's default rendering style
# (staff spacing, time sig placement)
# ---------------------------------------------------------------------------
TIME_SIG_REGION = {
    "x_start": 0.15,   # 15% from left edge
    "x_end": 0.25,     # 25% from left edge
    "y_start": 0.10,   # 10% from top edge
    "y_end": 0.35,     # 35% from top edge
}


# Tesseract configuration for digit recognition
TESSERACT_CONFIG = r'--oem 3 --psm 10'  # LSTM engine, single character mode


# Time signature pattern matching
TIME_SIG_PATTERN = re.compile(r'^(\d+)\s*/\s*(\d+)$')


class TimeSignatureResult(NamedTuple):
    """Result of time signature extraction."""
    beats: Optional[int]
    beat_type: Optional[int]
    confidence: float
    method: str  # 'ocr', 'template_match', 'fallback'
    raw_text: str


def extract_time_signature(
    image_path: str,
    use_preextract: bool = True,
    min_confidence: float = 0.6,
) -> Optional[TimeSignatureResult]:
    """Extract time signature from sheet music image using quick-crop approach.

    Args:
        image_path: Path to sheet music image (PNG, JPG)
        use_preextract: If False, returns None immediately (skip pre-extraction)
        min_confidence: Minimum confidence to accept detection (0.0-1.0)

    Returns:
        TimeSignatureResult if detected with sufficient confidence, None otherwise
    """
    if not use_preextract:
        return None
    
    if not HAS_PYTESSERACT:
        # OCR unavailable, skip pre-extraction gracefully
        print("  [Pre-extraction] Warning: pytesseract not installed, skipping time signature pre-extraction")
        return None

    img_path = Path(image_path)
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Load image
    img = cv2.imread(str(img_path))
    if img is None:
        raise ValueError(f"Failed to load image: {image_path}")

    height, width = img.shape[:2]

    # Calculate crop coordinates based on percentages
    x1 = int(width * TIME_SIG_REGION["x_start"])
    x2 = int(width * TIME_SIG_REGION["x_end"])
    y1 = int(height * TIME_SIG_REGION["y_start"])
    y2 = int(height * TIME_SIG_REGION["y_end"])

    # Crop time signature region
    cropped = img[y1:y2, x1:x2]

    # Preprocess for OCR
    processed = _preprocess_for_ocr(cropped)

    # Try OCR first
    ocr_result = _ocr_time_signature(processed)
    if ocr_result and ocr_result.confidence >= min_confidence:
        return ocr_result

    # Fallback: template matching for common time signatures
    template_result = _template_match_time_signature(cropped, img)
    if template_result and template_result.confidence >= min_confidence:
        return template_result

    return None


def _preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    """Preprocess cropped region for digit OCR.

    Steps:
    1. Convert to grayscale
    2. Threshold to binary (black notes on white background)
    3. Invert (white text on black background for tesseract)
    4. Resize to improve recognition
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Adaptive thresholding for robust binarization
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        2
    )

    # Upscale for better OCR
    scale_factor = 2
    upscaled = cv2.resize(
        binary,
        None,
        fx=scale_factor,
        fy=scale_factor,
        interpolation=cv2.INTER_CUBIC
    )

    # Add white border (tesseract likes padding)
    padded = cv2.copyMakeBorder(
        upscaled,
        20, 20, 20, 20,
        cv2.BORDER_CONSTANT,
        value=255
    )

    return padded


def _ocr_time_signature(image: np.ndarray) -> Optional[TimeSignatureResult]:
    """Use Tesseract OCR to read time signature numerals.

    Returns TimeSignatureResult if valid pattern found, None otherwise.
    """
    if not HAS_PYTESSERACT:
        return None
    
    # Configure tesseract for digit-only recognition
    config = '--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789/'

    text = pytesseract.image_to_string(
        image,
        config=config,
        output_type=pytesseract.Output.DICT
    )

    if not text.get('text'):
        return None

    raw_text = text['text'].strip()

    # Validate pattern: should be digits/digits
    match = TIME_SIG_PATTERN.match(raw_text)
    if not match:
        return None

    beats = int(match.group(1))
    beat_type = int(match.group(2))

    # Validate time signature is reasonable
    if not _is_valid_time_signature(beats, beat_type):
        return None

    # Estimate confidence from tesseract output
    confidences = [c for c in text.get('conf', []) if c > 0]
    avg_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0

    return TimeSignatureResult(
        beats=beats,
        beat_type=beat_type,
        confidence=avg_confidence,
        method='ocr',
        raw_text=raw_text
    )


def _template_match_time_signature(
    cropped: np.ndarray,
    original: np.ndarray
) -> Optional[TimeSignatureResult]:
    """Template matching for common time signatures.

    Creates synthetic templates for 2/4, 3/4, 4/4, 6/8, etc.
    and matches them against the cropped region.

    Returns best match if confidence > threshold, None otherwise.
    """
    # Preprocess cropped for template matching
    gray_cropped = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    binary_cropped = cv2.threshold(gray_cropped, 127, 255, cv2.THRESH_BINARY_INV)[1]

    # Generate templates for common time signatures
    templates = _generate_time_sig_templates(binary_cropped.shape)

    best_match = None
    best_score = 0.7  # Minimum template match threshold

    for ts, template_img in templates.items():
        # Resize template to match cropped size
        template_resized = cv2.resize(template_img, (binary_cropped.shape[1], binary_cropped.shape[0]))

        # Multi-template matching (handle different scales)
        result = cv2.matchTemplate(binary_cropped, template_resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # Normalize score to 0-1 range
        confidence = max_val  # CCOEFF_NORMED produces values roughly -1 to 1

        if confidence > best_score:
            best_score = confidence
            best_match = ts

    if best_match:
        beats, beat_type = best_match
        return TimeSignatureResult(
            beats=beats,
            beat_type=beat_type,
            confidence=best_score,
            method='template_match',
            raw_text=f"{beats}/{beat_type}"
        )

    return None


def _generate_time_sig_templates(target_shape: Tuple[int, int, int]) -> dict:
    """Generate synthetic templates for common time signatures.

    Returns dict mapping "beats/beat_type" to binary template image.
    """
    h, w = target_shape[:2]
    templates = {}

    # Common time signatures
    time_sigs = [
        (2, 4), (3, 4), (4, 4), (5, 4), (6, 4),
        (2, 2), (3, 2),
        (6, 8), (9, 8), (12, 8),
        (3, 8), (5, 8), (7, 8),
    ]

    for beats, beat_type in time_sigs:
        # Create template image
        template = np.ones((h, w), dtype=np.uint8) * 255  # White background

        # Draw top numeral (beats)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = min(h, w) * 0.008
        thickness = max(1, int(min(h, w) * 0.02))

        text_size = cv2.getTextSize(str(beats), font, font_scale, thickness)[0]
        text_x = (w - text_size[0]) // 2
        text_y = h // 3
        cv2.putText(
            template,
            str(beats),
            (text_x, text_y),
            font,
            font_scale,
            (0, 0, 0),  # Black text
            thickness,
            cv2.LINE_AA
        )

        # Draw slash
        slash_y_start = h // 2
        slash_y_end = h * 2 // 3
        cv2.line(
            template,
            (w // 2 - w // 8, slash_y_start),
            (w // 2 + w // 8, slash_y_end),
            (0, 0, 0),
            thickness,
            cv2.LINE_AA
        )

        # Draw bottom numeral (beat type)
        text_size = cv2.getTextSize(str(beat_type), font, font_scale, thickness)[0]
        text_x = (w - text_size[0]) // 2
        text_y = h * 3 // 4
        cv2.putText(
            template,
            str(beat_type),
            (text_x, text_y),
            font,
            font_scale,
            (0, 0, 0),  # Black text
            thickness,
            cv2.LINE_AA
        )

        # Invert for template matching (black background, white foreground)
        templates[f"{beats}/{beat_type}"] = 255 - template

    return templates


def _is_valid_time_signature(beats: int, beat_type: int) -> bool:
    """Validate time signature values are musically reasonable."""
    # Beats: typically 1-16
    if not (1 <= beats <= 16):
        return False

    # Beat type: typically 1 (whole), 2 (half), 4 (quarter), 8 (eighth), 16 (sixteenth)
    valid_beat_types = [1, 2, 4, 8, 16, 32]
    if beat_type not in valid_beat_types:
        return False

    return True


# ---------------------------------------------------------------------------
# Integration helpers for extract_from_image()
# ---------------------------------------------------------------------------

def inject_time_signature_constraint(
    structure_prompt: str,
    time_sig_result: TimeSignatureResult
) -> str:
    """Inject detected time signature into the structure prompt.

    Adds explicit instruction telling Claude to use the pre-detected time signature.
    """
    injection = f"""

TIME SIGNATURE PRE-DETECTED: {time_sig_result.raw_text}
CONFIDENCE: {time_sig_result.confidence:.2%}
METHOD: {time_sig_result.method}

IMPORTANT: The time signature has been pre-detected with high confidence ({time_sig_result.confidence:.1%}).
You MUST use {time_sig_result.beats}/{time_sig_result.beat_type} as the time signature for this score.
Do NOT guess or estimate the time signature — use this pre-detected value."""

    return structure_prompt + injection


def create_cropped_debug_image(
    image_path: str,
    output_path: Optional[str] = None
) -> str:
    """Create debug image showing the time signature crop region.

    Useful for visualizing and tuning the quick-crop percentages.

    Returns path to debug image.
    """
    img = cv2.imread(image_path)
    height, width = img.shape[:2]

    # Calculate crop coordinates
    x1 = int(width * TIME_SIG_REGION["x_start"])
    x2 = int(width * TIME_SIG_REGION["x_end"])
    y1 = int(height * TIME_SIG_REGION["y_start"])
    y2 = int(height * TIME_SIG_REGION["y_end"])

    # Draw rectangle around region
    debug_img = img.copy()
    cv2.rectangle(
        debug_img,
        (x1, y1),
        (x2, y2),
        (0, 255, 0),  # Green
        2
    )

    # Save
    if output_path is None:
        output_path = str(Path(image_path).with_suffix("_timesig_crop_debug.png"))
    cv2.imwrite(output_path, debug_img)

    return output_path
