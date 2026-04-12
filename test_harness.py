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
CORPUS_DIR = Path(__file__).parent / "corpus" / "originals"
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
    TestCase(
        name="annotations",
        musicxml_path=str(FIXTURE_DIR / "annotations.musicxml"),
        description="Piece with text annotations (rehearsal letters A, B, C), tempo markings, and expression text",
        difficulty="medium",
        tags=["text_expressions", "rehearsal_marks", "tempo_text"],
    ),
    TestCase(
        name="clef_changes",
        musicxml_path=str(FIXTURE_DIR / "clef_changes.musicxml"),
        description="Single staff with multiple clef changes (treble → bass → alto/tenor), mid-measure or at barline",
        difficulty="medium",
        tags=["mid_measure_clef", "bass_clef", "alto_clef", "tenor_clef"],
    ),
    TestCase(
        name="dynamics_hairpins",
        musicxml_path=str(FIXTURE_DIR / "dynamics_hairpins.musicxml"),
        description="Piece with dynamic markings (pp, mp, f, ff) and crescendo/decrescendo hairpins",
        difficulty="medium",
        tags=["dynamics", "hairpins", "cresc", "decresc", "pp_ff"],
    ),
    TestCase(
        name="empty_score",
        musicxml_path=str(FIXTURE_DIR / "empty_score.musicxml"),
        description="Valid MusicXML with one part, one measure, whole rest — no pitched notes (edge case)",
        difficulty="edge_case",
        tags=["empty", "zero_notes", "error_handling"],
    ),
    TestCase(
        name="full_orchestra",
        musicxml_path=str(FIXTURE_DIR / "full_orchestra.musicxml"),
        description="Full orchestra score with multiple parts including strings, winds, brass, and transposing instruments",
        difficulty="expert",
        tags=["multi_part", "transposing_instruments", "score_layout"],
    ),
    TestCase(
        name="key_changes",
        musicxml_path=str(FIXTURE_DIR / "key_changes.musicxml"),
        description="Multi-measure piece with key signature changes mid-piece and cancellation naturals",
        difficulty="medium",
        tags=["key_sig_change", "mid_piece_modulation", "naturals"],
    ),
    TestCase(
        name="lyrics_verses",
        musicxml_path=str(FIXTURE_DIR / "lyrics_verses.musicxml"),
        description="Vocal part with lyrics across multiple verses, syllable hyphenation and verse numbering",
        difficulty="medium",
        tags=["lyrics", "multi_verse", "syllable_split"],
    ),
    TestCase(
        name="marching_stickings",
        musicxml_path=str(FIXTURE_DIR / "marching_stickings.musicxml"),
        description="Snare drum part in 4/4 with unpitched percussion notation and R/L sticking text expressions",
        difficulty="medium",
        tags=["percussion", "unpitched", "stickings", "text_expressions"],
    ),
    TestCase(
        name="mixed_meters",
        musicxml_path=str(FIXTURE_DIR / "mixed_meters.musicxml"),
        description="4 measures with alternating unusual time signatures (7/8, 5/4, etc.), no key signature",
        difficulty="hard",
        tags=["time_sig_changes", "7/8", "5/4", "irregular_grouping"],
    ),
    TestCase(
        name="multi_voice",
        musicxml_path=str(FIXTURE_DIR / "multi_voice.musicxml"),
        description="4/4, 4 measures with two-voice counterpoint using backup element; measure 1 voice 1+2, measures 2-4 whole-note chords",
        difficulty="hard",
        tags=["two_voice", "backup_element", "counterpoint", "chord_vs_voice"],
    ),
    TestCase(
        name="ornaments",
        musicxml_path=str(FIXTURE_DIR / "ornaments.musicxml"),
        description="4/4, 4 measures in C major with ornaments: trill, turn, mordent, inverted-mordent, and tremolo",
        difficulty="medium",
        tags=["trill", "turn", "mordent", "tremolo", "notations"],
    ),
    TestCase(
        name="repeats_codas",
        musicxml_path=str(FIXTURE_DIR / "repeats_codas.musicxml"),
        description="Short piece with repeat barlines, 1st/2nd endings (volta brackets), and coda/segno navigation symbols",
        difficulty="medium",
        tags=["repeat_barlines", "volta_brackets", "coda", "segno"],
    ),
    TestCase(
        name="solo_with_accompaniment",
        musicxml_path=str(FIXTURE_DIR / "solo_with_accompaniment.musicxml"),
        description="Three-part score with solo violin melody over piano grand staff accompaniment",
        difficulty="medium",
        tags=["multi_part", "grand_staff", "solo", "accompaniment"],
    ),
    TestCase(
        name="title_metadata",
        musicxml_path=str(FIXTURE_DIR / "title_metadata.musicxml"),
        description="4/4 treble-clef melody with full score metadata: title, subtitle, composer, arranger, lyricist, copyright",
        difficulty="easy",
        tags=["metadata", "title", "composer", "copyright"],
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
    skipped: bool = False
    duration_seconds: float = 0.0
    gt_note_count: int = 0
    matched_note_count: int = 0


@dataclass
class CorpusResult:
    """Result from testing extraction on a real-world corpus PDF (no GT MusicXML)."""
    name: str
    passed: bool       # True = extraction + build succeeded without error
    extract_ok: bool = False
    build_ok: bool = False
    note_count: int = 0
    measure_count: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Harness runner
# ---------------------------------------------------------------------------

def discover_corpus_pdfs() -> list[Path]:
    """Discover all PDF files in the corpus directory."""
    pdfs = []
    if CORPUS_DIR.exists():
        for pdf in sorted(CORPUS_DIR.rglob("*.pdf")):
            pdfs.append(pdf)
    return pdfs


def run_corpus_pdf(
    pdf_path: Path,
    model: str = "auto",
) -> CorpusResult:
    """Test extraction on a real-world corpus PDF (no GT — parse success only).

    Passes if extraction and MusicXML build complete without exception.
    """
    import time
    start_time = time.time()
    result = CorpusResult(name=pdf_path.stem, passed=False)

    try:
        score, _model_info = extract_from_image(str(pdf_path), model=model)
        result.extract_ok = True
        result.note_count = sum(len(m.notes) for p in score.parts for m in p.measures)
        result.measure_count = sum(len(p.measures) for p in score.parts)
    except Exception as e:
        result.error = f"Extraction failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result

    try:
        work_dir = RESULTS_DIR / "corpus" / pdf_path.stem
        work_dir.mkdir(parents=True, exist_ok=True)
        musicxml_content = build_musicxml(score)
        out_path = work_dir / "extracted.musicxml"
        out_path.write_text(musicxml_content, encoding="utf-8")
        result.build_ok = True
        result.passed = True
    except Exception as e:
        result.error = f"Build failed: {e}"

    result.duration_seconds = time.time() - start_time
    return result


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
    model: str = "auto",
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
        result.error = None
        result.skipped = True
        return result

    # --- Step 2: Extract from image ---
    console.print(f"  [dim]Extracting with Claude Vision...[/dim]")
    try:
        score, _model_info = extract_from_image(gt_png, model=model)
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
    model: str = "auto",
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
        elif result.skipped:
            console.print(f"  [dim]SKIPPED[/dim] (--no-api, {result.duration_seconds:.1f}s)")
        elif result.error:
            console.print(f"  [bold red]ERROR[/bold red]: {result.error}")
        else:
            console.print(f"  [bold yellow]FAILED[/bold yellow] (overall: {result.scores.get('overall', 0)}%)")

    return results


def print_corpus_report(corpus_results: list[CorpusResult]):
    """Print corpus PDF test summary."""
    console.print("\n")
    console.print(Panel("[bold]Corpus PDF Parse Results[/bold]", expand=False))

    table = Table(title="Real-World PDF Extraction")
    table.add_column("PDF", style="bold")
    table.add_column("Status")
    table.add_column("Notes", justify="right")
    table.add_column("Measures", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Error")

    for r in corpus_results:
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        error_text = (r.error or "")[:60] if r.error else ""
        table.add_row(
            r.name,
            status,
            str(r.note_count) if r.extract_ok else "-",
            str(r.measure_count) if r.extract_ok else "-",
            f"{r.duration_seconds:.1f}s",
            error_text,
        )

    console.print(table)

    total = len(corpus_results)
    passed = sum(1 for r in corpus_results if r.passed)
    pct = passed / total * 100 if total else 0
    gate = "≥70%"
    gate_ok = pct >= 70
    gate_str = "[green]PASS[/green]" if gate_ok else "[red]FAIL[/red]"
    console.print(f"\n  Corpus: {passed}/{total} parsed ({pct:.0f}%)  BUILD gate ({gate}): {gate_str}")

    return passed, total, pct


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
        if r.passed:
            status = "[green]PASS[/green]"
        elif r.skipped:
            status = "[dim]SKIP[/dim]"
        elif r.error and not r.compare_ok:
            status = "[red]ERROR[/red]"
        else:
            status = "[yellow]FAIL[/yellow]"
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
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if not r.passed and not r.skipped and r.compare_ok)
    errors = sum(1 for r in results if r.error and not r.compare_ok and not r.skipped)

    console.print(f"\n  Total: {total}  Passed: {passed}  Failed: {failed}  Errors: {errors}  Skipped: {skipped}")

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
        "skipped": skipped,
        "results": [
            {
                "name": r.test_name,
                "passed": r.passed,
                "skipped": r.skipped,
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
@click.option("--model", "-m", default="auto", help="Claude model")
@click.option("--no-api", is_flag=True, help="Skip API calls (test rendering/infra only)")
@click.option("--list-fixtures", is_flag=True, help="List available fixtures and exit")
@click.option("--corpus", is_flag=True, help="Also run corpus PDF parse tests")
@click.option("--corpus-only", is_flag=True, help="Run ONLY corpus PDF parse tests")
def main(fixture, model, no_api, list_fixtures, corpus, corpus_only):
    """Run the ScoreForge test harness."""
    tests = discover_fixtures()

    if list_fixtures:
        console.print("[bold]Available test fixtures:[/bold]")
        for t in tests:
            exists = Path(t.musicxml_path).exists()
            status = "[green]OK[/green]" if exists else "[red]MISSING[/red]"
            console.print(f"  {status} {t.name}: {t.description}")
        pdfs = discover_corpus_pdfs()
        if pdfs:
            console.print(f"\n[bold]Corpus PDFs ({len(pdfs)}):[/bold]")
            for p in pdfs:
                console.print(f"  {p.stem}: {p}")
        return

    if fixture:
        tests = [t for t in tests if t.name == fixture]
        if not tests:
            console.print(f"[red]Fixture '{fixture}' not found.[/red]")
            sys.exit(1)

    corpus_pdfs = discover_corpus_pdfs() if (corpus or corpus_only) else []

    console.print(Panel(
        f"[bold]ScoreForge Test Harness[/bold]\n"
        f"Fixtures: {0 if corpus_only else len(tests)}\n"
        f"Corpus PDFs: {len(corpus_pdfs)}\n"
        f"Model: {model}\n"
        f"API calls: {'disabled' if no_api else 'enabled'}",
        title="Configuration",
    ))

    results = []
    if not corpus_only:
        results = run_all_tests(tests, model=model, skip_api=no_api)
        print_report(results)

    corpus_results = []
    if corpus_pdfs and not no_api:
        console.print(f"\n[bold cyan]Running corpus PDF tests ({len(corpus_pdfs)} PDFs)...[/bold cyan]")
        for i, pdf_path in enumerate(corpus_pdfs, 1):
            console.print(f"\n[bold cyan]Corpus {i}/{len(corpus_pdfs)}:[/bold cyan] {pdf_path.name}")
            cr = run_corpus_pdf(pdf_path, model=model)
            corpus_results.append(cr)
            if cr.passed:
                console.print(f"  [green]PASS[/green] — {cr.note_count} notes, {cr.measure_count} measures ({cr.duration_seconds:.1f}s)")
            else:
                console.print(f"  [red]FAIL[/red] — {cr.error}")

        passed_corpus, total_corpus, pct_corpus = print_corpus_report(corpus_results)

        # Save corpus results to JSON
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        corpus_report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total": total_corpus,
            "passed": passed_corpus,
            "parse_success_rate_pct": round(pct_corpus, 1),
            "build_gate_70pct": pct_corpus >= 70,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "extract_ok": r.extract_ok,
                    "build_ok": r.build_ok,
                    "note_count": r.note_count,
                    "measure_count": r.measure_count,
                    "duration_seconds": r.duration_seconds,
                    "error": r.error,
                }
                for r in corpus_results
            ],
        }
        corpus_report_path = RESULTS_DIR / "corpus_report.json"
        with open(corpus_report_path, "w") as f:
            json.dump(corpus_report, f, indent=2)
        console.print(f"\n  Corpus report saved to: {corpus_report_path}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Integration with validate_baseline.py
# ---------------------------------------------------------------------------

def get_baseline_metrics(model: str = "auto", skip_api: bool = False) -> dict:
    """Get baseline metrics for all fixtures.

    This function is designed to be imported by validate_baseline.py
    to provide a unified interface for running baseline validation.

    Args:
        model: Claude model to use for extraction
        skip_api: If True, skip API calls and only test infrastructure

    Returns:
        Dict with aggregate metrics and per-fixture results
    """
    tests = discover_fixtures()
    results = run_all_tests(tests, model=model, skip_api=skip_api)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if not r.passed and not r.skipped and r.compare_ok)
    errors = sum(1 for r in results if r.error and not r.compare_ok and not r.skipped)

    scored = [r for r in results if r.scores]
    if scored:
        avg_note = sum(r.scores.get("note_accuracy", 0) for r in scored) / len(scored)
        avg_pitch = sum(r.scores.get("pitch_accuracy", 0) for r in scored) / len(scored)
        avg_rhythm = sum(r.scores.get("rhythm_accuracy", 0) for r in scored) / len(scored)
        avg_overall = sum(r.scores.get("overall", 0) for r in scored) / len(scored)
        avg_measure = sum(r.scores.get("measure_accuracy", 0) for r in scored) / len(scored)
        avg_key = sum(r.scores.get("key_sig_accuracy", 0) for r in scored) / len(scored)
        avg_time = sum(r.scores.get("time_sig_accuracy", 0) for r in scored) / len(scored)
    else:
        avg_note = avg_pitch = avg_rhythm = avg_overall = 0.0
        avg_measure = avg_key = avg_time = 0.0

    return {
        "summary": {
            "total_fixtures": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "avg_note_accuracy": avg_note,
            "avg_pitch_accuracy": avg_pitch,
            "avg_rhythm_accuracy": avg_rhythm,
            "avg_overall_accuracy": avg_overall,
            "avg_measure_accuracy": avg_measure,
            "avg_key_sig_accuracy": avg_key,
            "avg_time_sig_accuracy": avg_time,
            "target_95_percent_met": avg_overall >= 95.0,
        },
        "results": [
            {
                "name": r.test_name,
                "passed": r.passed,
                "skipped": r.skipped,
                "scores": r.scores,
                "gt_notes": r.gt_note_count,
                "matched_notes": r.matched_note_count,
                "duration_seconds": r.duration_seconds,
                "error": r.error,
            }
            for r in results
        ],
    }


