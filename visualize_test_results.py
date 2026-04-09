#!/usr/bin/env python3
"""ScoreForge Test Result Visualization Tool.

Generates visual representations of test accuracy trends over time.
Supports both ASCII charts and HTML output.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def get_repo_root() -> Path:
    """Find the repository root directory."""
    current = Path(__file__).absolute()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    return current


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse various timestamp formats."""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y%m%d_%H%M%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    return None


def collect_test_report_results(results_dir: Path) -> List[Dict]:
    """Collect results from test_report.json files (actual format from test_harness.py)."""
    results = []

    # Look for historical test_report.json files
    for report_file in sorted(results_dir.rglob("test_report*.json")):
        try:
            with open(report_file, "r") as f:
                data = json.load(f)

            timestamp = None
            if "timestamp" in data:
                timestamp = parse_timestamp(data["timestamp"])
            else:
                # Use file modification time as fallback
                timestamp = datetime.fromtimestamp(report_file.stat().st_mtime)

            if timestamp is None:
                continue

            # Process each test result
            for item in data.get("results", []):
                overall_score = item.get("scores", {}).get("overall", 0.0)

                results.append({
                    "fixture": item["name"],
                    "timestamp": timestamp,
                    "scores": item.get("scores", {}),
                    "passed": item.get("passed", False),
                    "error": item.get("error"),
                    "report_file": str(report_file.relative_to(results_dir)),
                })
        except (json.JSONDecodeError, KeyError, IOError):
            continue

    return results


def collect_index_results(results_dir: Path) -> List[Dict]:
    """Collect results from index.json file (legacy format)."""
    index_file = results_dir / "index.json"
    if not index_file.exists():
        return []

    try:
        with open(index_file, "r") as f:
            data = json.load(f)

        # Handle both formats: direct list and {runs: [...]}
        runs = data if isinstance(data, list) else data.get("runs", [])

        results = []
        for item in runs:
            if "fixture" not in item:
                continue

            # Handle both best_score and overall score
            overall_score = None
            if "best_score" in item:
                overall_score = item["best_score"]
            elif "overall" in item:
                overall_score = item["overall"]

            if overall_score is None:
                continue

            timestamp = None
            if "timestamp" in item:
                timestamp = parse_timestamp(item["timestamp"])
            elif "run_id" in item:
                timestamp = parse_timestamp(item["run_id"])

            if timestamp is None:
                continue

            # Extract scores
            scores = {"overall": overall_score}
            if "pitch_accuracy" in item:
                scores["pitch_accuracy"] = item["pitch_accuracy"]
            if "rhythm_accuracy" in item:
                scores["rhythm_accuracy"] = item["rhythm_accuracy"]
            if "note_accuracy" in item:
                scores["note_accuracy"] = item["note_accuracy"]

            results.append({
                "fixture": item["fixture"],
                "timestamp": timestamp,
                "scores": scores,
                "run_id": item.get("run_id", ""),
            })

        return results
    except (json.JSONDecodeError, KeyError, IOError):
        return []


def collect_historical_results(results_dir: Path) -> Dict[str, List[Dict]]:
    """Collect all historical test results by fixture."""
    # First try test_report.json files (actual format from test_harness)
    test_report_results = collect_test_report_results(results_dir)

    fixture_data: Dict[str, List[Dict]] = defaultdict(list)
    for result in test_report_results:
        fixture_data[result["fixture"]].append(result)

    # If no test_report results, try legacy index.json
    if not fixture_data:
        index_results = collect_index_results(results_dir)
        for result in index_results:
            fixture_data[result["fixture"]].append(result)

    # If no index results, fall back to scanning directories
    if not fixture_data:
        if not results_dir.exists():
            return fixture_data

        for fixture_dir in results_dir.iterdir():
            if not fixture_dir.is_dir():
                continue

            fixture_name = fixture_dir.name

            for run_dir in fixture_dir.iterdir():
                if not run_dir.is_dir():
                    continue

                report_file = run_dir / "report.json"
                if not report_file.exists():
                    continue

                try:
                    with open(report_file, "r") as f:
                        data = json.load(f)

                    timestamp = None
                    if run_dir.name.startswith("20"):
                        timestamp = parse_timestamp(run_dir.name)
                    elif "timestamp" in data:
                        timestamp = parse_timestamp(data["timestamp"])
                    elif data.get("iterations"):
                        timestamp = parse_timestamp(data["iterations"][0].get("timestamp", ""))

                    if timestamp is None:
                        continue

                    scores = {}
                    if "scores" in data:
                        scores = data["scores"]
                    elif "best_score" in data:
                        scores = {"overall": data["best_score"]}

                    fixture_data[fixture_name].append({
                        "timestamp": timestamp,
                        "run_dir": run_dir,
                        "scores": scores,
                    })
                except (json.JSONDecodeError, KeyError, IOError, IndexError):
                    continue

    return fixture_data


