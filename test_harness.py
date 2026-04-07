#!/usr/bin/env python3
"""ScoreForge Test Harness — automated evaluation of the extraction pipeline.

This harness uses a ground-truth approach:
1. Start with known-correct MusicXML files (fixtures).
2. Render them to PNG images using Verovio.
3. Feed those images through the ScoreForge extraction pipeline.
4. Compare the extracted MusicXML against the original ground truth semantically.
5. Score and report results.

Usage:
    python test_harness.py                        # run all fixtures
    python test_harness.py --fixture simple_melody # run one fixture
    python test_harness.py --no-api               # skip API calls, test infra only
"""
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.renderer import render_musicxml_to_image
from core.comparator import compare_musicxml_semantic, compare_images
from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml

console = Console()

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single test case with ground truth MusicXML."""
    name: str
    musicxml_path: str
    description: str = ""
    difficulty: str = "easy"  # easy, medium, hard
    expected_notes: int = 0  # 0 = auto-count
    tags: list[str] = field(default_factory=list)


# Built-in test cases from fixtures
BUILT_IN_TESTS = [
    TestCase(
        name="simple_melody",
        musicxml_path=str(FIXTURE_DIR / "simple_melody.musicxml"),
        description="C major, 4/4, 8 measures of quarter and half notes, single staff",
        difficulty="easy",
        tags=["single_staff", "no_accidentals", "basic_rhythm"],
    ),
    TestCase(
        name="piano_chords",
        musicxml_path=str(FIXTURE_DIR / "piano_chords.musicxml"),
        description="G major, 3/4, 4 measures with chords, piano grand staff",
        difficulty="medium",
        tags=["grand_staff", "chords", "dotted_notes"],
    ),
    TestCase(
        name="complex_rhythm",
        musicxml_path=str(FIXTURE_DIR / "complex_rhythm.musicxml"),
        description="Bb major, 6/8, 4 measures with dotted notes, ties, eighth notes",
        difficulty="hard",
        tags=["compound_meter", "ties", "accidentals", "beams"],
    ),
    TestCase(
        name="nested_tuplets",
        musicxml_path=str(FIXTURE_DIR / "nested_tuplets.musicxml"),
        description="C major, 3/4, 4 measures, 2-voice counterpoint with triplet tuplets",
        difficulty="hard",
        tags=["tuplets", "multi_voice", "triplets", "time_modification"],
    ),
]


# ---------------------------------------------------------------------------
# Test result
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """Result from running a single test case."""
    test_name: str
    passed: bool
    scores: dict = field(default_factory=dict)
    render_ok: bool = False
    extract_ok: bool = False
    build_ok: bool = False
    compare_ok: bool = False
    visual_score: Optional[int] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    gt_note_count: int = 0
    matched_note_count: int = 0


# ---------------------------------------------------------------------------
# Harness runner
# ---------------------------------------------------------------------------

def discover_fixtures() -> list[TestCase]:
    """Discover all MusicXML fixtures in the fixture directory."""
    tests = []
    if not FIXTURE_DIR.exists():
        return BUILT_IN_TESTS

    # Check for custom fixtures beyond the built-in ones
    built_in_names = {t.name for t in BUILT_IN_TESTS}
    for mxml in sorted(FIXTURE_DIR.glob("*.musicxml")):
        name = mxml.stem
        if name not in built_in_names:
            tests.append(TestCase(
                name=name,
                musicxml_path=str(mxml),
                description=f"Custom fixture: {name}",
                difficulty="unknown",
            ))

    return BUILT_IN_TESTS + tests


def run_test(
    test: TestCase,
    model: str = "claude-sonnet-4-5-20250929",
    skip_api: bool = False,
    work_dir: Optional[Path] = None,
) -> TestResult:
    """Run a single test case through the full pipeline.

    Steps:
    1. Render ground truth MusicXML to PNG.
    2. Extract music from the PNG using Claude Vision.
    3. Build MusicXML from the extraction.
    4. Compare extracted MusicXML to ground truth semantically.
    5. Optionally compare rendered images visually.
    """
    start_time = time.time()
    result = TestResult(test_name=test.name, passed=False)

    if work_dir is None:
        work_dir = RESULTS_DIR / test.name
    work_dir.mkdir(parents=True, exist_ok=True)

    gt_path = test.musicxml_path
    gt_png = str(work_dir / "ground_truth.png")
    extracted_xml = str(work_dir / "extracted.musicxml")
    extracted_png = str(work_dir / "extracted.png")

    # --- Step 1: Render ground truth ---
    console.print(f"  [dim]Rendering ground truth...[/dim]")
    try:
        render_musicxml_to_image(gt_path, gt_png)
        result.render_ok = True
    except Exception as e:
        result.error = f"Render failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result

    if skip_api:
        console.print(f"  [yellow]Skipping API extraction (--no-api)[/yellow]")
        result.render_ok = True
        result.duration_seconds = time.time() - start_time
        result.error = "Skipped (--no-api)"
        return result

    # --- Step 2: Extract from image ---
    console.print(f"  [dim]Extracting with Claude Vision...[/dim]")
    try:
        score = extract_from_image(gt_png, model=model)
        result.extract_ok = True
    except Exception as e:
        result.error = f"Extraction failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result

    # --- Step 3: Build MusicXML ---
    console.print(f"  [dim]Building MusicXML...[/dim]")
    try:
        musicxml_content = build_musicxml(score)
        with open(extracted_xml, "w", encoding="utf-8") as f:
            f.write(musicxml_content)
        result.build_ok = True
    except Exception as e:
        result.error = f"Build failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result

    # --- Step 4: Semantic comparison ---
    console.print(f"  [dim]Comparing semantically...[/dim]")
    try:
        sem_result = compare_musicxml_semantic(gt_path, extracted_xml)
        result.scores = sem_result["scores"]
        result.gt_note_count = sem_result["total_notes_gt"]
        result.matched_note_count = sem_result["total_notes_matched"]
        result.compare_ok = True
        result.passed = sem_result["is_perfect"]

        # Save detailed comparison
        with open(str(work_dir / "comparison.json"), "w") as f:
            json.dump(sem_result, f, indent=2, default=str)
    except Exception as e:
        result.error = f"Comparison failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result

    # --- Step 5: Visual comparison (optional, non-blocking) ---
    try:
        render_musicxml_to_image(extracted_xml, extracted_png)
        vis_result = compare_images(gt_png, extracted_png)
        result.visual_score = vis_result["match_score"]
    except Exception:
        pass  # Visual comparison is supplementary

    result.duration_seconds = time.time() - start_time
    return result


def run_all_tests(
    tests: list[TestCase],
    model: str = "claude-sonnet-4-5-20250929",
    skip_api: bool = False,
) -> list[TestResult]:
    """Run all test cases and return results."""
    results = []
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for i, test in enumerate(tests, 1):
        console.print(f"\n[bold cyan]Test {i}/{len(tests)}:[/bold cyan] {test.name}")
        console.print(f"  {test.description}")
        console.print(f"  Difficulty: {test.difficulty}")

        result = run_test(test, model=model, skip_api=skip_api)
        results.append(result)

        # Print immediate result
        if result.passed:
            console.print(f"  [bold green]PASSED[/bold green] ({result.duration_seconds:.1f}s)")
        elif result.error:
            console.print(f"  [bold red]ERROR[/bold red]: {result.error}")
        else:
            console.print(f"  [bold yellow]FAILED[/bold yellow] (overall: {result.scores.get('overall', 0)}%)")

    return results


def print_report(results: list[TestResult]):
    """Print a formatted summary report."""
    console.print("\n")
    console.print(Panel("[bold]ScoreForge Test Report[/bold]", expand=False))

    # Summary table
    table = Table(title="Test Results")
    table.add_column("Test", style="bold")
    table.add_column("Status")
    table.add_column("Notes", justify="right")
    table.add_column("Pitch %", justify="right")
    table.add_column("Rhythm %", justify="right")
    table.add_column("Overall %", justify="right")
    table.add_column("Visual", justify="right")
    table.add_column("Time", justify="right")

    for r in results:
        status = "[green]PASS[/green]" if r.passed else ("[red]ERROR[/red]" if r.error and not r.compare_ok else "[yellow]FAIL[/yellow]")
        notes = f"{r.matched_note_count}/{r.gt_note_count}" if r.gt_note_count else "-"
        pitch = f"{r.scores.get('pitch_accuracy', 0):.0f}%" if r.scores else "-"
        rhythm = f"{r.scores.get('rhythm_accuracy', 0):.0f}%" if r.scores else "-"
        overall = f"{r.scores.get('overall', 0):.0f}%" if r.scores else "-"
        visual = f"{r.visual_score}" if r.visual_score is not None else "-"
        time_str = f"{r.duration_seconds:.1f}s"

        table.add_row(r.test_name, status, notes, pitch, rhythm, overall, visual, time_str)

    console.print(table)

    # Aggregate stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and r.compare_ok)
    errors = sum(1 for r in results if r.error and not r.compare_ok)

    console.print(f"\n  Total: {total}  Passed: {passed}  Failed: {failed}  Errors: {errors}")

    if results and any(r.scores for r in results):
        scored = [r for r in results if r.scores]
        avg_overall = sum(r.scores.get("overall", 0) for r in scored) / len(scored)
        avg_pitch = sum(r.scores.get("pitch_accuracy", 0) for r in scored) / len(scored)
        avg_rhythm = sum(r.scores.get("rhythm_accuracy", 0) for r in scored) / len(scored)
        console.print(f"  Average overall: {avg_overall:.1f}%")
        console.print(f"  Average pitch accuracy: {avg_pitch:.1f}%")
        console.print(f"  Average rhythm accuracy: {avg_rhythm:.1f}%")

    # Save JSON report
    report_path = RESULTS_DIR / "test_report.json"
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "results": [
            {
                "name": r.test_name,
                "passed": r.passed,
                "scores": r.scores,
                "visual_score": r.visual_score,
                "gt_notes": r.gt_note_count,
                "matched_notes": r.matched_note_count,
                "duration_seconds": r.duration_seconds,
                "error": r.error,
            }
            for r in results
        ],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)
    console.print(f"\n  Report saved to: {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--fixture", "-f", default=None, help="Run only this fixture (by name)")
@click.option("--model", "-m", default="claude-sonnet-4-5-20250929", help="Claude model")
@click.option("--no-api", is_flag=True, help="Skip API calls (test rendering/infra only)")
@click.option("--list-fixtures", is_flag=True, help="List available fixtures and exit")
def main(fixture, model, no_api, list_fixtures):
    """Run the ScoreForge test harness."""
    tests = discover_fixtures()

    if list_fixtures:
        console.print("[bold]Available test fixtures:[/bold]")
        for t in tests:
            exists = Path(t.musicxml_path).exists()
            status = "[green]OK[/green]" if exists else "[red]MISSING[/red]"
            console.print(f"  {status} {t.name}: {t.description}")
        return

    if fixture:
        tests = [t for t in tests if t.name == fixture]
        if not tests:
            console.print(f"[red]Fixture '{fixture}' not found.[/red]")
            sys.exit(1)

    console.print(Panel(
        f"[bold]ScoreForge Test Harness[/bold]\n"
        f"Fixtures: {len(tests)}\n"
        f"Model: {model}\n"
        f"API calls: {'disabled' if no_api else 'enabled'}",
        title="Configuration",
    ))

    results = run_all_tests(tests, model=model, skip_api=no_api)
    print_report(results)


if __name__ == "__main__":
    main()
