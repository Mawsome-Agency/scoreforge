# ScoreForge Baseline Accuracy Report
_Generated: 2026-04-13 | Comparator: post-fix (duration normalization, voice grouping, ornament scoring)_
_Note: Extractions are from April 11 runs (before model config fix, DETAIL_PROMPT fix, divisions fix). Re-extraction needed after API rate limit reset._

## Summary

- **Fixtures >= 95%**: 1 / 18
- **Average overall accuracy**: 34.0%

## Per-Fixture Results

| Fixture | Overall | Pitch | Rhythm | Note | Voice | Key Sig | Perfect |
|---------|---------|-------|--------|------|-------|---------|--------|
| annotations | 0.0% | 0.0% | 0.0% | 75.0% | 100.0% | 100% | no |
| clef_changes | 39.1% | 28.6% | 25.0% | 50.0% | 100.0% | 100% | no |
| complex_rhythm | 38.1% | 16.7% | 27.3% | 54.5% | 100.0% | 100% | no |
| dynamics_hairpins | 31.0% | 0.0% | 33.3% | 91.7% | 100.0% | 100% | no |
| empty_score | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100% | YES |
| full_orchestra | 0.0% | 0.0% | 0.0% | 62.5% | 62.5% | 100% | no |
| key_changes | 58.3% | 0.0% | 100.0% | 100.0% | 100.0% | 83% | no |
| lyrics_verses | 40.0% | 0.0% | 50.0% | 50.0% | 100.0% | 100% | no |
| marching_stickings | 5.9% | 100.0% | 0.0% | 25.0% | 100.0% | 100% | no |
| mixed_meters | 34.1% | 16.7% | 52.6% | 84.2% | 100.0% | 100% | no |
| multi_voice | 28.2% | 17.6% | 22.2% | 77.8% | 87.5% | 100% | no |
| nested_tuplets | 9.8% | 13.3% | 0.0% | 62.5% | 100.0% | 100% | no |
| ornaments | 12.5% | 0.0% | 0.0% | 16.7% | 100.0% | 100% | no |
| piano_chords | 14.3% | 0.0% | 10.0% | 30.0% | 80.0% | 100% | no |
| repeats_codas | 25.0% | 50.0% | 0.0% | 25.0% | 100.0% | 100% | no |
| simple_melody | 72.6% | 30.4% | 95.7% | 100.0% | 100.0% | 100% | no |
| solo_with_accompaniment | 33.3% | 40.0% | 0.0% | 100.0% | 83.3% | 100% | no |
| title_metadata | 69.4% | 31.2% | 100.0% | 100.0% | 100.0% | 100% | no |

## Top Failure Modes

1. **Pitch accuracy** (0-50% across most fixtures) — primary blocker for 95%+ overall
2. **Rhythm accuracy** (0-100%, wildly variable) — second priority
3. **Complex notation** (tuplets, ornaments, percussion) — nearly 0% accuracy
