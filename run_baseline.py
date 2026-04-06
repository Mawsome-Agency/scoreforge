#!/usr/bin/env python3
"""ScoreForge Baseline Assessment — run all tests and establish starting point.

This script:
1. Runs all fixtures through test harness
2. Runs all corpus PDFs for extraction/build success
3. Produces baseline_results.json with structured data
4. Generates gap_analysis.md summary
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

sys.path.insert(0, str(Path(__file__).parent))

from core.extractor import extract_from_image
from core.musicxml_builder import build_musicxml
from core.renderer import render_musicxml_to_image
from core.comparator import compare_musicxml_semantic, compare_images


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------

@dataclass
class FixtureResult:
    """Result from testing a fixture (has ground truth)."""
    name: str
    difficulty: str
    tags: list[str]
    passed: bool
    converged_to_100: bool = False
    iteration_count: int = 0
    best_score: float = 0.0
    pitch_accuracy: float = 0.0
    rhythm_accuracy: float = 0.0
    overall_accuracy: float = 0.0
    visual_score: Optional[float] = None
    note_count_gt: int = 0
    note_count_matched: int = 0
    measure_count_gt: int = 0
    measure_count_matched: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    failure_modes: list[str] = field(default_factory=list)


@dataclass
class CorpusResult:
    """Result from testing a corpus PDF (no ground truth)."""
    name: str
    tier: str  # simple, moderate, complex, choral, orchestral
    passed: bool  # extraction + build succeeded
    extract_ok: bool = False
    build_ok: bool = False
    note_count: int = 0
    measure_count: int = 0
    part_count: int = 0
    has_grand_staff: bool = False
    duration_seconds: float = 0.0
    error: Optional[str] = None
    complexity_tags: list[str] = field(default_factory=list)


@dataclass
class BaselineSummary:
    """Overall baseline summary."""
    timestamp: str
    total_fixtures: int
    total_corpus: int
    fixtures_passed: int
    fixtures_converged: int
    corpus_parsed: int
    avg_fixture_accuracy: float
    avg_corpus_parse_time: float
    top_failure_modes: list[tuple[str, int]]  # (mode, count)
    critical_blockers: list[str]


# ---------------------------------------------------------------------------
# Baseline runner
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures"
CORPUS_DIR = Path(__file__).parent / "corpus" / "originals"
RESULTS_DIR = Path(__file__).parent / "results"
WORK_DIR = RESULTS_DIR / "baseline" / datetime.now().strftime("%Y%m%d_%H%M%S")
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Difficulty tier mapping for corpus
TIER_MAP = {
    "simple": ("simple", 70, 80),  # (tier, overall gate, pitch gate)
    "moderate": ("moderate", 70, 80),
    "complex": ("complex", 60, 70),
    "choral": ("choral", 60, 60),
    "orchestral": ("orchestral", 50, 50),
}

# Complexity tags per tier
COMPLEXITY_TAGS = {
    "simple": ["single_staff", "basic_rhythm", "no_accidentals"],
    "moderate": ["grand_staff", "chords", "dotted_notes", "alberti_bass", "trills"],
    "complex": ["multi_voice", "counterpoint", "ornaments", "tuplets", "cross_staff_beams"],
    "choral": ["satb", "lyrics", "voice_assignment"],
    "orchestral": ["multi_part", "transposing_instruments", "page_breaks"],
}


def get_corpus_tier(path: Path) -> tuple[str, int, int]:
    """Determine tier and gate thresholds from path."""
    path_str = str(path).lower()
    for tier, (tier_name, overall_gate, pitch_gate) in TIER_MAP.items():
        if f"/{tier}/" in path_str:
            return tier_name, overall_gate, pitch_gate
    return "unknown", 50, 50


def run_fixture_baseline(fixture_path: Path, fixture_name: str, tags: list[str], difficulty: str) -> FixtureResult:
    """Run a single fixture through basic extraction pipeline.
    
    This is a quick sanity check, not full iteration loop.
    """
    start_time = time.time()
    result = FixtureResult(name=fixture_name, difficulty=difficulty, tags=tags, passed=False)
    
    # Render GT to PNG
    gt_png = str(WORK_DIR / f"{fixture_name}_gt.png")
    try:
        render_musicxml_to_image(str(fixture_path), gt_png)
    except Exception as e:
        result.error = f"GT render failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result
    
    # Extract from PNG
    try:
        score = extract_from_image(gt_png, model="claude-sonnet-4-6")
    except Exception as e:
        result.error = f"Extraction failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result
    
    # Build MusicXML
    extracted_xml = str(WORK_DIR / f"{fixture_name}_extracted.musicxml")
    try:
        musicxml_content = build_musicxml(score)
        with open(extracted_xml, "w", encoding="utf-8") as f:
            f.write(musicxml_content)
    except Exception as e:
        result.error = f"Build failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result
    
    # Compare semantically
    try:
        comp = compare_musicxml_semantic(str(fixture_path), extracted_xml)
        result.pitch_accuracy = comp["scores"].get("pitch_accuracy", 0)
        result.rhythm_accuracy = comp["scores"].get("rhythm_accuracy", 0)
        result.overall_accuracy = comp["scores"].get("overall", 0)
        result.note_count_gt = comp["total_notes_gt"]
        result.note_count_matched = comp["total_notes_matched"]
        result.measure_count_gt = comp.get("measure_count_gt", 0)
        result.measure_count_matched = comp.get("measure_count_matched", 0)
        result.passed = comp["is_perfect"]
        result.converged_to_100 = comp["is_perfect"]
        result.best_score = result.overall_accuracy
        result.iteration_count = 1
        
        # Extract failure modes
        result.failure_modes = []
        for pd in comp.get("part_diffs", []):
            for md in pd.get("measure_diffs", []):
                for diff in md.get("diffs", []):
                    dtype = diff.get("type", "unknown")
                    if dtype != "perfect_match":
                        result.failure_modes.append(dtype)
        
        # Visual comparison (non-blocking)
        try:
            ex_png = str(WORK_DIR / f"{fixture_name}_extracted.png")
            render_musicxml_to_image(extracted_xml, ex_png)
            vis = compare_images(gt_png, ex_png)
            result.visual_score = vis["match_score"]
        except Exception:
            pass
            
    except Exception as e:
        result.error = f"Comparison failed: {e}"
    
    result.duration_seconds = time.time() - start_time
    return result


def run_corpus_baseline(pdf_path: Path, tier: str) -> CorpusResult:
    """Run a corpus PDF for extraction success only.
    
    Since we don't have GT MusicXML, we check:
    - Did extraction succeed?
    - Did MusicXML build succeed?
    - What did we extract?
    """
    start_time = time.time()
    tier_name, overall_gate, pitch_gate = get_corpus_tier(pdf_path)
    
    result = CorpusResult(name=pdf_path.stem, tier=tier_name, passed=False)
    result.complexity_tags = COMPLEXITY_TAGS.get(tier_name, []).copy()
    
    # Extract from PDF
    try:
        score = extract_from_image(str(pdf_path), model="claude-sonnet-4-6")
        result.extract_ok = True
        result.note_count = sum(len(m.notes) for p in score.parts for m in p.measures)
        result.measure_count = sum(len(p.measures) for p in score.parts)
        result.part_count = len(score.parts)
        result.has_grand_staff = any(p.staves == 2 for p in score.parts)
        
        # Add complexity tags based on extraction
        if result.part_count > 2:
            result.complexity_tags.append("multi_part")
        if result.has_grand_staff:
            result.complexity_tags.append("grand_staff")
        if any(len(m.notes) > 10 for p in score.parts for m in p.measures):
            result.complexity_tags.append("dense_notation")
            
    except Exception as e:
        result.error = f"Extraction failed: {e}"
        result.duration_seconds = time.time() - start_time
        return result
    
    # Build MusicXML
    try:
        musicxml_content = build_musicxml(score)
        out_path = WORK_DIR / f"{pdf_path.stem}.musicxml"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(musicxml_content)
        result.build_ok = True
        result.passed = True
    except Exception as e:
        result.error = f"Build failed: {e}"
    
    result.duration_seconds = time.time() - start_time
    return result


def analyze_failure_modes(fixture_results: list[FixtureResult]) -> list[tuple[str, int]]:
    """Count frequency of failure modes."""
    mode_counts = {}
    
    for result in fixture_results:
        for mode in result.failure_modes:
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
    
    # Sort by frequency
    sorted_modes = sorted(mode_counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_modes[:10]  # Top 10


def run_baseline() -> BaselineSummary:
    """Run complete baseline assessment."""
    print("=" * 70)
    print("SCOREFORGE BASELINE ASSESSMENT")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Work dir: {WORK_DIR}")
    print("=" * 70)
    
    fixture_results = []
    corpus_results = []
    
    # -----------------------------------------------------------------------
    # Phase 1: Fixtures (with ground truth)
    # -----------------------------------------------------------------------
    print("\n[Phase 1/3] Running fixture tests (with ground truth)...")
    print("-" * 70)
    
    # Built-in fixtures with known difficulty
    builtin_fixtures = [
        ("simple_melody", "simple_melody.musicxml", "easy", ["single_staff", "no_accidentals", "basic_rhythm"]),
        ("piano_chords", "piano_chords.musicxml", "medium", ["grand_staff", "chords", "dotted_notes"]),
        ("complex_rhythm", "complex_rhythm.musicxml", "hard", ["compound_meter", "ties", "accidentals", "beams"]),
        ("multi_voice", "multi_voice.musicxml", "hard", ["two_voice", "backup_element", "counterpoint"]),
    ]
    
    for i, (name, filename, difficulty, tags) in enumerate(builtin_fixtures, 1):
        print(f"\n[{i}/{len(builtin_fixtures)}] Fixture: {name} ({difficulty})")
        fixture_path = FIXTURE_DIR / filename
        if not fixture_path.exists():
            print(f"  ⚠️  File not found: {fixture_path}")
            continue
        
        result = run_fixture_baseline(fixture_path, name, tags, difficulty)
        fixture_results.append(result)
        
        status = "✅ PASS" if result.passed else ("❌ FAIL" if result.error else "⚠️  INACCURATE")
        print(f"  {status} - Overall: {result.overall_accuracy:.1f}% | "
              f"Pitch: {result.pitch_accuracy:.1f}% | "
              f"Rhythm: {result.rhythm_accuracy:.1f}%")
        if result.error:
            print(f"  Error: {result.error}")
        elif not result.passed:
            print(f"  Notes: {result.note_count_matched}/{result.note_count_gt} matched")
            print(f"  Failure modes: {', '.join(result.failure_modes[:5])}")
    
    # -----------------------------------------------------------------------
    # Phase 2: Corpus PDFs (extraction success only)
    # -----------------------------------------------------------------------
    print("\n[Phase 2/3] Running corpus PDF tests...")
    print("-" * 70)
    
    tier_dirs = ["simple", "moderate", "complex", "choral", "orchestral"]
    
    for tier in tier_dirs:
        tier_path = CORPUS_DIR / tier
        if not tier_path.exists():
            continue
        
        pdfs = sorted(tier_path.glob("*.pdf"))
        if not pdfs:
            continue
        
        print(f"\nTier: {tier.upper()} ({len(pdfs)} files)")
        
        for i, pdf_path in enumerate(pdfs, 1):
            print(f"  [{i}/{len(pdfs)}] {pdf_path.name}", end=" ... ")
            result = run_corpus_baseline(pdf_path, tier)
            corpus_results.append(result)
            
            if result.passed:
                print(f"✅ ({result.note_count} notes, {result.measure_count} measures, "
                      f"{result.part_count} parts, {result.duration_seconds:.1f}s)")
            else:
                print(f"❌ {result.error[:60]}")
    
    # -----------------------------------------------------------------------
    # Phase 3: Analysis
    # -----------------------------------------------------------------------
    print("\n[Phase 3/3] Analyzing results...")
    print("-" * 70)
    
    # Fixture stats
    fixtures_passed = sum(1 for r in fixture_results if r.passed)
    fixtures_converged = sum(1 for r in fixture_results if r.converged_to_100)
    
    scores = [r.overall_accuracy for r in fixture_results if r.overall_accuracy > 0]
    avg_fixture_accuracy = sum(scores) / len(scores) if scores else 0
    
    # Corpus stats
    corpus_parsed = sum(1 for r in corpus_results if r.passed)
    corpus_times = [r.duration_seconds for r in corpus_results if r.passed]
    avg_corpus_time = sum(corpus_times) / len(corpus_times) if corpus_times else 0
    
    # Failure mode analysis
    top_failures = analyze_failure_modes(fixture_results)
    
    # Critical blockers (common errors that stop tests)
    error_counts = {}
    for result in fixture_results + corpus_results:
        if result.error:
            error_type = result.error.split(":")[0] if ":" in result.error else result.error
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
    
    critical_blockers = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Build summary
    summary = BaselineSummary(
        timestamp=datetime.now().isoformat(),
        total_fixtures=len(fixture_results),
        total_corpus=len(corpus_results),
        fixtures_passed=fixtures_passed,
        fixtures_converged=fixtures_converged,
        corpus_parsed=corpus_parsed,
        avg_fixture_accuracy=avg_fixture_accuracy,
        avg_corpus_parse_time=avg_corpus_time,
        top_failure_modes=top_failures,
        critical_blockers=[f"{err} ({count})" for err, count in critical_blockers[:5]],
    )
    
    # Print summary
    print("\n" + "=" * 70)
    print("BASELINE SUMMARY")
    print("=" * 70)
    print(f"\nFixtures (with GT): {summary.fixtures_passed}/{summary.total_fixtures} passed "
          f"({summary.fixtures_passed/max(1, summary.total_fixtures)*100:.0f}%)")
    print(f"  Converged to 100%: {summary.fixtures_converged}/{summary.total_fixtures}")
    print(f"  Average accuracy: {summary.avg_fixture_accuracy:.1f}%")
    
    print(f"\nCorpus PDFs: {summary.corpus_parsed}/{summary.total_corpus} parsed successfully "
          f"({summary.corpus_parsed/max(1, summary.total_corpus)*100:.0f}%)")
    print(f"  Average parse time: {summary.avg_corpus_parse_time:.1f}s")
    
    if summary.top_failure_modes:
        print(f"\nTop Failure Modes:")
        for i, (mode, count) in enumerate(summary.top_failure_modes, 1):
            print(f"  {i}. {mode}: {count} occurrences")
    
    if summary.critical_blockers:
        print(f"\nCritical Blockers:")
        for blocker in summary.critical_blockers:
            print(f"  - {blocker}")
    
    # Save results
    baseline_data = {
        "summary": asdict(summary),
        "fixtures": [asdict(r) for r in fixture_results],
        "corpus": [asdict(r) for r in corpus_results],
    }
    
    baseline_path = WORK_DIR / "baseline_results.json"
    with open(baseline_path, "w") as f:
        json.dump(baseline_data, f, indent=2, default=str)
    
    print(f"\nResults saved to: {baseline_path}")
    print("=" * 70)
    
    return summary


if __name__ == "__main__":
    summary = run_baseline()
    sys.exit(0 if summary.fixtures_passed == summary.total_fixtures else 1)
