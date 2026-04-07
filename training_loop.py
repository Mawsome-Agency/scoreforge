#!/usr/bin/env python3
"""ScoreForge Training Loop — continuous self-improving corpus builder.

Workflow per cycle:
  1. SOURCE   — discover & download public-domain sheet music PDFs
  2. CONVERT  — run each score through scoreforge.py pipeline
  3. VALIDATE — parse conversion results, capture accuracy metrics
  4. CATALOG  — persist everything to corpus.db + daily summary report

Usage:
    python training_loop.py --batch-size 10 --tier simple
    python training_loop.py --batch-size 5 --tier moderate
    python training_loop.py  # uses defaults (batch=10, all tiers)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
CORPUS_DIR = ROOT / "corpus"
ORIGINALS_DIR = CORPUS_DIR / "originals"
MUSICXML_DIR = CORPUS_DIR / "musicxml"
REPORTS_DIR = CORPUS_DIR / "reports"
DB_PATH = CORPUS_DIR / "corpus.db"
SCOREFORGE = ROOT / "scoreforge.py"

for d in [CORPUS_DIR, MUSICXML_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)
for tier in ["simple", "moderate", "complex", "orchestral"]:
    (ORIGINALS_DIR / tier).mkdir(parents=True, exist_ok=True)

# ─── Tier mapping ─────────────────────────────────────────────────────────────
TIER_DIFFICULTY = {
    "simple": ["Beginner"],
    "moderate": ["Easy", "Moderate"],
    "complex": ["Difficult"],
    "orchestral": ["Difficult"],  # orchestral subset sourced differently
}

TIER_INSTRUMENTS = {
    "simple": ["Piano"],
    "moderate": ["Piano", "Guitar", "Violin"],
    "complex": ["Piano", "Violin"],
    "orchestral": ["Orchestra", "Strings"],
}

# Accuracy threshold to "graduate" a tier (avg match score)
GRADUATION_THRESHOLD = 75.0

HEADERS = {
    "User-Agent": (
        "ScoreForge/1.0 (public domain sheet music research; "
        "scoreforge.ai; not for commercial scraping)"
    )
}


# ─── Database ─────────────────────────────────────────────────────────────────

def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corpus (
            id                TEXT PRIMARY KEY,
            source_url        TEXT UNIQUE NOT NULL,
            source_name       TEXT NOT NULL DEFAULT 'unknown',
            title             TEXT,
            composer          TEXT,
            complexity_tier   TEXT NOT NULL,
            download_date     TEXT,
            original_path     TEXT,
            musicxml_path     TEXT,
            report_path       TEXT,
            conversion_status TEXT NOT NULL DEFAULT 'pending',
            match_score       REAL,
            pitch_accuracy    REAL,
            rhythm_accuracy   REAL,
            iterations_used   INTEGER,
            converged         INTEGER,
            failure_mode      TEXT,
            error_message     TEXT,
            processed_date    TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_tier_status
            ON corpus (complexity_tier, conversion_status)
    """)
    conn.commit()
    return conn


