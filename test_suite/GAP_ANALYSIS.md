# Test Suite Gap Analysis

**Generated:** 2026-04-06  
**Current Coverage:** 10/17 categories (58.8%)  
**Target:** 100 scores  
**Current:** 41 scores (17 synthetic + 24 real-world)  
**Needed:** 59 additional scores

---

## Critical Gaps (High Priority)

### 1. Cross-staff Beaming - 6 scores needed
**Difficulty:** ★★★★☆  
**Why Critical:** Common in Romantic piano literature. Fails voice assignment if beaming isn't correctly parsed.

**Target Scores:**
| # | Composer | Work | Source | Priority |
|---|-----------|-------|---------|
| 1 | Frédéric Chopin | Etude Op. 10 No. 3 "Tristesse" | Mutopia | HIGH |
| 2 | Frédéric Chopin | Etude Op. 25 No. 1 "Aeolian Harp" | Mutopia | HIGH |
| 3 | Johannes Brahms | Intermezzo Op. 118 No. 2 | Mutopia | HIGH |
| 4 | Sergei Rachmaninoff | Prelude Op. 23 No. 5 in G minor | Mutopia | HIGH |
| 5 | Claude Debussy | Arabesque No. 1 | IMSLP | MED |
| 6 | Frédéric Chopin | Nocturne Op. 9 No. 1 | Mutopia | MED |

**Mutopia Search Terms:**
- `Chopin Etude Op 10 No 3`
- `Chopin Etude Op 25 No 1`
- `Brahms Intermezzo Op 118 No 2`
- `Rachmaninoff Prelude Op 23 No 5`

---

### 2. Ossia Staves & Cue Notes - 4 scores needed
**Difficulty:** ★★★★☆  
**Why Critical:** Alternative notation is common in concertos. Small note size affects detection.

**Target Scores:**
| # | Composer | Work | Source | Priority |
|---|-----------|-------|---------|
| 1 | W.A. Mozart | Piano Concerto No. 21 K. 467 (cadenza) | IMSLP | HIGH |
| 2 | L. van Beethoven | Piano Concerto No. 3 (cadenza) | IMSLP | HIGH |
| 3 | J.S. Bach | Violin Concerto in A minor BWV 1041 (solo with cues) | Mutopia | MED |
| 4 | A. Dvorak | Cello Concerto (cue notes) | IMSLP | MED |

**Note:** Ossia staves are marked with smaller noteheads. Cue notes have smaller font.

---

### 3. Polyrhythms - 5 scores needed
**Difficulty:** ★★★★★  
**Why Critical:** Tests OMR's ability to parse simultaneous different subdivisions (e.g., 3 against 2).

**Target Scores:**
| # | Composer | Work | Polyrhythm | Source | Priority |
|---|-----------|-------|-------------|---------|
| 1 | Olivier Messiaen | Quartet for the End of Time - Mvt 5 | 2 vs 3 | IMSLP | HIGH |
| 2 | Béla Bartók | String Quartet No. 4 - 5th Mvt | Multiple | IMSLP | HIGH |
| 3 | Igor Stravinsky | The Rite of Spring - excerpts | Various | IMSLP | HIGH |
| 4 | Elliott Carter | String Quartets | Complex | IMSLP | MED |
| 5 | György Ligeti | Etudes | Complex | IMSLP | LOW |

**IMSLP Search Terms:**
- `Messiaen Quartet End of Time`
- `Bartok String Quartet 4`
- `Stravinsky Rite of Spring`

---

## Medium Priority Gaps

### 4. Percussion Notation - 5 scores needed
**Difficulty:** ★★★★☆  
**Why Important:** Tests unpitched symbol recognition and percussion-specific notation.

**Target Scores:**
| # | Composer | Work | Source | Notes |
|---|-----------|-------|--------|
| 1 | Béla Bartók | Sonatina for percussion duet | Mutopia |
| 2 | Iannis Xenakis | Rebonds for percussion | IMSLP |
| 3 | Traditional | Drum set notation basics | Various |
| 4 | Carlos Chavez | Toccata for percussion | IMSLP |
| 5 | Edgard Varèse | Ionisation (excerpt) | IMSLP |

---

### 5. Guitar Tablature - 5 scores needed
**Difficulty:** ★★★★☆  
**Why Important:** Tab notation is completely different from standard notation.

**Target Scores:**
| # | Composer | Work | Source | Notes |
|---|-----------|-------|--------|
| 1 | Matteo Carcassi | 25 Melodic Studies Op. 60 | Mutopia/IMSLP |
| 2 | Fernando Sor | 20 Studies for Guitar | Mutopia/IMSLP |
| 3 | Mauro Giuliani | 120 Right Hand Studies | Mutopia/IMSLP |
| 4 | Traditional | Folk songs with tab | Various |
| 5 | Heitor Villa-Lobos | 5 Preludes (tab edition) | IMSLP |

**Challenge:** Tab uses 6 lines instead of 5 staff lines. Numbers = fret positions.

