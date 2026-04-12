#!/usr/bin/env python3
"""ScoreForge Baseline Validation Pipeline.

This script validates OMR accuracy against ground truth MusicXML fixtures.
It supports result caching for faster subsequent runs.

USAGE:
    # Run all fixtures with caching (fast for unchanged fixtures)
    python tests/validate_baseline.py

    # Run a single fixture
    python tests/validate_baseline.py --fixture simple_melody

    # Quick mode: only run failed/changed fixtures
    python tests/validate_baseline.py --quick

    # Force fresh run, bypassing cache
    python tests/validate_baseline.py --no-cache

    # Set cache age (default 24 hours)
    python tests/validate_baseline.py --max-age 48
"""
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.renderer import render_musicxml_to_image
from core.comparator import compare_musicxml_semantic
from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml

console = Console()

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR = FIXTURE_DIR / ".validation_cache"
DEFAULT_REPORT_PATH = Path(__file__).parent / "BASELINE_REPORT.md"
DEFAULT_CACHE_AGE_HOURS = 24


@dataclass
class FixtureInfo:
    """Information about a test fixture."""
    name: str
    path: Path
    description: str = ""
    difficulty: str = "easy"
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    
    def file_hash(self) -> str:
        """Calculate SHA256 hash of fixture file."""
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


@dataclass
class FixtureResult:
    """Result from running a single fixture."""
    fixture: FixtureInfo
    passed: bool
    scores: dict = field(default_factory=dict)
    gt_note_count: int = 0
    matched_note_count: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    render_ok: bool = False
    extract_ok: bool = False
    build_ok: bool = False
    compare_ok: bool = False
    from_cache: bool = False
    cached_at: Optional[datetime] = None

    @property
    def note_accuracy(self) -> float:
        return self.scores.get("note_accuracy", 0.0)

    @property
    def pitch_accuracy(self) -> float:
        return self.scores.get("pitch_accuracy", 0.0)

    @property
    def rhythm_accuracy(self) -> float:
        return self.scores.get("rhythm_accuracy", 0.0)

    @property
    def overall_accuracy(self) -> float:
        return self.scores.get("overall", 0.0)

    @property
    def measure_accuracy(self) -> float:
        return self.scores.get("measure_accuracy", 0.0)

    @property
    def key_sig_accuracy(self) -> float:
        return self.scores.get("key_sig_accuracy", 0.0)

    @property
    def time_sig_accuracy(self) -> float:
        return self.scores.get("time_sig_accuracy", 0.0)


@dataclass
class BaselineSummary:
    """Aggregate summary of all fixture results."""
    total_fixtures: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    cached: int = 0
    avg_note_accuracy: float = 0.0
    avg_pitch_accuracy: float = 0.0
    avg_rhythm_accuracy: float = 0.0
    avg_overall_accuracy: float = 0.0
    avg_measure_accuracy: float = 0.0
    avg_key_sig_accuracy: float = 0.0
    avg_time_sig_accuracy: float = 0.0
    total_duration: float = 0.0
    saved_duration: float = 0.0
    target_95_percent_met: bool = False
    timestamp: str = ""


@dataclass
class CacheEntry:
    """Cached result for a fixture."""
    fixture_name: str
    file_hash: str
    model: str
    timestamp: str
    result_data: dict