def url_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def already_processed(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute(
        "SELECT conversion_status FROM corpus WHERE source_url = ?", (url,)
    ).fetchone()
    if row is None:
        return False
    # Re-attempt failures that have a different root cause
    return row[0] in ("completed", "running")


def upsert_source(conn: sqlite3.Connection, url: str, tier: str,
                  title: str, composer: str, source_name: str):
    rid = url_id(url)
    conn.execute("""
        INSERT OR IGNORE INTO corpus
            (id, source_url, source_name, title, composer, complexity_tier,
             conversion_status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
    """, (rid, url, source_name, title, composer, tier))
    conn.commit()


def record_download(conn: sqlite3.Connection, url: str, local_path: str):
    conn.execute("""
        UPDATE corpus
        SET original_path = ?, download_date = ?
        WHERE source_url = ?
    """, (local_path, datetime.utcnow().isoformat(), url))
    conn.commit()


def record_conversion(conn: sqlite3.Connection, url: str, *,
                      status: str,
                      match_score: Optional[float] = None,
                      pitch_accuracy: Optional[float] = None,
                      rhythm_accuracy: Optional[float] = None,
                      iterations_used: Optional[int] = None,
                      converged: Optional[bool] = None,
                      failure_mode: Optional[str] = None,
                      error_message: Optional[str] = None,
                      musicxml_path: Optional[str] = None,
                      report_path: Optional[str] = None):
    conn.execute("""
        UPDATE corpus
        SET conversion_status = ?,
            match_score       = COALESCE(?, match_score),
            pitch_accuracy    = COALESCE(?, pitch_accuracy),
            rhythm_accuracy   = COALESCE(?, rhythm_accuracy),
            iterations_used   = COALESCE(?, iterations_used),
            converged         = COALESCE(?, converged),
            failure_mode      = COALESCE(?, failure_mode),
            error_message     = COALESCE(?, error_message),
            musicxml_path     = COALESCE(?, musicxml_path),
            report_path       = COALESCE(?, report_path),
            processed_date    = ?
        WHERE source_url = ?
    """, (
        status,
        match_score, pitch_accuracy, rhythm_accuracy,
        iterations_used, (1 if converged else 0) if converged is not None else None,
        failure_mode, error_message,
        musicxml_path, report_path,
        datetime.utcnow().isoformat(),
        url,
    ))
    conn.commit()


# ─── Phase 1: Source ──────────────────────────────────────────────────────────

def fetch_mutopia(tier: str, max_count: int = 50) -> list[dict]:
    """Discover sheet music PDFs from Mutopia Project."""
    difficulties = TIER_DIFFICULTY.get(tier, ["Beginner"])
    instruments = TIER_INSTRUMENTS.get(tier, ["Piano"])
    collected = []
    seen_urls = set()

    for instr in instruments:
        for level in difficulties:
            for start in range(0, max_count, 10):
                url = (
                    f"https://www.mutopiaproject.org/cgibin/make-table.cgi"
                    f"?Instrument={instr}&LevelDesc={level}&output=html"
                    f"&startindex={start}"
                )
                try:
                    r = requests.get(url, headers=HEADERS, timeout=15)
                    r.raise_for_status()
                except Exception as e:
                    print(f"  [mutopia] fetch error: {e}")
                    break

                soup = BeautifulSoup(r.text, "html.parser")
                page_links = [
                    a["href"]
                    for a in soup.find_all("a", href=True)
                    if "a4.pdf" in a.get("href", "")
                ]
                if not page_links:
                    break  # no more results

                for pdf_url in page_links:
                    if pdf_url in seen_urls:
                        continue
                    seen_urls.add(pdf_url)
                    # Extract title/composer from filename
                    filename = pdf_url.split("/")[-1].replace("-a4.pdf", "")
                    # Attempt to find composer from the path component
                    parts = pdf_url.split("/")
                    composer = parts[-3] if len(parts) >= 3 else "Unknown"
                    collected.append({
                        "url": pdf_url,
                        "source": "mutopia",
                        "title": filename.replace("-", " ").replace("_", " ").title(),
                        "composer": composer,
                        "tier": tier,
                    })

                if len(page_links) < 10:
                    break  # last page

    return collected


def fetch_imslp_category(category: str, tier: str,
                          max_count: int = 20) -> list[dict]:
    """Discover IMSLP scores via MediaWiki API and extract direct PDF links.

    Note: IMSLP's download system uses a disclaimer redirect. We handle this
    by scraping the score page to find the direct Wikimedia file URL.
    """
    collected = []
    api_url = "https://imslp.org/api.php"
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": min(max_count, 50),
        "format": "json",
    }
    try:
        r = requests.get(api_url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("categorymembers", [])
    except Exception as e:
        print(f"  [imslp] API error for {category}: {e}")
        return []

    for page in pages[:max_count]:
        title = page["title"]
        # Get the score page to find PDF file names
        try:
            page_r = requests.get(
                api_url,
                params={
                    "action": "parse",
                    "page": title,
                    "prop": "links",
                    "format": "json",
                },
                headers=HEADERS,
                timeout=15,
            )
            page_data = page_r.json()
            links = page_data.get("parse", {}).get("links", [])
            pdf_files = [
                l["*"] for l in links
                if l.get("ns") == 6 and l["*"].upper().endswith(".PDF")
            ]
            if not pdf_files:
                continue
            # Take the first PDF (usually the main score)
            file_title = pdf_files[0]
            # Construct direct download URL via IMSLP's CDN
            # Format: https://imslp.org/wiki/Special:IMSLPDisclaimerAccept/{filename}
            encoded = file_title.replace(" ", "_").replace("File:", "")
            pdf_url = f"https://imslp.org/wiki/Special:IMSLPDisclaimerAccept/{encoded}"
            # Extract composer from title (format: "Work Name (Composer, Name)")
            composer_match = re.search(r"\(([^)]+)\)$", title)
            composer = composer_match.group(1) if composer_match else "Unknown"
            work_name = re.sub(r"\s*\([^)]+\)$", "", title)
            collected.append({
                "url": pdf_url,
                "source": "imslp",
                "title": work_name,
                "composer": composer,
                "tier": tier,
            })
        except Exception as e:
            print(f"  [imslp] page error for {title}: {e}")
            continue

    return collected


def fetch_curated_simple() -> list[dict]:
    """Hard-coded curated list of known-good public domain simple piano PDFs.

    Used to guarantee the 'simple' tier has valid seeds regardless of
    scraper availability.
    """
    return [
        {
            "url": "https://www.mutopiaproject.org/ftp/BachJS/BWV772/bach-invention1/bach-invention1-a4.pdf",
            "source": "mutopia_curated",
            "title": "Invention No. 1 BWV 772",
            "composer": "Bach",
            "tier": "simple",
        },
        {
            "url": "https://www.mutopiaproject.org/ftp/BeethovenLv/O49/beet49-2/beet49-2-a4.pdf",
            "source": "mutopia_curated",
            "title": "Sonatina Op. 49 No. 2",
            "composer": "Beethoven",
            "tier": "simple",
        },
        {
            "url": "https://www.mutopiaproject.org/ftp/MozartWA/KV545/mozart-k545/mozart-k545-a4.pdf",
            "source": "mutopia_curated",
            "title": "Sonata K. 545 in C major",
            "composer": "Mozart",
            "tier": "simple",
        },
        {
            "url": "https://www.mutopiaproject.org/ftp/HandelGF/HWV430/handel-suites/handel-suites-a4.pdf",
            "source": "mutopia_curated",
            "title": "Keyboard Suites HWV 426-433",
            "composer": "Handel",
            "tier": "simple",
        },
        {
            "url": "https://www.mutopiaproject.org/ftp/ScarlattD/K001-050/scarlatti-k1/scarlatti-k1-a4.pdf",
            "source": "mutopia_curated",
            "title": "Sonata K. 1 in D minor",
            "composer": "Scarlatti",
            "tier": "simple",
        },
    ]


def discover_scores(tier: str, batch_size: int) -> list[dict]:
    """Aggregate score discovery across all sources."""
    print(f"\n[source] Discovering '{tier}' scores (need {batch_size})...")
    candidates = []

    # Mutopia — primary source
    mutopia_results = fetch_mutopia(tier, max_count=batch_size * 3)
    candidates.extend(mutopia_results)
    print(f"  mutopia: {len(mutopia_results)} candidates")

    # Curated seeds for 'simple' tier
    if tier == "simple":
        curated = fetch_curated_simple()
        candidates.extend(curated)
        print(f"  curated: {len(curated)} candidates")

    # IMSLP — secondary (may be rate-limited)
    imslp_category_map = {
        "simple":     "For_piano_(elementary)",
        "moderate":   "For_piano",
        "complex":    "For_piano_(advanced)",
        "orchestral": "Scores_featuring_the_orchestra",
    }
    cat = imslp_category_map.get(tier, "For_piano")
    imslp_results = fetch_imslp_category(cat, tier, max_count=batch_size)
    candidates.extend(imslp_results)
    print(f"  imslp: {len(imslp_results)} candidates")

    # Deduplicate by URL
    seen = set()
    unique = []
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)

    print(f"  total unique: {len(unique)}")
    return unique


