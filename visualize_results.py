#!/usr/bin/env python3
"""ScoreForge Test Result Visualization Tool.

Generates visual representations of test accuracy trends, highlighting
progress toward the 95%+ accuracy goal and showing which
fixtures need improvement.

Usage:
    python visualize_results.py [--format ascii|html] [--fixture NAME] [--top N]
    python visualize_results.py --list-fixtures
    python visualize_results.py --summary
"""
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.text import Text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

console = Console()

# Constants
RESULTS_DIR = Path(__file__).parent / "results"
FIXTURE_DIR = Path(__file__).parent / "tests" / "fixtures"
TARGET_ACCURACY = 95.0  # Goal from Q2 2026 rock


@dataclass
class FixtureDataPoint:
    """Single data point for a fixture at a specific timestamp."""
    fixture: str
    timestamp: str
    overall_accuracy: float
    note_accuracy: float = 0.0
    pitch_accuracy: float = 0.0
    rhythm_accuracy: float = 0.0
    measure_accuracy: float = 0.0
    passed: bool = False


@dataclass
class FixtureTrend:
    """Trend data for a single fixture across all runs."""
    fixture: str
    data_points: List[FixtureDataPoint] = field(default_factory=list)
    latest_accuracy: float = 0.0
    best_accuracy: float = 0.0
    first_accuracy: float = 0.0
    trend: str = "unknown"  # "improving", "declining", "stable", "unknown"
    meets_target: bool = False
    needs_improvement: bool = True


@dataclass
class VisualizationSummary:
    """Summary of all fixture trends."""
    total_fixtures: int = 0
    fixtures_meeting_target: int = 0
    fixtures_needing_improvement: int = 0
    avg_accuracy: float = 0.0
    best_performing_fixture: str = ""
    worst_performing_fixture: str = ""


def parse_timestamp(dir_name: str) -> Optional[datetime]:
    """Parse timestamp from directory name (YYYYMMDD_HHMMSS format)."""
    try:
        # Handle format like "20260326_113438"
        if "_" in dir_name:
            date_part, time_part = dir_name.split("_")
            if len(date_part) == 8 and len(time_part) == 6:
                year = int(date_part[:4])
                month = int(date_part[4:6])
                day = int(date_part[6:8])
                hour = int(time_part[:2])
                minute = int(time_part[2:4])
                second = int(time_part[4:6])
                return datetime(year, month, day, hour, minute, second)
        return None
    except (ValueError, IndexError):
        return None


def discover_fixture_directories() -> Dict[str, Path]:
    """Discover all fixture result directories under results/."""
    fixtures = {}
    if not RESULTS_DIR.exists():
        return fixtures
    
    for entry in RESULTS_DIR.iterdir():
        if entry.is_dir() and not entry.name.startswith('.'):
            # Skip non-fixture directories
            if entry.name in ['baseline', 'corpus']:
                continue
            fixtures[entry.name] = entry
    
    return fixtures


def load_comparison_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load comparison.json file safely."""
    try:
        if not path.exists():
            return None
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        console.print(f"[yellow]Warning: Could not read {path}: {e}[/yellow]")
        return None


def load_summary_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load summary.json file safely."""
    try:
        if not path.exists():
            return None
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        console.print(f"[yellow]Warning: Could not read {path}: {e}[/yellow]")
        return None


def extract_accuracy_from_comparison(data: Dict[str, Any]) -> float:
    """Extract overall accuracy from comparison data structure."""
    if not data:
        return 0.0
    
    # Try different possible paths based on schema variations
    scores = data.get("scores", {})
    if isinstance(scores, dict):
        return scores.get("overall", 0.0)
    
    # Fallback: check for direct overall_accuracy field
    return data.get("overall_accuracy", 0.0)


def extract_accuracy_from_summary(data: Dict[str, Any]) -> float:
    """Extract accuracy from summary data structure."""
    if not data:
        return 0.0
    
    # Try different possible paths
    if "best_score" in data:
        return float(data["best_score"])
    
    if "overall_accuracy" in data:
        return float(data["overall_accuracy"])
    
    return 0.0


