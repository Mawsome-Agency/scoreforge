"""Staff line detection and clef identification using OpenCV.

This module provides CV-based pre-processing to detect staff positions
and identify clef types before the LLM extraction pass, providing
ground-truth context that reduces pitch hallucination.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Tuning constants ─────────────────────────────────────────────────────────
# Fraction of image width that a row must be filled to count as a staff line.
STAFF_LINE_WIDTH_FRACTION = 0.45
# Max gap (pixels) between consecutive rows that are still the same staff line.
INTER_STAFF_GAP_PX = 3
# A valid staff must contain exactly 5 lines. We accept 4–6 to allow for
# thin-image quantisation artefacts.
MIN_STAFF_LINES = 4
MAX_STAFF_LINES = 6
# Left margin (fraction of image width) to search for clef symbol.
CLEF_SEARCH_WIDTH_FRACTION = 0.15


def _load_as_grayscale(image_path: str) -> Optional[np.ndarray]:
    """Load an image as grayscale, handling RGBA → gray conversion."""
    path = Path(image_path)
    if not path.exists():
        logger.warning("clef_detector: image not found: %s", image_path)
        return None
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        logger.warning("clef_detector: cv2.imread returned None for %s", image_path)
        return None
    if img.ndim == 2:
        return img
    if img.shape[2] == 4:
        # RGBA → RGB first, then to gray
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return gray


def _binarize(gray: np.ndarray) -> np.ndarray:
    """Adaptive threshold to produce a binary image (ink=255, paper=0)."""
    # Invert so ink pixels are white (255) for projection sums
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return binary


def detect_staff_lines(gray: np.ndarray) -> List[Tuple[int, int]]:
    """Detect staff line groups (one per staff) from a grayscale image.

    Args:
        gray: Grayscale image array.

    Returns:
        List of (top_y, bottom_y) tuples, one per detected staff system.
        Each tuple gives the pixel extent of the 5-line staff.
    """
    binary = _binarize(gray)
    img_h, img_w = binary.shape[:2]

    # Horizontal projection: count white (ink) pixels per row
    h_proj = np.sum(binary, axis=1).astype(float) / 255.0
    staff_threshold = img_w * STAFF_LINE_WIDTH_FRACTION
    staff_row_mask = h_proj >= staff_threshold

    staff_row_indices = np.where(staff_row_mask)[0]
    if len(staff_row_indices) == 0:
        return []

    # Cluster consecutive rows into individual staff lines
    line_groups: List[List[int]] = []
    current_group = [int(staff_row_indices[0])]
    for idx in staff_row_indices[1:]:
        if int(idx) - current_group[-1] <= INTER_STAFF_GAP_PX:
            current_group.append(int(idx))
        else:
            line_groups.append(current_group)
            current_group = [int(idx)]
    line_groups.append(current_group)

    # Each line_group = one staff line (a thin horizontal band).
    # Group these line groups into staves of 5 lines each.
    # Gap between consecutive staff lines within the same staff is small;
    # gap between staves is large. We use a simple median-gap heuristic.
    if len(line_groups) < MIN_STAFF_LINES:
        return []

    # Compute midpoint of each line group
    midpoints = [int(np.mean(g)) for g in line_groups]

    # Gaps between consecutive midpoints
    gaps = [midpoints[i + 1] - midpoints[i] for i in range(len(midpoints) - 1)]
    if not gaps:
        return []

    median_gap = float(np.median(gaps))
    # Inter-staff gap is typically 5-10× the inter-line gap.
    # Use 2.5× median as threshold to split staves.
    split_threshold = median_gap * 2.5

    # Partition line groups into staves
    staves: List[List[List[int]]] = []
    current_staff: List[List[int]] = [line_groups[0]]
    for i in range(1, len(line_groups)):
        gap = midpoints[i] - midpoints[i - 1]
        if gap > split_threshold:
            staves.append(current_staff)
            current_staff = []
        current_staff.append(line_groups[i])
    staves.append(current_staff)

    # Keep only staves with a plausible number of lines
    valid_staves = [s for s in staves if MIN_STAFF_LINES <= len(s) <= MAX_STAFF_LINES]

    # Return (top_y, bottom_y) for each staff
    results: List[Tuple[int, int]] = []
    for staff in valid_staves:
        top_y = staff[0][0]
        bottom_y = staff[-1][-1]
        results.append((top_y, bottom_y))

    return results


def identify_clef_symbols(
    gray: np.ndarray,
    staff_bounds: List[Tuple[int, int]],
) -> List[Dict]:
    """Identify clef type for each staff using pixel density analysis.

    Strategy: Examine the left margin of each staff. The clef symbol's
    ink distribution gives a signature:
    - Treble (G-clef): tall symbol extending well above and below staff → high
      vertical extent relative to staff height.
    - Bass (F-clef): compact, mostly in upper half of staff → ink concentrated
      in upper region.
    - Alto/Tenor (C-clef): symmetric bracket shape → ink spread across full
      staff height but more symmetric.

    This is a heuristic classifier; it falls back to "treble" when uncertain.

    Args:
        gray: Grayscale image array.
        staff_bounds: List of (top_y, bottom_y) per staff from detect_staff_lines.

    Returns:
        List of dicts, one per staff:
        {
            "staff_index": int,
            "clef_type": "treble" | "bass" | "alto" | "unknown",
            "confidence": float (0.0–1.0),
        }
    """
    binary = _binarize(gray)
    img_h, img_w = binary.shape[:2]
    clef_width = max(1, int(img_w * CLEF_SEARCH_WIDTH_FRACTION))

    results: List[Dict] = []

    for i, (top_y, bottom_y) in enumerate(staff_bounds):
        staff_height = max(1, bottom_y - top_y)
        # Expand search region: clefs extend above/below the staff
        margin = int(staff_height * 0.8)
        search_top = max(0, top_y - margin)
        search_bottom = min(img_h, bottom_y + margin)

        # Extract left-margin region
        clef_region = binary[search_top:search_bottom, 0:clef_width]
        if clef_region.size == 0:
            results.append({"staff_index": i, "clef_type": "unknown", "confidence": 0.0})
            continue

        region_h = clef_region.shape[0]
        if region_h == 0:
            results.append({"staff_index": i, "clef_type": "unknown", "confidence": 0.0})
            continue

        # Row-by-row ink density
        row_density = np.sum(clef_region, axis=1).astype(float) / (clef_width * 255.0)

        # Split into thirds: upper / middle / lower
        third = max(1, region_h // 3)
        upper_density = float(np.mean(row_density[:third]))
        middle_density = float(np.mean(row_density[third : 2 * third]))
        lower_density = float(np.mean(row_density[2 * third :]))
        total_density = float(np.mean(row_density))

        if total_density < 0.005:
            # Almost no ink — can't classify
            results.append({"staff_index": i, "clef_type": "unknown", "confidence": 0.1})
            continue

        # Heuristics:
        # Treble: ink present in all thirds (tall symbol); upper and lower both active
        # Bass:   ink concentrated in upper 2/3, very little below staff
        # Alto:   ink spread across middle region (bracket shape)

        upper_ratio = upper_density / (total_density + 1e-9)
        lower_ratio = lower_density / (total_density + 1e-9)
        middle_ratio = middle_density / (total_density + 1e-9)

        if upper_ratio > 0.4 and lower_ratio < 0.25:
            clef_type = "bass"
            confidence = min(1.0, upper_ratio)
        elif middle_ratio > 0.38 and abs(upper_ratio - lower_ratio) < 0.15:
            clef_type = "alto"
            confidence = min(1.0, middle_ratio)
        else:
            # Default: treble (most common; also fallback when uncertain)
            clef_type = "treble"
            confidence = 0.6

        results.append({"staff_index": i, "clef_type": clef_type, "confidence": confidence})

    return results


def detect_ledger_lines(
    gray: np.ndarray,
    staff_bounds: List[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Detect ledger lines above and below each staff.

    Ledger lines are short horizontal lines outside the 5-line staff.
    We look for rows with moderate (not full-width) ink density just
    above or below each detected staff.

    Args:
        gray: Grayscale image array.
        staff_bounds: List of (top_y, bottom_y) per staff.

    Returns:
        List of (y, staff_index) tuples for detected ledger line rows.
        (Informational — used for context building.)
    """
    binary = _binarize(gray)
    img_h, img_w = binary.shape[:2]
    h_proj = np.sum(binary, axis=1).astype(float) / 255.0

    # Ledger lines span a small fraction of the page width
    ledger_min = img_w * 0.03
    ledger_max = img_w * 0.25

    results: List[Tuple[int, int]] = []

    for i, (top_y, bottom_y) in enumerate(staff_bounds):
        staff_height = max(1, bottom_y - top_y)
        search_margin = int(staff_height * 1.0)

        for y in range(max(0, top_y - search_margin), top_y):
            if ledger_min <= h_proj[y] <= ledger_max:
                results.append((y, i))

        for y in range(bottom_y, min(img_h, bottom_y + search_margin)):
            if ledger_min <= h_proj[y] <= ledger_max:
                results.append((y, i))

    return results


