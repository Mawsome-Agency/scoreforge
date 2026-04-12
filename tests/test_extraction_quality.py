#!/usr/bin/env python3
"""ScoreForge Extraction Quality Smoke Test.

This is a diagnostic tool that validates the STRUCTURE of extracted MusicXML files
against their ground truth fixtures — no API calls required.

Usage:
    python3 tests/test_extraction_quality.py

Output: ASCII table showing per-fixture structural quality.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

# Add parent directory to path for imports
_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root))

from core.comparator import _parse_musicxml

FIXTURE_DIR = Path(__file__).parent / "fixtures"
# Results directory is in the main repo at /home/deployer/scoreforge/results/
# This script may run from a worktree, so we use the absolute path
RESULTS_DIR = Path("/home/deployer/scoreforge/results")


@dataclass
class FixtureQualityResult:
    """Result from checking a single fixture's structural quality."""
    fixture_name: str
    has_extracted: bool = False
    measure_count_match: bool = False
    gt_measure_count: int = 0
    ex_measure_count: int = 0
    all_durations_one: bool = False
    has_measure_stuffing: bool = False
    max_notes_in_measure: int = 0
    stuffing_measures: list[int] = field(default_factory=list)
    error: Optional[str] = None


class SmokeTest:
    """Smoke test for extraction quality without API calls."""

    def __init__(self):
        self.console = Console()

    def discover_fixtures(self) -> list[Path]:
        """Discover all MusicXML fixtures.

        Returns:
            List of fixture paths sorted by name.
        """
        if not FIXTURE_DIR.exists():
            return []
        return sorted(FIXTURE_DIR.glob("*.musicxml"))

    def check_fixture(self, fixture_path: Path) -> FixtureQualityResult:
        """Check structural quality of a single fixture.

        Args:
            fixture_path: Path to ground truth MusicXML fixture.

        Returns:
            FixtureQualityResult with validation results.
        """
        fixture_name = fixture_path.stem
        result = FixtureQualityResult(fixture_name=fixture_name)

        # Check if extracted file exists
        extracted_path = RESULTS_DIR / fixture_name / "extracted.musicxml"
        if not extracted_path.exists():
            result.has_extracted = False
            result.error = "No extracted file found"
            return result

        result.has_extracted = True

        try:
            # Parse ground truth
            gt_data = _parse_musicxml(str(fixture_path))

            # Parse extracted
            ex_data = _parse_musicxml(str(extracted_path))

            # Check measure count
            measure_match, gt_count, ex_count = self._check_measure_count(gt_data, ex_data)
            result.measure_count_match = measure_match
            result.gt_measure_count = gt_count
            result.ex_measure_count = ex_count

            # Check note durations
            result.all_durations_one = self._check_note_durations(ex_data)

            # Check measure stuffing
            has_stuffing, max_notes, stuffed_measures = self._check_measure_stuffing(ex_data)
            result.has_measure_stuffing = has_stuffing
            result.max_notes_in_measure = max_notes
            result.stuffing_measures = stuffed_measures

        except Exception as e:
            result.error = f"Parse error: {e}"

        return result

    def _check_measure_count(self, gt_data: dict, ex_data: dict) -> tuple[bool, int, int]:
        """Check if extracted measure count matches ground truth.

        Args:
            gt_data: Parsed ground truth MusicXML.
            ex_data: Parsed extracted MusicXML.

        Returns:
            (match: bool, gt_count: int, ex_count: int)
        """
        # Handle empty scores
        if not gt_data.get("parts") or not ex_data.get("parts"):
            return False, 0, 0

        # Get measure counts for each part
        gt_counts = [len(part.get("measures", [])) for part in gt_data["parts"]]
        ex_counts = [len(part.get("measures", [])) for part in ex_data["parts"]]

        # Use the maximum count for multi-part scores
        gt_total = max(gt_counts) if gt_counts else 0
        ex_total = max(ex_counts) if ex_counts else 0

        return gt_total == ex_total, gt_total, ex_total

    def _check_note_durations(self, ex_data: dict) -> bool:
        """Check if all notes have duration=1 (indicates extraction bug).

        This check uses duration_normalized to handle different divisions values.
        A normalized duration of 1.0 means a quarter note. If ALL notes have
        normalized duration of 1.0, it's likely a bug where the LLM set all
        durations to the same value regardless of note type.

        Args:
            ex_data: Parsed extracted MusicXML.

        Returns:
            True if all durations are 1.0 (bad), False otherwise (good).
        """
        all_durations = []

        for part in ex_data.get("parts", []):
            for measure in part.get("measures", []):
                for note in measure.get("notes", []):
                    # Skip grace notes and rests
                    if note.get("is_grace") or note.get("is_rest"):
                        continue

                    # Use normalized duration (quarter-note units)
                    norm_dur = note.get("duration_normalized")
                    if norm_dur is not None:
                        all_durations.append(norm_dur)

        # If no notes, can't determine - return False (not a bug)
        if not all_durations:
            return False

        # Check if all durations are exactly 1.0
        return all(d == 1.0 for d in all_durations)

    def _check_measure_stuffing(self, ex_data: dict) -> tuple[bool, int, list[int]]:
        """Check if any measure has >20 notes (indicates stuffing bug).

        Args:
            ex_data: Parsed extracted MusicXML.

        Returns:
            (has_stuffing: bool, max_notes: int, stuffed_measures: list[int])
        """
        max_notes = 0
        stuffed_measures = []

        for part in ex_data.get("parts", []):
            for measure in part.get("measures", []):
                # Count non-grace, non-rest notes
                note_count = sum(
                    1 for note in measure.get("notes", [])
                    if not note.get("is_grace") and not note.get("is_rest")
                )

                if note_count > max_notes:
                    max_notes = note_count

                if note_count > 20:
                    measure_num = measure.get("number", 0)
                    if measure_num not in stuffed_measures:
                        stuffed_measures.append(measure_num)

        has_stuffing = len(stuffed_measures) > 0
        return has_stuffing, max_notes, sorted(stuffed_measures)

    def run_all(self) -> list[FixtureQualityResult]:
        """Run smoke test on all fixtures.

        Returns:
            List of results for all fixtures.
        """
        fixtures = self.discover_fixtures()
        results = []

        for fixture_path in fixtures:
            result = self.check_fixture(fixture_path)
            results.append(result)

        return results

    def _print_report(self, results: list[FixtureQualityResult]) -> None:
        """Print ASCII table report of results.

        Args:
            results: List of fixture quality results.
        """
        self.console.print("\n")
        self.console.print("[bold]Extraction Quality Smoke Test Results[/bold]\n")

        table = Table(title="Per-Fixture Structural Quality")
        table.add_column("Fixture", style="bold")
        table.add_column("Extracted")
        table.add_column("Measures", justify="right")
        table.add_column("Dur=1", justify="center")
        table.add_column("Stuffing", justify="center")
        table.add_column("Max Notes", justify="right")
        table.add_column("Status")

        for result in sorted(results, key=lambda r: r.fixture_name):
            # Extracted status
            extracted = "[green]✓[/green]" if result.has_extracted else "[red]✗[/red]"

            # Measure count
            if result.has_extracted:
                measures = f"{result.ex_measure_count}/{result.gt_measure_count}"
                measure_ok = "[green]✓[/green]" if result.measure_count_match else "[red]✗[/red]"
            else:
                measures = "-"
                measure_ok = "-"

            # Duration check
            if result.has_extracted and not result.error:
                dur_status = "[red]✗[/red]" if result.all_durations_one else "[green]✓[/green]"
            else:
                dur_status = "-"

            # Stuffing check
            if result.has_extracted and not result.error:
                stuff_status = "[red]✗[/red]" if result.has_measure_stuffing else "[green]✓[/green]"
            else:
                stuff_status = "-"

            # Max notes
            max_notes = str(result.max_notes_in_measure) if result.has_extracted else "-"

            # Overall status
            if result.error:
                status = f"[yellow]SKIP[/yellow] ({result.error})"
            elif not result.measure_count_match or result.all_durations_one or result.has_measure_stuffing:
                status = "[red]FAIL[/red]"
            else:
                status = "[green]PASS[/green]"

            table.add_row(
                result.fixture_name,
                extracted,
                measures,
                dur_status,
                stuff_status,
                max_notes,
                status
            )

        self.console.print(table)

        # Summary
        total = len(results)
        with_extracted = sum(1 for r in results if r.has_extracted)
        passed = sum(1 for r in results if r.has_extracted and not r.error and r.measure_count_match and not r.all_durations_one and not r.has_measure_stuffing)
        failed = with_extracted - passed
        skipped = total - with_extracted

        self.console.print(f"\n  Total: {total}  With extracted: {with_extracted}  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")

        # Show fixtures with issues
        issues = [r for r in results if r.has_extracted and not r.error and (not r.measure_count_match or r.all_durations_one or r.has_measure_stuffing)]
        if issues:
            self.console.print("\n[bold]Fixtures with issues:[/bold]")
            for r in issues:
                issue_list = []
                if not r.measure_count_match:
                    issue_list.append(f"measure count mismatch ({r.ex_measure_count} vs {r.gt_measure_count})")
                if r.all_durations_one:
                    issue_list.append("all durations = 1.0")
                if r.has_measure_stuffing:
                    issue_list.append(f"stuffing in measures {r.stuffing_measures}")
                self.console.print(f"  [yellow]{r.fixture_name}:[/yellow] {', '.join(issue_list)}")


def main():
    """CLI entry point."""
    smoke_test = SmokeTest()
    results = smoke_test.run_all()
    smoke_test._print_report(results)


if __name__ == "__main__":
    main()
