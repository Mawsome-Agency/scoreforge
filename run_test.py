#!/usr/bin/env python3
"""ScoreForge CLI Test Runner — uses Claude CLI for extraction (no API key needed).

Usage:
    python run_test.py                              # all fixtures
    python run_test.py --fixture simple_melody      # single fixture
    python run_test.py --fixture simple_melody --iterations 3
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.renderer import render_musicxml_to_image
from core.comparator import compare_musicxml_semantic, compare_images
from core.musicxml_builder import build_musicxml
from core.extractor import _build_score, _extract_json_from_response, STRUCTURE_PROMPT, DETAIL_PROMPT
from core.report import generate_report

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures"
RESULTS_DIR = Path(__file__).parent / "results"


def claude_cli_extract(prompt: str, image_path: str, model: str = "sonnet") -> str:
    """Run Claude CLI with an image and prompt, return text response."""
    full_prompt = f"Read the image at {image_path}\n\n{prompt}\n\nOutput ONLY the JSON, no markdown code fences, no explanation text."

    result = subprocess.run(
        [
            "claude", "--print",
            "--max-turns", "3",
            "--model", model,
            "--allowedTools", "Read",
            "--output-format", "json",
        ],
        input=full_prompt,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "cli"},
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr[:300]}")

    # Parse the JSON output format
    try:
        output = json.loads(result.stdout)
        response_text = output.get("result", result.stdout)
    except json.JSONDecodeError:
        response_text = result.stdout

    return response_text


def extract_from_image_cli(image_path: str, model: str = "sonnet") -> dict:
    """Two-pass extraction using Claude CLI. Returns raw dict."""

    # Pass 1: Structure
    console.print("  [dim]Pass 1: Extracting structure...[/dim]")
    structure_response = claude_cli_extract(STRUCTURE_PROMPT, image_path, model)
    structure_json_str = _extract_json_from_response(structure_response)
    structure_data = json.loads(structure_json_str)
    console.print(f"  [dim]Structure: {json.dumps(structure_data, indent=None)[:200]}[/dim]")

    # Pass 2: Detailed notes
    console.print("  [dim]Pass 2: Extracting notes...[/dim]")
    detail_prompt = DETAIL_PROMPT.format(
        structure_json=json.dumps(structure_data, indent=2)
    )
    detail_response = claude_cli_extract(detail_prompt, image_path, model)
    json_str = _extract_json_from_response(detail_response)
    data = json.loads(json_str)

    return data


def run_fixture(
    fixture_name: str,
    fixture_path: str,
    max_iterations: int = 3,
    model: str = "sonnet",
) -> dict:
    """Run the full extract-compare-fix loop on a fixture."""
    run_dir = RESULTS_DIR / fixture_name / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    gt_png = str(run_dir / "ground_truth.png")

    # Step 1: Render ground truth MusicXML to PNG
    console.print("  Rendering ground truth to PNG...")
    render_musicxml_to_image(fixture_path, gt_png)
    console.print(f"  [green]Rendered: {gt_png}[/green]")

    iterations = []
    best_score = 0.0
    best_xml = None
    current_xml_content = None

    for iteration in range(1, max_iterations + 1):
        console.print(f"\n  [bold]--- Iteration {iteration}/{max_iterations} ---[/bold]")
        iter_start = time.time()
        iter_dir = run_dir / f"iter_{iteration}"
        iter_dir.mkdir(exist_ok=True)

        try:
            if iteration == 1 or current_xml_content is None:
                # Extract from image
                data = extract_from_image_cli(gt_png, model)
                score = _build_score(data)
                current_xml_content = build_musicxml(score)
            else:
                # Fix based on previous comparison
                prev = iterations[-1]
                if prev.get("comparison") and prev["comparison"].get("part_diffs"):
                    from core.extractor import _extract_json_from_response
                    diffs = _extract_fix_instructions(prev["comparison"])
                    if diffs:
                        console.print(f"  Fixing {len(diffs)} issues via Claude CLI...")
                        fix_response = claude_cli_extract(
                            f"You are a MusicXML editor. Fix these issues in the XML:\n"
                            f"ISSUES:\n{json.dumps(diffs, indent=2)}\n\n"
                            f"CURRENT MUSICXML:\n```xml\n{current_xml_content}\n```\n\n"
                            f"Output the COMPLETE corrected MusicXML. No markdown fences.",
                            gt_png, model
                        )
                        # Try to extract XML
                        if "<?xml" in fix_response:
                            current_xml_content = fix_response[fix_response.index("<?xml"):]
                        elif "<score-partwise" in fix_response:
                            current_xml_content = fix_response[fix_response.index("<score-partwise"):]
                        else:
                            console.print("  [yellow]Fix response didn't contain XML, re-extracting...[/yellow]")
                            data = extract_from_image_cli(gt_png, model)
                            score = _build_score(data)
                            current_xml_content = build_musicxml(score)
                    else:
                        console.print("  [yellow]No fixable diffs, re-extracting...[/yellow]")
                        data = extract_from_image_cli(gt_png, model)
                        score = _build_score(data)
                        current_xml_content = build_musicxml(score)

            # Save extracted MusicXML
            extracted_path = str(iter_dir / "extracted.musicxml")
            with open(extracted_path, "w") as f:
                f.write(current_xml_content)

            # Semantic comparison
            console.print("  Comparing semantically...")
            comparison = compare_musicxml_semantic(fixture_path, extracted_path)

            overall = comparison["scores"].get("overall", 0)
            console.print(
                f"  Overall: {overall:.1f}%  |  "
                f"Pitch: {comparison['scores'].get('pitch_accuracy', 0):.1f}%  |  "
                f"Rhythm: {comparison['scores'].get('rhythm_accuracy', 0):.1f}%  |  "
                f"Notes: {comparison['total_notes_matched']}/{comparison['total_notes_gt']}"
            )

            # Visual comparison
            visual_score = None
            try:
                rendered_png = str(iter_dir / "rendered.png")
                render_musicxml_to_image(extracted_path, rendered_png)
                vis = compare_images(gt_png, rendered_png)
                visual_score = vis["match_score"]
                console.print(f"  Visual match: {visual_score}/100")
            except Exception as e:
                console.print(f"  [yellow]Visual compare failed: {e}[/yellow]")

            iter_data = {
                "iteration": iteration,
                "scores": comparison["scores"],
                "is_perfect": comparison["is_perfect"],
                "total_notes_gt": comparison["total_notes_gt"],
                "total_notes_matched": comparison["total_notes_matched"],
                "visual_score": visual_score,
                "comparison": comparison,
                "duration_seconds": time.time() - iter_start,
                "musicxml": current_xml_content,
                "match_score": visual_score,
                "pixel_diff_pct": vis.get("pixel_diff_pct") if visual_score else None,
                "note_count": comparison["total_notes_matched"],
                "measure_count": len(comparison.get("part_diffs", [{}])[0].get("measure_diffs", [])) if comparison.get("part_diffs") else 0,
                "differences": [],
            }

            if overall > best_score:
                best_score = overall
                best_xml = current_xml_content
                console.print(f"  [green]New best: {best_score:.1f}%[/green]")

            if comparison["is_perfect"] or overall >= 98:
                console.print(f"  [bold green]PERFECT! Stopping.[/bold green]")
                iterations.append(iter_data)
                break

            # Collect differences for report
            for pd in comparison.get("part_diffs", []):
                for md in pd.get("measure_diffs", []):
                    for d in md.get("diffs", []):
                        iter_data["differences"].append({
                            "measure": d.get("measure", md.get("measure_number")),
                            "type": d.get("type"),
                            "description": d.get("description", str(d)),
                            "severity": "critical" if d["type"] in ("missing_note", "extra_note", "wrong_pitch") else "major",
                        })

            iterations.append(iter_data)

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
            iterations.append({
                "iteration": iteration,
                "error": str(e),
                "duration_seconds": time.time() - iter_start,
            })

    # Generate HTML report
    report_path = str(run_dir / "report.html")
    try:
        generate_report(gt_png, iterations, report_path, title=f"ScoreForge: {fixture_name}")
        console.print(f"\n  [bold]Report: {report_path}[/bold]")
    except Exception as e:
        console.print(f"  [yellow]Report generation failed: {e}[/yellow]")

    # Save summary
    summary = {
        "fixture": fixture_name,
        "best_score": best_score,
        "total_iterations": len(iterations),
        "converged": best_score >= 95,
        "run_dir": str(run_dir),
        "timestamp": datetime.now().isoformat(),
    }
    with open(str(run_dir / "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary


def _extract_fix_instructions(comparison: dict) -> list[dict]:
    """Extract fixable diffs from comparison."""
    fixes = []
    for pd in comparison.get("part_diffs", []):
        for md in pd.get("measure_diffs", []):
            for d in md.get("diffs", []):
                fixes.append({
                    "measure": d.get("measure", md.get("measure_number")),
                    "type": d.get("type"),
                    "description": str(d),
                })
    return fixes[:20]  # Cap at 20 to avoid prompt overflow


@click.command()
@click.option("--fixture", "-f", default=None, help="Run only this fixture")
@click.option("--iterations", "-n", default=3, help="Max iterations per fixture")
@click.option("--model", "-m", default="sonnet", help="Claude model (sonnet/opus/haiku)")
def main(fixture, iterations, model):
    """Run ScoreForge extraction tests using Claude CLI."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Discover fixtures
    fixtures = []
    for mxml in sorted(FIXTURE_DIR.glob("*.musicxml")):
        name = mxml.stem
        if fixture and name != fixture:
            continue
        fixtures.append((name, str(mxml)))

    if not fixtures:
        console.print("[red]No fixtures found.[/red]")
        return

    console.print(Panel(
        f"[bold]ScoreForge Test Runner (CLI)[/bold]\n"
        f"Fixtures: {len(fixtures)}\n"
        f"Max iterations: {iterations}\n"
        f"Model: {model}",
        title="Configuration",
    ))

    summaries = []
    for i, (name, path) in enumerate(fixtures, 1):
        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold cyan]Fixture {i}/{len(fixtures)}: {name}[/bold cyan]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]")

        summary = run_fixture(name, path, max_iterations=iterations, model=model)
        summaries.append(summary)

    # Print summary table
    console.print(f"\n{'='*60}")
    table = Table(title="ScoreForge Results")
    table.add_column("Fixture", style="bold")
    table.add_column("Best Score", justify="right")
    table.add_column("Iterations", justify="right")
    table.add_column("Converged")

    for s in summaries:
        converged = "[green]YES[/green]" if s["converged"] else "[red]NO[/red]"
        table.add_row(s["fixture"], f"{s['best_score']:.1f}%", str(s["total_iterations"]), converged)

    console.print(table)


if __name__ == "__main__":
    main()
