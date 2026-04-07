# Nested Tuplets Fixture Analysis

## Issue Summary

The nested_tuplets fixture has **0% measure accuracy** and **98.1% overall accuracy**, making it the biggest blocker for the Q2 rock (95%+ accuracy on all baseline fixtures).

## Root Cause

The vision model is incorrectly detecting the **time signature** as **3/4** instead of **4/4**. This is causing cascading failures:

1. **Time signature wrong**: All 4 measures show `expected: 4/4, got: 3/4`
2. **Measure count hallucination**: Extracting 20 measures instead of 4
3. **Tuplet notation lost**: None of the nested tuplet brackets (triplet, quintuplet, sextuplet) are detected
4. **Rhythm errors**: All note durations are wrong because they're calculated against wrong time signature

## Why This Happens

The fixture begins with a **triplet bracket** showing the numeral "3" immediately after the time signature:

```
Measure 1 (expected):
- Time signature: 4/4
- First notes: Quarter (C5) → Eighth tied (D5) → Eighth tied (D5) → Quarter (E5)
  All three notes are in a TRIPLET bracket showing numeral "3"
```

The vision model is confusing the **tuplet bracket numeral "3"** with the **time signature top number "4"**. The triplet bracket's "3" is positioned above the beam spanning the first three notes, making it visually similar to the top number of a time signature.

## Attempted Fix

**Added prompt guidance** to both STRUCTURE_PROMPT and DETAIL_PROMPT:

```
CRITICAL: Time signature numerals appear BEFORE ANY notes at the staff's beginning 
(e.g., 4 over 4 for 4/4). Tuplet bracket numerals (3, 5, 6, etc.) 
appear ABOVE OR BELOW beams spanning multiple notes. DO NOT confuse them. 
The time signature is ALWAYS at the very start of the staff before notes begin.
```

### Test Results

After running the fixture with the improved prompts:
- **Still detecting 3/4 time** (prompt guidance insufficient)
- **Still hallucinating 20 measures** (massive structural failure)
- **No tuplet notation detected** (entire content missed)

The fix did not work. The vision model is still fundamentally misreading the score structure.

## Current Status

- ✅ Fix pushed to \`feature/pipeline-hardening\` branch
- ❌ Test results show no improvement
- ❌ Measure accuracy remains at 0%

## What Needs to Change

### Option 1: Stronger Prompt Constraints (Low Complexity, Medium Effort)

Add even more aggressive prompt guidance:
- Specify that time signature numerals are **vertically stacked** (top/bottom aligned)
- Specify that tuplet numerals are **always horizontal** with beams
- Add examples: "A time signature looks like 4 over 4. A tuplet bracket looks like ─3─ with notes under it."
- Add negative constraint: "If you see a '3' above a beam, that is NOT the time signature"

### Option 2: Time Signature Pre-Detection (Medium Complexity, Medium Effort)

Use an OCR/heuristic approach before vision extraction:
1. Run a quick OCR check for time signature at the beginning of staff
2. Parse the stacked numerals at the very left of the staff
3. Force this as the ground truth time signature for vision extraction
4. This prevents the vision model from being confused by nearby numerals

### Option 3: Post-Extraction Correction (Low Complexity, High Effort)

After extraction, validate and correct automatically:
1. Check if measure count is reasonable (e.g., not 20 for a 4-measure fixture)
2. Validate note durations sum to expected time signature
3. If detected time signature causes duration mismatches, try common corrections
4. For nested_tuplets: force 4/4 if detected as 3/4

### Option 4: Image Preprocessing (High Complexity, Medium Effort)

Modify the image before sending to vision:
1. Add visual markers or crop regions to highlight time signature area
2. Use edge detection to identify and isolate the time signature region
3. Only send the time signature area to vision for that specific extraction
4. This isolates time signature detection from tuplet numerals

### Option 5: Model Fine-Tuning (Very High Complexity, Very High Effort)

Use vision model fine-tuning with examples of nested tuplets:
1. Create training set with examples showing tuplet numerals vs time signatures
2. Fine-tune Claude Sonnet to distinguish these cases
3. Deploy custom model for this specific fixture type
4. Long-term solution but significant engineering investment

## Recommended Next Steps

1. **Immediate**: Try Option 1 (stronger prompt constraints) - push to same branch
2. **Short-term**: If Option 1 fails, implement Option 3 (post-extraction correction)
3. **Medium-term**: Consider Option 2 or 4 for robust time signature detection
4. **Long-term**: Evaluate if this pattern appears in other fixtures, indicating need for Option 5

## Ground Truth Reference

The expected nested_tuplets fixture has:
- **4 measures** total
- **Time signature**: 4/4
- **Measure 1**: Triplet of notes (quarter-eighth-eighth quintuplet tied)
- **Measure 2**: Quintuplet with ties
- **Measure 3**: Sextuplet of quarter notes
- **Measure 4**: Two half notes
- **Total notes**: 24
- **Complex tuplets**: Nested structures with multiple bracket levels
