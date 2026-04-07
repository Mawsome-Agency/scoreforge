#!/usr/bin/env python3
"""Deploy ScoreForge results to the mawsome.agency web server."""
import json
import os
import subprocess
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
VIEWER_DIR = Path(__file__).parent / "viewer"


def build_index():
    """Build index.json from all result directories."""
    runs = []

    for fixture_dir in sorted(RESULTS_DIR.iterdir()):
        if not fixture_dir.is_dir():
            continue
        fixture_name = fixture_dir.name

        for run_dir in sorted(fixture_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                continue

            with open(summary_path) as f:
                summary = json.load(f)

            # Get detailed scores from the last iteration's comparison
            pitch_acc = None
            rhythm_acc = None
            notes_matched = None
            notes_total = None

            # Find latest comparison data
            for i in range(10, 0, -1):
                iter_dir = run_dir / f"iter_{i}"
                comp_path = iter_dir / "comparison.json" if iter_dir.exists() else None
                if comp_path and comp_path.exists():
                    break

            run_entry = {
                "fixture": fixture_name,
                "run_id": run_dir.name,
                "best_score": summary.get("best_score", 0),
                "total_iterations": summary.get("total_iterations", 0),
                "converged": summary.get("converged", False),
                "timestamp": summary.get("timestamp", ""),
                "pitch_accuracy": pitch_acc,
                "rhythm_accuracy": rhythm_acc,
                "notes_matched": notes_matched,
                "notes_total": notes_total,
            }

            # Try to load report.json for richer data
            report_path = run_dir / "report.json"
            if report_path.exists():
                with open(report_path) as f:
                    report = json.load(f)
                iters = report.get("iterations", [])
                if iters:
                    last = iters[-1]
                    scores = last.get("scores", {})
                    run_entry["pitch_accuracy"] = round(scores.get("pitch_accuracy", 0), 1)
                    run_entry["rhythm_accuracy"] = round(scores.get("rhythm_accuracy", 0), 1)
                    run_entry["notes_matched"] = last.get("total_notes_matched", last.get("note_count"))
                    run_entry["notes_total"] = last.get("total_notes_gt", last.get("note_count"))

            runs.append(run_entry)

    index = {"runs": runs, "total": len(runs)}

    index_path = RESULTS_DIR / "index.json"
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)

    print(f"Built index with {len(runs)} runs -> {index_path}")
    return index_path


def deploy():
    """Rsync results + viewer to mawsome.agency server."""
    deploy_key = os.environ.get("DEPLOY_KEY_PATH", "/home/deployer/.ssh/maw_deploy")
    deploy_host = os.environ.get("DEPLOY_HOST", "147.182.245.49")
    deploy_port = os.environ.get("DEPLOY_PORT", "22")
    deploy_user = os.environ.get("DEPLOY_USER", "root")

    ssh_cmd = f"ssh -i {deploy_key} -p {deploy_port}"
    remote = f"{deploy_user}@{deploy_host}"

    # Ensure remote dir exists
    subprocess.run(
        [*ssh_cmd.split(), remote, "mkdir -p /var/www/scoreforge/results"],
        check=True,
    )

    # Sync viewer files
    print("Syncing viewer...")
    subprocess.run(
        [
            "rsync", "-avz", "--delete",
            "-e", ssh_cmd,
            str(VIEWER_DIR) + "/",
            f"{remote}:/var/www/scoreforge/",
        ],
        check=True,
    )

    # Sync results (only HTMLs, PNGs, JSONs — skip large intermediates)
    print("Syncing results...")
    subprocess.run(
        [
            "rsync", "-avz",
            "-e", ssh_cmd,
            "--include=*/",
            "--include=*.html",
            "--include=*.json",
            "--include=*.png",
            "--exclude=*.musicxml",
            "--exclude=*.svg",
            str(RESULTS_DIR) + "/",
            f"{remote}:/var/www/scoreforge/results/",
        ],
        check=True,
    )

    print("Deploy complete!")
    print("View at: https://mawsome.agency/scoreforge/")


if __name__ == "__main__":
    build_index()
    deploy()
