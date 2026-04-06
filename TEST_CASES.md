# ScoreForge Corpus Validation — Test Case Reference
_Written: 2026-03-29 | Lyra Chen_

Each entry documents: fixture file, what's being tested, expected extraction behavior,
known comparator gotchas, and pass/fail criteria. Use this as the authoritative reference
when interpreting harness results after April 2.

---

## TC-01: simple_melody
**File:** `tests/fixtures/simple_melody.musicxml`
**Difficulty:** Easy
**Tags:** `single_staff`, `no_accidentals`, `basic_rhythm`

**Score:** C major, 4/4, 8 measures, treble clef only.
Content: quarter notes and half notes, no accidentals, no chords.

**Expected extraction:**
- `part_count`: 1
- `measure_count`: 8
- `key_signature`: `{fifths: 0, mode: "major"}` in measure 1
- `time_signature`: `{beats: 4, beat_type: 4}` in measure 1
- Note types: `quarter`, `half` only
- `pitch_accuracy`: 100%
- `rhythm_accuracy`: 100% (after divisions normalization fix)
- `overall`: 100%

**Pass criteria:** `is_perfect = true`. Baseline fixture — if this fails, there's a
fundamental problem with the extraction or comparison pipeline.

**Gotchas:** None. Used as the smoke-test for "is the API working at all."

---

## TC-02: piano_chords
**File:** `tests/fixtures/piano_chords.musicxml`
**Difficulty:** Medium
**Tags:** `grand_staff`, `chords`, `dotted_notes`

**Score:** G major (1 sharp), 3/4, 4 measures. Piano grand staff (treble + bass).
Content: chords (3-4 notes stacked), dotted quarter notes.

**Expected extraction:**
- `part_count`: 1, `staves`: 2
- `key_signature`: `{fifths: 1, mode: "major"}`
- `time_signature`: `{beats: 3, beat_type: 4}`
- Chord notes: `is_chord=true` for all stacked notes after first
- Staff assignment: staff=1 treble, staff=2 bass
- `dot_count`: 1 for dotted notes
- `pitch_accuracy`: ≥95% (chord stacking is a common miss)

**Pass criteria:** `overall ≥ 90%`. Grand-staff voice assignment is the key challenge.

**Gotchas:**
- The comparator's multi-voice bug (Gap #2) will cause staff-2 notes to be compared
  against wrong staff-1 notes. Fix voice-grouping before running this.
- The `alter` field for F# (key sig) must be `0` (not 1) since the sharp is implied
  by key sig and not written as an explicit accidental on the note.

---

## TC-03: complex_rhythm
**File:** `tests/fixtures/complex_rhythm.musicxml`
**Difficulty:** Hard
**Tags:** `compound_meter`, `ties`, `accidentals`, `beams`

**Score:** Bb major (2 flats), 6/8, 4 measures.
Content: dotted eighth + sixteenth patterns, tied notes across barlines, Bb/Eb accidentals.

**Expected extraction:**
- `key_signature`: `{fifths: -2, mode: "major"}` (Bb major = 2 flats)
- `time_signature`: `{beats: 6, beat_type: 8}`
- `dot_count`: 1 for dotted eighths
- `tie_start/stop`: correctly paired across measure boundary
- Beam groupings: `begin`/`continue`/`end` on eighth/sixteenth runs
- `pitch_accuracy`: ≥90% (accidental application is error-prone)

**Pass criteria:** `overall ≥ 85%`. Rhythm complexity makes this the hardest of the
baseline three.

**Gotchas:**
- 6/8 duration math: 6 eighth notes per measure. With `divisions=1`, a beat is `0.5`
  (not integer). The extractor may use `divisions=2` to keep integers. Normalization
  must handle fractional beats.
- Ties: the comparator checks `tie_start` at note level. Claude often misses tie-stop
  on the second note of a cross-barline tie.
- Beam data is NOT currently compared by the semantic comparator (only checked visually).

---

## TC-04: mixed_meters
**File:** `tests/fixtures/mixed_meters.musicxml`
**Difficulty:** Hard
**Tags:** `time_sig_changes`, `7/8`, `5/4`, `irregular_grouping`

**Score:** 4 measures with alternating unusual time signatures (7/8, 5/4, etc.), no key
signature (C major / atonal context).