def collect_baseline_report(tests_dir: Path) -> Optional[Dict]:
    """Read the latest baseline report."""
    report_file = tests_dir / "BASELINE_REPORT.json"
    if not report_file.exists():
        return None
    
    try:
        with open(report_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def generate_ascii_chart(values: List[float], labels: List[str], 
                      title: str, width: int = 50, 
                      target: float = 95.0) -> str:
    """Generate ASCII bar chart."""
    max_val = max(max(values), target) if values else 100.0
    lines = [f"\n{BOLD}{title}{RESET}", "─" * 60]
    
    for i, (value, label) in enumerate(zip(values, labels)):
        bar_length = int((value / max_val) * width)
        color = GREEN if value >= target else YELLOW if value >= 70 else RED
        bar = color + "█" * bar_length + RESET + "░" * (width - bar_length)
        label_str = f"{label:20s}"
        target_label = "Target (95%)"
        lines.append(f"{label_str} │{bar} {value:5.1f}%")
    
    target_line = "█" * int((target / max_val) * width)
    target_label_str = f"{target_label:20s}"
    lines.append(f"{target_label_str} │{BLUE}{target_line}{RESET} {target:5.1f}%")
    
    return "\n".join(lines)


def generate_trend_line(values: List[float], labels: List[str],
                     title: str, target: float = 95.0) -> str:
    """Generate ASCII line chart showing trend over time."""
    if not values:
        return f"{BOLD}{title}{RESET}\nNo data available.\n"
    
    lines = [f"\n{BOLD}{title}{RESET}", "─" * 60]
    
    height = 15
    width = 50
    max_val = max(max(values), target)
    min_val = min(values)
    
    norm_values = []
    for v in values:
        if max_val == min_val:
            norm_values.append(height // 2)
        else:
            norm_values.append(int((v - min_val) / (max_val - min_val) * (height - 1)))
    
    for y in range(height - 1, -1, -1):
        row = f"{min_val + y * (max_val - min_val) / (height - 1):5.1f} │"
        for x in range(len(values)):
            if norm_values[x] == y:
                row += "●"
            elif x < len(values) - 1:
                next_y = norm_values[x + 1]
                curr_y = norm_values[x]
                if min(curr_y, next_y) <= y <= max(curr_y, next_y):
                    row += "─"
                else:
                    row += " "
            else:
                row += " "
        
        target_y = int((target - min_val) / (max_val - min_val) * (height - 1)) if max_val != min_val else 0
        if y == target_y:
            row = f"{BOLD}TARG {RESET}{row[6:]}"
        
        lines.append(row)
    
    lines.append("      └" + "─" * width)
    
    if labels:
        time_labels = [datetime.fromisoformat(l.replace('_', 'T')).strftime("%m/%d") 
                     if 'T' in l or '_' in l else l[:10] for l in labels]
        label_line = "       "
        for i, tl in enumerate(time_labels):
            if i % max(1, len(time_labels) // 5) == 0:
                label_line += tl[:5] + " " * (width // max(1, len(time_labels) // 5) - 5)
        lines.append(label_line)
    
    return "\n".join(lines)


def print_summary(baseline: Dict, fixture_data: Dict[str, List[Dict]]):
    """Print summary statistics."""
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}SCOREFORGE TEST ACCURACY DASHBOARD{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    
    if baseline:
        summary = baseline.get("summary", {})
        print(f"\n📊 Latest Baseline Report: {baseline.get('timestamp', 'N/A')}")
        print(f"   Model: {baseline.get('model', 'N/A')}")
        print(f"   Fixtures: {summary.get('total_fixtures', 0)}")
        print(f"   Passed: {GREEN}{summary.get('passed', 0)}{RESET}")
        print(f"   Failed: {RED}{summary.get('failed', 0)}{RESET}")
        print(f"   Errors: {YELLOW}{summary.get('errors', 0)}{RESET}")
        
        avg_overall = summary.get('avg_overall_accuracy', 0.0)
        target_met = summary.get('target_95_percent_met', False)
        color = GREEN if target_met else RED
        print(f"\n   {BOLD}Overall Accuracy:{RESET} {color}{avg_overall:.1f}%{RESET}")
        status = f"{GREEN}✓{RESET}" if target_met else f"{RED}✗{RESET}"
        print(f"   {BOLD}95% Goal Met:{RESET} {status}")
        
        print(f"\n📈 Metric Averages:")
        metrics = [
            ("Note Accuracy", summary.get('avg_note_accuracy', 0.0)),
            ("Pitch Accuracy", summary.get('avg_pitch_accuracy', 0.0)),
            ("Rhythm Accuracy", summary.get('avg_rhythm_accuracy', 0.0)),
            ("Measure Accuracy", summary.get('avg_measure_accuracy', 0.0)),
        ]
        for name, value in metrics:
            color = GREEN if value >= 95 else YELLOW if value >= 70 else RED
            print(f"   {name}: {color}{value:.1f}%{RESET}")
    
    print(f"\n📁 Historical Results Found: {sum(len(v) for v in fixture_data.values())} runs")
    print(f"   Fixtures with history: {len(fixture_data)}")


def print_fixture_ranking(fixture_data: Dict[str, List[Dict]]):
    """Print fixtures ranked by current accuracy."""
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}FIXTURE ACCURACY RANKING{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}\n")
    
    fixture_scores = []
    for fixture_name, runs in fixture_data.items():
        if not runs:
            continue
        
        latest = sorted(runs, key=lambda x: x["timestamp"])[-1]
        scores = latest["scores"]
        overall = scores.get("overall", 0.0)
        
        if overall > 0:
            fixture_scores.append((fixture_name, overall, scores))
    
    fixture_scores.sort(key=lambda x: x[1], reverse=True)
    
    if not fixture_scores:
        print("No fixture data available yet.")
        return
    
    print(f"{'Rank':<6} {'Fixture':<25} {'Accuracy':<10} {'Status':<10}")
    print("─" * 60)
    
    for i, (name, accuracy, scores) in enumerate(fixture_scores, 1):
        color = GREEN if accuracy >= 95 else YELLOW if accuracy >= 70 else RED
        status = "✓ Excellent" if accuracy >= 95 else "~ Good" if accuracy >= 70 else "✗ Needs Work"
        print(f"{i:<6} {name[:25]:<25} {color}{accuracy:.1f}%{RESET:<9} {status:<10}")
    
    print(f"\n{BOLD}⚠️  Fixtures Needing Improvement (Below 95%):{RESET}")
    needs_work = [(n, s) for n, a, s in fixture_scores if a < 95]
    if needs_work:
        for name, scores in needs_work:
            print(f"   • {name}: {scores.get('overall', 0):.1f}%")
            weak_metrics = []
            if scores.get('pitch_accuracy', 0) < 95:
                weak_metrics.append(f"pitch ({scores['pitch_accuracy']:.1f}%)")
            if scores.get('rhythm_accuracy', 0) < 95:
                weak_metrics.append(f"rhythm ({scores['rhythm_accuracy']:.1f}%)")
            if scores.get('measure_accuracy', 0) and scores.get('measure_accuracy', 0) < 95:
                weak_metrics.append(f"measures ({scores['measure_accuracy']:.1f}%)")
            if weak_metrics:
                print(f"     Weak: {', '.join(weak_metrics)}")
    else:
        print(f"   {GREEN}All fixtures meeting 95% target!{RESET}")


def print_trends(fixture_data: Dict[str, List[Dict]], fixture: Optional[str] = None):
    """Print accuracy trends for fixtures."""
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}ACCURACY TRENDS OVER TIME{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    
    fixtures_to_show = [fixture] if fixture else sorted(fixture_data.keys())[:5]
    
    for fixture_name in fixtures_to_show:
        runs = fixture_data.get(fixture_name, [])
        if not runs:
            continue
        
        runs.sort(key=lambda x: x["timestamp"])
        
        values = [r["scores"].get("overall", 0.0) for r in runs if r["scores"].get("overall", 0) > 0]
        labels = [r["timestamp"].strftime("%Y-%m-%d %H:%M") for r in runs if r["scores"].get("overall", 0) > 0]
        
        if not values:
            continue
        
        title = f"{fixture_name} Accuracy Trend ({len(values)} runs)"
        chart = generate_trend_line(values, labels, title)
        print(chart)


def generate_html_report(fixture_data: Dict[str, List[Dict]], 
                     baseline: Optional[Dict], 
                     output_path: Path):
    """Generate HTML report with charts."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ScoreForge Test Results</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                background: #0f172a; color: #e2e8f0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { text-align: center; margin-bottom: 30px; padding: 20px; 
                  background: linear-gradient(135deg, #3b82f6, #8b5cf6); border-radius: 12px; }
        .header h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .header p { opacity: 0.9; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
        .card h2 { margin-bottom: 15px; color: #60a5fa; }
        .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                    gap: 15px; margin-bottom: 20px; }
        .stat-box { background: #334155; padding: 15px; border-radius: 8px; text-align: center; }
        .stat-value { font-size: 2rem; font-weight: bold; color: #34d399; }
        .stat-label { font-size: 0.9rem; opacity: 0.8; margin-top: 5px; }
        .fixture-table { width: 100%; border-collapse: collapse; }
        .fixture-table th, .fixture-table td { padding: 12px; text-align: left; 
                                             border-bottom: 1px solid #334155; }
        .fixture-table th { background: #334155; font-weight: 600; }
        .status-good { color: #34d399; }
        .status-warn { color: #fbbf24; }
        .status-bad { color: #f87171; }
        .progress-bar { height: 20px; background: #334155; border-radius: 10px; 
                      overflow: hidden; margin: 5px 0; }
        .progress-fill { height: 100%; transition: width 0.3s ease; }
        .progress-fill.good { background: linear-gradient(90deg, #34d399, #22c55e); }
        .progress-fill.warn { background: linear-gradient(90deg, #fbbf24, #f59e0b); }
        .progress-fill.bad { background: linear-gradient(90deg, #f87171, #ef4444); }
        .target-line { border-top: 2px dashed #f87171; margin-top: 10px; 
                     padding-top: 5px; font-size: 0.85rem; color: #f87171; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎵 ScoreForge Test Results</h1>
            <p>Accuracy trends and progress toward 95% goal</p>
        </div>
"""
    
    if baseline:
        summary = baseline.get("summary", {})
        avg_overall = summary.get('avg_overall_accuracy', 0.0)
        target_met = summary.get('target_95_percent_met', False)
        status_class = "status-good" if avg_overall >= 95 else "status-bad"
        
        html += f"""
        <div class="card">
            <h2>📊 Latest Baseline Summary</h2>
            <div class="stat-grid">
                <div class="stat-box">
                    <div class="stat-value {status_class}">
                        {avg_overall:.1f}%
                    </div>
                    <div class="stat-label">Overall Accuracy</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value status-good">{summary.get('passed', 0)}</div>
                    <div class="stat-label">Passed Fixtures</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value status-bad">{summary.get('failed', 0)}</div>
                    <div class="stat-label">Failed Fixtures</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value status-warn">{summary.get('total_fixtures', 0)}</div>
                    <div class="stat-label">Total Fixtures</div>
                </div>
            </div>
            <div class="target-line">
                🎯 Target: 95% accuracy - {'✓ Met!' if target_met else '✗ Not yet met'}
            </div>
        </div>
"""
    
    fixture_scores = []
    for fixture_name, runs in fixture_data.items():
        if not runs:
            continue
        latest = sorted(runs, key=lambda x: x["timestamp"])[-1]
        scores = latest["scores"]
        overall = scores.get("overall", 0.0)
        if overall > 0:
            fixture_scores.append((fixture_name, overall, scores))
    
    fixture_scores.sort(key=lambda x: x[1], reverse=True)
    
    html += """
        <div class="card">
            <h2>🏆 Fixture Accuracy Ranking</h2>
            <table class="fixture-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Fixture</th>
                        <th>Overall Accuracy</th>
                        <th>Progress</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
"""
    for i, (name, accuracy, scores) in enumerate(fixture_scores, 1):
        status_class = "good" if accuracy >= 95 else "warn" if accuracy >= 70 else "bad"
        status_text = "✓ Excellent" if accuracy >= 95 else "~ Good" if accuracy >= 70 else "✗ Needs Work"
        html += f"""
                    <tr>
                        <td>{i}</td>
                        <td>{name}</td>
                        <td>{accuracy:.1f}%</td>
                        <td style="width: 30%;">
                            <div class="progress-bar">
                                <div class="progress-fill {status_class}" style="width: {accuracy}%"></div>
                            </div>
                        </td>
                        <td class="status-{status_class}">{status_text}</td>
                    </tr>
"""
    html += """
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>⚠️  Fixtures Needing Improvement</h2>
"""
    needs_work = [(n, s) for n, a, s in fixture_scores if a < 95]
    if needs_work:
        html += '<ul style="list-style: none;">'
        for name, scores in needs_work:
            weak_areas = []
            if scores.get('pitch_accuracy', 0) < 95:
                weak_areas.append(f"pitch ({scores['pitch_accuracy']:.1f}%)")
            if scores.get('rhythm_accuracy', 0) < 95:
                weak_areas.append(f"rhythm ({scores['rhythm_accuracy']:.1f}%)")
            if scores.get('measure_accuracy', 0) and scores.get('measure_accuracy', 0) < 95:
                weak_areas.append(f"measures ({scores['measure_accuracy']:.1f}%)")
            
            html += f'<li style="padding: 10px 0; border-bottom: 1px solid #334155;"><strong>{name}</strong>: {scores.get("overall", 0):.1f}%'
            if weak_areas:
                html += f' <span style="color: #f87171; font-size: 0.9em;">(weak: {", ".join(weak_areas)})</span>'
            html += '</li>'
        html += '</ul>'
    else:
        html += '<p style="color: #34d399;">✓ All fixtures meeting 95% target!</p>'
    
    html += """
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_path, "w") as f:
        f.write(html)
    
    print(f"{GREEN}✓{RESET} HTML report generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Visualize ScoreForge test results and accuracy trends"
    )
    parser.add_argument(
        "--results-dir", "-r",
        type=Path,
        default=get_repo_root() / "results",
        help="Path to results directory (default: repo_root/results)"
    )
    parser.add_argument(
        "--tests-dir", "-t",
        type=Path,
        default=get_repo_root() / "tests",
        help="Path to tests directory (default: repo_root/tests)"
    )
    parser.add_argument(
        "--fixture", "-f",
        help="Show trends for specific fixture only"
    )
    parser.add_argument(
        "--html", "-H",
        action="store_true",
        help="Generate HTML report instead of ASCII output"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=get_repo_root() / "test_results_report.html",
        help="Output path for HTML report"
    )
    parser.add_argument(
        "--no-ascii",
        action="store_true",
        help="Skip ASCII charts (only HTML or summary)"
    )
    
    args = parser.parse_args()
    
    fixture_data = collect_historical_results(args.results_dir)
    baseline = collect_baseline_report(args.tests_dir)
    
    print_summary(baseline, fixture_data)
    
    if fixture_data and not args.no_ascii and not args.html:
        print_fixture_ranking(fixture_data)
    
    if fixture_data and not args.no_ascii and not args.html:
        print_trends(fixture_data, args.fixture)
    
    if args.html:
        generate_html_report(fixture_data, baseline, args.output)


if __name__ == "__main__":
    main()