def run_baseline_validation(output_path: Optional[Path] = None, model: str = "auto") -> dict:
    """Run baseline validation and return results.

    This is a convenience function that can be called from validate_baseline.py
    or any other script that needs to run the baseline validation.

    Args:
        output_path: Path to save the baseline report (default: tests/BASELINE_REPORT.md)
        model: Claude model to use for extraction

    Returns:
        Same dict as get_baseline_metrics()
    """
    if output_path is None:
        output_path = Path(__file__).parent / "tests" / "BASELINE_REPORT.md"

    metrics = get_baseline_metrics(model=model, skip_api=False)

    # Import the report generation from validate_baseline if available
    try:
        from tests.validate_baseline import generate_markdown_report, save_report
        from tests.validate_baseline import BaselineSummary, FixtureResult, FixtureInfo

        summary = BaselineSummary(
            total_fixtures=metrics["summary"]["total_fixtures"],
            passed=metrics["summary"]["passed"],
            failed=metrics["summary"]["failed"],
            errors=metrics["summary"]["errors"],
            avg_note_accuracy=metrics["summary"]["avg_note_accuracy"],
            avg_pitch_accuracy=metrics["summary"]["avg_pitch_accuracy"],
            avg_rhythm_accuracy=metrics["summary"]["avg_rhythm_accuracy"],
            avg_overall_accuracy=metrics["summary"]["avg_overall_accuracy"],
            avg_measure_accuracy=metrics["summary"]["avg_measure_accuracy"],
            avg_key_sig_accuracy=metrics["summary"]["avg_key_sig_accuracy"],
            avg_time_sig_accuracy=metrics["summary"]["avg_time_sig_accuracy"],
            target_95_percent_met=metrics["summary"]["target_95_percent_met"],
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        results = []
        for r in metrics["results"]:
            fixture = FixtureInfo(name=r["name"], path=Path(""))
            result = FixtureResult(
                fixture=fixture,
                passed=r["passed"],
                scores=r["scores"],
                gt_note_count=r["gt_notes"],
                matched_note_count=r["matched_notes"],
                duration_seconds=r["duration_seconds"],
                error=r["error"],
            )
            results.append(result)

        markdown = generate_markdown_report(results, summary, model)
        save_report(markdown, output_path)
    except ImportError:
        # Fallback: just save JSON
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path.with_suffix(".json"), "w") as f:
            json.dump(metrics, f, indent=2)

    return metrics