def collect_fixture_data(fixture_name: str, fixture_dir: Path) -> List[FixtureDataPoint]:
    """Collect all data points for a single fixture."""
    data_points = []
    
    # Scan for timestamped directories
    for entry in sorted(fixture_dir.iterdir()):
        if not entry.is_dir():
            continue
        
        timestamp = parse_timestamp(entry.name)
        if not timestamp:
            continue
        
        # Try to find comparison.json or summary.json
        comparison_file = entry / "comparison.json"
        summary_file = entry / "summary.json"
        
        accuracy = 0.0
        source_file = None
        
        # Check for iter_N subdirectories first
        iter_dirs = sorted([d for d in entry.iterdir() if d.is_dir() and d.name.startswith('iter_')])
        if iter_dirs:
            # Use the latest iteration
            latest_iter = iter_dirs[-1]
            iter_comparison = latest_iter / "comparison.json"
            if iter_comparison.exists():
                comp_data = load_comparison_json(iter_comparison)
                accuracy = extract_accuracy_from_comparison(comp_data)

        # If no iter dirs, check direct comparison.json
        if accuracy == 0.0 and comparison_file.exists():
            comp_data = load_comparison_json(comparison_file)
            accuracy = extract_accuracy_from_comparison(comp_data)

        # If still no accuracy, try summary.json
        if accuracy == 0.0 and summary_file.exists():
            sum_data = load_summary_json(summary_file)
            accuracy = extract_accuracy_from_summary(sum_data)
        
        if accuracy > 0:
            data_points.append(FixtureDataPoint(
                fixture=fixture_name,
                timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                overall_accuracy=accuracy,
                passed=accuracy >= TARGET_ACCURACY
            ))
    
    return data_points


def calculate_trend(data_points: List[FixtureDataPoint]) -> str:
    """Determine if fixture is improving, declining, or stable."""
    if len(data_points) < 2:
        return "unknown"
    
    # Compare first and last data points
    first = data_points[0].overall_accuracy
    last = data_points[-1].overall_accuracy
    
    # Consider trend if difference is meaningful (>2%)
    if last - first > 2.0:
        return "improving"
    elif first - last > 2.0:
        return "declining"
    else:
        return "stable"


def build_fixture_trend(fixture_name: str, fixture_dir: Path) -> FixtureTrend:
    """Build complete trend data for a fixture."""
    data_points = collect_fixture_data(fixture_name, fixture_dir)
    
    if not data_points:
        return FixtureTrend(fixture=fixture_name, needs_improvement=False)
    
    latest = data_points[-1].overall_accuracy
    best = max(dp.overall_accuracy for dp in data_points)
    first = data_points[0].overall_accuracy
    trend = calculate_trend(data_points)
    meets_target = latest >= TARGET_ACCURACY
    
    return FixtureTrend(
        fixture=fixture_name,
        data_points=data_points,
        latest_accuracy=latest,
        best_accuracy=best,
        first_accuracy=first,
        trend=trend,
        meets_target=meets_target,
        needs_improvement=not meets_target
    )


def build_all_trends() -> Dict[str, FixtureTrend]:
    """Build trend data for all fixtures."""
    trends = {}
    fixture_dirs = discover_fixture_directories()
    
    for fixture_name, fixture_dir in fixture_dirs.items():
        trends[fixture_name] = build_fixture_trend(fixture_name, fixture_dir)
    
    return trends


def calculate_summary(trends: Dict[str, FixtureTrend]) -> VisualizationSummary:
    """Calculate aggregate summary."""
    valid_trends = [t for t in trends.values() if t.data_points]
    
    if not valid_trends:
        return VisualizationSummary()
    
    total = len(valid_trends)
    meeting = sum(1 for t in valid_trends if t.meets_target)
    needs = total - meeting
    
    avg_acc = sum(t.latest_accuracy for t in valid_trends) / total
    
    best_fixture = max(valid_trends, key=lambda t: t.latest_accuracy)
    worst_fixture = min(valid_trends, key=lambda t: t.latest_accuracy)
    
    return VisualizationSummary(
        total_fixtures=total,
        fixtures_meeting_target=meeting,
        fixtures_needing_improvement=needs,
        avg_accuracy=avg_acc,
        best_performing_fixture=best_fixture.fixture,
        worst_performing_fixture=worst_fixture.fixture
    )


