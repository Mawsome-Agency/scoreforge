# Test Result Visualization Tool

A command-line tool for visualizing ScoreForge test accuracy trends and progress toward the 95% accuracy goal.

## Usage

### Basic Usage

```bash
# Show ASCII dashboard with fixture ranking and trends
python3 visualize_test_results.py

# Generate HTML report
python3 visualize_test_results.py --html

# Show trends for a specific fixture
python3 visualize_test_results.py --fixture simple_melody

# Generate HTML report to custom location
python3 visualize_test_results.py --html --output custom_report.html

# Summary only (no charts)
python3 visualize_test_results.py --no-ascii
```

### Command Line Options

- `-r, --results-dir`: Path to results directory (default: `./results`)
- `-t, --tests-dir`: Path to tests directory (default: `./tests`)
- `-f, --fixture`: Show trends for specific fixture only
- `-H, --html`: Generate HTML report instead of ASCII output
- `-o, --output`: Output path for HTML report (default: `./test_results_report.html`)
- `--no-ascii`: Skip ASCII charts (only HTML or summary)

## Output

### ASCII Dashboard

- **Summary Panel**: Latest baseline report with overall accuracy, passed/failed counts, and metric averages
- **Fixture Ranking**: Sorted list of all fixtures with accuracy and status
- **Improvement List**: Fixtures below 95% with specific weak areas identified
- **Trend Charts**: ASCII line charts showing accuracy over time for top 5 fixtures

### HTML Report

- Modern dark-themed dashboard
- Visual progress bars for each fixture
- Color-coded status (green/yellow/red)
- Fixtures needing improvement highlighted with weak metrics

## Data Sources

The tool reads from:

1. `results/index.json`: Historical test runs with best scores (primary source)
2. `tests/BASELINE_REPORT.json`: Latest baseline validation report
3. Individual `results/{fixture}/{timestamp}/report.json` files: Fallback data

## Color Coding

- **Green**: 95%+ accuracy (meets goal)
- **Yellow**: 70-95% accuracy (good)
- **Red**: Below 70% accuracy (needs work)

## Example Output

```
============================================================
SCOREFORGE TEST ACCURACY DASHBOARD
============================================================

📊 Latest Baseline Report: 2026-04-08 19:02:53
   Model: claude-sonnet-4-6
   Fixtures: 1
   Passed: 0
   Failed: 0
   Errors: 1

   Overall Accuracy: 0.0%
   95% Goal Met: ✗

📈 Metric Averages:
   Note Accuracy: 0.0%
   Pitch Accuracy: 0.0%
   Rhythm Accuracy: 0.0%
   Measure Accuracy: 0.0%

📁 Historical Results Found: 3 runs
   Fixtures with history: 3
```