# ─── Phase 1b: Download ───────────────────────────────────────────────────────

def download_score(url: str, tier: str, title: str) -> Optional[Path]:
    """Download a PDF to the appropriate corpus originals folder."""
    dest_dir = ORIGINALS_DIR / tier
    safe_name = re.sub(r"[^\w\-.]", "_", url.split("/")[-1])
    dest_path = dest_dir / safe_name

    if dest_path.exists() and dest_path.stat().st_size > 1000:
        return dest_path  # already on disk

    try:
        r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        r.raise_for_status()
        content = r.content
        # Validate it's actually a PDF
        if not content[:4] == b"%PDF":
            # Some sources return HTML redirect pages
            return None
        with open(dest_path, "wb") as f:
            f.write(content)
        return dest_path
    except Exception as e:
        print(f"  [download] failed {url}: {e}")
        return None


# ─── Phase 2: Convert ─────────────────────────────────────────────────────────

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def parse_conversion_output(stdout: str, stderr: str) -> dict:
    """Extract metrics from scoreforge.py terminal output."""
    text = strip_ansi(stdout + "\n" + stderr)
    result = {
        "match_score": None,
        "iterations_used": None,
        "converged": False,
        "failure_mode": None,
    }

    # Match score: "Best match score: 87/100" or "Pixel match score: 87/100"
    m = re.search(r"Best match score:\s*(\d+(?:\.\d+)?)/100", text)
    if not m:
        m = re.search(r"Pixel match score:\s*(\d+(?:\.\d+)?)/100", text)
    if m:
        result["match_score"] = float(m.group(1))

    # Converged: threshold met message
    if re.search(r"Match score \d+ >= \d+ threshold", text):
        result["converged"] = True
    if "AI reports perfect match" in text:
        result["match_score"] = 100.0
        result["converged"] = True

    # Iteration count (look for "Step 3" iteration patterns)
    iteration_nums = re.findall(r"Iteration (\d+)/", text)
    if iteration_nums:
        result["iterations_used"] = int(iteration_nums[-1])

    # Failure modes — ordered from most specific to least
    if "Render failed" in text or "render_failed" in text.lower():
        result["failure_mode"] = "render_failed"
    elif "JSONDecodeError" in text or "json.decoder" in text:
        result["failure_mode"] = "json_parse_error"
    elif "BadRequestError" in text or "invalid_request_error" in text:
        result["failure_mode"] = "api_invalid_request"
    elif "overloaded" in text.lower() or "529" in text:
        result["failure_mode"] = "api_overloaded"
    elif "rate_limit" in text.lower() or "RateLimitError" in text:
        result["failure_mode"] = "rate_limit"
    elif "Extraction failed" in text or "extraction_failed" in text.lower():
        result["failure_mode"] = "extraction_failed"
    elif "Error" in text and result["match_score"] is None:
        result["failure_mode"] = "conversion_error"

    # If we have a score but didn't converge
    if result["match_score"] is not None and not result["converged"]:
        result["failure_mode"] = result["failure_mode"] or "threshold_not_met"

    return result


