# ScoreForge Test Suite

Comprehensive test suite for OMR (Optical Music Recognition) accuracy validation across all notation edge cases.

## Overview

This test suite is designed to achieve 100/100 accuracy on real-world complex scores. It covers 17 complexity categories representing the full spectrum of music notation challenges.

### Current Status

- **Total Complexity Categories:** 17
- **Covered Categories:** 10 (58.8%)
- **Synthetic Fixtures:** 17
- **Real World Scores:** 24
- **Total Test Items:** 41
- **Target:** 100 items
- **Needed:** 59 additional scores

## Complexity Categories

### Fully Covered ✓

1. **Multi-voice Counterpoint** (★★★☆☆) - 3 existing
   - Two or more independent voices per staff
   - Examples: Bach Inventions, Sinfonias

2. **Complex Tuplets** (★★★★☆) - 1 existing
   - Nested tuplets, cross-beat, cross-staff
   - Examples: Stravinsky, Bartok

3. **Grace Notes & Ornaments** (★★★☆☆) - 3 existing
   - Appoggiaturas, trills, turns, mordents
   - Examples: Baroque works, Classical concertos

4. **Transposing Instruments** (★★★☆☆) - 1 existing
   - Clarinet in Bb, Horn in F, Saxophones
   - Examples: Orchestral scores

5. **Irregular Time Signatures** (★★★☆☆) - 2 existing
   - 5/8, 7/8, mixed meter
   - Examples: Bartok, Stravinsky

6. **Mid-piece Key Changes** (★★★☆☆) - 2 existing
   - Modulations, key signature changes
   - Examples: Sonata form

7. **Repeats & Navigation** (★★☆☆☆) - 3 existing
   - DC al Fine, DS al Coda, volta brackets
   - Examples: Binary/ternary forms

8. **Dynamics & Articulations** (★★☆☆☆) - 2 existing
   - pp, mf, sfz, staccato, tenuto
   - Examples: Romantic works

9. **Lyrics** (★★☆☆☆) - 3 existing
   - Single and multi-verse lyrics
   - Examples: Songs, choral works

10. **Multi-instrument Ensemble** (★★★★☆) - 2 existing
    - 4+ parts, full scores
    - Examples: String quartets, symphonies

### Partial Coverage ⚠️

11. **Figured Bass** (★★★★★) - 1 existing
    - Baroque continuo numerals
    - Need 3 more
    - Examples: Bach cantatas, Handel oratorios

### Missing Gaps ✗

12. **Ossia Staves & Cue Notes** (★★★★☆) - 0 existing
    - Alternative passages, smaller cue notes
    - Need 4
    - Examples: Concertos, orchestral parts

13. **Percussion Notation** (★★★★☆) - 0 existing
    - Unpitched percussion, drum set
    - Need 5
    - Examples: Percussion ensemble, drum methods

14. **Guitar Tablature** (★★★★☆) - 0 existing
    - Tab notation, chord diagrams
    - Need 5
    - Examples: Guitar methods, rock/pop

15. **Cross-staff Beaming** (★★★★☆) - 0 existing
    - Notes beamed between staves
    - Need 6
    - Examples: Chopin, Brahms, Rachmaninoff

16. **Polyrhythms** (★★★★★) - 0 existing
    - 3 against 2, simultaneous subdivisions
    - Need 5
    - Examples: Messiaen, Elliott Carter

17. **Chord Symbols** (★★★☆☆) - 0 existing
    - Jazz/pop chord symbols
    - Need 5
    - Examples: Lead sheets, fake books

## Directory Structure

```
test_suite/
├── manifest.json           # Complete catalog of test suite
├── README.md              # This file
└── [category directories]  # Scores organized by complexity category
```

## Adding New Scores

To add a new score to the test suite:

1. Download public domain score from:
   - Mutopia Project (CC0/LGPL)
   - IMSLP (Public Domain)
   - OpenScore (CC0)
   - CPDL (Choral works)

2. Place in appropriate category directory

3. Update `manifest.json` with score metadata:
   ```json
   {
     "filename": "path/to/score.pdf",
     "composer": "Composer Name",
     "work": "Work Title",
     "source": "Mutopia/IMSLP/etc",
     "categories": ["category1", "category2"],
     "difficulty": "★★☆☆☆",
     "pages": 1,
     "key_features": ["feature1", "feature2"]
   }
   ```

## Priority Targets

### High Priority (Coverage Critical)

1. **Cross-staff Beaming** - 6 scores needed
   - Chopin Etude Op. 10 No. 3
   - Chopin Etude Op. 25 No. 1 (Aeolian Harp)
   - Brahms Intermezzo Op. 118 No. 2

2. **Ossia/Cue Notes** - 4 scores needed
   - Mozart Piano Concerto K. 467
   - Beethoven Piano Concerto No. 3

3. **Polyrhythms** - 5 scores needed
   - Messiaen Quartet for the End of Time
   - Bartok String Quartet No. 4

### Medium Priority

4. **Percussion Notation** - 5 scores needed
5. **Guitar Tablature** - 5 scores needed
6. **Chord Symbols** - 5 scores needed

## Running Tests

Test entire suite:
```bash
python3 run_test.py --suite
```

Test specific category:
```bash
python3 run_test.py --category cross_staff_beaming
```

Test individual score:
```bash
python3 run_test.py --file test_suite/cross_staff_beaming/chopin-etude-op10-3.pdf
```

## Accuracy Targets

| Category | Target | Current | Gap |
|----------|--------|----------|------|
| Multi-voice Counterpoint | 8 | 3 | -5 |
| Complex Tuplets | 6 | 1 | -5 |
| Grace Notes & Ornaments | 8 | 3 | -5 |
| Ossia/Cue Notes | 4 | 0 | -4 |
| Transposing Instruments | 6 | 1 | -5 |
| Percussion Notation | 5 | 0 | -5 |
| Guitar Tablature | 5 | 0 | -5 |
| Figured Bass | 4 | 1 | -3 |
| Cross-staff Beaming | 6 | 0 | -6 |
| Irregular Time Signatures | 6 | 2 | -4 |
| Polyrhythms | 5 | 0 | -5 |
| Mid-piece Key Changes | 6 | 2 | -4 |
| Repeats & Navigation | 6 | 3 | -3 |
| Dynamics & Articulations | 6 | 2 | -4 |
| Lyrics | 6 | 3 | -3 |
| Chord Symbols | 5 | 0 | -5 |
| Multi-instrument Ensemble | 8 | 2 | -6 |

**Total Gap:** 76 additional scores needed

## Sources

### Public Domain Score Repositories

- **Mutopia Project**: https://www.mutopiaproject.org/
  - CC0/LGPL licensed
  - Direct PDF downloads
  - LilyPond-rendered, clean notation

- **IMSLP**: https://imslp.org/
  - Largest public domain repository
  - Download-gate for some files
  - Best for facsimiles, autographs

- **OpenScore**: https://openscore.cc/
  - CC0 licensed
  - MuseScore-based editions
  - MusicXML ground truth available

- **CPDL**: https://www.cpdl.org/
  - Choral Public Domain Library
  - SATB repertoire
  - Free for non-commercial use

## Contributing

When adding scores:
1. Verify public domain status
2. Document source in manifest
3. Tag with all applicable complexity categories
4. Test with current OMR pipeline
5. Note accuracy issues in score metadata

---
*Created: 2026-04-06*
*Last Updated: 2026-04-06*
*Test Suite Version: 1.0*