def ensure_cache_dir() -> None:
    """Ensure cache directory exists."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Create .gitignore to exclude cache from git
    gitignore = CACHE_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")


def get_cache_path(fixture_name: str) -> Path:
    """Get cache file path for a fixture."""
    return CACHE_DIR / f"{fixture_name}.json"


def load_cache(fixture_name: str) -> Optional[CacheEntry]:
    """Load cached result for a fixture."""
    cache_path = get_cache_path(fixture_name)
    if not cache_path.exists():
        return None
    
    try:
        data = json.loads(cache_path.read_text())
        return CacheEntry(
            fixture_name=data.get("fixture_name"),
            file_hash=data.get("file_hash"),
            model=data.get("model"),
            timestamp=data.get("timestamp"),
            result_data=data.get("result_data", {}),
        )
    except (json.JSONDecodeError, KeyError):
        return None


def save_cache(fixture_name: str, file_hash: str, model: str, result: FixtureResult) -> None:
    """Save result to cache."""
    cache_path = get_cache_path(fixture_name)
    ensure_cache_dir()
    
    cache_data = {
        "fixture_name": fixture_name,
        "file_hash": file_hash,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "result_data": {
            "passed": result.passed,
            "scores": result.scores,
            "gt_note_count": result.gt_note_count,
            "matched_note_count": result.matched_note_count,
            "duration_seconds": result.duration_seconds,
            "error": result.error,
            "render_ok": result.render_ok,
            "extract_ok": result.extract_ok,
            "build_ok": result.build_ok,
            "compare_ok": result.compare_ok,
        },
    }
    
    with open(cache_path, "w") as f:
        json.dump(cache_data, f, indent=2)


def get_last_run_summary() -> Optional[dict]:
    """Get summary of last run to identify failed fixtures."""
    summary_path = CACHE_DIR / "last_run_summary.json"
    if not summary_path.exists():
        return None
    
    try:
        return json.loads(summary_path.read_text())
    except (json.JSONDecodeError, KeyError):
        return None


def save_last_run_summary(summary_data: dict) -> None:
    """Save summary of current run."""
    ensure_cache_dir()
    summary_path = CACHE_DIR / "last_run_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary_data, f, indent=2)


def is_cache_valid(
    cache: Optional[CacheEntry],
    fixture: FixtureInfo,
    model: str,
    max_age_hours: float,
) -> bool:
    """Check if cache is valid and can be used."""
    if cache is None:
        return False
    
    # Check file hash - fixture must not have changed
    if cache.file_hash != fixture.file_hash():
        return False
    
    # Check model - must be same model
    if cache.model != model:
        return False
    
    # Check age - must not be too old
    try:
        cache_time = datetime.fromisoformat(cache.timestamp)
        age = datetime.now() - cache_time
        if age > timedelta(hours=max_age_hours):
            return False
    except (ValueError, TypeError):
        return False
    
    return True


def result_from_cache(cache: CacheEntry, fixture: FixtureInfo) -> FixtureResult:
    """Create FixtureResult from cache entry."""
    data = cache.result_data
    
    try:
        cache_time = datetime.fromisoformat(cache.timestamp)
    except (ValueError, TypeError):
        cache_time = None
    
    return FixtureResult(
        fixture=fixture,
        passed=data.get("passed", False),
        scores=data.get("scores", {}),
        gt_note_count=data.get("gt_note_count", 0),
        matched_note_count=data.get("matched_note_count", 0),
        duration_seconds=data.get("duration_seconds", 0.0),
        error=data.get("error"),
        render_ok=data.get("render_ok", False),
        extract_ok=data.get("extract_ok", False),
        build_ok=data.get("build_ok", False),
        compare_ok=data.get("compare_ok", False),
        from_cache=True,
        cached_at=cache_time,
    )


def discover_fixtures() -> list[FixtureInfo]:
    """Discover all MusicXML fixtures."""
    fixtures = []
    if not FIXTURE_DIR.exists():
        return fixtures
    for mxml in sorted(FIXTURE_DIR.glob("*.musicxml")):
        fixtures.append(FixtureInfo(name=mxml.stem, path=mxml))
    return fixtures


def filter_fixtures_for_quick(
    fixtures: list[FixtureInfo],
    model: str,
    max_age_hours: float,
) -> list[FixtureInfo]:
    """Filter fixtures to only those that need running in quick mode.
    
    Returns fixtures that:
    - Have never been cached
    - Failed in the last run
    - Have changed since last cache
    - Are older than max_age_hours
    """
    to_run = []
    last_summary = get_last_run_summary()
    
    # Get failed fixtures from last run
    failed_fixtures = set()
    if last_summary:
        for result in last_summary.get("results", []):
            if not result.get("passed") and result.get("compare_ok"):
                failed_fixtures.add(result["name"])
    
    for fixture in fixtures:
        cache = load_cache(fixture.name)
        
        # No cache = needs to run
        if cache is None:
            to_run.append(fixture)
            continue
        
        # Failed last run = needs to run
        if fixture.name in failed_fixtures:
            to_run.append(fixture)
            continue
        
        # File changed = needs to run
        if cache.file_hash != fixture.file_hash():
            to_run.append(fixture)
            continue
        
        # Model changed = needs to run
        if cache.model != model:
            to_run.append(fixture)
            continue
        
        # Cache too old = needs to run
        try:
            cache_time = datetime.fromisoformat(cache.timestamp)
            if datetime.now() - cache_time > timedelta(hours=max_age_hours):
                to_run.append(fixture)
                continue
        except (ValueError, TypeError):
            to_run.append(fixture)
            continue
    
    return to_run


def run_fixture(fixture: FixtureInfo, model: str = "claude-sonnet-4-6") -> FixtureResult:
    """Run a single fixture through the pipeline."""
    start_time = time.time()
    result = FixtureResult(fixture=fixture, passed=False)
    work_dir = RESULTS_DIR / fixture.name
    work_dir.mkdir(parents=True, exist_ok=True)

    gt_path = str(fixture.path)
    gt_png = str(work_dir / "ground_truth.png")
    extracted_xml = str(work_dir / "extracted.musicxml")

    try:
        render_musicxml_to_image(gt_path, gt_png)
        result.render_ok = True
    except Exception as e:
        result.error = f"Render failed: {e}"
        return result

    try:
        score = extract_from_image(gt_png, model=model)
        result.extract_ok = True
    except Exception as e:
        result.error = f"Extraction failed: {e}"
        return result

    try:
        musicxml_content = build_musicxml(score)
        with open(extracted_xml, "w") as f:
            f.write(musicxml_content)
        result.build_ok = True
    except Exception as e:
        result.error = f"Build failed: {e}"
        return result

    try:
        sem_result = compare_musicxml_semantic(gt_path, extracted_xml)
        result.scores = sem_result["scores"]
        result.gt_note_count = sem_result["total_notes_gt"]
        result.matched_note_count = sem_result["total_notes_matched"]
        result.compare_ok = True
        result.passed = sem_result["is_perfect"]
        with open(str(work_dir / "comparison.json"), "w") as f:
            json.dump(sem_result, f, indent=2, default=str)
    except Exception as e:
        result.error = f"Comparison failed: {e}"
        return result

    result.duration_seconds = time.time() - start_time
    return result


def run_all_fixtures(
    fixtures: list[FixtureInfo],
    model: str = "claude-sonnet-4-6",
    verbose: bool = True,
    use_cache: bool = True,
    max_age_hours: float = DEFAULT_CACHE_AGE_HOURS,
) -> list[FixtureResult]:
    """Run all fixtures with optional caching."""
    results = []
    total_saved = 0.0
    
    for i, fixture in enumerate(fixtures, 1):
        current_hash = fixture.file_hash()
        cache = load_cache(fixture.name)
        
        # Try to use cached result
        if use_cache and is_cache_valid(cache, fixture, model, max_age_hours):
            result = result_from_cache(cache, fixture)
            total_saved += result.duration_seconds
            if verbose:
                status = f"[dim](cached {result.cached_at.strftime('%H:%M') if result.cached_at else 'older'})[/dim]"
                console.print(f"\n[bold cyan]Fixture {i}/{len(fixtures)}:[/bold cyan] {fixture.name} {status}")
                if result.passed:
                    console.print(f"  [green]✓ PASSED from cache[/green]")
                else:
                    console.print(f"  [yellow]✗ FAILED from cache[/yellow] (overall: {result.overall_accuracy:.1f}%)")
            results.append(result)
            continue
        
        # Run full pipeline
        if verbose:
            cache_status = ""
            if cache:
                if cache.file_hash != current_hash:
                    cache_status = " [dim](file changed)[/dim]"
                elif cache.model != model:
                    cache_status = f" [dim](model changed: {cache.model} → {model})[/dim]"
                else:
                    try:
                        cache_time = datetime.fromisoformat(cache.timestamp)
                        age = datetime.now() - cache_time
                        cache_status = f" [dim](cache stale: {age.total_seconds()/3600:.1f}h old)[/dim]"
                    except (ValueError, TypeError):
                        cache_status = " [dim](cache invalid)[/dim]"
            console.print(f"\n[bold cyan]Fixture {i}/{len(fixtures)}:[/bold cyan] {fixture.name}{cache_status}")
        
        result = run_fixture(fixture, model=model)
        
        # Save to cache
        save_cache(fixture.name, current_hash, model, result)
        
        results.append(result)
        if verbose:
            if result.passed:
                console.print(f"  [green]✓ PASSED[/green] ({result.duration_seconds:.1f}s)")
            elif result.error:
                console.print(f"  [red]✗ ERROR[/red]: {result.error}")
            else:
                console.print(f"  [yellow]✗ FAILED[/yellow] (overall: {result.overall_accuracy:.1f}%)")
    
    # Report time saved
    if total_saved > 0 and verbose:
        console.print(f"\n[dim]💾 Cache saved {total_saved:.0f}s ({total_saved/60:.1f}m) by reusing {sum(1 for r in results if r.from_cache)} cached results[/dim]")
    
    return results


def calculate_summary(results: list[FixtureResult]) -> BaselineSummary:
    """Calculate aggregate summary."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and r.compare_ok)
    errors = sum(1 for r in results if r.error and not r.compare_ok)
    cached = sum(1 for r in results if r.from_cache)

    scored = [r for r in results if r.scores]
    if scored:
        avg_note = sum(r.note_accuracy for r in scored) / len(scored)
        avg_pitch = sum(r.pitch_accuracy for r in scored) / len(scored)
        avg_rhythm = sum(r.rhythm_accuracy for r in scored) / len(scored)
        avg_overall = sum(r.overall_accuracy for r in scored) / len(scored)
        avg_measure = sum(r.measure_accuracy for r in scored) / len(scored)
        avg_key = sum(r.key_sig_accuracy for r in scored) / len(scored)
        avg_time = sum(r.time_sig_accuracy for r in scored) / len(scored)
    else:
        avg_note = avg_pitch = avg_rhythm = avg_overall = 0.0
        avg_measure = avg_key = avg_time = 0.0

    total_duration = sum(r.duration_seconds for r in results)
    saved_duration = sum(r.duration_seconds for r in results if r.from_cache)

    return BaselineSummary(
        total_fixtures=total, passed=passed, failed=failed, errors=errors, cached=cached,
        avg_note_accuracy=avg_note, avg_pitch_accuracy=avg_pitch,
        avg_rhythm_accuracy=avg_rhythm, avg_overall_accuracy=avg_overall,
        avg_measure_accuracy=avg_measure, avg_key_sig_accuracy=avg_key,
        avg_time_sig_accuracy=avg_time,
        total_duration=total_duration, saved_duration=saved_duration,
        target_95_percent_met=avg_overall >= 95.0,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def generate_markdown_report(results: list[FixtureResult], summary: BaselineSummary, model: str = "claude-sonnet-4-6") -> str:
    """Generate markdown report."""
    sorted_results = sorted(results, key=lambda r: r.fixture.name)
    lines = [
        "# ScoreForge Baseline Accuracy Report",
        "",
        f"**Generated:** {summary.timestamp}",
        f"**Model:** {model}",
        f"**Total Fixtures:** {summary.total_fixtures}",
        f"**From Cache:** {summary.cached} / {summary.total_fixtures}",
        "",
        "## Summary",
        "",
        "| Metric | Value | Target |",
        "|--------|-------|--------|",
        f"| Total Fixtures | {summary.total_fixtures} | - |",
        f"| Passed | {summary.passed} | {summary.total_fixtures} |",
        f"| Failed | {summary.failed} | 0 |",
        f"| Errors | {summary.errors} | 0 |",
        f"| Cached Results | {summary.cached} | - |",
        f"| Note Accuracy | **{summary.avg_note_accuracy:.1f}%** | ≥95% |",
        f"| Pitch Accuracy | **{summary.avg_pitch_accuracy:.1f}%** | ≥95% |",
        f"| Rhythm Accuracy | **{summary.avg_rhythm_accuracy:.1f}%** | ≥95% |",
        f"| Measure Accuracy | **{summary.avg_measure_accuracy:.1f}%** | ≥95% |",
        f"| Key Signature Accuracy | **{summary.avg_key_sig_accuracy:.1f}%** | ≥95% |",
        f"| Time Signature Accuracy | **{summary.avg_time_sig_accuracy:.1f}%** | ≥95% |",
        f"| **Overall Accuracy** | **{summary.avg_overall_accuracy:.1f}%** | **≥95%** |",
        "",
        f"**Status:** {'✅ PASS' if summary.target_95_percent_met else '❌ FAIL'} - 95% target {'met' if summary.target_95_percent_met else 'not met'}",
        "",
        "## Per-Fixture Results",
        "",
        "| Fixture | Status | Note Acc | Pitch Acc | Rhythm Acc | Overall Acc | Notes | Time |",
        "|---------|--------|----------|-----------|-------------|-------------|-------|------|",
    ]

    for r in sorted_results:
        cache_tag = " 📦" if r.from_cache else ""
        status = "✅ PASS" if r.passed else ("❌ ERROR" if r.error and not r.compare_ok else "⚠️ FAIL")
        notes = f"{r.matched_note_count}/{r.gt_note_count}" if r.gt_note_count else "-"
        time_str = f"{r.duration_seconds:.1f}s"
        lines.append(f"| {r.fixture.name}{cache_tag} | {status} | {r.note_accuracy:.1f}% | {r.pitch_accuracy:.1f}% | {r.rhythm_accuracy:.1f}% | {r.overall_accuracy:.1f}% | {notes} | {time_str} |")

    lines.extend([
        "",
        "## Progress Tracking",
        "",
        "This report tracks progress against the Q2 2026 rock:",
        "- **Rock:** Achieve 95%+ accuracy on simple/moderate fixtures",
        f"- **Current:** {summary.avg_overall_accuracy:.1f}% overall accuracy",
        f"- **Target:** ≥95% overall accuracy",
        f"- **Gap:** {max(0, 95.0 - summary.avg_overall_accuracy):.1f}%",
        "",
        "---",
        "",
        "*Report generated by `tests/validate_baseline.py`*",
        f"*Cache enabled: Results reused when fixtures unchanged*",
    ])
    return "\n".join(lines)


def save_report(markdown: str, output_path: Path) -> None:
    """Save markdown report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(markdown)
    console.print(f"\n[green]Report saved to:[/green] {output_path}")


def print_console_report(results: list[FixtureResult], summary: BaselineSummary) -> None:
    """Print console report."""
    console.print("\n")
    console.print(Panel("[bold]Baseline Validation Results[/bold]", expand=False))

    table = Table(title="Per-Fixture Accuracy")
    table.add_column("Fixture", style="bold")
    table.add_column("Status")
    table.add_column("Notes", justify="right")
    table.add_column("Pitch %", justify="right")
    table.add_column("Rhythm %", justify="right")
    table.add_column("Overall %", justify="right")
    table.add_column("Time", justify="right")

    for r in sorted(results, key=lambda x: x.fixture.name):
        cache_suffix = " 📦" if r.from_cache else ""
        status = "[green]PASS[/green]" if r.passed else ("[red]ERROR[/red]" if r.error and not r.compare_ok else "[yellow]FAIL[/yellow]")
        notes = f"{r.matched_note_count}/{r.gt_note_count}" if r.gt_note_count else "-"
        time_str = f"{r.duration_seconds:.1f}s"
        table.add_row(r.fixture.name + cache_suffix, status, notes, f"{r.pitch_accuracy:.0f}%", f"{r.rhythm_accuracy:.0f}%", f"{r.overall_accuracy:.0f}%", time_str)

    console.print(table)
    
    if summary.cached > 0:
        time_saved_pct = (summary.saved_duration / (summary.total_duration + summary.saved_duration)) * 100 if (summary.total_duration + summary.saved_duration) > 0 else 0
        console.print(f"\n  Total: {summary.total_fixtures}  Passed: {summary.passed}  Failed: {summary.failed}  Errors: {summary.errors}  [dim]Cached: {summary.cached}[/dim]")
        console.print(f"  Time: {summary.total_duration/60:.1f}m run + {summary.saved_duration/60:.1f}m cached = {(summary.total_duration + summary.saved_duration)/60:.1f}m total [dim]({time_saved_pct:.0f}% saved via cache)[/dim]")
    else:
        console.print(f"\n  Total: {summary.total_fixtures}  Passed: {summary.passed}  Failed: {summary.failed}  Errors: {summary.errors}")
        console.print(f"  Time: {summary.total_duration/60:.1f}m")
    
    console.print(f"  Overall accuracy: {summary.avg_overall_accuracy:.1f}% (target: ≥95%)")
    console.print(f"  Pitch accuracy: {summary.avg_pitch_accuracy:.1f}%")
    console.print(f"  Rhythm accuracy: {summary.avg_rhythm_accuracy:.1f}%")
    console.print(f"  Measure accuracy: {summary.avg_measure_accuracy:.1f}%")
    gate_status = "[green]✓ PASS[/green]" if summary.target_95_percent_met else "[red]✗ FAIL[/red]"
    console.print(f"\n  95% Target Gate: {gate_status}")


@click.command()
@click.option("--fixture", "-f", default=None, help="Run only this fixture (e.g., simple_melody)")
@click.option("--quick", "-q", is_flag=True, help="Quick mode: only run failed/changed fixtures")
@click.option("--model", "-m", default="claude-sonnet-4-6", help="Claude model")
@click.option("--output", "-o", default=None, help="Output path for markdown report")
@click.option("--quiet", is_flag=True, help="Quiet mode")
@click.option("--no-cache", is_flag=True, help="Disable caching, run all fixtures fresh")
@click.option("--max-age", default=DEFAULT_CACHE_AGE_HOURS, type=float, help=f"Maximum cache age in hours (default: {DEFAULT_CACHE_AGE_HOURS})")
@click.option("--list-fixtures", is_flag=True, help="List fixtures")
@click.option("--clear-cache", is_flag=True, help="Clear validation cache")
def main(fixture, quick, model, output, quiet, no_cache, max_age, list_fixtures, clear_cache):
    """Run baseline validation.
    
    Examples:
        python tests/validate_baseline.py                    # Run all fixtures with caching
        python tests/validate_baseline.py --fixture simple_melody  # Single fixture
        python tests/validate_baseline.py --quick              # Only failed/changed
        python tests/validate_baseline.py --no-cache           # Force fresh run
        python tests/validate_baseline.py --max-age 48         # 48h cache window
    """
    fixtures = discover_fixtures()

    if list_fixtures:
        console.print("[bold]Available fixtures:[/bold]")
        for f in fixtures:
            console.print(f"  [green]✓[/green] {f.name}: {f.path}")
        return

    if not fixtures:
        console.print("[red]No fixtures found![/red]")
        return

    if clear_cache:
        if CACHE_DIR.exists():
            import shutil
            shutil.rmtree(CACHE_DIR)
            console.print(f"[green]Cache cleared:[/green] {CACHE_DIR}")
        else:
            console.print("[yellow]No cache to clear.[/yellow]")
        return

    use_cache = not no_cache
    
    # Filter fixtures based on options
    if fixture:
        fixtures = [f for f in fixtures if f.name == fixture]
        if not fixtures:
            console.print(f"[red]Fixture '{fixture}' not found.[/red]")
            console.print(f"[dim]Use --list-fixtures to see available fixtures.[/dim]")
            sys.exit(1)
    elif quick:
        original_count = len(fixtures)
        fixtures = filter_fixtures_for_quick(fixtures, model, max_age)
        console.print(f"[cyan]Quick mode:[/cyan] {len(fixtures)}/{original_count} fixtures need running")
        if not fixtures:
            console.print("[green]All fixtures up to date! Use --no-cache to force fresh run.[/green]")
            return

    output_path = Path(output) if output else DEFAULT_REPORT_PATH

    console.print(Panel(
        f"[bold]ScoreForge Baseline Validation[/bold]\n"
        f"Fixtures: {len(fixtures)}\n"
        f"Model: {model}\n"
        f"Cache: {'disabled' if no_cache else f'enabled (max {max_age}h)'}\n"
        f"Output: {output_path}",
        title="Configuration",
    ))

    results = run_all_fixtures(
        fixtures, 
        model=model, 
        verbose=not quiet, 
        use_cache=use_cache,
        max_age_hours=max_age,
    )
    summary = calculate_summary(results)
    
    if not quiet:
        print_console_report(results, summary)

    markdown = generate_markdown_report(results, summary, model)
    save_report(markdown, output_path)

    # Save JSON report
    json_path = output_path.with_suffix(".json")
    json_data = {
        "timestamp": summary.timestamp,
        "model": model,
        "summary": {
            "total_fixtures": summary.total_fixtures,
            "passed": summary.passed,
            "failed": summary.failed,
            "errors": summary.errors,
            "cached": summary.cached,
            "avg_note_accuracy": summary.avg_note_accuracy,
            "avg_pitch_accuracy": summary.avg_pitch_accuracy,
            "avg_rhythm_accuracy": summary.avg_rhythm_accuracy,
            "avg_overall_accuracy": summary.avg_overall_accuracy,
            "avg_measure_accuracy": summary.avg_measure_accuracy,
            "avg_key_sig_accuracy": summary.avg_key_sig,
            "avg_time_sig_accuracy": summary.avg_time_sig,
            "target_95_percent_met": summary.target_95_percent_met,
            "total_duration": summary.total_duration,
            "saved_duration": summary.saved_duration,
        },
        "results": [
            {
                "name": r.fixture.name,
                "passed": r.passed,
                "scores": r.scores,
                "gt_notes": r.gt_note_count,
                "matched_notes": r.matched_note_count,
                "duration_seconds": r.duration_seconds,
                "error": r.error,
                "from_cache": r.from_cache,
            }
            for r in results
        ],
    }
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    console.print(f"  JSON report saved to: {json_path}")

    # Save last run summary for quick mode
    last_run_data = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "results": [
            {
                "name": r.fixture.name,
                "passed": r.passed,
                "compare_ok": r.compare_ok,
            }
            for r in results
        ],
    }
    save_last_run_summary(last_run_data)

    sys.exit(0 if summary.target_95_percent_met else 1)


if __name__ == "__main__":
    main()
