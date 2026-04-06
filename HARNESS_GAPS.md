# ScoreForge Harness — Gap Analysis
_Written: 2026-03-29 | Lyra Chen_

## Summary

The harness infrastructure is largely sound. Rendering works (verovio-python ✓), all 17
fixtures resolve, corpus PDFs are discoverable, and the `--no-api` smoke-path completes
cleanly. The blockers below are **correctness gaps** — issues that will cause misleading
results as soon as API calls resume on April 2.

---

## Critical Gaps (will produce wrong scores)

### 1. Duration comparison is NOT normalized for `divisions`
**File:** `core/comparator.py` — `_parse_note_element`, `_compare_measures`

**Problem:** Raw `<duration>` values are compared directly. Ground-truth fixtures use
`divisions=10080` (a whole note = `40320`). The extractor emits `divisions=1` by default
(a whole note = `4`). Even for perfectly-correct rhythm, every duration comparison will
fail because `40320 ≠ 4`.

**Fix needed:** Normalize each note's duration to beats:
```
normalized_duration = raw_duration / divisions_per_quarter
```
Then compare normalized values, or compare the `<type>` string + dot count instead of
raw duration integers.

**Impact:** `rhythm_accuracy` will report ~0% for all tests until fixed. The `overall`
score will cap at roughly 50% (pitch half) even on perfect extraction.

---

### 2. Multi-voice comparison is naively positional (cross-voice matching)
**File:** `core/comparator.py` — `_compare_measures`

**Problem:** Notes from all voices are compared sequentially by list index. For
`multi_voice.musicxml` measure 1, the parsed list is:
```
[C5(v1), C#5(v1), D5(v1), Eb5(v1), E4(v2), rest(v2)]
```
If the extractor outputs voice 2 first (or in any different ordering), every note
comparison produces a false mismatch. Multi-voice scores will never pass even if the
content is correct.

**Fix needed:** Group notes by `voice` before comparing, then compare voice-by-voice:
```python
gt_by_voice = group_by(gt_notes, key=lambda n: n["voice"])
ex_by_voice = group_by(ex_notes, key=lambda n: n["voice"])
for voice in set(gt_by_voice) | set(ex_by_voice):
    compare_voice(gt_by_voice.get(voice, []), ex_by_voice.get(voice, []))
```

**Impact:** All multi-voice, grand-staff piano, and orchestral fixtures will report near-0%
even on correct extraction.

---

### 3. `is_perfect` doesn't require correct key/time signatures
**File:** `core/comparator.py` — `compare_musicxml_semantic`

**Problem:** The `is_perfect` condition is:
```python
result["is_perfect"] = (
    total_notes_correct == total_notes
    and total_pitches_correct == total_pitches
    and total_durations_correct == total_notes
    and result["part_count_match"]
)
```
A score with every pitch and duration correct but the wrong key signature (e.g., G major
rendered as C major) will still be marked "perfect". This is semantically wrong — a
key signature determines which accidentals are implicit and affects playback.

**Fix needed:** Add to `is_perfect`:
```python
and (total_key_checks == 0 or total_key_correct == total_key_checks)
and (total_time_checks == 0 or total_time_correct == total_time_checks)
```

---

## Medium Gaps (missing coverage)

### 4. Ornaments not compared at all
**File:** `core/comparator.py` — `_parse_note_element`

`<notations>/<ornaments>` (trill, turn, mordent, tremolo) are not parsed. The
`ornaments.musicxml` fixture tests trill-mark, turn, mordent, inverted-mordent, and
tremolo. The semantic score will show pitch/rhythm as 100% even if all ornaments are
missing from extraction — providing false confidence.

**Fix needed:** Parse `<notations>/<ornaments>` and score ornament presence separately.
Add an `ornament_accuracy` subscores to `result["scores"]`.

---

### 5. Grace notes not scored
**File:** `core/comparator.py` — `_compare_measures`

