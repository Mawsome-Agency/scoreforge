#!/usr/bin/env python3
"""
ScoreForge Test Result Visualization Tool.

Generates ASCII charts and HTML reports showing accuracy trends over time.
Highlights progress toward 95%+ accuracy goal and identifies fixtures needing improvement.
"""
import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# ANSI colors for terminal output
class Colors:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


@dataclass
class AccuracyMetric:
    """Accuracy metric for a single test run."""
    timestamp: str
    overall_accuracy: float
    pitch_accuracy: float
    rhythm_accuracy: float
    note_accuracy: float
    measure_accuracy: float


@dataclass
class FixtureData:
    """Data for a single fixture across multiple runs."""
    name: str
    metrics: list[AccuracyMetric]
    latest_accuracy: float
    trend: str  # "improving", "declining", "stable"


class ResultReader:
    """Reads and parses test result files."""

    RESULT_DIR = Path("results")

    @classmethod
    def read_result(cls, path: Path) -> Optional[dict]:
        """Read a JSON result file."""
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    @classmethod
    def parse_comparison_json(cls, data: dict, timestamp: str) -> Optional[AccuracyMetric]:
        """Parse a comparison.json file into an AccuracyMetric."""
        scores = data.get("scores", {})
        if not scores:
            return None

        return AccuracyMetric(
            timestamp=timestamp,
            overall_accuracy=scores.get("overall", 0.0),
            pitch_accuracy=scores.get("pitch_accuracy", 0.0),
            rhythm_accuracy=scores.get("rhythm_accuracy", 0.0),
            note_accuracy=scores.get("note_accuracy", 0.0),
            measure_accuracy=scores.get("measure_accuracy", 0.0),
        )

    @classmethod
    def discover_fixture_results(cls) -> dict[str, list[tuple[str, Path]]]:
        """Discover all result directories organized by fixture."""
        fixtures = {}

        if not cls.RESULT_DIR.exists():
            return fixtures

        for fixture_dir in cls.RESULT_DIR.iterdir():
            if not fixture_dir.is_dir():
                continue

            # Look for timestamp subdirectories
            timestamps = []
            for timestamp_dir in fixture_dir.iterdir():
                if not timestamp_dir.is_dir():
                    continue

                # Check for comparison.json
                comparison_path = timestamp_dir / "comparison.json"
                if comparison_path.exists():
                    timestamps.append((timestamp_dir.name, comparison_path))

            if timestamps:
                # Sort by timestamp (format: YYYYMMDD_HHMMSS)
                timestamps.sort(key=lambda x: x[0])
                fixtures[fixture_dir.name] = timestamps

        return fixtures


class TrendAnalyzer:
    """Analyzes accuracy trends."""

    TARGET_ACCURACY = 95.0

    @staticmethod
    def calculate_trend(metrics: list[AccuracyMetric]) -> str:
        """Calculate trend direction based on recent data points."""
        if len(metrics) < 2:
            return "stable"

        # Compare last 3 runs if available
        recent = metrics[-3:]
        if len(recent) < 2:
            return "stable"

        # Simple linear regression
        n = len(recent)
        x = list(range(n))
        y = [m.overall_accuracy for m in recent]

        # Calculate slope
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        if n * sum_x2 - sum_x * sum_x == 0:
            return "stable"

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

        if slope > 0.5:
            return "improving"
        elif slope < -0.5:
            return "declining"
        else:
            return "stable"