def render_ascii_chart(data_points: List[FixtureDataPoint], width: int = 40) -> str:
    """Render a simple ASCII chart of accuracy over time."""
    if len(data_points) < 2:
        return "  (insufficient data for chart)"
    
    chart_lines = []
    max_acc = max(dp.overall_accuracy for dp in data_points)
    min_acc = min(dp.overall_accuracy for dp in data_points)
    range_acc = max(max_acc - min_acc, 1.0)
    
    # Normalize heights to fit in chart
    for dp in data_points:
        normalized = (dp.overall_accuracy - min_acc) / range_acc
        bar_height = int(normalized * width)
        
        # Use different characters for target line
        is_target = dp.overall_accuracy >= TARGET_ACCURACY
        marker = "█" if is_target else "░"
        bar = marker * bar_height + "░" * (width - bar_height)
        
        # Add percentage label
        label = f"{dp.overall_accuracy:5.1f}%"
        chart_lines.append(f"  {label} │{bar}")
    
    # Add time labels
    if data_points:
        first_date = data_points[0].timestamp[:10]
        last_date = data_points[-1].timestamp[:10]
        chart_lines.append(f"  └───── {first_date} → {last_date}")
    
    return "\n".join(chart_lines)


def render_summary_table(summary: VisualizationSummary) -> Table:
    """Render summary table."""
    table = Table(title="Test Accuracy Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Total Fixtures", str(summary.total_fixtures))
    table.add_row("Meeting 95% Goal", 
                  f"[green]{summary.fixtures_meeting_target}[/green]" if summary.fixtures_meeting_target > 0 else "0")
    table.add_row("Needs Improvement", 
                  f"[red]{summary.fixtures_needing_improvement}[/red]" if summary.fixtures_needing_improvement > 0 else "0")
    table.add_row("Average Accuracy", f"{summary.avg_accuracy:.2f}%")
    table.add_row("Best Fixture", summary.best_performing_fixture)
    table.add_row("Worst Fixture", summary.worst_performing_fixture)
    
    return table


def render_fixture_table(trends: Dict[str, FixtureTrend], show_all: bool = False, top_n: int = 10) -> Table:
    """Render fixtures table sorted by priority."""
    table = Table(title="Fixture Status", show_header=True, header_style="bold magenta")
    table.add_column("Fixture", style="cyan", width=20)
    table.add_column("Latest", justify="right", width=8)
    table.add_column("Best", justify="right", width=8)
    table.add_column("Trend", justify="center", width=10)
    table.add_column("Status", justify="center", width=12)
    
    # Sort: fixtures needing improvement first, then by latest accuracy
    sorted_trends = sorted(
        trends.values(),
        key=lambda t: (not t.needs_improvement, -t.latest_accuracy, t.fixture)
    )
    
    # Filter: only show fixtures with data
    with_data = [t for t in sorted_trends if t.data_points]
    
    # Limit results
    if not show_all:
        with_data = with_data[:top_n]
    
    for trend in with_data:
        # Status styling
        if trend.meets_target:
            status = "[green]✓ GOAL MET[/green]"
        elif trend.trend == "improving":
            status = "[yellow]↑ IMPROVING[/yellow]"
        elif trend.trend == "declining":
            status = "[red]↓ DECLINING[/red]"
        else:
            status = "[dim]→ STABLE[/dim]"
        
        # Trend indicator
        trend_icon = "↑" if trend.trend == "improving" else "↓" if trend.trend == "declining" else "→"
        
        table.add_row(
            trend.fixture[:20],
            f"{trend.latest_accuracy:5.2f}%",
            f"{trend.best_accuracy:5.2f}%",
            f"{trend_icon} {trend.trend}",
            status
        )
    
    return table


def render_fixture_detail(trend: FixtureTrend) -> None:
    """Render detailed view for a single fixture."""
    console.print(Panel.fit(
        f"[bold cyan]{trend.fixture}[/bold cyan]",
        border_style="cyan"
    ))
    
    # Summary stats
    stats_table = Table(show_header=False)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", justify="right")
    
    stats_table.add_row("Latest Accuracy", f"{trend.latest_accuracy:.2f}%")
    stats_table.add_row("Best Accuracy", f"{trend.best_accuracy:.2f}%")
    stats_table.add_row("First Accuracy", f"{trend.first_accuracy:.2f}%")
    stats_table.add_row("Trend", trend.trend)
    stats_table.add_row("Target Met", 
                     "[green]Yes[/green]" if trend.meets_target else "[red]No[/red]")
    
    console.print(stats_table)
    console.print()
    
    # Data points table
    if trend.data_points:
        points_table = Table(title="Historical Runs", show_header=True)
        points_table.add_column("Timestamp", style="dim")
        points_table.add_column("Accuracy", justify="right")
        points_table.add_column("Status", justify="center")
        
        for dp in trend.data_points:
            status = "[green]✓[/green]" if dp.overall_accuracy >= TARGET_ACCURACY else " "
            points_table.add_row(dp.timestamp, f"{dp.overall_accuracy:.2f}%", status)
        
        console.print(points_table)
        console.print()
    
    # ASCII chart
    if len(trend.data_points) >= 2:
        console.print("[bold]Accuracy Trend:[/bold]")
        console.print(render_ascii_chart(trend.data_points))
        console.print()
    
    # Goal line
    console.print(f"Target: {TARGET_ACCURACY}% | Current: {trend.latest_accuracy:.2f}% | Gap: {TARGET_ACCURACY - trend.latest_accuracy:.2f}%")


