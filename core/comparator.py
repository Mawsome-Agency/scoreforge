"""Visual comparison between original sheet music and re-rendered MusicXML."""
import base64
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
import imagehash
import anthropic


def compare_images(original_path: str, rendered_path: str) -> dict:
    """Compare original sheet music with re-rendered version.

    Returns a dict with:
    - match_score: 0-100 (100 = perfect match)
    - phash_distance: perceptual hash distance (0 = identical)
    - pixel_diff_pct: percentage of pixels that differ
    - diff_regions: list of bounding boxes where diffs occur
    """
    orig = Image.open(original_path).convert("L")  # grayscale
    rend = Image.open(rendered_path).convert("L")

    # Resize rendered to match original dimensions for comparison
    if orig.size != rend.size:
        rend = rend.resize(orig.size, Image.LANCZOS)

    # Perceptual hash comparison
    orig_hash = imagehash.phash(orig, hash_size=16)
    rend_hash = imagehash.phash(rend, hash_size=16)
    phash_distance = orig_hash - rend_hash

    # Pixel-level comparison
    orig_arr = np.array(orig, dtype=np.float32) / 255.0
    rend_arr = np.array(rend, dtype=np.float32) / 255.0
    diff = np.abs(orig_arr - rend_arr)
    pixel_diff_pct = (diff > 0.3).mean() * 100  # threshold at 30% brightness diff

    # Find diff regions (simple grid-based)
    diff_regions = _find_diff_regions(diff, threshold=0.3)

    # Composite match score
    # phash_distance of 0 = perfect, 50+ = very different
    phash_score = max(0, 100 - phash_distance * 2)
    pixel_score = max(0, 100 - pixel_diff_pct * 2)
    match_score = int(phash_score * 0.4 + pixel_score * 0.6)

    return {
        "match_score": match_score,
        "phash_distance": phash_distance,
        "pixel_diff_pct": round(pixel_diff_pct, 2),
        "diff_regions": diff_regions,
        "is_perfect": match_score >= 95,
    }


def _find_diff_regions(diff: np.ndarray, threshold: float = 0.3) -> list[dict]:
    """Find rectangular regions where differences exceed threshold."""
    binary = (diff > threshold).astype(np.uint8)
    h, w = binary.shape

    # Divide into grid cells
    cell_h = max(1, h // 10)
    cell_w = max(1, w // 10)
    regions = []

    for row in range(0, h, cell_h):
        for col in range(0, w, cell_w):
            cell = binary[row:row + cell_h, col:col + cell_w]
            if cell.mean() > 0.05:  # >5% of cell has diffs
                regions.append({
                    "x": col,
                    "y": row,
                    "width": min(cell_w, w - col),
                    "height": min(cell_h, h - row),
                    "severity": round(float(cell.mean()), 3),
                })

    return regions


def ai_compare(original_path: str, rendered_path: str) -> dict:
    """Use Claude Vision to compare original and rendered sheet music.

    Returns detailed analysis of differences.
    """
    client = anthropic.Anthropic()

    def encode(path):
        suffix = Path(path).suffix.lower()
        media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
            suffix.lstrip("."), "image/png"
        )
        with open(path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode(), media_type

    orig_data, orig_type = encode(original_path)
    rend_data, rend_type = encode(rendered_path)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Image 1 is the ORIGINAL sheet music. Image 2 is a re-rendered version from extracted MusicXML."},
                    {"type": "image", "source": {"type": "base64", "media_type": orig_type, "data": orig_data}},
                    {"type": "image", "source": {"type": "base64", "media_type": rend_type, "data": rend_data}},
                    {"type": "text", "text": """Compare these two images measure by measure. For EACH difference found, output a JSON array:

[
  {
    "measure": 1,
    "type": "missing_note|wrong_pitch|wrong_duration|wrong_key|wrong_time|missing_rest|extra_note|wrong_accidental|missing_dynamic|missing_slur|missing_tie|other",
    "description": "Detailed description of the difference",
    "severity": "critical|major|minor",
    "fix": "Specific fix instruction for the MusicXML"
  }
]

If the images match perfectly, return an empty array: []

Be EXTREMELY thorough. Check:
- Every note pitch and duration
- Key and time signatures
- Accidentals
- Rests
- Ties, slurs, beams
- Dynamics and articulations
- Clef changes
- Barlines (repeats, double bars)
- Lyrics if present"""},
                ],
            }
        ],
    )

    response_text = message.content[0].text
    import json

    # Extract JSON
    json_str = response_text
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        differences = json.loads(json_str.strip())
    except json.JSONDecodeError:
        differences = [{"type": "parse_error", "description": response_text, "severity": "critical"}]

    return {
        "differences": differences,
        "diff_count": len(differences),
        "is_perfect": len(differences) == 0,
        "critical_count": sum(1 for d in differences if d.get("severity") == "critical"),
        "major_count": sum(1 for d in differences if d.get("severity") == "major"),
        "minor_count": sum(1 for d in differences if d.get("severity") == "minor"),
    }