def estimate_accuracy_from_musicxml(musicxml_path: Path) -> dict:
    """Heuristic pitch/rhythm accuracy from the output MusicXML.

    Without ground truth MusicXML, we can only estimate from structural
    indicators: note count plausibility, duration consistency, etc.
    Returns rough estimates (0-100) — real accuracy requires diff vs ground truth.
    """
    if not musicxml_path.exists():
        return {"pitch_accuracy": None, "rhythm_accuracy": None}

    try:
        content = musicxml_path.read_text(encoding="utf-8", errors="replace")
        # Count notes
        note_count = content.count("<note>") + content.count("<note ")
        # Check for duration elements
        duration_count = content.count("<duration>")
        # Check for malformed XML indicators
        has_pitch = "<pitch>" in content
        has_duration = "<duration>" in content
        has_measure = "<measure" in content

        if not (has_pitch and has_duration and has_measure):
            return {"pitch_accuracy": 10.0, "rhythm_accuracy": 10.0}

        # Rough heuristic: if note/duration ratio is close to 1:1, rhythm is sane
        if note_count > 0 and duration_count > 0:
            ratio = duration_count / note_count
            rhythm_est = min(100.0, max(10.0, 100 - abs(1 - ratio) * 50))
        else:
            rhythm_est = 20.0

        # Pitch accuracy — check if pitch elements have step+octave
        step_count = content.count("<step>")
        octave_count = content.count("<octave>")
        if note_count > 0:
            pitch_est = min(100.0, 100 * min(step_count, octave_count) / note_count)
        else:
            pitch_est = 20.0

        return {
            "pitch_accuracy": round(pitch_est, 1),
            "rhythm_accuracy": round(rhythm_est, 1),
        }
    except Exception:
        return {"pitch_accuracy": None, "rhythm_accuracy": None}


