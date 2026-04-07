# ScoreForge Test Suite

This directory contains the comprehensive test suite for the ScoreForge OMR pipeline.

## Directory Structure

- `fixtures/` - MusicXML test fixtures (ground truth scores)
- `samples/` - Sample MusicXML files for round-trip testing
- `output/` - Generated test output (PNGs, extracted MusicXML)
- `validate_baseline.py` - Baseline validation pipeline
- `roundtrip.py` - Round-trip test runner
- `test_api.py` - API integration tests (mocked)

## Baseline Validation

The `validate_baseline.py` script runs the full extraction pipeline on all fixtures
and generates a comprehensive accuracy report in markdown format.

### Usage

```bash
# Run all fixtures
python tests/validate_baseline.py

# Run a single fixture
python tests/validate_baseline.py --fixture simple_melody

# Use a specific model
python tests/validate_baseline.py --model claude-sonnet-4-6

# Custom output path
python tests/validate_baseline.py --output reports/baseline.md

# List available fixtures
python tests/validate_baseline.py --list-fixtures

# Quiet mode (only print summary)
python tests/validate_baseline.py --quiet
```

### Report Format

The script generates two reports:

1. **BASELINE_REPORT.md** - Human-readable markdown report with:
   - Summary table with all accuracy metrics
   - Per-fixture detailed results
   - Failure details for fixtures that didn't pass
   - Progress tracking against the 95% target
   - Breakdown by difficulty level

2. **BASELINE_REPORT.json** - Machine-readable JSON with:
   - Aggregate summary metrics
   - Per-fixture results with all scores
   - Timing information
   - Error details

### Accuracy Metrics

The baseline validation tracks the following metrics:

- **Note Accuracy** - Percentage of notes correctly identified (pitch + duration)
- **Pitch Accuracy** - Percentage of notes with correct pitch
- **Rhythm Accuracy** - Percentage of notes with correct duration
- **Measure Accuracy** - Percentage of measures with correct content
- **Key Signature Accuracy** - Percentage of key signatures correctly identified
- **Time Signature Accuracy** - Percentage of time signatures correctly identified
- **Overall Accuracy** - Weighted composite score

### Target

**Q2 2026 Rock:** Achieve 95%+ accuracy on simple/moderate fixtures.

The baseline report tracks progress against this target and provides
a clear view of what's working and what needs improvement.

## Test Harness Integration

The `test_harness.py` in the project root provides integration with the
baseline validation:

```python
from test_harness import get_baseline_metrics, run_baseline_validation

# Get metrics without generating report
metrics = get_baseline_metrics(model="claude-sonnet-4-6")

# Run full validation and generate report
metrics = run_baseline_validation(output_path="reports/baseline.md")
```

## Fixtures

Fixtures are organized by complexity and feature coverage:

### Easy Fixtures
- `simple_melody.musicxml` - C major, 4/4, single staff
- `empty_score.musicxml` - Minimal valid score with whole note rest

### Medium Fixtures
- `piano_chords.musicxml` - G major, 3/4, piano grand staff with chords
- `annotations.musicxml` - Score with text annotations
- `clef_changes.musicxml` - Score with clef changes
- `dynamics_hairpins.musicxml` - Dynamics with hairpins
- `key_changes.musicxml` - Score with key signature changes
- `lyrics_verses.musicxml` - Score with multi-verse lyrics
- `title_metadata.musicxml` - Score with title and composer metadata

### Hard Fixtures
- `complex_rhythm.musicxml` - Bb major, 6/8, ties, beams
- `full_orchestra.musicxml` - Multi-part orchestral score
- `marching_stickings.musicxml` - Percussion with stickings
- `mixed_meters.musicxml` - Multiple time signatures
- `multi_voice.musicxml` - Multiple voices per staff
- `nested_tuplets.musicxml` - Complex tuplet structures
- `ornaments.musicxml` - Score with ornaments
- `repeats_codas.musicxml` - Score with repeats and codas
- `solo_with_accompaniment.musicxml` - Solo instrument with accompaniment

## Running Tests

### Quick Validation (No API)
```bash
python test_harness.py --no-api
```

### Full Test Suite
```bash
python test_harness.py
```

### Baseline Validation
```bash
python tests/validate_baseline.py
```

### API Tests (Mocked)
```bash
pytest tests/test_api.py
```

## CI/CD Integration

The baseline validation can be integrated into CI/CD pipelines:

```yaml
- name: Run Baseline Validation
  run: python tests/validate_baseline.py --quiet
  continue-on-error: true

- name: Check 95% Target
  run: |
    python -c "import json; data = json.load(open('tests/BASELINE_REPORT.json')); exit(0 if data['summary']['target_95_percent_met'] else 1)"
```

## Adding New Fixtures

To add a new fixture:

1. Create the MusicXML file in `tests/fixtures/`
2. Optionally add metadata to the fixture (difficulty, description, tags)
3. Run the baseline validation to include it in reports

```bash
# Create fixture (using music21 or any MusicXML editor)
python tests/fixtures/generate_fixtures.py

# Run validation
python tests/validate_baseline.py --list-fixtures
```

## Troubleshooting

### Rendering Issues
If Verovio is not installed, install it:
```bash
npm install -g verovio
# or
pip install verovio cairosvg
```

### API Errors
Make sure `ANTHROPIC_API_KEY` is set:
```bash
export ANTHROPIC_API_KEY=your-key-here
```

### Timeout Issues
For complex scores, consider using extended thinking:
```bash
python tests/validate_baseline.py --model claude-sonnet-4-5-20250929
```
