#!/usr/bin/env python3
"""Extraction quality smoke test — validates extracted MusicXML structure.

Usage: python3 tests/test_extraction_quality.py
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

_repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(_repo_root))
from core.comparator import _parse_musicxml

FIXTURE_DIR = _repo_root / "tests" / "fixtures"
RESULTS_DIR = _repo_root / "results"


@dataclass
class FixtureQualityResult:
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
    def __init__(self):
        self.console = Console()

    def discover_fixtures(self) -> list[Path]:
        if not FIXTURE_DIR.exists():
            return []
        return sorted(FIXTURE_DIR.glob("*.musicxml"))

    def check_fixture(self, fixture_path: Path) -> FixtureQualityResult:
        result = FixtureQualityResult(fixture_name=fixture_path.stem)
        extracted_path = RESULTS_DIR / result.fixture_name / "extracted.musicxml"

        if not extracted_path.exists():
            candidates = list(RESULTS_DIR.glob(f"{result.fixture_name}/**/extracted.musicxml"))
            if candidates:
                extracted_path = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
            else:
                result.error = "No extracted file found"
                return result

        result.has_extracted = True

        try:
            gt_data = _parse_musicxml(str(fixture_path))
            ex_data = _parse_musicxml(str(extracted_path))

            result.measure_count_match, result.gt_measure_count, result.ex_measure_count = self._check_measure_count(gt_data, ex_data)
            result.all_durations_one = self._check_note_durations(ex_data)
            result.has_measure_stuffing, result.max_notes_in_measure, result.stuffing_measures = self._check_measure_stuffing(ex_data)
        except Exception as e:
            result.error = f"Parse error: {e}"

        return result

    def _check_measure_count(self, gt_data: dict, ex_data: dict) -> tuple[bool, int, int]:
        if not gt_data.get("parts") or not ex_data.get("parts"):
            return False, 0, 0
        gt_total = max((len(p.get("measures", [])) for p in gt_data["parts"]), default=0)
        ex_total = max((len(p.get("measures", [])) for p in ex_data["parts"]), default=0)
        return gt_total == ex_total, gt_total, ex_total

    def _check_note_durations(self, ex_data: dict) -> bool:
        durations = [
            note.get("duration_normalized")
            for part in ex_data.get("parts", [])
            for measure in part.get("measures", [])
            for note in measure.get("notes", [])
            if not note.get("is_grace") and not note.get("is_rest") and note.get("duration_normalized") is not None
        ]
        return bool(durations) and all(d == 1.0 for d in durations)

    def _check_measure_stuffing(self, ex_data: dict) -> tuple[bool, int, list[int]]:
        max_notes = 0
        stuffed = []
        for part in ex_data.get("parts", []):
            for measure in part.get("measures", []):
                note_count = sum(1 for n in measure.get("notes", []) if not n.get("is_grace") and not n.get("is_rest"))
                max_notes = max(max_notes, note_count)
                if note_count > 20:
                    num = measure.get("number", 0)
                    if num not in stuffed:
                        stuffed.append(num)
        return len(stuffed) > 0, max_notes, sorted(stuffed)

    def run_all(self) -> list[FixtureQualityResult]:
        return [self.check_fixture(p) for p in self.discover_fixtures()]

    def _print_report(self, results: list[FixtureQualityResult]) -> None:
        console = self.console
        console.print("\n[bold]Extraction Quality Smoke Test Results[/bold]\n")
        table = Table(title="Per-Fixture Structural Quality")
        table.add_column("Fixture", style="bold")
        table.add_column("Extracted")
        table.add_column("Measures", justify="right")
        table.add_column("Dur=1", justify="center")
        table.add_column("Stuffing", justify="center")
        table.add_column("Max Notes", justify="right")
        table.add_column("Status")
        for r in sorted(results, key=lambda x: x.fixture_name):
            extracted = "[green]✓[/green]" if r.has_extracted else "[red]✗[/red]"
            measures = f"{r.ex_measure_count}/{r.gt_measure_count}" if r.has_extracted else "-"
            dur_status = "[red]✗[/red]" if r.has_extracted and not r.error and r.all_durations_one else "[green]✓[/green]" if r.has_extracted and not r.error else "-"
            stuff_status = "[red]✗[/red]" if r.has_extracted and not r.error and r.has_measure_stuffing else "[green]✓[/green]" if r.has_extracted and not r.error else "-"
            max_notes = str(r.max_notes_in_measure) if r.has_extracted else "-"
            if r.error:
                status = f"[yellow]SKIP[/yellow] ({r.error})"
            elif not r.measure_count_match or r.all_durations_one or r.has_measure_stuffing:
                status = "[red]FAIL[/red]"
            else:
                status = "[green]PASS[/green]"
            table.add_row(r.fixture_name, extracted, measures, dur_status, stuff_status, max_notes, status)
        console.print(table)
        total = len(results)
        with_extracted = sum(1 for r in results if r.has_extracted)
        passed = sum(1 for r in results if r.has_extracted and not r.error and r.measure_count_match and not r.all_durations_one and not r.has_measure_stuffing)
        failed = with_extracted - passed
        skipped = total - with_extracted
        console.print(f"\n  Total: {total}  With extracted: {with_extracted}  Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
        issues = [r for r in results if r.has_extracted and not r.error and (not r.measure_count_match or r.all_durations_one or r.has_measure_stuffing)]
        if issues:
            console.print("\n[bold]Fixtures with issues:[/bold]")
            for r in issues:
                parts = []
                if not r.measure_count_match:
                    parts.append(f"measure count mismatch ({r.ex_measure_count} vs {r.gt_measure_count})")
                if r.all_durations_one:
                    parts.append("all durations = 1.0")
                if r.has_measure_stuffing:
                    parts.append(f"stuffing in measures {r.stuffing_measures}")
                console.print(f"  [yellow]{r.fixture_name}:[/yellow] {', '.join(parts)}")

def main():
    smoke_test = SmokeTest()
    smoke_test._print_report(smoke_test.run_all())

if __name__ == "__main__":
    main()
