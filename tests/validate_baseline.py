#!/usr/bin/env python3
"""ScoreForge Baseline Validation Pipeline."""
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
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
DEFAULT_REPORT_PATH = Path(__file__).parent / "BASELINE_REPORT.md"


@dataclass
class FixtureInfo:
    """Information about a test fixture."""
    name: str
    path: Path
    description: str = ""
    difficulty: str = "easy"
    category: str = "general"
    tags: list[str] = field(default_factory=list)


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
    failure_modes: list = field(default_factory=list)

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

    @property
    def voice_accuracy(self) -> float:
        return self.scores.get("voice_accuracy", 0.0)


@dataclass
class BaselineSummary:
    """Aggregate summary of all fixture results."""
    total_fixtures: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    avg_note_accuracy: float = 0.0
    avg_pitch_accuracy: float = 0.0
    avg_rhythm_accuracy: float = 0.0
    avg_overall_accuracy: float = 0.0
    avg_measure_accuracy: float = 0.0
    avg_key_sig_accuracy: float = 0.0
    avg_time_sig_accuracy: float = 0.0
    avg_voice_accuracy: float = 0.0
    target_95_percent_met: bool = False
    timestamp: str = ""


def discover_fixtures() -> list[FixtureInfo]:
    """Discover all MusicXML fixtures."""
    fixtures = []
    if not FIXTURE_DIR.exists():
        return fixtures
    for mxml in sorted(FIXTURE_DIR.glob("*.musicxml")):
        fixtures.append(FixtureInfo(name=mxml.stem, path=mxml))
    return fixtures


def run_fixture(fixture: FixtureInfo, model: str = "glm-5.1") -> FixtureResult:
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

        # Extract top 3 failure modes from all diffs
        all_diffs = []
        for part_diff in sem_result.get("part_diffs", []):
            for m_diff in part_diff.get("measure_diffs", []):
                all_diffs.extend(m_diff.get("diffs", []))
        mode_counts = Counter(d["type"] for d in all_diffs if isinstance(d, dict) and "type" in d)
        result.failure_modes = [mode for mode, _ in mode_counts.most_common(3)]

        with open(str(work_dir / "comparison.json"), "w") as f:
            json.dump(sem_result, f, indent=2, default=str)
    except Exception as e:
        result.error = f"Comparison failed: {e}"
        return result

    result.duration_seconds = time.time() - start_time
    return result


def run_all_fixtures(fixtures: list[FixtureInfo], model: str = "glm-5.1", verbose: bool = True) -> list[FixtureResult]:
    """Run all fixtures."""
    results = []
    for i, fixture in enumerate(fixtures, 1):
        if verbose:
            console.print(f"\n[bold cyan]Fixture {i}/{len(fixtures)}:[/bold cyan] {fixture.name}")
        result = run_fixture(fixture, model=model)
        results.append(result)
        if verbose:
            if result.passed:
                console.print(f"  [green]✓ PASSED[/green] ({result.duration_seconds:.1f}s)")
            elif result.error:
                console.print(f"  [red]✗ ERROR[/red]: {result.error}")
            else:
                console.print(f"  [yellow]✗ FAILED[/yellow] (overall: {result.overall_accuracy:.1f}%)")
    return results


