#!/usr/bin/env python3
"""ScoreForge Iteration Runner — loop until extraction accuracy converges.

This script implements the "loop until perfect" approach:
1. For each ground-truth fixture, render to image and run ScoreForge extraction.
2. Compare extracted MusicXML to ground truth semantically.
3. Log results and analyze failure patterns.
4. Optionally re-run with adjusted prompts or parameters.

Usage:
    python iterate.py                              # run all fixtures, 1 iteration
    python iterate.py --max-iterations 5           # loop up to 5 times per fixture
    python iterate.py --fixture simple_melody      # single fixture
    python iterate.py --threshold 95               # stop at 95% overall accuracy
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

from core.renderer import render_musicxml_to_image
from core.comparator import compare_musicxml_semantic, compare_images
from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml
from core.fixer import fix_musicxml

console = Console()

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Iteration logic
# ---------------------------------------------------------------------------

def iterate_fixture(
    fixture_path: str,
    fixture_name: str,
    max_iterations: int = 5,
    threshold: float = 95.0,
    model: str = "claude-sonnet-4-5-20250929",
) -> dict:
    """Run the extraction-comparison-fix loop on a single fixture.

    Returns a summary dict with per-iteration results.
    """
    run_dir = RESULTS_DIR / fixture_name / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    gt_path = fixture_path
    gt_png = str(run_dir / "ground_truth.png")

    # Step 1: Render ground truth to PNG
    console.print(f"  Rendering ground truth to PNG...")
    render_musicxml_to_image(gt_path, gt_png)

    iterations = []
    best_score = 0.0
    best_xml_path = None
    current_xml_content = None

    for iteration in range(1, max_iterations + 1):
        console.print(f"\n  [bold]--- Iteration {iteration}/{max_iterations} ---[/bold]")
        iter_start = time.time()

        iter_dir = run_dir / f"iter_{iteration}"
        iter_dir.mkdir(exist_ok=True)

        extracted_xml_path = str(iter_dir / "extracted.musicxml")
        extracted_png_path = str(iter_dir / "extracted.png")

        iter_result = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "scores": {},
            "error": None,
            "duration_seconds": 0,
        }

        try:
            if iteration == 1 or current_xml_content is None:
                # First iteration: extract from scratch
                console.print(f"  Extracting from image with Claude Vision...")
                score = extract_from_image(gt_png, model=model)
                current_xml_content = build_musicxml(score)
            else:
                # Subsequent iterations: apply fixes based on previous comparison
                console.print(f"  Applying AI fixes based on previous comparison...")
                prev_comparison = iterations[-1].get("comparison", {})
                diffs_to_fix = _extract_fix_instructions(prev_comparison)

                if diffs_to_fix:
                    console.print(f"  Fixing {len(diffs_to_fix)} issues...")
                    current_xml_content = fix_musicxml(current_xml_content, diffs_to_fix)
                else:
                    console.print(f"  [yellow]No specific diffs to fix. Re-extracting...[/yellow]")
                    score = extract_from_image(gt_png, model=model)
                    current_xml_content = build_musicxml(score)

            # Write extracted MusicXML
            with open(extracted_xml_path, "w", encoding="utf-8") as f:
                f.write(current_xml_content)

            # Semantic comparison
            console.print(f"  Comparing semantically...")
            comparison = compare_musicxml_semantic(gt_path, extracted_xml_path)
            iter_result["scores"] = comparison["scores"]
            iter_result["is_perfect"] = comparison["is_perfect"]
            iter_result["total_notes_gt"] = comparison["total_notes_gt"]
            iter_result["total_notes_matched"] = comparison["total_notes_matched"]
            iter_result["comparison"] = comparison

            overall = comparison["scores"].get("overall", 0)
            console.print(f"  Overall: {overall:.1f}%  |  "
                          f"Pitch: {comparison['scores'].get('pitch_accuracy', 0):.1f}%  |  "
                          f"Rhythm: {comparison['scores'].get('rhythm_accuracy', 0):.1f}%  |  "
                          f"Notes: {comparison['total_notes_matched']}/{comparison['total_notes_gt']}")

            # Track best
            if overall > best_score:
                best_score = overall
                best_xml_path = extracted_xml_path
                console.print(f"  [green]New best score: {best_score:.1f}%[/green]")

            # Visual comparison (supplementary)
            try:
                render_musicxml_to_image(extracted_xml_path, extracted_png_path)
                vis = compare_images(gt_png, extracted_png_path)
                iter_result["visual_score"] = vis["match_score"]
            except Exception:
                pass

            # Save comparison details
            comparison_save = {
                k: v for k, v in comparison.items()
                if k != "part_diffs"  # keep the file small
            }
            comparison_save["part_diff_summary"] = []
            for pd in comparison.get("part_diffs", []):
                pd_summary = {
                    "part_index": pd["part_index"],
                    "gt_measures": pd["gt_measure_count"],
                    "ex_measures": pd["ex_measure_count"],
                    "imperfect_measures": [
                        {
                            "measure": md["measure_number"],
                            "diffs": md["diffs"],
                        }
                        for md in pd["measure_diffs"]
                        if not md["is_perfect"]
                    ],
                }
                comparison_save["part_diff_summary"].append(pd_summary)

            with open(str(iter_dir / "comparison.json"), "w") as f:
                json.dump(comparison_save, f, indent=2, default=str)

            # Check convergence
            if comparison["is_perfect"] or overall >= threshold:
                console.print(f"  [bold green]Threshold reached ({overall:.1f}% >= {threshold}%). Stopping.[/bold green]")
                iter_result["duration_seconds"] = time.time() - iter_start
                iterations.append(iter_result)
                break

        except Exception as e:
            iter_result["error"] = str(e)
            console.print(f"  [red]Error: {e}[/red]")

        iter_result["duration_seconds"] = time.time() - iter_start
        iterations.append(iter_result)

    # Analyze failure patterns across iterations
    failure_patterns = _analyze_failures(iterations)

    summary = {
        "fixture": fixture_name,
        "fixture_path": fixture_path,
        "best_score": best_score,
        "best_xml_path": best_xml_path,
        "total_iterations": len(iterations),
        "converged": best_score >= threshold,
        "iterations": [
            {k: v for k, v in it.items() if k != "comparison"}
            for it in iterations
        ],
        "failure_patterns": failure_patterns,
        "run_dir": str(run_dir),
    }

    # Save run summary
    with open(str(run_dir / "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary


def _extract_fix_instructions(comparison: dict) -> list[dict]:
    """Extract actionable fix instructions from a semantic comparison result."""
    fixes = []

    for part_diff in comparison.get("part_diffs", []):
        for m_diff in part_diff.get("measure_diffs", []):
            for diff in m_diff.get("diffs", []):
                fix = {
                    "measure": diff.get("measure", m_diff.get("measure_number", 0)),
                    "type": diff.get("type", "unknown"),
                    "description": diff.get("description", str(diff)),
                    "severity": "critical" if diff["type"] in (
                        "missing_note", "extra_note", "wrong_pitch", "missing_measure"
                    ) else "major",
                }

                # Add specific fix instructions
                if diff["type"] == "wrong_pitch":
                    fix["fix"] = (
                        f"Change pitch at position {diff.get('position', '?')} "
                        f"from {diff.get('got', '?')} to {diff.get('expected', '?')}"
                    )
                elif diff["type"] == "wrong_duration":
                    fix["fix"] = (
                        f"Change duration at position {diff.get('position', '?')} "
                        f"from {diff.get('got_duration', '?')} to {diff.get('expected_duration', '?')}"
                    )
                elif diff["type"] == "wrong_key":
                    fix["fix"] = f"Change key signature to fifths={diff.get('expected', {}).get('fifths', '?')}"
                elif diff["type"] == "wrong_time":
                    fix["fix"] = f"Change time signature to {diff.get('expected', '?')}"
                else:
                    fix["fix"] = diff.get("description", "Fix this issue")

                fixes.append(fix)

    return fixes


def _analyze_failures(iterations: list[dict]) -> dict:
    """Analyze common failure patterns across iterations."""
    patterns = {
        "pitch_errors": 0,
        "duration_errors": 0,
        "missing_notes": 0,
        "extra_notes": 0,
        "key_sig_errors": 0,
        "time_sig_errors": 0,
        "tie_errors": 0,
        "measure_count_errors": 0,
        "improving": False,
        "trend": [],
    }

    scores = []
    for it in iterations:
        comp = it.get("comparison", {})
        scores.append(comp.get("scores", {}).get("overall", 0))

        for pd in comp.get("part_diffs", []):
            if pd.get("gt_measure_count", 0) != pd.get("ex_measure_count", 0):
                patterns["measure_count_errors"] += 1

            for md in pd.get("measure_diffs", []):
                for d in md.get("diffs", []):
                    dtype = d.get("type", "")
                    if "pitch" in dtype:
                        patterns["pitch_errors"] += 1
                    elif "duration" in dtype:
                        patterns["duration_errors"] += 1
                    elif dtype == "missing_note":
                        patterns["missing_notes"] += 1
                    elif dtype == "extra_note":
                        patterns["extra_notes"] += 1
                    elif "key" in dtype:
                        patterns["key_sig_errors"] += 1
                    elif "time" in dtype:
                        patterns["time_sig_errors"] += 1
                    elif "tie" in dtype:
                        patterns["tie_errors"] += 1

    patterns["trend"] = scores
    if len(scores) >= 2:
        patterns["improving"] = scores[-1] > scores[0]

    return patterns


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--fixture", "-f", default=None, help="Run only this fixture")
@click.option("--fixture-dir", "-d", default=None, help="Directory with MusicXML fixtures")
@click.option("--max-iterations", "-n", default=3, help="Max iterations per fixture")
@click.option("--threshold", "-t", default=95.0, help="Stop when overall accuracy >= this")
@click.option("--model", "-m", default="claude-sonnet-4-5-20250929", help="Claude model")
def main(fixture, fixture_dir, max_iterations, threshold, model):
    """Run the ScoreForge iteration loop on test fixtures."""
    fdir = Path(fixture_dir) if fixture_dir else FIXTURE_DIR

    if not fdir.exists():
        console.print(f"[red]Fixture directory not found: {fdir}[/red]")
        sys.exit(1)

    # Discover fixtures
    fixtures = []
    for mxml in sorted(fdir.glob("*.musicxml")):
        name = mxml.stem
        if fixture and name != fixture:
            continue
        fixtures.append((name, str(mxml)))

    if not fixtures:
        console.print("[red]No fixtures found.[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]ScoreForge Iteration Runner[/bold]\n"
        f"Fixtures: {len(fixtures)}\n"
        f"Max iterations: {max_iterations}\n"
        f"Threshold: {threshold}%\n"
        f"Model: {model}",
        title="Configuration",
    ))

    all_summaries = []
    for i, (name, path) in enumerate(fixtures, 1):
        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold cyan]Fixture {i}/{len(fixtures)}: {name}[/bold cyan]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]")

        summary = iterate_fixture(
            fixture_path=path,
            fixture_name=name,
            max_iterations=max_iterations,
            threshold=threshold,
            model=model,
        )
        all_summaries.append(summary)

    # Final report
    console.print(f"\n\n{'='*60}")
    console.print("[bold]ITERATION SUMMARY[/bold]")
    console.print(f"{'='*60}")

    table = Table()
    table.add_column("Fixture", style="bold")
    table.add_column("Best Score", justify="right")
    table.add_column("Iterations", justify="right")
    table.add_column("Converged")
    table.add_column("Top Failure")

    for s in all_summaries:
        fp = s.get("failure_patterns", {})
        # Find the most common failure type
        failure_counts = {
            "pitch": fp.get("pitch_errors", 0),
            "duration": fp.get("duration_errors", 0),
            "missing": fp.get("missing_notes", 0),
            "extra": fp.get("extra_notes", 0),
            "key_sig": fp.get("key_sig_errors", 0),
            "time_sig": fp.get("time_sig_errors", 0),
        }
        top_failure = max(failure_counts, key=failure_counts.get) if any(failure_counts.values()) else "none"

        converged = "[green]YES[/green]" if s["converged"] else "[red]NO[/red]"

        table.add_row(
            s["fixture"],
            f"{s['best_score']:.1f}%",
            str(s["total_iterations"]),
            converged,
            top_failure,
        )

    console.print(table)

    # Save overall summary
    overall_path = RESULTS_DIR / "iteration_summary.json"
    with open(overall_path, "w") as f:
        json.dump(all_summaries, f, indent=2, default=str)
    console.print(f"\nResults saved to: {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