def pdf_to_png(pdf_path: Path) -> Optional[Path]:
    """Convert first page of a PDF to PNG using pdftoppm.

    Claude Vision only accepts image/jpeg, image/png, image/gif, image/webp —
    not application/pdf. We convert first page at 150 DPI (good quality for OMR).
    Returns path to the .png file, or None if conversion failed.
    """
    out_prefix = pdf_path.with_suffix("")
    png_path = Path(str(out_prefix) + "-1.png")
    if png_path.exists():
        return png_path
    try:
        result = subprocess.run(
            ["pdftoppm", "-r", "150", "-png", "-f", "1", "-l", "1",
             str(pdf_path), str(out_prefix)],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0 and png_path.exists():
            return png_path
        # pdftoppm might produce -01.png instead of -1.png
        alt = Path(str(out_prefix) + "-01.png")
        if alt.exists():
            alt.rename(png_path)
            return png_path
        return None
    except Exception as e:
        print(f"  [pdf2png] {e}")
        return None


def run_conversion(pdf_path: Path, max_iterations: int = 5) -> dict:
    """Run scoreforge.py on a PDF and return parsed metrics.

    Converts PDF to PNG first since Claude Vision requires image formats.
    """
    # Convert PDF → PNG for Claude Vision
    img_path = pdf_to_png(pdf_path)
    if img_path is None:
        return {
            "status": "failed",
            "failure_mode": "pdf_conversion_failed",
            "error_message": "Could not convert PDF to PNG for vision processing",
            "musicxml_path": None,
            "report_path": None,
        }

    musicxml_path = MUSICXML_DIR / pdf_path.with_suffix(".musicxml").name
    report_path = MUSICXML_DIR / pdf_path.with_suffix(".html").name

    cmd = [
        sys.executable, str(SCOREFORGE),
        str(img_path),
        "--output", str(musicxml_path),
        "--validate",
        "--max-iterations", str(max_iterations),
        "--report",
    ]

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min per score
            cwd=str(ROOT),
        )
        elapsed = time.time() - start
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "failure_mode": "timeout",
            "error_message": "Conversion timed out after 300s",
            "musicxml_path": None,
            "report_path": None,
        }
    except Exception as e:
        return {
            "status": "failed",
            "failure_mode": "subprocess_error",
            "error_message": str(e),
            "musicxml_path": None,
            "report_path": None,
        }

    metrics = parse_conversion_output(stdout, stderr)

    if proc.returncode != 0 and metrics["match_score"] is None:
        # Extract last error from output
        error_lines = [l for l in (stdout + stderr).split("\n") if l.strip()]
        error_msg = error_lines[-1] if error_lines else "unknown error"
        return {
            "status": "failed",
            "failure_mode": metrics.get("failure_mode") or "conversion_error",
            "error_message": strip_ansi(error_msg)[:500],
            "musicxml_path": None,
            "report_path": None,
        }

    # Check output file
    if not musicxml_path.exists():
        return {
            "status": "failed",
            "failure_mode": "no_output",
            "error_message": "No .musicxml file produced",
            "musicxml_path": None,
            "report_path": None,
        }

    accuracy = estimate_accuracy_from_musicxml(musicxml_path)

    return {
        "status": "completed",
        "match_score": metrics["match_score"],
        "pitch_accuracy": accuracy["pitch_accuracy"],
        "rhythm_accuracy": accuracy["rhythm_accuracy"],
        "iterations_used": metrics["iterations_used"],
        "converged": metrics["converged"],
        "failure_mode": metrics["failure_mode"],
        "musicxml_path": str(musicxml_path),
        "report_path": str(report_path) if report_path.exists() else None,
        "elapsed_seconds": round(elapsed, 1),
    }


# ─── Phase 4: Daily Summary Report ────────────────────────────────────────────

def generate_daily_report(conn: sqlite3.Connection) -> Path:
    """Generate a markdown daily summary report."""
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT complexity_tier, conversion_status, match_score, failure_mode
        FROM corpus
    """).fetchall()

    total = len(rows)
    completed = [r for r in rows if r[1] == "completed"]
    failed = [r for r in rows if r[1] == "failed"]
    pending = [r for r in rows if r[1] == "pending"]

    scores = [r[2] for r in completed if r[2] is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    # Failure breakdown
    failure_counts: dict[str, int] = {}
    for r in failed:
        fm = r[3] or "unknown"
        failure_counts[fm] = failure_counts.get(fm, 0) + 1

    # Per-tier stats
    tier_stats: dict[str, dict] = {}
    for tier in ["simple", "moderate", "complex", "orchestral"]:
        tier_rows = [r for r in rows if r[0] == tier]
        tier_completed = [r for r in tier_rows if r[1] == "completed"]
        tier_scores = [r[2] for r in tier_completed if r[2] is not None]
        tier_stats[tier] = {
            "total": len(tier_rows),
            "completed": len(tier_completed),
            "failed": len([r for r in tier_rows if r[1] == "failed"]),
            "avg_score": round(sum(tier_scores) / len(tier_scores), 1) if tier_scores else 0,
        }

    report = f"""# ScoreForge Corpus Daily Report — {today}

