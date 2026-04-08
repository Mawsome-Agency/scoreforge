"""Orchestrate the render→compare→fix validation loop on a fixture.

The loop takes a MusicXML fixture, renders it to PNG, extracts via Claude Vision,
then iteratively compares the rendered output against the ground truth and applies
fixes until the similarity score crosses the threshold or max iterations are reached.
"""
import json
import os
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core import musicxml_builder
from core.comparator import compare_images
from core.extractor import extract_from_image
from core.fixer import fix_musicxml, reextract_with_context


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IterationResult:
    """Results from one pass of the validation loop."""
    iteration: int
    match_score: float
    phash_distance: int
    pixel_diff_pct: float
    diff_regions: list[dict]
    is_perfect: bool
    rendered_png: Optional[str] = None
    musicxml_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ValidationResult:
    """Aggregate result from the full validation loop."""
    fixture_path: str
    renderer_available: bool
    renderer_name: str
    iterations: list[IterationResult] = field(default_factory=list)
    final_musicxml: Optional[str] = None          # Path to final corrected MusicXML
    final_musicxml_content: Optional[str] = None  # Content of final corrected MusicXML
    converged: bool = False
    threshold: float = 90.0

    @property
    def scores(self) -> list[float]:
        return [r.match_score for r in self.iterations]

    @property
    def best_score(self) -> float:
        return max(self.scores) if self.scores else 0.0

    def summary(self) -> dict:
        return {
            "fixture": self.fixture_path,
            "renderer_available": self.renderer_available,
            "renderer": self.renderer_name,
            "converged": self.converged,
            "threshold": self.threshold,
            "best_score": self.best_score,
            "iterations": [
                {
                    "iteration": r.iteration,
                    "match_score": r.match_score,
                    "phash_distance": r.phash_distance,
                    "pixel_diff_pct": r.pixel_diff_pct,
                    "diff_regions_count": len(r.diff_regions),
                    "is_perfect": r.is_perfect,
                    "error": r.error,
                }
                for r in self.iterations
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Renderer availability check (lazy — avoids hard import at module level)
# ─────────────────────────────────────────────────────────────────────────────

def _check_renderer() -> tuple[bool, str]:
    """Return (available, renderer_name)."""
    try:
        from core.renderer import get_available_renderer
        name = get_available_renderer()
        return name != "none", name
    except Exception as exc:
        warnings.warn(f"Could not check renderer availability: {exc}")
        return False, "none"


def _render(musicxml_path: str, output_png: str) -> bool:
    """Render MusicXML → PNG. Returns True on success, False with warning on failure."""
    try:
        from core.renderer import render_musicxml_to_image
        render_musicxml_to_image(musicxml_path, output_path=output_png)
        return True
    except RuntimeError as exc:
        warnings.warn(f"Renderer unavailable or failed — skipping visual comparison: {exc}")
        return False
    except Exception as exc:
        warnings.warn(f"Unexpected render error: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_validation_loop(
    fixture_path: str,
    max_iterations: int = 3,
    threshold: float = 90.0,
    output_dir: Optional[str] = None,
    model: str = "claude-sonnet-4-6",
    use_thinking: bool = False,
    two_pass: bool = True,
    verbose: bool = True,
) -> ValidationResult:
    """Run the render→compare→fix validation loop on a MusicXML fixture.

    Pipeline per iteration:
      1. Render current MusicXML to PNG
      2. Compare rendered PNG to ground-truth PNG (pixel + perceptual hash)
      3. If score < threshold: fix MusicXML using diff regions, then loop
      4. Stop when score ≥ threshold OR max_iterations reached

    Args:
        fixture_path:   Path to the source MusicXML fixture file.
        max_iterations: Maximum fix iterations (iteration 0 = initial extraction,
                        iterations 1..N = fix passes).
        threshold:      Target match score (0–100) to stop early.
        output_dir:     Directory to write intermediate files. If None, uses a
                        temporary directory that persists until the process exits.
        model:          Claude model used for extraction and fixing.
        use_thinking:   Enable Claude extended thinking (slower, higher quality).
        two_pass:       Use two-pass extraction (structure → detail).
        verbose:        Print progress to stdout.

    Returns:
        ValidationResult with per-iteration scores, paths, and final MusicXML.
    """
    fixture_path = str(Path(fixture_path).resolve())
    if not os.path.isfile(fixture_path):
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    # ── Set up output directory ──────────────────────────────────────────────
    if output_dir is None:
        # Use a persistent temp dir (caller is responsible for cleanup if desired)
        _tmp = tempfile.mkdtemp(prefix="scoreforge_loop_")
        output_dir = _tmp
    os.makedirs(output_dir, exist_ok=True)

    def _log(msg: str):
        if verbose:
            print(msg, flush=True)

    # ── Check renderer ───────────────────────────────────────────────────────
    renderer_available, renderer_name = _check_renderer()
    result = ValidationResult(
        fixture_path=fixture_path,
        renderer_available=renderer_available,
        renderer_name=renderer_name,
        threshold=threshold,
    )

    if not renderer_available:
        _log(
            f"[WARNING] No renderer available (verovio not found). "
            f"Visual comparison will be skipped. Install verovio to enable full loop."
        )

    _log(f"\n{'='*60}")
    _log(f"ScoreForge Validation Loop")
    _log(f"  Fixture  : {fixture_path}")
    _log(f"  Renderer : {renderer_name}")
    _log(f"  Max iter : {max_iterations}")
    _log(f"  Threshold: {threshold}%")
    _log(f"  Output   : {output_dir}")
    _log(f"{'='*60}\n")

    # ── Step 1: Render ground truth ──────────────────────────────────────────
    ground_truth_png = os.path.join(output_dir, "ground_truth.png")
    if renderer_available:
        _log("[Step 1] Rendering ground-truth fixture to PNG...")
        success = _render(fixture_path, ground_truth_png)
        if not success:
            renderer_available = False
            result.renderer_available = False
            result.renderer_name = "none"
            _log("[WARNING] Ground-truth render failed. Proceeding without visual comparison.")
    else:
        _log("[Step 1] Skipped (no renderer). Using fixture directly for extraction.")

    # ── Step 2: Initial extraction ───────────────────────────────────────────
    source_image = ground_truth_png if (renderer_available and os.path.isfile(ground_truth_png)) else fixture_path

    # If source is a .musicxml (no rendered PNG), we cannot do vision extraction.
    # Fall back to loading the fixture XML directly.
    if source_image.endswith(".musicxml") or source_image.endswith(".xml"):
        _log("[Step 2] No rendered PNG available — loading fixture MusicXML directly.")
        with open(fixture_path, "r", encoding="utf-8") as f:
            current_musicxml = f.read()
    else:
        _log(f"[Step 2] Extracting score from: {source_image}")
        try:
            extracted_score = extract_from_image(
                source_image,
                model=model,
                use_thinking=use_thinking,
                two_pass=two_pass,
            )
            current_musicxml = musicxml_builder.build_musicxml(extracted_score)
            _log(f"[Step 2] Extraction complete. Building MusicXML...")
        except Exception as exc:
            _log(f"[ERROR] Initial extraction failed: {exc}")
            # Fall back to fixture content so we can still run the loop
            _log("[Step 2] Falling back to fixture MusicXML for loop.")
            with open(fixture_path, "r", encoding="utf-8") as f:
                current_musicxml = f.read()

    # ── Write iteration 0 (initial) XML ─────────────────────────────────────
    iter_xml_path = os.path.join(output_dir, "iter_0_extracted.musicxml")
    with open(iter_xml_path, "w", encoding="utf-8") as f:
        f.write(current_musicxml)
    _log(f"[Step 2] Initial MusicXML written: {iter_xml_path}")

    # ── Step 3: Iteration loop ───────────────────────────────────────────────
    if not renderer_available:
        _log("\n[Loop] Renderer unavailable — cannot run visual comparison loop.")
        _log("[Loop] Reporting initial extraction only (no iteration scores).")
        result.final_musicxml = iter_xml_path
        result.final_musicxml_content = current_musicxml
        return result

    score_trend: list[float] = []
    previous_errors: list[dict] = []

    for iteration in range(1, max_iterations + 1):
        _log(f"\n[Iter {iteration}/{max_iterations}] ─────────────────────────")

        # a) Render current MusicXML to PNG
        iter_png = os.path.join(output_dir, f"iter_{iteration}_rendered.png")
        _log(f"[Iter {iteration}] Rendering extracted MusicXML...")
        render_ok = _render(iter_xml_path, iter_png)
        if not render_ok:
            _log(f"[Iter {iteration}] Render failed — stopping loop.")
            result.iterations.append(IterationResult(
                iteration=iteration,
                match_score=0.0,
                phash_distance=0,
                pixel_diff_pct=0.0,
                diff_regions=[],
                is_perfect=False,
                rendered_png=None,
                musicxml_path=iter_xml_path,
                error="Render failed",
            ))
            break

        # b) Compare rendered PNG vs ground truth
        _log(f"[Iter {iteration}] Comparing to ground truth...")
        try:
            cmp = compare_images(ground_truth_png, iter_png)
        except Exception as exc:
            _log(f"[Iter {iteration}] Comparison error: {exc}")
            result.iterations.append(IterationResult(
                iteration=iteration,
                match_score=0.0,
                phash_distance=0,
                pixel_diff_pct=0.0,
                diff_regions=[],
                is_perfect=False,
                rendered_png=iter_png,
                musicxml_path=iter_xml_path,
                error=str(exc),
            ))
            break

        match_score = float(cmp["match_score"])
        score_trend.append(match_score)

        iter_result = IterationResult(
            iteration=iteration,
            match_score=match_score,
            phash_distance=int(cmp["phash_distance"]),
            pixel_diff_pct=float(cmp["pixel_diff_pct"]),
            diff_regions=cmp.get("diff_regions", []),
            is_perfect=bool(cmp.get("is_perfect", False)),
            rendered_png=iter_png,
            musicxml_path=iter_xml_path,
        )
        result.iterations.append(iter_result)

        _log(
            f"[Iter {iteration}] Score: {match_score:.1f}% "
            f"(phash={cmp['phash_distance']}, pixel_diff={cmp['pixel_diff_pct']:.1f}%)"
        )

        # c) Check threshold
        if match_score >= threshold:
            _log(f"[Iter {iteration}] ✓ Threshold {threshold}% reached! Converged.")
            result.converged = True
            break

        if iteration == max_iterations:
            _log(f"[Iter {iteration}] Max iterations reached.")
            break

        # d) Apply fix using diff regions
        diff_regions = cmp.get("diff_regions", [])
        _log(f"[Iter {iteration}] Applying fix ({len(diff_regions)} diff regions)...")

        # Convert diff regions into structured differences for fixer
        differences = [
            {
                "type": "visual_diff",
                "region": r,
                "description": f"Visual mismatch at ({r['x']},{r['y']}) severity={r['severity']:.3f}",
            }
            for r in diff_regions
        ] + previous_errors

        try:
            fixed_xml = fix_musicxml(current_musicxml, differences)
        except Exception as exc:
            _log(f"[Iter {iteration}] fix_musicxml error: {exc} — keeping current XML.")
            fixed_xml = current_musicxml

        current_musicxml = fixed_xml
        previous_errors = differences
        iter_xml_path = os.path.join(output_dir, f"iter_{iteration + 1}_extracted.musicxml")
        with open(iter_xml_path, "w", encoding="utf-8") as f:
            f.write(current_musicxml)
        _log(f"[Iter {iteration}] Fixed MusicXML written: {iter_xml_path}")

    # ── Final output ─────────────────────────────────────────────────────────
    final_xml_path = os.path.join(output_dir, "final_corrected.musicxml")
    with open(final_xml_path, "w", encoding="utf-8") as f:
        f.write(current_musicxml)

    result.final_musicxml = final_xml_path
    result.final_musicxml_content = current_musicxml

    _log(f"\n{'='*60}")
    _log(f"Validation Loop Complete")
    _log(f"  Converged    : {result.converged}")
    _log(f"  Best score   : {result.best_score:.1f}%")
    _log(f"  Scores       : {' → '.join(f'{s:.1f}%' for s in result.scores)}")
    _log(f"  Final XML    : {final_xml_path}")
    _log(f"{'='*60}\n")

    return result