def render_html_report(trends: Dict[str, FixtureTrend], summary: VisualizationSummary, output_path: Path) -> None:
    """Generate an HTML report with visual charts."""
    # Sanitize fixture names to prevent XSS
    def sanitize(s: str) -> str:
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace('"', "&quot;")
                 .replace("'", "&#39;"))
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ScoreForge Test Results</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f0f;
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
            line-height: 1.6;
        }}
        h1 {{ color: #4ecdc4; border-bottom: 2px solid #4ecdc4; padding-bottom: 10px; }}
        h2 {{ color: #a8e6cf; margin-top: 30px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric {{ background: #1a1a1a; padding: 20px; border-radius: 8px; border-left: 4px solid #4ecdc4; }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #4ecdc4; }}
        .metric-label {{ color: #888; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #1a1a1a; color: #4ecdc4; padding: 12px; text-align: left; }}
        td {{ padding: 12px; border-bottom: 1px solid #333; }}
        .status-pass {{ color: #4ecdc4; font-weight: bold; }}
        .status-fail {{ color: #ff6b6b; font-weight: bold; }}
        .status-improving {{ color: #feca57; }}
        .status-declining {{ color: #ff6b6b; }}
        .chart-container {{ height: 200px; background: #1a1a1a; padding: 20px; border-radius: 8px; }}
    </style>
</head>
<body>
    <h1>ScoreForge Test Results</h1>
    <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    
    <h2>Summary</h2>
    <div class="summary">
        <div class="metric">
            <div class="metric-value">{summary.total_fixtures}</div>
            <div class="metric-label">Total Fixtures</div>
        </div>
        <div class="metric">
            <div class="metric-value" style="color: {'#4ecdc4' if summary.fixtures_meeting_target > 0 else '#888'}">{summary.fixtures_meeting_target}</div>
            <div class="metric-label">Meeting 95% Goal</div>
        </div>
        <div class="metric">
            <div class="metric-value" style="color: {'#ff6b6b' if summary.fixtures_needing_improvement > 0 else '#888'}">{summary.fixtures_needing_improvement}</div>
            <div class="metric-label">Needs Improvement</div>
        </div>
        <div class="metric">
            <div class="metric-value">{summary.avg_accuracy:.2f}%</div>
            <div class="metric-label">Average Accuracy</div>
        </div>
    </div>
    
    <h2>Fixture Details</h2>
    <table>
        <tr>
            <th>Fixture</th>
            <th>Latest</th>
            <th>Best</th>
            <th>Trend</th>
            <th>Status</th>
        </tr>
"""
    
    # Add fixture rows
    sorted_trends = sorted(
        trends.values(),
        key=lambda t: (not t.needs_improvement, -t.latest_accuracy, t.fixture)
    )
    
    for trend in sorted_trends:
        if not trend.data_points:
            continue
        
        status_class = "status-pass" if trend.meets_target else "status-fail"
        trend_class = f"status-{trend.trend}" if trend.trend in ["improving", "declining"] else ""
        trend_icon = "↑" if trend.trend == "improving" else "↓" if trend.trend == "declining" else "→"
        
        html += f"""
        <tr>
            <td>{sanitize(trend.fixture)}</td>
            <td>{trend.latest_accuracy:.2f}%</td>
            <td>{trend.best_accuracy:.2f}%</td>
            <td class="{trend_class}">{trend_icon} {trend.trend}</td>
            <td class="{status_class}">{'✓ GOAL MET' if trend.meets_target else 'Needs Work'}</td>
        </tr>"""
    
    html += """
    </table>
    
    <h2>Fixtures Needing Improvement</h2>
"""
    
    # List fixtures needing work
    needs_work = [t for t in sorted_trends if t.needs_improvement and t.data_points]
    if needs_work:
        html += "<ul>"
        for trend in needs_work[:20]:  # Top 20
            gap = TARGET_ACCURACY - trend.latest_accuracy
            html += f"<li><strong>{sanitize(trend.fixture)}</strong>: {trend.latest_accuracy:.2f}% (gap: {gap:.2f}%)</li>"
        html += "</ul>"
    else:
        html += "<p><em>All fixtures meeting target! 🎉</em></p>"
    
    html += """
</body>
</html>"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    console.print(f"[green]HTML report saved to: {output_path}[/green]")


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """ScoreForge test result visualization tool."""
    pass


@cli.command()
@click.option('--format', '-f', type=click.Choice(['ascii', 'html', 'both']), default='ascii',
              help='Output format')
@click.option('--fixture', '-F', help='Show details for specific fixture')
@click.option('--top', '-t', default=10, type=int, help='Show top N fixtures (default: 10)')
@click.option('--all', 'show_all', is_flag=True, help='Show all fixtures')
@click.option('--output', '-o', type=click.Path(), help='Output file for HTML report')
def visualize(format, fixture, top, show_all, output):
    """Generate test result visualization."""
    trends = build_all_trends()
    summary = calculate_summary(trends)
    
    if fixture:
        # Show specific fixture detail
        if fixture not in trends:
            console.print(f"[red]Fixture '{fixture}' not found[/red]")
            console.print(f"[dim]Run --list-fixtures to see available fixtures[/dim]")
            return
        
        render_fixture_detail(trends[fixture])
        return
    
    # Show summary
    console.print()
    console.print(Panel(
        f"[bold]ScoreForge Test Results[/bold]\n"
        f"Goal: {TARGET_ACCURACY}% accuracy on simple/moderate fixtures\n"
        f"Fixtures with data: {summary.total_fixtures}",
        title="Overview",
        border_style="magenta"
    ))
    console.print()
    
    console.print(render_summary_table(summary))
    console.print()
    
    if summary.total_fixtures == 0:
        console.print("[yellow]No test results found in results/ directory[/yellow]")
        console.print("[dim]Run baseline tests first: python tests/validate_baseline.py[/dim]")
        return
    
    console.print(render_fixture_table(trends, show_all=show_all, top_n=top))
    console.print()
    
    if summary.fixtures_needing_improvement > 0 and summary.total_fixtures <= top:
        console.print(Rule("[yellow]Fixtures Needing Improvement[/yellow]", style="yellow"))
        needs = [t for t in trends.values() if t.needs_improvement and t.data_points]
        for trend in sorted(needs, key=lambda t: t.latest_accuracy):
            gap = TARGET_ACCURACY - trend.latest_accuracy
            console.print(f"  • {trend.fixture}: {trend.latest_accuracy:.2f}% (gap: {gap:.2f}%)")
    
    # Generate HTML if requested
    if format in ['html', 'both']:
        if not output:
            output = RESULTS_DIR / "visualization_report.html"
        render_html_report(trends, summary, Path(output))


@cli.command()
def list_fixtures():
    """List all available fixtures with their status."""
    trends = build_all_trends()
    
    table = Table(title="Available Fixtures", show_header=True, header_style="bold cyan")
    table.add_column("Fixture", style="cyan")
    table.add_column("Data Points", justify="right")
    table.add_column("Latest", justify="right")
    table.add_column("Status")
    
    for fixture, trend in sorted(trends.items()):
        if trend.data_points:
            status = "[green]✓ Data[/green]" if trend.meets_target else "[yellow]✗ Below 95%[/yellow]"
            table.add_row(
                fixture,
                str(len(trend.data_points)),
                f"{trend.latest_accuracy:.2f}%",
                status
            )
        else:
            table.add_row(fixture, "[dim]0[/dim]", "[dim]N/A[/dim]", "[dim]No data[/dim]")
    
    console.print(table)


@cli.command()
def summary():
    """Show quick summary of test results."""
    trends = build_all_trends()
    summary = calculate_summary(trends)
    
    console.print(Panel.fit(
        f"[bold cyan]Test Accuracy Summary[/bold cyan]\n\n"
        f"Total Fixtures: {summary.total_fixtures}\n"
        f"Meeting 95% Goal: [green]{summary.fixtures_meeting_target}[/green]\n"
        f"Needs Improvement: [red]{summary.fixtures_needing_improvement}[/red]\n"
        f"Average Accuracy: {summary.avg_accuracy:.2f}%",
        border_style="cyan"
    ))


if __name__ == "__main__":
    cli()