**Expected extraction:**
- Time signature changes on EACH measure (not just measure 1)
- Each measure has a different `{beats, beat_type}` — extractor must update per measure
- Duration totals per measure must match the indicated time sig
- `time_sig_accuracy`: 100% (each change must be caught)

**Pass criteria:** `time_sig_accuracy = 100%`, `overall ≥ 80%`.

**Gotchas:**
- Claude frequently assumes 4/4 when a non-standard time sig is ambiguous visually.
- Duration normalization is especially important here — 7/8 with `divisions=1` means
  total_beats = 3.5 (not integer). Extractor needs `divisions=2` for clean values.
- The comparator only checks time sig in measures where the XML has a `<time>` element.
  If GT has it every measure but extraction only writes it in measure 1, the check
  only fires once, masking the other three changes.

---

## TC-05: multi_voice
**File:** `tests/fixtures/multi_voice.musicxml`
**Difficulty:** Hard
**Tags:** `two_voice`, `backup_element`, `counterpoint`, `chord_vs_voice`

**Score:** 4/4, 4 measures. Measure 1: voice 1 = C5 C#5 D5 Eb5 (quarters); voice 2 = E4
(half) + half rest. Measures 2-4: 4-note whole-note chords (C major root position).

**Expected extraction:**
- Measure 1: 6 notes total, voices [1,1,1,1,2,2]
- Voice 2 half rest must be present (even if `print-object="no"`)
- Measures 2-4: chord blocks with `is_chord=true` for stacked notes
- `voice` assignment must match: stem-up = voice 1, stem-down = voice 2

