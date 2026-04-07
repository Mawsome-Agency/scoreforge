# ScoreForge OMR Test Corpus Matrix
_Lyra Chen — Compiled 2026-03-29 (ZAI API offline, resumes 2026-04-02)_

This document catalogues the full test corpus for end-to-end OMR validation. It covers:
- **Synthetic fixtures** (TC-01 through TC-14 in `TEST_CASES.md`) — MusicXML ground-truth
- **Real PDF corpus** (this document) — public domain PDFs for image-to-MusicXML pipeline testing

Real PDF tests require a running ZAI API. Run these on April 2+ using:
```bash
python3 run_test.py --corpus --tier moderate
```

---

## Dataset Sources

| Source | License | URL | Notes |
|--------|---------|-----|-------|
| **Mutopia Project** | CC0 / LGPL | https://www.mutopiaproject.org/ | Primary source. Direct PDF downloads. LilyPond-rendered, clean notation. |
| **IMSLP** | Public Domain / CC | https://imslp.org/ | Largest repository. PDFs require manual download (download-gate page). Best for handwritten facsimiles. |
| **OpenScore** | CC0 | https://openscore.cc/ | High-quality MuseScore-based editions. MusicXML ground truth also available. |
| **MuseScore Community** | Various | https://musescore.com/ | Community scores. Variable quality. Good for "real world messy" tests. |
| **Choral Public Domain Library (CPDL)** | Free | https://www.cpdl.org/ | SATB choral repertoire. Good for vocal+lyrics tests. |

---

## Corpus Directory Layout

```
corpus/originals/
├── simple/          # 1-page, single staff, clean notation, 0-1 flats/sharps
├── moderate/        # 1-3 pages, grand staff, moderate complexity
├── complex/         # 3-6 pages, multi-voice, ornaments, complex rhythm
├── orchestral/      # Multi-instrument, transposing, full score or parts
├── choral/          # SATB, lyrics, vocal notation
└── handwritten/     # Manuscript facsimiles, low-quality scans (to be added)
```

---

## Tier 1: Simple

**Gate:** ≥70% parse accuracy on all metrics. Baseline sanity — if these fail, extraction pipeline is broken.

| ID | File | Composer | Work | Pages | Key | Time | Key Challenges |
|----|------|----------|------|-------|-----|------|----------------|
| CP-S01 | `simple/bluemtns-a4.pdf` | Traditional | "Blue Mountains" | 1 | C maj | 4/4 | Syllabic lyrics, simple melody |
| CP-S02 | `simple/giselle-a4.pdf` | Adam | Giselle excerpt | 1 | — | — | Piano reduction, moderate chords |
| CP-S03 | `simple/minuit_chretiens-a4.pdf` | Adam | O Holy Night | 1 | — | 12/8 | Compound meter, vocal line |
| CP-S04 | `simple/swallows-a4.pdf` | Traditional | Swallows folk song | 1 | — | — | Single melody, clean notation |
| CP-S05 | `simple/Vocalise1-a4.pdf` | — | Vocalise | 1 | — | — | Simple vocalise exercise |

**Expected accuracy gate:** `overall ≥ 70%`, `pitch_accuracy ≥ 80%`

---

## Tier 2: Moderate

**Gate:** ≥70% overall, ≥80% pitch. Covers grand staff, dotted notes, basic ornamentation.

| ID | File | Composer | Work | Pages | Key | Time | Key Challenges |
|----|------|----------|------|-------|-----|------|----------------|
| CP-M01 | `moderate/bach-invention-01-a4.pdf` | J.S. Bach | Two-Part Invention No. 1, BWV 772 | 1 | C maj | 4/4 | Two independent voices, imitative counterpoint, no key sig |
| CP-M02 | `moderate/wtk1-prelude1-a4.pdf` | J.S. Bach | WTC Book I Prelude No. 1, BWV 846 | 1 | C maj | 4/4 | Arpeggiated chords, grand staff, no melodic line — all harmony |
| CP-M03 | `moderate/fur_Elise_WoO59-a4.pdf` | Beethoven | Für Elise, WoO 59 | 3 | A min | 3/8 | Grace notes, triplet arpeggios, repeat structure, key change to F maj |
| CP-M04 | `moderate/chopin-prelude-28-4-a4.pdf` | Chopin | Prelude Op. 28 No. 4 in E minor | 1 | E min | 4/4 | Melody in treble + sustained chords in bass, dotted rhythms |
| CP-M05 | `moderate/mozart-K545-1-a4.pdf` | Mozart | Piano Sonata K. 545, Mvt 1 | 2 | C maj | 4/4 | Alberti bass accompaniment, ornamental trill, standard classical form |