## Summary
| Metric | Value |
|--------|-------|
| Total scores in corpus | {total} |
| Completed conversions | {len(completed)} |
| Failed conversions | {len(failed)} |
| Pending | {len(pending)} |
| Average match score | {avg_score}/100 |

## Per-Tier Performance
| Tier | Total | Completed | Failed | Avg Score |
|------|-------|-----------|--------|-----------|
"""
    for tier, stats in tier_stats.items():
        report += f"| {tier} | {stats['total']} | {stats['completed']} | {stats['failed']} | {stats['avg_score']}/100 |\n"

    report += "\n## Failure Categories\n"
    if failure_counts:
        report += "| Failure Mode | Count |\n|---|---|\n"
        for mode, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
            report += f"| {mode} | {count} |\n"
    else:
        report += "_No failures recorded._\n"

    # Accuracy progression (last 20 completed, by processed_date)
    recent = conn.execute("""
        SELECT title, complexity_tier, match_score, pitch_accuracy, rhythm_accuracy,
               iterations_used, converged
        FROM corpus
        WHERE conversion_status = 'completed'
        ORDER BY processed_date DESC
        LIMIT 20
    """).fetchall()

    if recent:
        report += "\n## Recent Completions (last 20)\n"
        report += "| Title | Tier | Match | Pitch | Rhythm | Iters | Converged |\n"
        report += "|-------|------|-------|-------|--------|-------|-----------|\n"
        for row in recent:
            title, tier, match, pitch, rhythm, iters, conv = row
            report += (
                f"| {(title or 'Unknown')[:40]} | {tier} "
                f"| {match or '-'} | {pitch or '-'} | {rhythm or '-'} "
                f"| {iters or '-'} | {'✓' if conv else '✗'} |\n"
            )

    report_path = REPORTS_DIR / f"daily_{today}.md"
    report_path.write_text(report)
    return report_path


# ─── Main Loop ────────────────────────────────────────────────────────────────

def run_loop(tier: Optional[str], batch_size: int, max_iterations: int,
             dry_run: bool = False):
    conn = init_db(DB_PATH)
    tiers = [tier] if tier else ["simple", "moderate", "complex", "orchestral"]

    print(f"\n{'='*60}")
    print(f"ScoreForge Training Loop")
    print(f"  date:        {datetime.utcnow().isoformat()}")
    print(f"  tiers:       {tiers}")
    print(f"  batch_size:  {batch_size}")
    print(f"  max_iters:   {max_iterations}")
    print(f"  db:          {DB_PATH}")
    print(f"{'='*60}\n")

    processed_this_run = 0
    results_this_run = []

    for current_tier in tiers:
        print(f"\n{'─'*40}")
        print(f"TIER: {current_tier}")
        print(f"{'─'*40}")

        # ── Phase 1: Discover ──────────────────────────────────────────────────
        candidates = discover_scores(current_tier, batch_size)

        # Filter already-processed
        new_candidates = [
            c for c in candidates
            if not already_processed(conn, c["url"])
        ]
        print(f"  new (unprocessed): {len(new_candidates)}")
        if not new_candidates:
            print(f"  nothing new for tier '{current_tier}', skipping")
            continue

        batch = new_candidates[:batch_size]
        print(f"  processing batch of {len(batch)}")

        for i, candidate in enumerate(batch, 1):
            url = candidate["url"]
            title = candidate["title"]
            composer = candidate["composer"]
            source = candidate["source"]

            print(f"\n  [{i}/{len(batch)}] {title} ({composer})")
            print(f"         url: {url}")

            if dry_run:
                print(f"         [dry-run] skipping download + conversion")
                continue

            # Register in DB
            upsert_source(conn, url, current_tier, title, composer, source)

            # ── Phase 1b: Download ─────────────────────────────────────────────
            pdf_path = download_score(url, current_tier, title)
            if pdf_path is None:
                print(f"         download failed — skipping")
                record_conversion(
                    conn, url,
                    status="failed",
                    failure_mode="download_failed",
                    error_message="Could not download or validate PDF",
                )
                results_this_run.append({
                    "url": url, "tier": current_tier,
                    "status": "failed", "match_score": None,
                })
                continue

            record_download(conn, url, str(pdf_path))
            print(f"         downloaded: {pdf_path.name} ({pdf_path.stat().st_size // 1024}KB)")

            # ── Phase 2: Convert ───────────────────────────────────────────────
            print(f"         converting (max {max_iterations} iters)...")
            result = run_conversion(pdf_path, max_iterations=max_iterations)

            # ── Phase 3: Record ────────────────────────────────────────────────
            record_conversion(
                conn, url,
                status=result["status"],
                match_score=result.get("match_score"),
                pitch_accuracy=result.get("pitch_accuracy"),
                rhythm_accuracy=result.get("rhythm_accuracy"),
                iterations_used=result.get("iterations_used"),
                converged=result.get("converged"),
                failure_mode=result.get("failure_mode"),
                error_message=result.get("error_message"),
                musicxml_path=result.get("musicxml_path"),
                report_path=result.get("report_path"),
            )

            status_str = result["status"]
            if result.get("match_score") is not None:
                status_str += f"  match={result['match_score']}/100"
            if result.get("failure_mode"):
                status_str += f"  ({result['failure_mode']})"
            if result.get("elapsed_seconds"):
                status_str += f"  {result['elapsed_seconds']}s"
            print(f"         {status_str}")

            results_this_run.append({
                "url": url,
                "tier": current_tier,
                "status": result["status"],
                "match_score": result.get("match_score"),
            })
            processed_this_run += 1

    # ── Phase 4: Daily Report ──────────────────────────────────────────────────
    report_path = generate_daily_report(conn)
    print(f"\n{'='*60}")
    print(f"Run complete. Processed: {processed_this_run}")

    if results_this_run:
        completed = [r for r in results_this_run if r["status"] == "completed"]
        failed = [r for r in results_this_run if r["status"] == "failed"]
        scores = [r["match_score"] for r in completed if r["match_score"] is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else 0
        print(f"  completed: {len(completed)}  failed: {len(failed)}")
        print(f"  avg match score (this run): {avg}/100")

    print(f"  daily report: {report_path}")
    print(f"  corpus db:    {DB_PATH}")

    # Print corpus totals from DB
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN conversion_status='completed' THEN 1 ELSE 0 END) as done,
            AVG(CASE WHEN match_score IS NOT NULL THEN match_score END) as avg_score
        FROM corpus
    """).fetchone()
    if row:
        total, done, avg_all = row
        print(f"\n  CORPUS TOTALS:")
        print(f"    total records:   {total}")
        print(f"    completed:       {done}")
        print(f"    overall avg:     {round(avg_all, 1) if avg_all else 'N/A'}/100")
    print(f"{'='*60}\n")
    conn.close()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ScoreForge training loop — continuous corpus builder"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int, default=10,
        help="Number of scores to process per run (default: 10)"
    )
    parser.add_argument(
        "--tier", "-t",
        choices=["simple", "moderate", "complex", "orchestral"],
        default=None,
        help="Target complexity tier (default: all tiers)"
    )
    parser.add_argument(
        "--max-iterations", "-m",
        type=int, default=5,
        help="Max scoreforge validation iterations per score (default: 5)"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Just regenerate the daily report, no downloads/conversions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover sources only, no downloads or conversions"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print corpus stats and exit"
    )
    args = parser.parse_args()

    if args.stats or args.report_only:
        conn = init_db(DB_PATH)
        report_path = generate_daily_report(conn)
        rows = conn.execute("""
            SELECT complexity_tier, conversion_status,
                   AVG(match_score), COUNT(*)
            FROM corpus
            GROUP BY complexity_tier, conversion_status
        """).fetchall()
        print(f"\nCorpus stats ({DB_PATH}):")
        for row in rows:
            print(f"  {row[0]:12} {row[1]:12} count={row[3]}  avg_score={round(row[2], 1) if row[2] else 'N/A'}")
        print(f"\nReport: {report_path}")
        conn.close()
        return

    run_loop(
        tier=args.tier,
        batch_size=args.batch_size,
        max_iterations=args.max_iterations,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
