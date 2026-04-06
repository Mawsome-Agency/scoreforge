# Baseline Update Plan — Pipeline Hardening Fix

## Before Fix (from original baseline_results.json)

```
lyrics_verses: 
  - converged: false
  - iterations_to_converge: null
  - max_iterations_run: 50
  - final_overall_score: 0.0
  - final_pitch_accuracy: 0.0
  - final_rhythm_accuracy: 0.0
  - final_note_accuracy: 0.0
  - final_measure_accuracy: 0.0
  - failure_patterns: ["build_error_type"]
  - processing_time_seconds: 2705.7
  - error: "Argument must be bytes or unicode, got 'dict'"
```

## After Fix (expected)

```
lyrics_verses:
  - converged: true
  - iterations_to_converge: 2-3
  - max_iterations_run: 2-3
  - final_overall_score: 95-100%
  - final_pitch_accuracy: 95-100%
  - final_rhythm_accuracy: 95-100%
  - final_note_accuracy: 100%
  - final_measure_accuracy: 100%
  - failure_patterns: []
  - processing_time_seconds: ~120-180
  - error: null
```

## Expected Impact on Aggregate Metrics

### Original Baseline Metrics

```json
{
  "aggregate": {
    "pass_rate": "14/18 (77.8%)",
    "converged_count": 14,
    "failed_count": 4,
    "avg_iterations": 2.3,
    "avg_final_score": 88.0
  }
}
```

### Expected Updated Baseline Metrics

```json
{
  "aggregate": {
    "pass_rate": "15/18 (83.3%)",  // +5.5%
    "converged_count": 15,  // +1
    "failed_count": 3,  // -1
    "avg_iterations": 2.2,  // -0.1
    "avg_final_score": 90.3  // +2.3 (from 88.0)
  }
}
```

### Fixtures Expected to Improve

1. ✅ **lyrics_verses**: 0% → 95-100% (+95-100% points)
2. 🔮 **nested_tuplets**: 98.1% → 98.5-100% (potential minor improvement)
3. 🔄 **full_orchestra**: 96.3% → 96.5-97% (potential minor improvement)

### Fixtures Unchanged (Expected to remain at 100%)

- annotations, clef_changes, complex_rhythm, dynamics_hairpins, key_changes
- marching_stickings, mixed_meters, multi_voice, ornaments
- piano_chords, repeats_codas, simple_melody, solo_with_accompaniment, title_metadata

### Fixtures Unchanged (Expected to remain at 0%)

- 🔄 **empty_score**: 0% → 0% (JSON truncation requires separate fix)

## Technical Details of Fix

### Problem Statement

The #1 most common failure mode across all fixtures was `duration_errors` (17 occurrences), 
but the most critical blocker was the lyrics_verses build crash.

### Root Cause

When Claude Vision API returns nested dict structures for note attributes:

```json
{
  "lyrics": [{"text": {"en": "Hello"}, "syllabic": {"value": "begin"}}]
}
```

The code attempted to assign these dict values directly to lxml `.text` attributes:

```python
etree.SubElement(lyric, "text").text = lyric_item.get("text")  # lyric_text is a dict!
```

This caused: `ValueError: Argument must be bytes or unicode, got 'dict'`

### Solution

Added defensive type checking in `core/musicxml_builder.py` `_build_note()`:

1. **Lyrics handling** (lines 196-213): Extract string values from nested dicts
2. **Beam handling** (lines 159-165): Convert dict beam values to strings
3. **Dynamic handling** (lines 189-197): Extract actual dynamic values from dicts

### Code Pattern

```python
# Instead of:
value = item.get("key")  # May return dict

# Use:
value = item.get("key")
if isinstance(value, dict):
    value = str(value)  # Defensive: convert to string
```

## Files Modified

- `core/musicxml_builder.py`: 3 sections updated with defensive type checking

## Verification

Unit test passed all edge cases:
- ✓ Nested dict lyrics converted to strings
- ✓ Dict beam values converted to strings
- ✓ Dict dynamic values extracted and converted

## Next Action

Once baseline test completes:
1. Update baseline_results.json with actual before/after metrics
2. Commit updated baseline_results.json
3. Push feature/pipeline-hardening branch for review

---

*Generated: 2026-04-06*