**Source:** All from Mutopia Project (CC0)
- CP-M01: https://www.mutopiaproject.org/ftp/BachJS/BWV772/bach-invention-01/
- CP-M02: https://www.mutopiaproject.org/ftp/BachJS/BWV846/wtk1-prelude1/
- CP-M03: https://www.mutopiaproject.org/ftp/BeethovenLv/WoO59/fur_Elise_WoO59/
- CP-M04: https://www.mutopiaproject.org/ftp/ChopinFF/O28/Chop-28-4/
- CP-M05: https://www.mutopiaproject.org/ftp/MozartWA/KV545/K545-1/

### CP-M01 — Bach Invention No. 1
**OMR Challenges:**
- Two completely independent voices on separate staves — voice assignment critical
- Imitative counterpoint: same motif appears in both hands — ordering matters
- No key signature, but C major context; no accidentals at all
- Sixteenth note runs require precise beam grouping
- Good regression test for grand staff voice separation (Gap #2 from HARNESS_GAPS.md)

### CP-M02 — WTC Book I Prelude No. 1
**OMR Challenges:**
- No melodic line whatsoever — pure harmonic arpeggios
- Each beat is the same 5-note arpeggio pattern (C-E-G-C-E etc.) — pitch accuracy test
- High note density (~200 notes per page)
- Grand staff with clear staff-1 / staff-2 assignment
- Common OMR failure: duplicating notes across staves

### CP-M03 — Für Elise
**OMR Challenges:**
- Grace note (the famous appoggiatura in bar 1) — must appear as `<grace/>` in MusicXML
- 3/8 time: compound subdivision interacts with triplet figuration in middle section
- Section A: simple A minor; Section B: F major (key change mid-piece)
- Repeat barlines and D.C. structure
- Several register shifts across 3 pages — top-of-page context loss

### CP-M04 — Chopin Prelude Op. 28 No. 4
**OMR Challenges:**
- Right hand: simple descending melody in long notes
- Left hand: chromatic inner voices moving against static melody
- Dotted-rhythm interplay between voices
- Harmonic rhythm dense — many chords with altered tones
- pp dynamic with hairpin to ppp at end — dynamics test

### CP-M05 — Mozart K. 545 Mvt 1
**OMR Challenges:**
- Classic Alberti bass: C-G-E-G pattern repeated — repetition detection
- Trill ornament on bar 6 — `<ornaments>` extraction
- Binary form: exposition (C major) then development/recap
- 2 pages = cross-page note continuity
- Fairly clean notation — should be near-baseline accuracy

---

## Tier 3: Complex

**Gate:** ≥60% overall, ≥70% pitch. Involves ornaments, complex rhythm, multi-voice on single stave.

| ID | File | Composer | Work | Pages | Key | Time | Key Challenges |
|----|------|----------|------|-------|-----|------|----------------|
| CP-C01 | `complex/chopin-prelude-28-20-a4.pdf` | Chopin | Prelude Op. 28 No. 20 in C minor | 1 | C min | 4/4 | Dense 4-voice homophony, all chords, ppp to pp dynamics |
| CP-C02 | `complex/chopin_nocturne_op9_n2-a4.pdf` | Chopin | Nocturne Op. 9 No. 2 in Eb major | 4 | Eb maj | 12/8 | Ornamental runs (triplet-in-triplet), hairpins, compound meter, 3+ pages |
| CP-C03 | `complex/bach-invention-13-a4.pdf` | J.S. Bach | Two-Part Invention No. 13, BWV 784 | 1 | A min | 3/4 | Chromatic voice-leading, syncopated cross-beat ties |
| CP-C04 | `complex/bach-sinfonia-bwv787-a4.pdf` | J.S. Bach | Sinfonia No. 1, BWV 787 | 1 | C maj | 4/4 | Three independent voices (soprano, alto, bass) on two staves |
| CP-C05 | `complex/mozart-alla-turca-KV331-a4.pdf` | Mozart | Rondo alla Turca, K. 331 | 3 | A min | 2/4 | Ornamental grace-note figures, repeated 16th runs, mid-section key change to A maj |

**Source:** All from Mutopia Project (CC0)
- CP-C01: https://www.mutopiaproject.org/ftp/ChopinFF/O28/Chop-28-20/
- CP-C02: https://www.mutopiaproject.org/ftp/ChopinFF/O9/chopin_nocturne_op9_n2/
- CP-C03: https://www.mutopiaproject.org/ftp/BachJS/BWV784/bach-invention-13/
- CP-C04: https://www.mutopiaproject.org/ftp/BachJS/BWV787/bwv787/
- CP-C05: https://www.mutopiaproject.org/ftp/MozartWA/KV331/KV331_3_RondoAllaTurca/

### CP-C01 — Chopin Prelude Op. 28 No. 20
**OMR Challenges:**
- Entirely chords, 4 voices simultaneously — very high chord density
- C minor / Eb major alternation within 13 bars
- Dotted quarter + eighth rhythmic pattern throughout
- Only 13 bars total — extremely short, zero tolerance for extraction errors
- Perfect accuracy test for homophonic texture
- **Gold standard test:** if ZAI gets this wrong, chord extraction is broken

### CP-C02 — Chopin Nocturne Op. 9 No. 2
**OMR Challenges:**
- Triplet subdivision within 12/8 compound meter = nested tuplets
- Ornamental "runs" that span many notes with complex beam/flag notation
- Hairpin crescendi and decrescendi spanning multiple bars
- Lyrical right-hand melody against left-hand "oom-pah" accompaniment
- 4 pages = most context-window pressure of any current corpus entry
- Eb major (3 flats) + multiple chromatic alterations
- **Hardest real-score test for ZAI.** Expect 50-70% accuracy initially.

### CP-C03 — Bach Invention No. 13
**OMR Challenges:**
- A minor with chromatic passing tones (C#, G#, F#, etc.)
- Cross-beat syncopation: tied notes spanning barlines in both voices
- Imitative entries at different rhythmic offsets — voice ordering test
- 3/4 time with dotted rhythms overlapping with 3/8 feel
- Compact notation (2 systems per page) — spacing may affect vision model

### CP-C04 — Bach Sinfonia No. 1 (3-Voice)
**OMR Challenges:**
- Three independent voices distributed across two staves (grand staff)
- Voice 1: soprano (treble staff); Voice 2: alto (treble staff); Voice 3: bass (bass staff)
- `<backup>` element usage for multiple voices on same staff
- MusicXML requires explicit `<voice>` elements for each note group
- This is the **real-score equivalent of TC-05** (multi_voice synthetic fixture)

### CP-C05 — Mozart Alla Turca
**OMR Challenges:**
- Grace note ornamental figures (quick Bb-A grace before main note) throughout
- Rapid 16th note passages — note type accuracy under speed
- "Turkish" grace note idiom: multiple grace notes before beat
- A minor → A major key change (parallel minor/major shift)
- Repeat structure with different endings (1st/2nd volta)
- 3 pages — moderate multi-page load

---

## Tier 4: Choral (SATB)

**Gate:** ≥60% pitch, ≥60% rhythm. Lyrics not compared yet (known gap). Voice assignment critical.

| ID | File | Composer | Work | Pages | Key | Time | Key Challenges |
|----|------|----------|------|-------|-----|------|----------------|
| CP-CH01 | `choral/bach-chorale-BWV277-a4.pdf` | J.S. Bach | "Christ lag in Todes Banden" BWV 277 | 1 | E min | 4/4 | 4-part SATB on 2 staves, hymn text, voice-leading chromatics |
| CP-CH02 | `choral/bach-chorale-BWV264-a4.pdf` | J.S. Bach | Chorale BWV 264 | 1 | G maj | 4/4 | 4-part SATB, figured bass symbols, standard Bach chorale texture |

**Source:** Mutopia Project (CC0)
- CP-CH01: https://www.mutopiaproject.org/ftp/BachJS/BWV277/Bach_ChristLag/
- CP-CH02: https://www.mutopiaproject.org/ftp/BachJS/BWV264/bwv-264/

### CP-CH01 — Bach Chorale BWV 277
**OMR Challenges:**
- SATB on 2 staves: Soprano+Alto on treble, Tenor+Bass on bass
- Each staff carries 2 voices — requires `<voice>` disambiguation
- Soprano and alto stems go up/down simultaneously on same staff
- Hymn text (German) under soprano — lyric extraction test
- Chromatic voice-leading in inner parts (typical Bach harmony)
- Short (16-24 bars) — zero tolerance for barline miscounting

### CP-CH02 — Bach Chorale BWV 264
**OMR Challenges:**
- Same 4-part layout as CP-CH01
- G major — slightly different voice range expectations
- Longer phrase structure than CP-CH01
- Tests that extraction handles multiple chorales consistently

---

## Tier 5: Orchestral

**Gate:** `part_count_match = true`, ≥50% overall. Multi-page, multi-instrument context.

| ID | File | Composer | Work | Pages | Instruments | Key Challenges |
|----|------|----------|------|-------|-------------|----------------|
| CP-O01 | `orchestral/beethoven-sym5-op67-a4.pdf` | Beethoven | Symphony No. 5 Op. 67 (full score) | ~50 | Full orch (Fl, Ob, Cl, Fg, Hn, Tp, Timp, Str) | Multi-system layout, transposing instruments (Cl in Bb, Hn in Eb), page count hits context limit |
| CP-O02 | `orchestral/bach-bwv1041-violin-solo-a4.pdf` | J.S. Bach | Violin Concerto in A minor BWV 1041, Violin Solo Part | 4 | Violin solo | Single-instrument part, rapid 16th passages, double-stops, bow markings |

**Source:** Mutopia Project (CC0)
- CP-O01: https://www.mutopiaproject.org/ftp/BeethovenLv/O67/beethoven_fifth_op67/
- CP-O02: https://www.mutopiaproject.org/ftp/BachJS/BWV1041/bach-bwv1041-part-violin-solo/

### CP-O01 — Beethoven Symphony No. 5 (Full Score)
**OMR Challenges:**
- ~50 pages — FAR exceeds max_tokens=16000 extractor limit (see TC-09 gotchas)
- Use only pages 1-3 (first movement opening) for initial test runs:
  ```bash
  python3 run_test.py --corpus --file orchestral/beethoven-sym5-op67-a4.pdf --pages 1-3
  ```
- Transposing instruments: Clarinet in Bb (sounds M2 lower), Horn in Eb (sounds M6 lower)
- Extractor should extract **written** pitch, not concert pitch
- Fermata on bars 5-6 — articulation extraction test
- `pp` to `sf` (sforzando) dynamic contrast — dynamics extraction
- 8+ simultaneous parts — `part_count` and `part_name` extraction critical

### CP-O02 — Bach Violin Concerto Solo Part
**OMR Challenges:**
- Single instrument — simpler part_count (should be 1)
- Rapid 16th note runs testing pitch accuracy at high density
- Ornamental trills (tr) and mordents in baroque style
- Double-stops (two notes on one bow) — chord detection in single-line instrument
- Bow markings (slur) vs tie — must distinguish visual slur from tie
- 4 pages = multi-page test without full score complexity

---

## Tier 6: Handwritten / Degraded Quality (TO BE ADDED)

These test cases require manual download from IMSLP facsimile collections.
**Priority: Medium — add before April 2 if time allows, otherwise Phase 2.**

| ID | Source | Work | Why It's Valuable |
|----|--------|------|-------------------|
| CP-HW01 | IMSLP Mozart autograph | Mozart K. 331 autograph manuscript | Tests handwritten baroque notation recognition |
| CP-HW02 | IMSLP Bach autograph | Bach BWV 772 Invention autograph | Compare against clean CP-M01 — same score, different quality |
| CP-HW03 | Low-resolution scan | Any (simulate with imagemagick blur) | Tests performance degradation with scan quality |

**Download links (require IMSLP account or anonymous delay):**
- Mozart K. 331 autograph: https://imslp.org/wiki/Piano_Sonata_No.11_in_A_major,_K.331/385i_(Mozart,_Wolfgang_Amadeus)
- Bach autograph facsimiles: https://imslp.org/wiki/Category:Bach,_Johann_Sebastian#Autographs

---

## Test Matrix Summary

| Tier | Count | Difficulty | Accuracy Gate | Status |
|------|-------|-----------|---------------|--------|
| Simple | 5 | ★☆☆☆☆ | ≥70% overall | ✅ Files present |
| Moderate | 5 | ★★☆☆☆ | ≥70% overall | ✅ Files present |
| Complex | 5 | ★★★☆☆ | ≥60% overall | ✅ Files present |
| Choral | 2 | ★★★☆☆ | ≥60% pitch | ✅ Files present |
| Orchestral | 2 | ★★★★☆ | part_count match | ✅ Files present |
| Handwritten | 0 | ★★★★★ | ≥40% pitch | ⚠️ Not downloaded yet |
| **Total** | **19** | — | — | — |

---

## Priority Execution Order (April 2)

Run in this order — stop and fix issues before advancing:

```
1. python3 run_test.py --corpus --tier simple        # Sanity check
2. python3 run_test.py --corpus --tier moderate       # Core functionality
3. python3 run_test.py --corpus --file complex/chopin-prelude-28-20-a4.pdf   # Dense chords
4. python3 run_test.py --corpus --tier choral         # SATB voice assignment
5. python3 run_test.py --corpus --tier complex        # Full complex run
6. python3 run_test.py --corpus --file orchestral/bach-bwv1041-violin-solo-a4.pdf
7. python3 run_test.py --corpus --file orchestral/beethoven-sym5-op67-a4.pdf --pages 1-3
```

---

## Key Dimensions Tested

| Dimension | Covered By | Notes |
|-----------|------------|-------|
| Single staff melody | CP-S01–S05, CP-O02 | Baseline |
| Grand staff | CP-M01–M05, CP-C01–C03 | Most piano music |
| Two voices on one staff | CP-M01, CP-C03, CP-C04 | Uses `<backup>` element |
| Three voices | CP-C04 (Bach Sinfonia) | Hard |
| Four-part SATB | CP-CH01, CP-CH02 | Choral tier |
| Grace notes | CP-M03, CP-C05 | Für Elise, Alla Turca |
| Ornamental runs | CP-C02 (Nocturne) | Most complex ornament test |
| Compound meter (6/8, 12/8) | CP-S03, CP-C02 | Timing math |
| Triplets/tuplets | CP-M03, CP-C02 | Duration normalization needed |
| Chromatic accidentals | CP-C01, CP-C03 | Mid-piece accidentals |
| Key changes | CP-M03, CP-C05 | Fur Elise, Alla Turca |
| Repeat barlines | CP-M03, CP-C05 | Structural navigation |
| Hairpin dynamics | CP-C02, CP-M04 | Not scored yet — Gap #5 |
| Lyric text | CP-CH01, CP-CH02 | Not scored yet |
| Transposing instruments | CP-O01 | Written vs concert pitch |
| Multi-page (3+) | CP-C02, CP-O01, CP-C05 | Context window pressure |

---

## Corpus Download Log

All downloads completed 2026-03-29 from Mutopia Project (direct PDFs, no auth required).

```
simple/         5 files (pre-existing)
moderate/       bach-invention-01, wtk1-prelude1, fur_Elise, chopin-28-4, mozart-K545
complex/        chopin-28-20, chopin-nocturne-op9-2, bach-invention-13, bach-sinfonia-bwv787, mozart-alla-turca
orchestral/     beethoven-sym5, bach-bwv1041-violin-solo
choral/         bach-chorale-BWV277, bach-chorale-BWV264
```

To re-download any missing file, run the URL from its tier section above.

---

## Future Corpus Additions (Phase 2)

Priority additions for improving coverage:

| Score | Why | Source |
|-------|-----|--------|
| Schubert Impromptu Op. 90 No. 2 | Complex RH runs + bass ostinato | IMSLP |
| Brahms Intermezzo Op. 118 No. 2 | Cross-staff beams, thick chords | IMSLP |
| Mozart Symphony No. 40 K. 550, Violin I part | Standard orchestral part | Mutopia |
| Handel "Hallelujah" chorus (SATB+Piano) | Complex SATB with dynamics | CPDL |
| Handwritten manuscript facsimile | Real-world worst-case | IMSLP autographs |
| Lead sheet (jazz standard) | Non-classical notation, chord symbols | n/a |
| Percussion part (snare drum) | Non-pitched notation | Mutopia |
| Figured bass score | Baroque continuo numerals | IMSLP |
