#!/usr/bin/env python3
"""Run the render→compare→fix validation loop on a fixture.

Usage examples:
    # Run on simple_melody (default, 3 iterations, 90% threshold)
    python run_validation_loop.py

    # Custom fixture and settings
    python run_validation_loop.py --fixture tests/fixtures/piano_chords.musicxml
    python run_validation_loop.py --max-iterations 5 --threshold 95
    python run_validation_loop.py --output-dir results/my_run
    python run_validation_loop.py --no-two-pass --thinking
"""
import json
import os
import sys
from pathlib import Path

import click


@click.command()
@click.option(
    "--fixture",
    default="tests/fixtures/simple_melody.musicxml",
    show_default=True,
    help="Path to MusicXML fixture file.",
)
@click.option(
    "--max-iterations", "-n",
    default=3,
    show_default=True,
    type=int,
    help="Maximum fix iterations.",
)
@click.option(
    "--threshold", "-t",
    default=90.0,
    show_default=True,
    type=float,
    help="Match score threshold to stop early (0–100).",
)
@click.option(
    "--output-dir", "-o",
    default=None,
    help="Directory for output files. Defaults to results/validation_loop/<fixture_name>/.",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Claude model for extraction and fixing.",
)
@click.option(
    "--thinking/--no-thinking",
    default=False,
    show_default=True,
    help="Enable extended thinking for higher quality (slower).",
)
@click.option(
    "--two-pass/--no-two-pass",
    default=True,
    show_default=True,
    help="Use two-pass extraction (structure then detail).",
)
@click.option(
    "--quiet/--verbose",
    default=False,
    help="Suppress progress output.",
)
@click.option(
    "--json-output", "-j",
    is_flag=True,
    default=False,
    help="Print final summary as JSON to stdout.",
)
def main(
    fixture: str,
    max_iterations: int,
    threshold: float,
    output_dir: str | None,
    model: str,
    thinking: bool,
    two_pass: bool,
    quiet: bool,
    json_output: bool,
):
    """Run the ScoreForge render→compare→fix validation loop."""
    # Load .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    fixture_path = Path(fixture)
    if not fixture_path.exists():
        click.echo(f"ERROR: Fixture not found: {fixture_path}", err=True)
        sys.exit(1)

    # Default output dir
    if output_dir is None:
        output_dir = os.path.join("results", "validation_loop", fixture_path.stem)

    os.makedirs(output_dir, exist_ok=True)

    # Import here so dotenv is loaded first
    from core.validation_loop import run_validation_loop

    try:
        result = run_validation_loop(
            fixture_path=str(fixture_path),
            max_iterations=max_iterations,
            threshold=threshold,
            output_dir=output_dir,
            model=model,
            use_thinking=thinking,
            two_pass=two_pass,
            verbose=not quiet,
        )
    except Exception as exc:
        click.echo(f"\nERROR: Validation loop failed: {exc}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    summary = result.summary()

    # Save summary JSON
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    if json_output:
        print(json.dumps(summary, indent=2))
    else:
        click.echo("\n── Summary ──────────────────────────────────────────────")
        click.echo(f"  Fixture    : {summary['fixture']}")
        click.echo(f"  Renderer   : {summary['renderer']} (available={summary['renderer_available']})")
        click.echo(f"  Converged  : {summary['converged']}")
        click.echo(f"  Best score : {summary['best_score']:.1f}%")
        if summary["iterations"]:
            scores_str = " → ".join(f"{i['match_score']:.1f}%" for i in summary["iterations"])
            click.echo(f"  Scores     : {scores_str}")
        else:
            click.echo("  Scores     : (no iterations — renderer unavailable)")
        click.echo(f"  Summary    : {summary_path}")
        if result.final_musicxml:
            click.echo(f"  Final XML  : {result.final_musicxml}")
        click.echo("─────────────────────────────────────────────────────────\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