**Pass criteria:** `overall ≥ 85%` AFTER voice-grouping fix is applied (Gap #2).
Without the fix, expected score is ~30% due to positional mismatch.

**Gotchas:**
- The `<backup>` element resets the beat position for voice 2. The extractor MUST
  recognize this to assign voices correctly.
- Print-object="no" rests: the GT has a hidden half rest in voice 2. The extractor may
  omit it (treating it as invisible). This will cause a note-count mismatch but should
  NOT fail the test — hidden rests are acceptable to omit.
- Chord vs. voice: measures 2-4 have chords without explicit `<voice>` elements.
  This is correct MusicXML — voice defaults to 1 for all chord notes.

---

## TC-06: ornaments
**File:** `tests/fixtures/ornaments.musicxml`
**Difficulty:** Medium
**Tags:** `trill`, `turn`, `mordent`, `tremolo`, `notations`

**Score:** 4/4, 4 measures, C major. Each measure has a whole or half note with a
different ornament: trill-mark, turn, mordent, inverted-mordent, tremolo (single, 3
beams).

**Expected extraction (current capability):**
- Pitch and duration: 100% (notes themselves are simple)
- Ornament symbols: Extractor's `grace` and `articulation` fields capture some markings,
  but `<ornaments>` (trill, turn, mordent) are not in the current extraction schema

**Pass criteria (CURRENT):** `pitch_accuracy = 100%`, `rhythm_accuracy = 100%`.
Ornament presence is not yet scored by the comparator (Gap #4). Do NOT mark as failed
due to missing ornaments — this is a known limitation.

**Pass criteria (POST-FIX):** Once ornament scoring is added, `ornament_accuracy ≥ 80%`.

**Gotchas:**
- Claude Vision reliably detects trills (written "tr~") and turns (~) visually.
  It less reliably distinguishes mordent from inverted-mordent.
- Tremolo (3 slashes through note stem) is the hardest — may be confused with beaming.

---

## TC-07: nested_tuplets
**File:** `tests/fixtures/nested_tuplets.musicxml`
**Difficulty:** Expert
**Tags:** `triplets`, `quintuplets`, `nested_tuplets`, `time_modification`

**Score:** 4/4, multiple measures. Contains triplets (3 notes in space of 2), quintuplets
(5 in space of 4), and possibly nested tuplets.

**Expected extraction:**
- `<time-modification>` elements on tuplet notes (not parsed by comparator yet)
- Duration values will NOT match GT raw integers due to tuplet modification
- The `type` strings (eighth, sixteenth) will match even if durations don't

**Pass criteria:** `pitch_accuracy ≥ 90%`. Duration/rhythm accuracy is EXPECTED to be
low (~40-60%) because the comparator does not yet handle tuplet normalization.
Do NOT mark this fixture as "failed harness" — it is a known comparator limitation.

**Gotchas:**
- This is the hardest fixture for Vision extraction. Claude frequently miscounts tuplet
  groups or assigns wrong note types to tuplet subdivisions.
- "Nested" tuplets (tuplet within a triplet) are very rare in real scores and very hard
  to extract. Expect ~50% accuracy.

---

## TC-08: key_changes
**File:** `tests/fixtures/key_changes.musicxml`
**Difficulty:** Medium
**Tags:** `key_sig_change`, `mid_piece_modulation`, `naturals`

**Score:** Multi-measure piece with key signature changes mid-piece (e.g., C major →
G major → D major or similar). Contains naturals as cancellation accidentals.

**Expected extraction:**
- Key signature MUST appear in the measure where it changes, not just measure 1
- `key_sig_accuracy` must catch each change
- Natural accidentals: `accidental="natural"` and `alter=0` on notes that would be
  sharpened by new key sig

**Pass criteria:** `key_sig_accuracy = 100%`, `overall ≥ 85%`.

**Gotchas:**
- Claude often extracts the first key and never updates it on modulation. Look for
  `key_sig_accuracy < 100%` as the failure signal.
- After a key change, previously-affected notes need accidentals cleared. The extractor
  tends to omit cancellation naturals.

---

## TC-09: full_orchestra
**File:** `tests/fixtures/full_orchestra.musicxml`
**Difficulty:** Expert
**Tags:** `multi_part`, `transposing_instruments`, `score_layout`

**Score:** Full orchestra score with multiple parts (strings, winds, brass, etc.).
May include transposing instruments (Bb clarinet, F horn).

**Expected extraction:**
- `part_count`: ≥ 4 (verify against fixture)
- Each part correctly identified with name
- Transposing parts: extractor should extract WRITTEN pitch, not concert pitch
- Part count mismatch is the primary failure mode

**Pass criteria:** `part_count_match = true`, `overall ≥ 70%` (lower bar due to complexity).

**Gotchas:**
- The comparator processes only `min(gt_parts, ex_parts)` — missing parts don't
  penalize the score directly. Watch `part_count_match` as a separate signal.
- Long orchestral scores may hit `max_tokens=16000` limit in the extractor. The
  extractor will truncate silently, leaving measures missing.
- Multi-page rendering: the Python verovio renderer stacks pages vertically. The
  resulting tall image may cause Claude to miss lower-page content.

---

## TC-10: repeats_codas
**File:** `tests/fixtures/repeats_codas.musicxml`
**Difficulty:** Medium
**Tags:** `repeat_barlines`, `volta_brackets`, `coda`, `segno`

**Score:** Short piece with repeat barlines, 1st/2nd endings (volta brackets), and
coda/segno navigation symbols.

**Expected extraction:**
- `barline_right.style`: `"light-heavy"` for final barline, repeat-specific styles
  for repeat barlines
- Volta brackets: NOT in the current extraction schema (not a blocker)
- Coda/segno text marks: NOT compared by semantic comparator

**Pass criteria:** `pitch_accuracy ≥ 90%`, `rhythm_accuracy ≥ 90%`. Structural/
navigation symbols are not scored yet — do not count as failures.

**Gotchas:**
- Repeat barlines look similar to double barlines visually. Claude may confuse them.
- The semantic comparator does NOT verify barline types — only note content is scored.

---

## TC-11: dynamics_hairpins
**File:** `tests/fixtures/dynamics_hairpins.musicxml`
**Difficulty:** Medium
**Tags:** `dynamics`, `hairpins`, `cresc`, `decresc`, `pp_ff`

**Score:** Piece with dynamic markings (pp, mp, f, ff) and crescendo/decrescendo hairpins.

**Expected extraction:**
- `dynamic` field on notes: "pp", "mp", "f", "ff"
- Hairpins: NOT in the current `Note` model or extraction schema
- Dynamics are extracted per-note but not scored by the comparator yet

**Pass criteria:** `pitch_accuracy = 100%`, `rhythm_accuracy = 100%`.
Dynamic accuracy is not yet scored — treat as informational.

---

## TC-12: lyrics_verses
**File:** `tests/fixtures/lyrics_verses.musicxml`
**Difficulty:** Medium
**Tags:** `lyrics`, `multi_verse`, `syllable_split`

**Score:** Vocal part with lyrics, multiple verses (verse 1 and 2 on same notes),
syllable hyphenation (hel-lo, etc.).

**Expected extraction:**
- `lyrics` array on each syllabified note
- Verse number in lyrics objects
- Syllable type (begin, middle, end)

**Pass criteria:** `pitch_accuracy = 100%`. Lyric accuracy is NOT compared by the
semantic comparator — do not penalize lyric omissions.

**Gotchas:**
- Vocal music often has slurs that Claude confuses with ties.
- Multi-verse lyrics may be truncated if the extractor only reads one verse.

---

## TC-13: clef_changes
**File:** `tests/fixtures/clef_changes.musicxml`
**Difficulty:** Medium
**Tags:** `mid_measure_clef`, `bass_clef`, `alto_clef`, `tenor_clef`

**Score:** Single staff with multiple clef changes (treble → bass → alto/tenor/etc.),
mid-measure or at barline.

**Expected extraction:**
- Clef must be updated in the correct measure when it changes
- Pitch values MUST be re-interpreted relative to the new clef
- Alto clef (C clef, line 3) = middle C on third line

**Pass criteria:** `pitch_accuracy ≥ 80%`. Clef changes are a known difficult case.

**Gotchas:**
- This is the most common pitch error in Claude extractions. After a clef change,
  pitch reading shifts by several staff positions.
- The comparator checks pitch step+octave+alter, so a clef misread (e.g., reading
  bass clef as treble) will show up as multiple wrong pitches in succession.

---

## TC-14: annotations
**File:** `tests/fixtures/annotations.musicxml`
**Difficulty:** Medium
**Tags:** `text_expressions`, `rehearsal_marks`, `tempo_text`

**Score:** Piece with text annotations (rehearsal letters A, B, C), tempo markings
(Allegro, Adagio), expression text (dolce, espressivo).

**Pass criteria:** `pitch_accuracy = 100%`, `rhythm_accuracy = 100%`.
Text annotations are not compared semantically.

---

## EDGE CASE: empty_score (TO BE CREATED)
**File:** `tests/fixtures/empty_score.musicxml` — **DOES NOT EXIST YET**
**Difficulty:** Edge case
**Tags:** `empty`, `zero_notes`, `error_handling`

**Score:** Valid MusicXML with one part, one measure, no notes (measures with only a
whole rest or truly empty).

**Expected extraction:**
- Should not raise an exception — `extract_from_image` must return a Score object
- `note_count`: 0 or 1 (if a whole rest is correctly extracted)
- `build_musicxml()` must not crash on empty/near-empty Score

**Pass criteria:** No exception raised. Score produces valid (parseable) MusicXML output.

**Why this matters:** The most common API-era failure is when Claude returns `{}` or
`{"parts": []}` due to unrecognizable input. The harness must not crash on this.

---

## Corpus PDF Tier Reference

_Updated 2026-03-29 — corpus populated during ZAI API downtime window._
_Full catalog and per-file challenge notes in `CORPUS_TEST_MATRIX.md`._

| Tier | Directory | PDFs | Gate | Status |
|------|-----------|------|------|--------|
| Simple | `corpus/originals/simple/` | 5 | ≥70% overall | ✅ Ready |
| Moderate | `corpus/originals/moderate/` | 5 | ≥70% overall | ✅ Ready |
| Complex | `corpus/originals/complex/` | 5 | ≥60% overall | ✅ Ready |
| Choral | `corpus/originals/choral/` | 2 | ≥60% pitch | ✅ Ready |
| Orchestral | `corpus/originals/orchestral/` | 2 | part_count match | ✅ Ready |
| Handwritten | `corpus/originals/handwritten/` | 0 | ≥40% pitch | ⚠️ Phase 2 |

**Moderate tier files:** Bach Invention 1 (BWV 772), WTC Prelude 1 (BWV 846),
Für Elise (WoO 59), Chopin Prelude Op. 28 No. 4, Mozart K. 545 Mvt 1.

**Run order for April 2:** simple → moderate → complex/chopin-prelude-28-20 (gold
standard chord test) → choral → remaining complex → orchestral (pages 1-3 only).

---

## Scoring Reference

| Score | Interpretation |
|-------|---------------|
| 100% | Perfect round-trip |
| 95-99% | Minor errors (1-2 missed notes, wrong accidental) |
| 85-94% | Good extraction (some rhythm or pitch errors) |
| 70-84% | Acceptable for simple scores, investigate for complex |
| 50-69% | Systematic failure (wrong key, clef, or divisions bug) |
| <50% | Pipeline error — check comparator gaps, not just extraction |