class ClefDetector:
    """High-level interface for clef detection.

    Usage:
        detector = ClefDetector()
        result = detector.process("path/to/sheet.png")
        # result["context_block"] → string to inject into LLM prompt
    """

    def process(self, image_path: str) -> Dict:
        """Run full detection pipeline on an image.

        Args:
            image_path: Path to sheet music image.

        Returns:
            Dict with keys:
            - "staff_count": int — number of detected staves
            - "staves": list of staff dicts (staff_index, clef_type, confidence,
              top_y, bottom_y)
            - "context_block": str — formatted text for LLM prompt injection
            - "error": str or None — non-fatal error message if detection failed
        """
        empty = {
            "staff_count": 0,
            "staves": [],
            "context_block": "",
            "error": None,
        }

        try:
            gray = _load_as_grayscale(image_path)
            if gray is None:
                empty["error"] = f"Could not load image: {image_path}"
                return empty

            staff_bounds = detect_staff_lines(gray)
            if not staff_bounds:
                empty["error"] = "No staff lines detected"
                return empty

            clef_info = identify_clef_symbols(gray, staff_bounds)

            staves = []
            for clef in clef_info:
                idx = clef["staff_index"]
                top_y, bottom_y = staff_bounds[idx]
                staves.append({
                    "staff_index": idx,
                    "clef_type": clef["clef_type"],
                    "confidence": clef["confidence"],
                    "top_y": top_y,
                    "bottom_y": bottom_y,
                })

            context_block = self._build_context_block(staves)

            return {
                "staff_count": len(staves),
                "staves": staves,
                "context_block": context_block,
                "error": None,
            }

        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("clef_detector: unexpected error: %s", exc, exc_info=True)
            empty["error"] = str(exc)
            return empty

    def _build_context_block(self, staves: List[Dict]) -> str:
        """Format stave/clef data as a prompt-injectable context string."""
        if not staves:
            return ""

        lines = [
            "CV PRE-ANALYSIS (computer vision scan performed before this prompt):",
            f"  Detected {len(staves)} staff system(s) in the image.",
        ]
        for s in staves:
            clef_label = {
                "treble": "Treble (G-clef)",
                "bass": "Bass (F-clef)",
                "alto": "Alto/Tenor (C-clef)",
                "unknown": "Unknown clef",
            }.get(s["clef_type"], s["clef_type"])
            conf_str = f"{s['confidence']:.0%}"
            lines.append(
                f"  Staff {s['staff_index'] + 1}: {clef_label} "
                f"(CV confidence: {conf_str}, "
                f"y-range: {s['top_y']}–{s['bottom_y']}px)"
            )
        lines.append(
            "Use the above as a cross-check when identifying clefs from the image. "
            "If the CV result conflicts with what you see visually, trust your visual reading."
        )
        return "\n".join(lines)