class AsciiChart:
    """Generates ASCII charts."""

    WIDTH = 50
    HEIGHT = 10
    TARGET_ACCURACY = 95.0  # Add TARGET_ACCURACY constant

    @classmethod
    def draw_chart(cls, metrics: list[AccuracyMetric], title: str = "") -> str:
        """Draw an ASCII chart of accuracy over time."""
        if not metrics:
            return f"{title}\nNo data available"

        max_acc = max(m.overall_accuracy for m in metrics)
        min_acc = min(m.overall_accuracy for m in metrics)
        range_acc = max_acc - min_acc or 1.0

        # Create grid
        grid = [[" " for _ in range(cls.WIDTH)] for _ in range(cls.HEIGHT)]

        # Plot points
        for i, metric in enumerate(metrics):
            x = int((i / (len(metrics) - 1 or 1)) * (cls.WIDTH - 1))
            y = int(cls.HEIGHT - 1 - ((metric.overall_accuracy - min_acc) / range_acc) * (cls.HEIGHT - 1))
            y = max(0, min(cls.HEIGHT - 1, y))
            grid[y][x] = "*"

        # Add target line at 95%
        if min_acc <= cls.TARGET_ACCURACY <= max_acc:
            target_y = int(cls.HEIGHT - 1 - ((cls.TARGET_ACCURACY - min_acc) / range_acc) * (cls.HEIGHT - 1))
            target_y = max(0, min(cls.HEIGHT - 1, target_y))
            grid[target_y] = ["=" if c != "*" else "*" for c in grid[target_y]]

        # Build output
        lines = [title]
        # Y-axis labels
        y_labels = []
        for i in range(cls.HEIGHT - 1, -1, -1):
            val = i * 100 / cls.HEIGHT
            y_labels.append(f"{val:.0f}"[-1])
        lines.append(" " * 6 + "".join(y_labels))
        lines.append(" " * 6 + "+" + "-" * (cls.WIDTH - 2) + "+")
        for row in grid:
            left = "".join(row[:cls.WIDTH // 2 - 1])
            right = "".join(row[cls.WIDTH // 2:])
            lines.append(" " * 5 + "|".join([left, right]))
        lines.append(" " * 6 + "+" + "-" * (cls.WIDTH - 2) + "+")

        # Add legend
        legend = f"Latest: {metrics[-1].overall_accuracy:.1f}%  Target: {cls.TARGET_ACCURACY}% (* = data, = = target)"
        lines.append(" " * 6 + legend)

        return "\n".join(lines)


class HtmlReport:
    """Generates HTML reports."""

    TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ScoreForge Test Results</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .metric-card {{ background: #f9f9f9; padding: 15px; border-radius: 6px; border-left: 4px solid #ddd; }}
        .metric-card.success {{ border-left-color: #4CAF50; }}
        .metric-card.warning {{ border-left-color: #FF9800; }}
        .metric-card.danger {{ border-left-color: #f44336; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #333; }}
        .metric-label {{ color: #666; font-size: 14px; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f0f0f0; font-weight: 600; }}
        tr:hover {{ background: #f9f9f9; }}
        .pass {{ color: #4CAF50; font-weight: bold; }}
        .fail {{ color: #f44336; font-weight: bold; }}
        .trend-up {{ color: #4CAF50; }}
        .trend-down {{ color: #f44336; }}
        .trend-flat {{ color: #999; }}
        .progress-bar {{ width: 100px; height: 8px; background: #e0e0e0; border-radius: 4px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: #4CAF50; transition: width 0.3s; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎼 ScoreForge Test Results Visualization</h1>
        <p><strong>Generated:</strong> {timestamp}</p>

        <h2>Summary</h2>
        <div class="summary">
            <div class="metric-card {total_class}">
                <div class="metric-value">{total_fixtures}</div>
                <div class="metric-label">Total Fixtures</div>
            </div>
            <div class="metric-card {meeting_target_class}">
                <div class="metric-value">{meeting_target:.1f}%</div>
                <div class="metric-label">Meeting 95% Goal</div>
            </div>
            <div class="metric-card {avg_class}">
                <div class="metric-value">{avg_accuracy:.1f}%</div>
                <div class="metric-label">Average Accuracy</div>
            </div>
            <div class="metric-card {improving_class}">
                <div class="metric-value">{improving_count}</div>
                <div class="metric-label">Improving Fixtures</div>
            </div>
        </div>

        <h2>Fixture Details</h2>
        <table>
            <tr>
                <th>Fixture</th>
                <th>Latest Accuracy</th>
                <th>Trend</th>
                <th>Progress</th>
                <th>Status</th>
            </tr>
            {rows}
        </table>

        <h2>Fixtures Needing Improvement</h2>
        {needs_improvement}

        <p><em>Report generated by visualize_results.py</em></p>
    </div>
</body>
</html>"""

    @classmethod
    def generate(cls, fixtures: dict[str, FixtureData]) -> str:
        """Generate HTML report."""
        total_fixtures = len(fixtures)
        meeting_target = sum(1 for f in fixtures.values() if f.latest_accuracy >= 95.0)
        avg_accuracy = sum(f.latest_accuracy for f in fixtures.values()) / total_fixtures if total_fixtures else 0
        improving_count = sum(1 for f in fixtures.values() if f.trend == "improving")

        # Determine metric card classes
        total_class = "success" if total_fixtures > 0 else "warning"
        meeting_target_class = "success" if total_fixtures > 0 and meeting_target >= 0.9 * total_fixtures else "danger"
        avg_class = "success" if avg_accuracy >= 90 else "warning" if avg_accuracy >= 70 else "danger"
        improving_class = "success" if total_fixtures > 0 and improving_count >= 0.5 * total_fixtures else "warning"

        # Generate table rows
        rows = []
        for name, data in sorted(fixtures.items()):
            status_class = "pass" if data.latest_accuracy >= 95.0 else "fail"
            status = "✓ PASS" if data.latest_accuracy >= 95.0 else "✗ FAIL"

            trend_class = {"improving": "trend-up", "declining": "trend-down", "stable": "trend-flat"}[data.trend]
            trend_icon = {"improving": "↑", "declining": "↓", "stable": "→"}[data.trend]

            progress_pct = min(100, data.latest_accuracy)
            progress_fill = f'<div class="progress-fill" style="width: {progress_pct}%"></div>'

            rows.append(f"""
                <tr>
                    <td>{name}</td>
                    <td>{data.latest_accuracy:.1f}%</td>
                    <td class="{trend_class}">{trend_icon} {data.trend}</td>
                    <td>
                        <div class="progress-bar">
                            {progress_fill}
                        </div>
                    </td>
                    <td class="{status_class}">{status}</td>
                </tr>
            """)

        # Fixtures needing improvement
        needs_improvement = []
        for name, data in sorted(fixtures.items()):
            if data.latest_accuracy < 95.0:
                gap = 95.0 - data.latest_accuracy
                needs_improvement.append(f"<p><strong>{name}</strong>: {data.latest_accuracy:.1f}% (gap: {gap:.1f}%)</p>")

        if not needs_improvement:
            needs_improvement = ["<p>All fixtures meet the 95% accuracy goal! 🎉</p>"]

        return cls.TEMPLATE.format(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_fixtures=total_fixtures,
            meeting_target=meeting_target / total_fixtures * 100 if total_fixtures else 0,
            avg_accuracy=avg_accuracy,
            improving_count=improving_count,
            total_class=total_class,
            meeting_target_class=meeting_target_class,
            avg_class=avg_class,
            improving_class=improving_class,
            rows="".join(rows),
            needs_improvement="".join(needs_improvement),
        )


class Visualizer:
    """Main visualization orchestrator."""

    @staticmethod
    def load_fixture_data() -> dict[str, FixtureData]:
        """Load all fixture data from results directory."""
        fixtures_data = {}
        raw_results = ResultReader.discover_fixture_results()

        for fixture_name, timestamps in raw_results.items():
            metrics = []
            for timestamp, comparison_path in timestamps:
                result = ResultReader.read_result(comparison_path)
                if result:
                    metric = ResultReader.parse_comparison_json(result, timestamp)
                    if metric:
                        metrics.append(metric)

            if metrics:
                latest = metrics[-1].overall_accuracy
                trend = TrendAnalyzer.calculate_trend(metrics)
                fixtures_data[fixture_name] = FixtureData(
                    name=fixture_name,
                    metrics=metrics,
                    latest_accuracy=latest,
                    trend=trend,
                )

        return fixtures_data

    @staticmethod
    def print_ascii_report(fixtures: dict[str, FixtureData]) -> None:
        """Print ASCII report to console."""
        print(f"\n{Colors.CYAN}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.CYAN}📊 ScoreForge Test Results Visualization{Colors.RESET}")
        print(f"{Colors.CYAN}{'=' * 60}{Colors.RESET}\n")

        if not fixtures:
            print(f"{Colors.YELLOW}No test results found in results/ directory.{Colors.RESET}")
            print("Run tests first to generate result data.")
            return

        # Summary
        total = len(fixtures)
        meeting_target = sum(1 for f in fixtures.values() if f.latest_accuracy >= 95.0)
        avg_acc = sum(f.latest_accuracy for f in fixtures.values()) / total

        print(f"{Colors.MAGENTA}Summary:{Colors.RESET}")
        print(f"  Total Fixtures: {total}")
        print(f"  Meeting 95% Goal: {meeting_target}/{total} ({meeting_target/total*100:.0f}%)")
        print(f"  Average Accuracy: {avg_acc:.1f}%")

        # Top and bottom performers
        sorted_fixtures = sorted(fixtures.items(), key=lambda x: x[1].latest_accuracy, reverse=True)
        print(f"\n{Colors.GREEN}Top Performers:{Colors.RESET}")
        for name, data in sorted_fixtures[:3]:
            print(f"  {Colors.GREEN}✓{Colors.RESET} {name}: {data.latest_accuracy:.1f}%")

        print(f"\n{Colors.RED}Needs Improvement:{Colors.RESET}")
        for name, data in sorted_fixtures[-3:]:
            if data.latest_accuracy < 95.0:
                gap = 95.0 - data.latest_accuracy
                print(f"  {Colors.RED}✗{Colors.RESET} {name}: {data.latest_accuracy:.1f}% (gap: {gap:.1f}%)")

        # Detailed chart for top fixture with most data
        chart_fixture = max(fixtures.items(), key=lambda x: len(x[1].metrics), default=(None, None))
        if chart_fixture[0]:
            print(f"\n{Colors.CYAN}Accuracy Trend: {chart_fixture[0]}{Colors.RESET}")
            chart = AsciiChart.draw_chart(chart_fixture[1].metrics, f"  {chart_fixture[0]}")
            print(chart)

        print(f"\n{Colors.CYAN}{'=' * 60}{Colors.RESET}\n")

    @staticmethod
    def generate_html_report(fixtures: dict[str, FixtureData], output_path: Path) -> None:
        """Generate HTML report."""
        html = HtmlReport.generate(fixtures)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)
        print(f"{Colors.GREEN}HTML report saved to: {output_path}{Colors.RESET}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Visualize ScoreForge test results with ASCII charts and HTML reports"
    )
    parser.add_argument(
        "--format", "-f", choices=["ascii", "html", "both"], default="both",
        help="Output format"
    )
    parser.add_argument(
        "--output", "-o", default="test_results_report.html",
        help="Output path for HTML report"
    )
    args = parser.parse_args()

    fixtures = Visualizer.load_fixture_data()

    if args.format in ("ascii", "both"):
        Visualizer.print_ascii_report(fixtures)

    if args.format in ("html", "both"):
        Visualizer.generate_html_report(fixtures, Path(args.output))


if __name__ == "__main__":
    main()
