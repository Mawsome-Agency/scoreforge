#!/usr/bin/env python3
"""Round-trip test: render known MusicXML → image → extract → compare.

This tests the full pipeline by using known-good MusicXML files,
rendering them to images, then running ScoreForge extraction and
comparing the output MusicXML against the original.

Usage:
    python tests/roundtrip.py                          # Run all samples
    python tests/roundtrip.py --sample c_major_scale   # Run one sample
    python tests/roundtrip.py --render-only             # Just generate test images
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from rich.console import Console
from rich.table import Table

from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml
from core.comparator import compare_images, ai_compare
from core.report import generate_report

console = Console()
SAMPLES_DIR = Path(__file__).parent / "samples"
OUTPUT_DIR = Path(__file__).parent / "output"


def render_musicxml_to_png(musicxml_path: str, output_path: str) -> bool:
    """Render MusicXML to PNG using verovio CLI or Python verovio."""
    # Try verovio CLI
    try:
        result = subprocess.run(
            ["verovio", musicxml_path, "-o", output_path,
             "--adjust-page-height", "--scale", "60"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass

    # Try Python verovio
    try:
        import verovio
        tk = verovio.toolkit()
        tk.setOptions({
            "scale": 60,
            "adjustPageHeight": True,
            "pageWidth": 2000,
        })
        with open(musicxml_path) as f:
            tk.loadData(f.read())
        svg = tk.renderToSVG(1)

        # Convert SVG to PNG via cairosvg
        import cairosvg
        cairosvg.svg2png(bytestring=svg.encode(), write_to=output_path)
        return True
    except ImportError:
        pass

    console.print("[yellow]Warning: No verovio/cairosvg available for rendering.[/yellow]")
    console.print("Install: pip install verovio cairosvg  OR  npm install -g verovio")
    return False


@click.command()
@click.option("--sample", default=None, help="Specific sample name to test")
@click.option("--render-only", is_flag=True, help="Only render test images, don't run extraction")
@click.option("--model", default="claude-sonnet-4-6", help="Claude model for extraction")
@click.option("--max-iterations", "-m", default=3, help="Max validation iterations")
def main(sample, render_only, model, max_iterations):
    """Run round-trip tests on known MusicXML samples."""
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Find samples
    samples = list(SAMPLES_DIR.glob("*.musicxml"))
    if sample:
        samples = [s for s in samples if sample in s.stem]
    if not samples:
        console.print("[red]No samples found![/red]")
        return

    console.print(f"\n[bold]ScoreForge Round-Trip Test[/bold]")
    console.print(f"Samples: {len(samples)}")
    console.print(f"Model: {model}")
    console.print(f"Max iterations: {max_iterations}\n")

    results = []

    for sample_path in samples:
        console.print(f"\n{'='*60}")
        console.print(f"[bold cyan]Sample: {sample_path.stem}[/bold cyan]")

        # Step 1: Render known MusicXML to image
        img_path = OUTPUT_DIR / f"{sample_path.stem}_reference.png"
        console.print(f"  Rendering to: {img_path}")

        if not render_musicxml_to_png(str(sample_path), str(img_path)):
            console.print("[red]  Skipping — no renderer available[/red]")
            results.append({"sample": sample_path.stem, "status": "skip", "reason": "no renderer"})
            continue

        if render_only:
            console.print(f"  [green]Rendered![/green]")
            results.append({"sample": sample_path.stem, "status": "rendered"})
            continue

        # Step 2: Extract from image
        console.print("  Extracting with Claude Vision...")
        try:
            score = extract_from_image(str(img_path), model=model)
        except Exception as e:
            console.print(f"  [red]Extraction failed: {e}[/red]")
            results.append({"sample": sample_path.stem, "status": "failed", "reason": str(e)})
            continue

        console.print(f"  Extracted: {score.part_count} parts, {score.measure_count} measures")

        # Step 3: Build MusicXML
        extracted_xml = build_musicxml(score)
        extracted_path = OUTPUT_DIR / f"{sample_path.stem}_extracted.musicxml"
        extracted_path.write_text(extracted_xml)

        # Step 4: Visual comparison
        iterations = []
        current_xml = extracted_xml

        for iteration in range(1, max_iterations + 1):
            console.print(f"\n  [bold]--- Iteration {iteration} ---[/bold]")

            # Render extracted MusicXML
            rendered_path = OUTPUT_DIR / f"{sample_path.stem}_iter{iteration}.png"
            if not render_musicxml_to_png(
                str(OUTPUT_DIR / f"{sample_path.stem}_iter{iteration}.musicxml")
                if iteration > 1
                else str(extracted_path),
                str(rendered_path)
            ):
                break

            # Compare
            pixel_result = compare_images(str(img_path), str(rendered_path))
            console.print(f"  Match score: {pixel_result['match_score']}/100")
            console.print(f"  Pixel diff: {pixel_result['pixel_diff_pct']}%")

            iter_data = {
                "iteration": iteration,
                "musicxml": current_xml,
                "match_score": pixel_result["match_score"],
                "pixel_diff_pct": pixel_result["pixel_diff_pct"],
                "note_count": sum(len(m.notes) for p in score.parts for m in p.measures),
                "measure_count": score.measure_count,
                "differences": [],
            }

            if pixel_result["match_score"] >= 90:
                console.print("  [green]Match threshold met![/green]")
                iterations.append(iter_data)
                break

            # AI comparison
            console.print("  Running AI comparison...")
            try:
                ai_result = ai_compare(str(img_path), str(rendered_path))
                iter_data["differences"] = ai_result["differences"]
                console.print(f"  Diffs: {ai_result['diff_count']} "
                             f"(critical={ai_result['critical_count']}, "
                             f"major={ai_result['major_count']}, "
                             f"minor={ai_result['minor_count']})")

                if ai_result["is_perfect"]:
                    console.print("  [green]AI says perfect![/green]")
                    iterations.append(iter_data)
                    break

                # Fix
                from core.fixer import fix_musicxml
                current_xml = fix_musicxml(current_xml, ai_result["differences"])
                fixed_path = OUTPUT_DIR / f"{sample_path.stem}_iter{iteration + 1}.musicxml"
                fixed_path.write_text(current_xml)
            except Exception as e:
                console.print(f"  [yellow]AI comparison failed: {e}[/yellow]")

            iterations.append(iter_data)

        # Step 5: Generate HTML report
        report_path = OUTPUT_DIR / f"{sample_path.stem}_report.html"
        generate_report(
            original_image_path=str(img_path),
            iterations=iterations,
            output_path=str(report_path),
            title=f"ScoreForge: {sample_path.stem}",
        )
        console.print(f"\n  [bold green]Report: {report_path}[/bold green]")

        best_score = max((i["match_score"] for i in iterations if i["match_score"]), default=0)
        results.append({
            "sample": sample_path.stem,
            "status": "complete",
            "best_score": best_score,
            "iterations": len(iterations),
            "report": str(report_path),
        })

    # Summary table
    console.print(f"\n{'='*60}")
    table = Table(title="Round-Trip Test Results")
    table.add_column("Sample", style="bold")
    table.add_column("Status")
    table.add_column("Best Score")
    table.add_column("Iterations")

    for r in results:
        score = str(r.get("best_score", "—"))
        status_style = "green" if r["status"] == "complete" else "yellow" if r["status"] == "rendered" else "red"
        table.add_row(
            r["sample"],
            f"[{status_style}]{r['status']}[/{status_style}]",
            score,
            str(r.get("iterations", "—")),
        )
    console.print(table)

    # Save summary
    summary_path = OUTPUT_DIR / "test_summary.json"
    with open(summary_path, "w") as f:
        json.dump({"results": results}, f, indent=2)
    console.print(f"\nSummary saved to: {summary_path}")


if __name__ == "__main__":
    main()
