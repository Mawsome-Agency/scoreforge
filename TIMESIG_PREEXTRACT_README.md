# Time Signature Pre-Extraction (Approach A)

## Overview

This feature implements Approach A from the research report: pre-extract time signature region and inject it as a constraint to Claude Vision extraction pipeline. This prevents hallucination by giving Claude explicit ground truth before extraction begins.

## How It Works

```
Input Image
     ↓
┌──────────────────────────────┐
│                           3/4      │ ← Quick-crop (15-25% width, 10-35% height)
├──────────────────────────────┤
│  Staff lines...          │
│                         │
└──────────────────────────────┘
     ↓
[OCR/Template Match]
     ↓
TimeSignatureResult(beats=3, beat_type=4, confidence=0.85)
     ↓
[Inject into Prompt]
     ↓
Claude Vision: "You MUST use 3/4..."
     ↓
Correct MusicXML (time_signature: 3/4)
```

## Quick-Crop Region

The region percentages are tuned for Verovio-rendered test fixtures:
- **X-axis**: 15% to 25% of image width (left side, near clef)
- **Y-axis**: 10% to 35% of image height (top, first staff area)

These values work for:
- Standard Verovio rendering (used by test harness)
- First staff on single-page scores
- Most common time signature placements

May need adjustment for:
- Scanned scores (time sig lower on staff)
- Multi-page PDFs (different regions per page)
- Non-standard layouts

## Detection Methods

### Primary: OCR (Tesseract)
- Digit-only character set: `0123456789/`
- Pattern matching: `(\d+)\s*/\s*(\d+)`
- Adaptive thresholding for robust binarization
- Upscale 2x for better digit recognition
- Confidence from tesseract character confidence scores

### Fallback: Template Matching
- Synthetic templates for: 2/4, 3/4, 4/4, 5/4, 6/4, 2/2, 3/2, 6/8, 9/8, 12/8, 3/8, 5/8, 7/8
- OpenCV matchTemplate with TM_CCOEFF_NORMED
- Resize templates to match cropped region size
- Minimum confidence threshold: 0.7

## Prompt Injection

When time signature is detected with `confidence >= 0.60`, injection adds:

```
TIME SIGNATURE PRE-DETECTED: 3/4
CONFIDENCE: 85.00%
METHOD: ocr

IMPORTANT: The time signature has been pre-detected with high confidence (85.0%).
You MUST use 3/4 as the time signature for this score.
Do NOT guess or estimate the time signature — use this pre-detected value.
```

## Usage

### CLI

```bash
# Enable time signature pre-extraction
python scoreforge.py input.png --output output.musicxml --time-sig-preextract

# Short flag
python scoreforge.py input.png -ts
```

### Python API

```python
from core.extractor import extract_from_image

# With pre-extraction
score = extract_from_image(
    image_path="sheet.png",
    model="claude-sonnet-4-5-20250929",
    use_time_sig_preextract=True  # Enable pre-extraction
)

# Without (default behavior)
score = extract_from_image(
    image_path="sheet.png",
    model="claude-sonnet-4-5-20250929"
    # use_time_sig_preextract=False (default)
)
```

### Iteration/Testing

```bash
# Enable in test harness
python iterate.py --time-sig-preextract

# Compare results with/without pre-extraction
python iterate.py --time-sig-preextract > results/with_preextract.json
python iterate.py > results/without_preextract.json
# Compare accuracy metrics
```

## Debugging

### Visualize Crop Region

```python
from core.timesig_extractor import create_cropped_debug_image

debug_path = create_cropped_debug_image("sheet.png")
print(f"Debug image saved to: {debug_path}")
```

This creates a copy of the input with a green rectangle around the time signature region.

### Check Module Availability

```python
from core.timesig_extractor import HAS_PYTESSERACT

if HAS_PYTESSERACT:
    print("Tesseract available - OCR will be used")
else:
    print("Tesseract unavailable - template matching only")
```

## Testing

### Unit Tests

Run the full test suite:

```bash
python -m pytest tests/test_timesig_extractor.py -v
```

Coverage:
- Time signature validation logic
- Preprocessing transformations
- Template generation
- Prompt injection formatting
- Quick-crop region configuration

### Fixture Testing

Test on the `nested_tuplets` fixture (3/4 time signature):

```bash
# Render fixture to image
python -c "
from core.renderer import render_musicxml_to_image
render_musicxml_to_image('tests/fixtures/nested_tuplets.musicxml', 'nested_tuplets.png')
"

# Extract with pre-extraction
python scoreforge.py nested_tuplets.png --time-sig-preextract --output nested_tuplets_extracted.musicxml

# Compare with ground truth
python -c "
from core.comparator import compare_musicxml_semantic
result = compare_musicxml_semantic(
    'tests/fixtures/nested_tuplets.musicxml',
    'nested_tuplets_extracted.musicxml'
)
print(f'Accuracy: {result[\"accuracy\"]:.1%}')
"
```

## Advantages (from research report)

1. **High confidence**: OCR + template matching gives reliable detection
2. **Low risk**: Quick-crop avoids complex layout analysis
3. **Minimal latency**: ~100-200ms pre-extraction time
4. **Transparent integration**: Optional/toggleable, graceful degradation
5. **Reusable**: Templates cover most common time signatures

## Limitations

- Quick-crop percentages tuned for Verovio rendering
- Scanned scores may need region adjustment
- pytesseract dependency optional (graceful skip if unavailable)
- Complex/compound time signatures (e.g., 4/4+4/4) not supported

## Future Improvements

- [ ] Adaptive crop region based on staff detection
- [ ] Machine learning model for time sig detection
- [ ] Support for cut-time and other complex signatures
- [ ] Per-page detection for multi-page PDFs

## Files Added

- `core/timesig_extractor.py` - Main module
- `tests/test_timesig_extractor.py` - Unit tests (14 tests)
- `tests/fixtures/nested_tuplets.musicxml` - Test fixture (3/4)

## Files Modified

- `core/extractor.py` - Added pre-extraction pipeline
- `core/__init__.py` - Exported new functions
- `scoreforge.py` - Added CLI flag
- `iterate.py` - Added test parameter
- `requirements.txt` - Added pytesseract dependency