---

### 6. Chord Symbols - 5 scores needed
**Difficulty:** ★★★☆  
**Why Important:** Jazz/pop notation uses chord symbols instead of staff notation.

**Target Scores:**
| # | Work | Chords | Source | Notes |
|---|-------|--------|-------|
| 1 | Autumn Leaves | jazz progression | Fake book |
| 2 | All the Things You Are | ii-V-I progression | Fake book |
| 3 | Blue Bossa | Latin progression | Fake book |
| 4 | Autumn in New York | chromatic | Fake book |
| 5 | Basic progression exercises | I-vi-ii-V-I | Various |

**Challenge:** Text symbols above staff (Cmaj7, F#m7(b5)) need separate parsing.

---

### 7. Figured Bass - 3 more needed (1 existing)
**Difficulty:** ★★★★★  
**Why Important:** Baroque continuo requires numeral interpretation.

**Target Scores:**
| # | Composer | Work | Source | Notes |
|---|-----------|-------|--------|
| 1 | Arcangelo Corelli | Trio Sonata Op. 1 No. 3 | Mutopia |
| 2 | G.F. Handel | Concerto Grosso Op. 6 No. 1 | Mutopia |
| 3 | J.S. Bach | Cantata with continuo | IMSLP |
| 4 | Henry Purcell | Trio Sonatas | IMSLP |

**Challenge:** Numerals (6, 4+2, 7) below staff need translation to chords.

---

## Additional Scores Needed (by Category)

### Multi-voice Counterpoint - 5 more needed
**Current:** 3 (Bach Invention 1, Invention 13, Sinfonia 1)  
**Target:** 8

| Priority | Composer | Work | Source |
|----------|-----------|-------|--------|
| HIGH | J.S. Bach | Fugue in C major (WTC) | Mutopia |
| HIGH | J.S. Bach | Fugue in C minor (WTC) | Mutopia |
| MED | J.S. Bach | Three-Part Invention No. 4 | Mutopia |
| MED | D. Scarlatti | Sonata in G major | Mutopia |
| LOW | J.J. Fux | Gradus ad Parnassum example | IMSLP |

---

### Complex Tuplets - 5 more needed
**Current:** 1 (nested_tuplets fixture)  
**Target:** 6

| Priority | Composer | Work | Tuplet Type | Source |
|----------|-----------|-------|-------------|--------|
| HIGH | G. Ligeti | Etudes | Complex | IMSLP |
| HIGH | P. Boulez | Douze Notations | Nested | IMSLP |
| MED | H. Dutilleux | Etudes | Nested | IMSLP |
| MED | I. Stravinsky | Movements for Piano | Cross-beat | IMSLP |
| LOW | O. Messiaen | Preludes | Irregular | IMSLP |

---

### Grace Notes & Ornaments - 5 more needed
**Current:** 3 (Für Elise, Nocturne Op. 9 No. 2, Mozart K. 545)  
**Target:** 8

| Priority | Composer | Work | Ornament Type | Source |
|----------|-----------|-------|---------------|--------|
| HIGH | J.S. Bach | Solo Sonatas & Partitas | Trills/turns | Mutopia |
| HIGH | G.P. Telemann | Fantasias | Ornaments | Mutopia |
| MED | A. Corelli | Violin Sonatas | Graces | Mutopia |
| MED | G.F. Handel | Violin Sonatas | Trills | Mutopia |
| LOW | J. Haydn | Keyboard works | Ornaments | Mutopia |

---

### Transposing Instruments - 5 more needed
**Current:** 1 (Beethoven Symphony No. 5)  
**Target:** 6

| Priority | Work | Transposing Instruments | Source |
|----------|-------|---------------------|--------|
| HIGH | Mozart Serenade No. 10 "Gran Partita" | Clarinets, Horns | Mutopia |
| HIGH | R. Strauss | Serenades | Horns | IMSLP |
| MED | A. Dvorak | Serenade for Winds Op. 44 | Clarinets, Bassoons | Mutopia |
| MED | Military band arrangements | Various transposing | Various |
| LOW | Big band charts | Saxophones | Various |

---

### Irregular Time Signatures - 4 more needed
**Current:** 2 (mixed_meters fixture, O Holy Night 12/8)  
**Target:** 6

| Priority | Composer | Work | Time Signature | Source |
|----------|-----------|-------|----------------|--------|
| HIGH | B. Bartók | 6 Romanian Folk Dances | Various (5/8, 7/8) | Mutopia |
| HIGH | I. Stravinsky | Octet for Winds | Various | IMSLP |
| MED | C. Ives | The Unanswered Question | Multiple | IMSLP |
| LOW | Folk collections | Eastern European | 5/8, 7/8 | Various |

---

### Mid-piece Key Changes - 4 more needed
**Current:** 2 (Für Elise, Alla Turca)  
**Target:** 6

| Priority | Composer | Work | Key Changes | Source |
|----------|-----------|-------|-------------|--------|
| HIGH | L. van Beethoven | Piano Sonata Op. 13 | C → Cm → C | Mutopia |
| HIGH | W.A. Mozart | Symphony No. 40 in G minor | Gm → Eb → Cm | Mutopia |
| MED | F. Chopin | Ballade No. 1 in G minor | Multiple | IMSLP |
| MED | F. Schubert | Wanderer Fantasy | Multiple | IMSLP |

---

### Repeats & Navigation - 3 more needed
**Current:** 3 (Für Elise, Alla Turca, repeats_codas fixture)  
**Target:** 6

| Priority | Composer | Work | Navigation | Source |
|----------|-----------|--------|------------|--------|
| HIGH | W.A. Mozart | Minuet and Trio (multiple) | Binary form | Mutopia |
| HIGH | J. Haydn | Keyboard works | Various | Mutopia |
| MED | L. van Beethoven | Bagatelles | Various | Mutopia |

---

### Dynamics & Articulations - 4 more needed
**Current:** 2 (Chopin Prelude Op. 28 No. 4, Chopin Prelude Op. 28 No. 20)  
**Target:** 6

| Priority | Composer | Work | Markings | Source |
|----------|-----------|-------|-----------|--------|
| HIGH | P.I. Tchaikovsky | Symphony No. 6 "Pathétique" | pp to sfz | Mutopia |
| HIGH | G. Mahler | Symphonic excerpts | Extreme dynamics | IMSLP |
| MED | S. Rachmaninoff | Piano works | sfz accents | IMSLP |
| LOW | Modern works | Complex articulations | Various |

---

### Lyrics - 3 more needed
**Current:** 3 (Blue Mountains, Giselle, O Holy Night, 2 chorales)  
**Actually 5** - wait, let me recount  
Actually: 1 (Blue Mountains) + 0 (Giselle - no lyrics) + 1 (O Holy Night) + 2 (chorales) = 4 with lyrics

| Priority | Composer | Work | Lyrics | Source |
|----------|-----------|-------|--------|--------|
| HIGH | F. Schubert | Lieder | German | IMSLP |
| HIGH | J. Brahms | German Requiem | Latin | IMSLP |
| MED | G.F. Handel | Arias | English | Mutopia |
| LOW | Folk songs | Various | Multi-verse | Various |

---

### Multi-instrument Ensemble - 6 more needed
**Current:** 2 (Beethoven Symphony No. 5, Bach Violin Concerto solo part)  
**Target:** 8

| Priority | Composer | Work | Parts | Source |
|----------|-----------|-------|--------|--------|
| HIGH | F.J. Haydn | String Quartets Op. 76 | 4 strings | Mutopia |
| HIGH | W.A. Mozart | String Quartets | 4 strings | Mutopia |
| HIGH | F. Schubert | Octet D. 803 | 8 instruments | IMSLP |
| HIGH | F. Mendelssohn | Octet Op. 20 | 8 instruments | Mutopia |
| MED | L. van Beethoven | Septet Op. 20 | 7 instruments | Mutopia |
| LOW | A. Dvorak | Serenade for Winds | 8+ winds | Mutopia |

---

## Download Strategy

### Phase 1: High Priority (Week 1)
1. Cross-staff Beaming (6 scores) - Chopin Etudes
2. Ossia/Cue Notes (4 scores) - Concerto cadenzas
3. Polyrhythms (3 scores) - Bartok, Stravinsky

**Expected Coverage After:** 13/17 categories (76.5%)

### Phase 2: Medium Priority (Week 2)
4. Percussion Notation (5 scores)
5. Guitar Tablature (5 scores)
6. Chord Symbols (5 scores)
7. Additional Counterpoint (5 scores)

**Expected Coverage After:** 16/17 categories (94.1%)

### Phase 3: Remaining (Week 3)
8. Fill remaining gaps across all categories
9. Verify all 100 scores are valid PDFs
10. Run baseline OMR tests and document accuracy

**Expected Coverage After:** 17/17 categories (100%)

---

## Quality Criteria for Added Scores

Each added score must:

1. **Public Domain**: CC0, PD, or LGPL (for Mutopia)
2. **Clear Notation**: Prefer engraved/laser-printed over handwritten for baseline
3. **Relevant Complexity**: Must demonstrate the category it fills
4. **Reasonable Size**: 1-5 pages preferred (avoid 50+ page scores)
5. **Verified Quality**: Downloaded from trusted source (Mutopia, IMSLP PD)

---

## Next Actions

- [ ] Download cross-staff beaming scores from Mutopia
- [ ] Download ossia examples from IMSLP
- [ ] Download polyrhythm scores from IMSLP
- [ ] Download percussion notation examples
- [ ] Create guitar tab examples if PD sources scarce
- [ ] Download figured bass scores from Mutopia
- [ ] Update manifest.json with new scores
- [ ] Run OMR pipeline on new scores
- [ ] Document accuracy results

---
*Last Updated: 2026-04-06*