`is_grace` is parsed but comparison logic ignores it. Grace notes appear in
`ornaments.musicxml` and real-world Baroque/Classical repertoire. A missing grace note
is not penalized.

**Fix needed:** Count grace notes separately in the scoring model.

---

### 6. No "empty score" edge case fixture
**File:** `tests/fixtures/`

There is no fixture testing the edge case where extraction returns 0 notes. This is the
most common failure mode when Claude returns malformed JSON or the image is blank/unrecognizable.

**Fix needed:** Add `empty_score.musicxml` (a valid but note-empty score) and a
corresponding negative-path test that verifies `build_musicxml()` handles 0 notes without
crashing, and the comparator correctly reports 0% recall.

---

### 7. `BUILT_IN_TESTS` only covers 3 of 17 fixtures
**File:** `test_harness.py`

The 14 auto-discovered fixtures (`mixed_meters`, `nested_tuplets`, `ornaments`, etc.)
have no descriptions, difficulty ratings, or tags. They run correctly but produce minimal
metadata in reports, making it hard to triage failures by complexity.

**Fix needed:** Promote all 17 fixtures to `BUILT_IN_TESTS` with descriptions. See
`TEST_CASES.md` for the reference data.

---

## Minor Gaps (polish / correctness)

### 8. `--no-api` mode shows ERROR for all fixtures
**File:** `test_harness.py` — `run_test`

When `skip_api=True`, the function sets `result.error = "Skipped (--no-api)"` and returns.
The report then treats this as an ERROR (red) rather than SKIPPED (yellow/grey). The
render step may have succeeded — this is a false ERROR.

**Fix needed:** Set `result.error = None` and add a `result.skipped = True` flag so the
report can distinguish SKIPPED from ERROR.

---

### 9. Corpus `moderate/`, `complex/`, `orchestral/` tiers are empty
**File:** `corpus/originals/`

Only `simple/` has PDFs (5 files). The other three tiers are empty directories. The
corpus gate (≥70% parse success) only tests against the 5 simple PDFs.

**Fix needed before April 2:** Seed at least 2-3 PDFs per tier so the gate is
meaningful. Good sources: IMSLP (public domain), MuseScore sample files.

---

### 10. Renderer hardcodes macOS paths (`/opt/homebrew/bin/verovio`, `/opt/local/bin/rsvg-convert`)
**File:** `core/renderer.py`

`VEROVIO_BIN` and `RSVG_BIN` point to Homebrew/MacPorts paths. On Linux (the Hetzner
server), these paths don't exist. The code falls through to PATH search and then to
verovio-python, which works — but is slower and produces slightly different output than
the CLI. Confirmed: `verovio-python` renders correctly on the current host.

**Status:** Working via fallback. Not blocking.

---

## Dependency Status

| Package | Version | Status |
|---------|---------|--------|
| anthropic | 0.78.0 | ✅ Current (0.39+ required) |
| music21 | 9.9.1 | ✅ |
| verovio (python) | 6.1.0 | ✅ Renders correctly |
| Pillow | (installed) | ✅ |
| numpy | (installed) | ✅ |
| imagehash | (installed) | ✅ |
| lxml | (installed) | ✅ |
| click, rich | (installed) | ✅ |
| cairosvg | (installed) | ✅ SVG→PNG fallback works |
| verovio (CLI) | NOT FOUND | ⚠️ Fallback active, lower perf |
| rsvg-convert | NOT FOUND | ⚠️ cairosvg fallback active |

All Python deps are installed and importable. No `pip install` needed before April 2.

---

## Priority Order for Fixes

1. **[Critical]** Duration normalization — fix before first API run
2. **[Critical]** Multi-voice grouping — fix before multi-voice fixtures are run
3. **[Critical]** `is_perfect` key/time requirement
4. **[Medium]** Add empty score fixture
5. **[Medium]** Ornament scoring
6. **[Low]** `--no-api` SKIPPED display
7. **[Low]** Promote all fixtures to BUILT_IN_TESTS
