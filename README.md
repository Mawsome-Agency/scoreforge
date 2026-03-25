# ScoreForge

AI-powered sheet music to MusicXML converter with iterative visual validation.

## What It Does

Takes a PDF, screenshot, or photo of sheet music and produces **perfect** MusicXML output through an iterative loop:

1. **Extract** — Vision AI reads the sheet music image and produces MusicXML
2. **Render** — MusicXML is rendered back to a visual score image
3. **Compare** — Original and re-rendered images are compared measure-by-measure
4. **Fix** — Discrepancies are identified and the MusicXML is corrected
5. **Repeat** — Loop until the output matches the source (or max iterations)

## Architecture

```
input (PDF/PNG/JPG)
    │
    ▼
┌─────────────────┐
│  Vision Extract  │  Claude Vision / Audiveris
│  (sheet → XML)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  MusicXML Gen   │  Build valid MusicXML from extracted data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Render Back     │  MuseScore CLI / Verovio
│  (XML → image)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Visual Diff     │  Perceptual hash + structural comparison
└────────┬────────┘
         │
    ┌────┴────┐
    │ Match?  │
    └────┬────┘
     No  │  Yes
     │   └──→ ✅ Done! Output final MusicXML
     ▼
┌─────────────────┐
│  AI Fix Pass     │  Claude identifies and corrects diffs
└────────┬────────┘
         │
         └──→ Loop back to Render
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install system deps (Ubuntu/Debian)
sudo apt install musescore3 # or musescore4

# Run on a sheet music image
python scoreforge.py input.pdf --output output.musicxml

# Run with visual validation loop
python scoreforge.py input.pdf --output output.musicxml --validate --max-iterations 10
```

## Project Structure

```
scoreforge/
├── scoreforge.py          # Main CLI entry point
├── core/
│   ├── __init__.py
│   ├── extractor.py       # Vision-based music extraction
│   ├── musicxml_builder.py # MusicXML document construction
│   ├── renderer.py        # MusicXML → image rendering
│   ├── comparator.py      # Visual diff engine
│   └── fixer.py           # AI-powered correction pass
├── models/
│   ├── __init__.py
│   ├── measure.py         # Measure data model
│   ├── note.py            # Note/rest data model
│   └── score.py           # Full score data model
├── tests/
│   ├── fixtures/          # Sample sheet music images
│   └── test_pipeline.py   # End-to-end pipeline tests
├── requirements.txt
└── README.md
```

## Tech Stack

- **Python 3.11+**
- **Claude Vision API** — Primary music notation reader
- **Audiveris** — Open source OMR as fallback/baseline
- **MuseScore CLI** or **Verovio** — MusicXML rendering
- **Pillow / OpenCV** — Image comparison
- **music21** — MusicXML validation and manipulation

## MusicXML Output

Produces standard MusicXML 4.0 compatible with:
- MuseScore
- Finale
- Sibelius
- Dorico
- Any MusicXML-compatible notation software

## License

MIT