def calculate_summary(results: list[FixtureResult]) -> BaselineSummary:
    """Calculate aggregate summary."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and r.compare_ok)
    errors = sum(1 for r in results if r.error and not r.compare_ok)

    scored = [r for r in results if r.scores]
    if scored:
        avg_note = sum(r.note_accuracy for r in scored) / len(scored)
        avg_pitch = sum(r.pitch_accuracy for r in scored) / len(scored)
        avg_rhythm = sum(r.rhythm_accuracy for r in scored) / len(scored)
        avg_overall = sum(r.overall_accuracy for r in scored) / len(scored)
        avg_measure = sum(r.measure_accuracy for r in scored) / len(scored)
        avg_key = sum(r.key_sig_accuracy for r in scored) / len(scored)
        avg_time = sum(r.time_sig_accuracy for r in scored) / len(scored)
        avg_voice = sum(r.voice_accuracy for r in scored) / len(scored)
    else:
        avg_note = avg_pitch = avg_rhythm = avg_overall = 0.0
        avg_measure = avg_key = avg_time = avg_voice = 0.0

    return BaselineSummary(
        total_fixtures=total, passed=passed, failed=failed, errors=errors,
        avg_note_accuracy=avg_note, avg_pitch_accuracy=avg_pitch,
        avg_rhythm_accuracy=avg_rhythm, avg_overall_accuracy=avg_overall,
        avg_measure_accuracy=avg_measure, avg_key_sig_accuracy=avg_key,
        avg_time_sig_accuracy=avg_time, avg_voice_accuracy=avg_voice,
        target_95_percent_met=avg_overall >= 95.0,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def generate_markdown_report(results: list[FixtureResult], summary: BaselineSummary, model: str = "glm-5.1") -> str:
    """Generate markdown report."""
    sorted_results = sorted(results, key=lambda r: r.fixture.name)
    lines = [
        "# ScoreForge Baseline Accuracy Report",
        "",
        f"**Generated:** {summary.timestamp}",
        f"**Model:** {model}",
        f"**Total Fixtures:** {summary.total_fixtures}",
        "",
        "## Summary",
        "",
        "| Metric | Value | Target |",
        "|--------|-------|--------|",
        f"| Total Fixtures | {summary.total_fixtures} | - |",
        f"| Passed | {summary.passed} | {summary.total_fixtures} |",
        f"| Failed | {summary.failed} | 0 |",
        f"| Errors | {summary.errors} | 0 |",
        f"| Note Accuracy | **{summary.avg_note_accuracy:.1f}%** | ≥95% |",
        f"| Pitch Accuracy | **{summary.avg_pitch_accuracy:.1f}%** | ≥95% |",
        f"| Rhythm Accuracy | **{summary.avg_rhythm_accuracy:.1f}%** | ≥95% |",
        f"| Measure Accuracy | **{summary.avg_measure_accuracy:.1f}%** | ≥95% |",
        f"| Key Signature Accuracy | **{summary.avg_key_sig_accuracy:.1f}%** | ≥95% |",
        f"| Time Signature Accuracy | **{summary.avg_time_sig_accuracy:.1f}%** | ≥95% |",
        f"| Voice Accuracy | **{summary.avg_voice_accuracy:.1f}%** | ≥95% |",
        f"| **Overall Accuracy** | **{summary.avg_overall_accuracy:.1f}%** | **≥95%** |",
        "",
        f"**Status:** {'✅ PASS' if summary.target_95_percent_met else '❌ FAIL'} - 95% target {'met' if summary.target_95_percent_met else 'not met'}",
        "",
        "## Per-Fixture Results",
        "",
        "| Fixture | Status | Note Acc | Pitch Acc | Rhythm Acc | Voice Acc | Overall Acc | Notes | Time |",
        "|---------|--------|----------|-----------|------------|-----------|-------------|-------|------|",
    ]

    for r in sorted_results:
        status = "✅ PASS" if r.passed else ("❌ ERROR" if r.error and not r.compare_ok else "⚠️ FAIL")
        notes = f"{r.matched_note_count}/{r.gt_note_count}" if r.gt_note_count else "-"
        time_str = f"{r.duration_seconds:.1f}s"
        lines.append(f"| {r.fixture.name} | {status} | {r.note_accuracy:.1f}% | {r.pitch_accuracy:.1f}% | {r.rhythm_accuracy:.1f}% | {r.voice_accuracy:.1f}% | {r.overall_accuracy:.1f}% | {notes} | {time_str} |")

    # Top Failure Modes section
    lines.extend(["", "## Top Failure Modes", ""])
    all_mode_counts: dict[str, int] = {}
    for r in sorted_results:
        for mode in r.failure_modes:
            all_mode_counts[mode] = all_mode_counts.get(mode, 0) + 1
    if all_mode_counts:
        sorted_modes = sorted(all_mode_counts.items(), key=lambda x: -x[1])
        lines.append("| Failure Mode | Fixtures Affected |")
        lines.append("|--------------|-------------------|")
        for mode, count in sorted_modes:
            lines.append(f"| {mode} | {count} |")
    else:
        lines.append("_No failure modes recorded._")

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
    table.add_column("Voice %", justify="right")
    table.add_column("Overall %", justify="right")
    table.add_column("Time", justify="right")

    for r in sorted(results, key=lambda x: x.fixture.name):
        status = "[green]PASS[/green]" if r.passed else ("[red]ERROR[/red]" if r.error and not r.compare_ok else "[yellow]FAIL[/yellow]")
        notes = f"{r.matched_note_count}/{r.gt_note_count}" if r.gt_note_count else "-"
        time_str = f"{r.duration_seconds:.1f}s"
        table.add_row(r.fixture.name, status, notes, f"{r.pitch_accuracy:.0f}%", f"{r.rhythm_accuracy:.0f}%", f"{r.voice_accuracy:.0f}%", f"{r.overall_accuracy:.0f}%", time_str)

    console.print(table)
    console.print(f"\n  Total: {summary.total_fixtures}  Passed: {summary.passed}  Failed: {summary.failed}  Errors: {summary.errors}")
    console.print(f"  Overall accuracy: {summary.avg_overall_accuracy:.1f}% (target: ≥95%)")
    console.print(f"  Pitch accuracy: {summary.avg_pitch_accuracy:.1f}%")
    console.print(f"  Rhythm accuracy: {summary.avg_rhythm_accuracy:.1f}%")
    console.print(f"  Voice accuracy: {summary.avg_voice_accuracy:.1f}%")
    console.print(f"  Measure accuracy: {summary.avg_measure_accuracy:.1f}%")
    gate_status = "[green]✓ PASS[/green]" if summary.target_95_percent_met else "[red]✗ FAIL[/red]"
    console.print(f"\n  95% Target Gate: {gate_status}")


@click.command()
@click.option("--fixture", "-f", default=None, help="Run only this fixture")
@click.option("--model", "-m", default="glm-5.1", help="Claude model")
@click.option("--output", "-o", default=None, help="Output path for markdown report")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode")
@click.option("--list-fixtures", is_flag=True, help="List fixtures")
def main(fixture, model, output, quiet, list_fixtures):
    """Run baseline validation."""
    fixtures = discover_fixtures()

    if list_fixtures:
        console.print("[bold]Available fixtures:[/bold]")
        for f in fixtures:
            console.print(f"  [green]✓[/green] {f.name}: {f.path}")
        return

    if not fixtures:
        console.print("[red]No fixtures found![/red]")
        return

    if fixture:
        fixtures = [f for f in fixtures if f.name == fixture]
        if not fixtures:
            console.print(f"[red]Fixture '{fixture}' not found.[/red]")
            sys.exit(1)

    output_path = Path(output) if output else DEFAULT_REPORT_PATH

    console.print(Panel(
        f"[bold]ScoreForge Baseline Validation[/bold]\n"
        f"Fixtures: {len(fixtures)}\n"
        f"Model: {model}\n"
        f"Output: {output_path}",
        title="Configuration",
    ))

    results = run_all_fixtures(fixtures, model=model, verbose=not quiet)
    summary = calculate_summary(results)
    print_console_report(results, summary)

    markdown = generate_markdown_report(results, summary, model)
    save_report(markdown, output_path)

    json_path = output_path.with_suffix(".json")
    json_data = {
        "timestamp": summary.timestamp,
        "model": model,
        "summary": {
            "total_fixtures": summary.total_fixtures,
            "passed": summary.passed,
            "failed": summary.failed,
            "errors": summary.errors,
            "avg_note_accuracy": summary.avg_note_accuracy,
            "avg_pitch_accuracy": summary.avg_pitch_accuracy,
            "avg_rhythm_accuracy": summary.avg_rhythm_accuracy,
            "avg_overall_accuracy": summary.avg_overall_accuracy,
            "avg_measure_accuracy": summary.avg_measure_accuracy,
            "avg_key_sig_accuracy": summary.avg_key_sig_accuracy,
            "avg_time_sig_accuracy": summary.avg_time_sig_accuracy,
            "avg_voice_accuracy": summary.avg_voice_accuracy,
            "target_95_percent_met": summary.target_95_percent_met,
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
                "failure_modes": r.failure_modes,
            }
            for r in results
        ],
    }
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    console.print(f"  JSON report saved to: {json_path}")

    # Write results/test_report.json (matching test_harness.py print_report() format)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    test_report_path = RESULTS_DIR / "test_report.json"
    test_report_data = {
        "timestamp": summary.timestamp,
        "total": summary.total_fixtures,
        "passed": summary.passed,
        "failed": summary.failed,
        "errors": summary.errors,
        "results": [
            {
                "name": r.fixture.name,
                "passed": r.passed,
                "scores": r.scores,
                "visual_score": None,
                "gt_notes": r.gt_note_count,
                "matched_notes": r.matched_note_count,
                "duration_seconds": r.duration_seconds,
                "error": r.error,
            }
            for r in results
        ],
    }
    with open(test_report_path, "w") as f:
        json.dump(test_report_data, f, indent=2)
    console.print(f"  Test report saved to: {test_report_path}")

    # Write results/iteration_summary.json (matching iterate.py format)
    iteration_summary_path = RESULTS_DIR / "iteration_summary.json"
    iteration_summary_data = {
        "timestamp": summary.timestamp,
        "model": model,
        "total_fixtures": summary.total_fixtures,
        "passed": summary.passed,
        "failed": summary.failed,
        "errors": summary.errors,
        "avg_note_accuracy": round(summary.avg_note_accuracy, 1),
        "avg_pitch_accuracy": round(summary.avg_pitch_accuracy, 1),
        "avg_rhythm_accuracy": round(summary.avg_rhythm_accuracy, 1),
        "avg_overall_accuracy": round(summary.avg_overall_accuracy, 1),
        "avg_measure_accuracy": round(summary.avg_measure_accuracy, 1),
        "avg_key_sig_accuracy": round(summary.avg_key_sig_accuracy, 1),
        "avg_time_sig_accuracy": round(summary.avg_time_sig_accuracy, 1),
        "avg_voice_accuracy": round(summary.avg_voice_accuracy, 1),
        "target_95_percent_met": summary.target_95_percent_met,
        "fixture_results": [
            {
                "name": r.fixture.name,
                "passed": r.passed,
                "overall_accuracy": r.overall_accuracy,
                "pitch_accuracy": r.pitch_accuracy,
                "rhythm_accuracy": r.rhythm_accuracy,
                "voice_accuracy": r.voice_accuracy,
                "failure_modes": r.failure_modes,
                "error": r.error,
            }
            for r in results
        ],
    }
    with open(iteration_summary_path, "w") as f:
        json.dump(iteration_summary_data, f, indent=2)
    console.print(f"  Iteration summary saved to: {iteration_summary_path}")

    sys.exit(0 if summary.target_95_percent_met else 1)


if __name__ == "__main__":
    main()
