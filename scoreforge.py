#!/usr/bin/env python3
"""ScoreForge — AI-powered sheet music to MusicXML converter.

Usage:
    python scoreforge.py input.pdf --output output.musicxml
    python scoreforge.py input.png --output output.musicxml --validate --max-iterations 10
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml
from core.renderer import render_musicxml_to_image, get_available_renderer
from core.comparator import compare_images, ai_compare
from core.fixer import fix_musicxml

console = Console()


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", default=None, help="Output MusicXML path")
@click.option("--validate", "-v", is_flag=True, help="Enable visual validation loop")
@click.option("--max-iterations", "-m", default=5, help="Max validation iterations")
@click.option("--threshold", "-t", default=90, help="Match score threshold (0-100)")
@click.option("--model", default="claude-sonnet-4-5-20250929", help="Claude model for extraction")
@click.option("--verbose", is_flag=True, help="Verbose output")
@click.option("--save-intermediates", is_flag=True, help="Save intermediate files")
def main(input_path, output, validate, max_iterations, threshold, model, verbose, save_intermediates):
    """Convert sheet music to MusicXML."""
    input_path = Path(input_path)

    if output is None:
        output = str(input_path.with_suffix(".musicxml"))

    console.print(Panel(
        f"[bold]ScoreForge[/bold]\n"
        f"Input: {input_path}\n"
        f"Output: {output}\n"
        f"Validate: {validate} (threshold={threshold}, max={max_iterations})\n"
        f"Model: {model}",
        title="Configuration",
    ))

    # Step 1: Extract
    console.print("\n[bold cyan]Step 1:[/bold cyan] Extracting music notation from image...")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Analyzing sheet music with Claude Vision...", total=None)
        score = extract_from_image(str(input_path), model=model)
        progress.update(task, completed=True)

    console.print(f"  Extracted: {score.part_count} part(s), {score.measure_count} measure(s)")
    if score.title:
        console.print(f"  Title: {score.title}")
    if score.composer:
        console.print(f"  Composer: {score.composer}")

    # Step 2: Build MusicXML
    console.print("\n[bold cyan]Step 2:[/bold cyan] Building MusicXML...")
    musicxml_content = build_musicxml(score)
    _write_file(output, musicxml_content)
    console.print(f"  Written: {output} ({len(musicxml_content):,} bytes)")

    if not validate:
        console.print("\n[bold green]Done![/bold green] MusicXML saved without validation.")
        return

    # Step 3: Validation loop
    renderer = get_available_renderer()
    if renderer == "none":
        console.print("[bold yellow]Warning:[/bold yellow] No renderer available. Install MuseScore, Verovio, or LilyPond for validation.")
        console.print("Skipping validation loop.")
        return

    console.print(f"\n[bold cyan]Step 3:[/bold cyan] Starting validation loop (renderer: {renderer})")

    work_dir = Path(tempfile.mkdtemp(prefix="scoreforge_"))
    best_score = 0
    best_xml = musicxml_content

    for iteration in range(1, max_iterations + 1):
        console.print(f"\n[bold]--- Iteration {iteration}/{max_iterations} ---[/bold]")

        # Render current MusicXML
        xml_path = work_dir / f"iter_{iteration}.musicxml"
        render_path = work_dir / f"iter_{iteration}.png"
        _write_file(str(xml_path), musicxml_content)

        console.print("  Rendering MusicXML to image...")
        try:
            render_musicxml_to_image(str(xml_path), str(render_path))
        except Exception as e:
            console.print(f"  [red]Render failed:[/red] {e}")
            break

        # Compare images
        console.print("  Comparing original vs. rendered...")
        pixel_result = compare_images(str(input_path), str(render_path))

        console.print(f"  Pixel match score: {pixel_result['match_score']}/100")
        console.print(f"  Pixel diff: {pixel_result['pixel_diff_pct']}%")
        console.print(f"  Diff regions: {len(pixel_result['diff_regions'])}")

        if pixel_result["match_score"] >= threshold:
            console.print(f"\n[bold green]Match score {pixel_result['match_score']} >= {threshold} threshold. Done![/bold green]")
            best_xml = musicxml_content
            best_score = pixel_result["match_score"]
            break

        # AI comparison for detailed diffs
        console.print("  Running AI comparison for detailed diff analysis...")
        ai_result = ai_compare(str(input_path), str(render_path))

        if ai_result["is_perfect"]:
            console.print("[bold green]AI reports perfect match![/bold green]")
            best_xml = musicxml_content
            best_score = 100
            break

        # Show diff summary
        table = Table(title=f"Differences Found: {ai_result['diff_count']}")
        table.add_column("Severity", style="bold")
        table.add_column("Count")
        table.add_row("[red]Critical[/red]", str(ai_result["critical_count"]))
        table.add_row("[yellow]Major[/yellow]", str(ai_result["major_count"]))
        table.add_row("Minor", str(ai_result["minor_count"]))
        console.print(table)

        if verbose:
            for diff in ai_result["differences"]:
                console.print(f"  [{diff.get('severity', '?')}] M{diff.get('measure', '?')}: {diff.get('description', '')}")

        # Apply fixes
        console.print("  Applying AI fixes...")
        musicxml_content = fix_musicxml(musicxml_content, ai_result["differences"])

        if pixel_result["match_score"] > best_score:
            best_score = pixel_result["match_score"]
            best_xml = musicxml_content

        if save_intermediates:
            _write_file(str(work_dir / f"iter_{iteration}_fixed.musicxml"), musicxml_content)
            console.print(f"  Saved intermediate: {work_dir}/iter_{iteration}_fixed.musicxml")

    # Save best result
    _write_file(output, best_xml)
    console.print(f"\n[bold]Final result:[/bold]")
    console.print(f"  Best match score: {best_score}/100")
    console.print(f"  Output: {output}")

    if best_score < threshold:
        console.print(f"\n[yellow]Warning: Best score {best_score} is below threshold {threshold}.[/yellow]")
        console.print("Consider running with more iterations or manually reviewing the output.")

    # Cleanup
    if not save_intermediates:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)


def _write_file(path: str, content: str):
    """Write content to file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()
