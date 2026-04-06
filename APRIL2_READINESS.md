# April 2 Readiness Checklist — ZAI API Reset
_Written: 2026-03-29 | Lyra Chen_

ZAI API key resets April 2. This checklist is the complete pre-flight before running
corpus validation. Work through it in order.

---

## Phase 0: Verify API is live (do this first)

- [ ] **Check ZAI key is set:** `echo $ZAI_API_KEY` — must not be empty
- [ ] **Check ZAI base URL:** `echo $ZAI_BASE_URL` — must not be empty
- [ ] **Smoke test API call:**
  ```bash
  cd /home/deployer/scoreforge
  python3 -c "
  from core import api
  r = api.create_message(
      model='claude-sonnet-4-6',
      max_tokens=10,
      messages=[{'role':'user','content':'say ok'}]
  )
  print('API live:', r.content[0].text)
  "
  ```
  Expected: `API live: ok` (or similar). If this fails, stop — everything else depends on it.

- [ ] **Confirm fallback order:** `api.py` tries `ANTHROPIC_API_KEY` first, `ZAI_API_KEY`
  second. If ANTHROPIC_API_KEY is empty (or rate-limited), ZAI is used automatically.
  Set `ANTHROPIC_API_KEY=` in env if you want ZAI-only for testing.

---

## Phase 1: Fix critical harness gaps (before first real run)

- [ ] **Fix #1 — Duration normalization** (`core/comparator.py`)
  Change `_compare_measures` to normalize duration to note-type beats, not raw integers.
  See `HARNESS_GAPS.md` §1 for the exact fix. Without this, `rhythm_accuracy` reads 0%
  for all fixtures.

- [ ] **Fix #2 — Multi-voice grouping** (`core/comparator.py`)
  Add voice-based grouping before note comparison. Affects `piano_chords`, `multi_voice`,
  `full_orchestra`. See `HARNESS_GAPS.md` §2.

- [ ] **Fix #3 — `is_perfect` key/time guard** (`core/comparator.py`)
  Add key_sig and time_sig correctness to `is_perfect` condition.
  See `HARNESS_GAPS.md` §3.

---

## Phase 2: Verify renderer

- [ ] **Render a fixture to PNG:**
  ```bash
  cd /home/deployer/scoreforge
  python3 -c "
  from core.renderer import render_musicxml_to_image, get_available_renderer
  print('Renderer:', get_available_renderer())
  out = render_musicxml_to_image('tests/fixtures/simple_melody.musicxml', '/tmp/smoke_render.png')
  print('PNG:', out)
  from PIL import Image; img = Image.open(out); print('Size:', img.size)
  "
  ```
  Expected: `Renderer: verovio-python`, valid PNG with reasonable dimensions (>400px wide).

- [ ] **Verify all 18 fixtures resolve** (17 + empty_score):
  ```bash
  python3 test_harness.py --no-api --list-fixtures
  ```
  Every line should show `OK`. No `MISSING` entries.

---

## Phase 3: Run baseline — easy fixtures first

- [ ] **TC-01 simple_melody** (the canary):
  ```bash
  python3 test_harness.py --fixture simple_melody --model claude-sonnet-4-6
  ```
  Pass threshold: `overall ≥ 95%`. If this fails, stop and debug before proceeding.

- [ ] **TC-02 piano_chords:**
  ```bash
  python3 test_harness.py --fixture piano_chords
  ```
  Pass threshold: `overall ≥ 90%`.

- [ ] **TC-03 complex_rhythm:**
  ```bash
  python3 test_harness.py --fixture complex_rhythm
  ```
  Pass threshold: `overall ≥ 85%`.

---

## Phase 4: Run medium/hard fixtures

- [ ] **TC-04 mixed_meters** — expected `time_sig_accuracy = 100%`
- [ ] **TC-05 multi_voice** — requires voice-grouping fix to be meaningful
- [ ] **TC-06 ornaments** — pitch/rhythm 100% expected; ornaments not yet scored
- [ ] **TC-07 nested_tuplets** — `pitch_accuracy ≥ 90%`, rhythm accuracy expected low (~50%)
- [ ] **TC-08 key_changes** — `key_sig_accuracy = 100%`
- [ ] **TC-09 full_orchestra** — `part_count_match = true`, `overall ≥ 70%`
- [ ] **TC-10 repeats_codas** — pitch/rhythm only; structural elements not scored

Run all fixtures at once:
```bash
python3 test_harness.py 2>&1 | tee results/april2_full_run.log
```

---

## Phase 5: Run corpus PDFs (parse-only gate)

**Pre-condition:** At least 2-3 PDFs per tier ideally. Current state: 5 PDFs in `simple/`
only. Gate is ≥70% parse success.

```bash
python3 test_harness.py --corpus-only 2>&1 | tee results/april2_corpus.log
```

Expect: 5 PDFs in simple tier, ~4-5 should parse without error (80-100%).

**To add moderate-tier PDFs before this step:**
```bash
# Copy a PDF to corpus/originals/moderate/
cp <your_pdf> corpus/originals/moderate/
```
Suggested sources: IMSLP Bach inventions, Clementi sonatinas, Scarlatti sonatas (short).

---

## Phase 6: Review results and triage

- [ ] Check `results/test_report.json` — review per-fixture scores
- [ ] Check `results/corpus_report.json` — verify parse gate ≥70%
- [ ] For any fixture scoring <70%: check `results/<fixture_name>/comparison.json`
  for measure-level diff detail
- [ ] File issues for any systematic failures (e.g., all key changes wrong)

---

## Quick-reference commands

```bash
# Single fixture
python3 test_harness.py --fixture simple_melody

# Single fixture, specific model
python3 test_harness.py --fixture ornaments --model claude-opus-4-6

# All fixtures
python3 test_harness.py

# All fixtures + corpus PDFs
python3 test_harness.py --corpus

# Corpus PDFs only
python3 test_harness.py --corpus-only

# Dry run (render test, no API calls)
python3 test_harness.py --no-api

# List all fixtures
python3 test_harness.py --list-fixtures
```

---

## Known issues that are NOT blockers on April 2

| Issue | Status | Notes |
|-------|--------|-------|
| `--no-api` shows ERROR not SKIPPED | Minor UX | Doesn't affect real runs |
| Ornament scoring not implemented | Low pri | Ornament accuracy = N/A |
| Lyrics not compared | Low pri | Lyric accuracy = N/A |
| Renderer uses verovio-python (not CLI) | Working | Slightly slower, same output |
| Corpus moderate/complex/orchestral empty | Informational | Only simple tier tested |

---

## Environment checklist

```bash
# Required env vars (check .env or shell)
echo "ZAI_API_KEY: ${ZAI_API_KEY:0:8}..."
echo "ZAI_BASE_URL: $ZAI_BASE_URL"
# Optional — if set, takes priority over ZAI
echo "ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:0:8}..."

# Python deps (should all be installed)
cd /home/deployer/scoreforge
python3 -c "import anthropic, music21, verovio, PIL, numpy, imagehash, lxml, click, rich, cairosvg; print('all deps ok')"

# Verify fixture count
python3 test_harness.py --no-api --list-fixtures | grep -c "OK"
# Expected: 18
```
