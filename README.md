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

---

## Running the API

The ScoreForge API provides a REST interface for sheet music to MusicXML conversion.

### Development Mode

For development with hot-reload:

```bash
# Start dev server with hot-reload (watches api/ and core/)
python api/run_dev.py

# Or via PM2 (auto-restarts on file changes)
pm2 start pm2.ecosystem.dev.json
pm2 logs scoreforge-api-dev
```

Features:
- **Hot-reload**: Auto-restarts when you save changes to `api/` or `core/`
- **In-memory job store**: Jobs are lost on restart (acceptable for dev)
- **Verbose logging**: See all requests and errors in console

### Production Mode

For production with persistent job storage:

```bash
# Start production server with SQLite job persistence
pm2 start pm2.ecosystem.prod.json
pm2 logs scoreforge-api-prod

# Or manually with uvicorn
JOB_STORE_TYPE=sqlite JOB_STORE_PATH=data/jobs.db \
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Features:
- **Persistent job store**: Jobs survive server restarts (SQLite database)
- **Process management**: Auto-restart on crash via PM2
- **Graceful shutdown**: In-flight jobs complete before shutdown

### API Endpoints

| Method | Endpoint | Description |
|---------|-----------|-------------|
| GET | `/health` | Liveness check |
| POST | `/convert` | Upload sheet music, returns job_id |
| GET | `/job/{id}` | Poll job status |
| GET | `/job/{id}/result` | Download completed MusicXML |

#### Upload and Convert

```bash
curl -X POST http://localhost:8000/convert \
  -H "Content-Type: multipart/form-data" \
  -F "file=@score.png"

# Response: {"job_id": "uuid", "status": "pending"}
```

#### Poll Status

```bash
curl http://localhost:8000/job/{job_id}

# Response: {
#   "id": "...",
#   "status": "completed",
#   "filename": "score.png",
#   "measure_count": 8,
#   "part_count": 1
# }
```

#### Download Result

```bash
curl http://localhost:8000/job/{job_id}/result -o output.musicxml
```

### Environment Variables

| Variable | Default | Description |
|----------|----------|-------------|
| `JOB_STORE_TYPE` | `memory` | Job storage: `memory` (dev) or `sqlite` (prod) |
| `JOB_STORE_PATH` | `data/jobs.db` | Path to SQLite database (for sqlite mode) |
| `PORT` | `8000` | Server port |

### PM2 Commands

```bash
# List all processes
pm2 list

# View logs
pm2 logs scoreforge-api-dev
pm2 logs scoreforge-api-prod

# Stop a process
pm2 stop scoreforge-api-dev

# Restart a process
pm2 restart scoreforge-api-prod

# Remove from PM2
pm2 delete scoreforge-api-dev

# Save process list for auto-start on reboot
pm2 save
pm2 startup
```

### Data Directory

Production mode stores job data in `data/jobs.db` (SQLite database). This file persists across restarts and contains all completed, running, and failed jobs.

To clear old jobs (optional):

```bash
# Stop the service first
pm2 stop scoreforge-api-prod

# Delete or backup the database
rm data/jobs.db
mv data/jobs.db data/jobs.db.backup

# Restart the service
pm2 restart scoreforge-api-prod
```
