#!/usr/bin/env python3
"""
Manuscript Figure 2: Source Assembly and Overlap (Sankey + UpSet)
Cross-platform CLI driver for automatic snapshot discovery and figure rendering.

Usage:
    python run_plot.py
    python run_plot.py --snapshot /path/to/snapshot
    python run_plot.py --output-dir /path/to/output
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def find_latest_result_snapshot(repo_root: Path) -> Path:
    results_dir = repo_root / "Result"
    if not results_dir.is_dir():
        raise FileNotFoundError(f"Result directory not found at: {results_dir}")

    candidates = []
    for item in results_dir.iterdir():
        if item.is_dir():
            candidate = item / "07. Prioritization" / "analysis_snapshot"
            compounds_csv = candidate / "ChemicalPrio_compounds.csv"
            audit_sqlite = candidate / "ChemicalPrio_audit.sqlite"
            if compounds_csv.is_file() and audit_sqlite.is_file():
                candidates.append((item.name, candidate))

    if not candidates:
        raise FileNotFoundError(
            f"No valid analysis_snapshot found under {results_dir} containing "
            "ChemicalPrio_compounds.csv and ChemicalPrio_audit.sqlite."
        )

    # Sort lexicographically by folder name (ISO 8601 UTC timestamp format e.g. 20260922T014944Z)
    candidates.sort(key=lambda x: x[0], reverse=True)
    latest_name, latest_snapshot = candidates[0]
    print(f"[*] Discovered latest Result snapshot: {latest_name}")
    return latest_snapshot


def check_r_environment():
    rscript_bin = shutil.which("Rscript")
    if not rscript_bin:
        print("[ERROR] Rscript is not found on PATH.", file=sys.stderr)
        print("Please install R (https://cran.r-project.org/) and ensure Rscript is available.", file=sys.stderr)
        sys.exit(1)
    return rscript_bin


def main():
    parser = argparse.ArgumentParser(description="Render Figure 2: Source Assembly and Overlap (Sankey + UpSet)")
    parser.add_argument("--snapshot", type=str, default=None, help="Path to specific analysis_snapshot directory")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory (defaults to the snapshot run / Figures / module directory)")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    if args.snapshot:
        snapshot_path = Path(args.snapshot).resolve()
        if not snapshot_path.is_dir():
            print(f"[ERROR] Specified snapshot path does not exist: {snapshot_path}", file=sys.stderr)
            sys.exit(1)
    else:
        snapshot_path = find_latest_result_snapshot(repo_root)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else snapshot_path.parent.parent / "Figures" / script_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    rscript_bin = check_r_environment()
    r_script = script_dir / "run_plot.R"

    cmd = [
        rscript_bin,
        str(r_script),
        "--snapshot",
        str(snapshot_path),
        "--output-dir",
        str(output_dir),
    ]

    print(f"[*] Running R rendering pipeline...")
    print(f"    Script:   {r_script}")
    print(f"    Snapshot: {snapshot_path}")
    print(f"    Output:   {output_dir}")

    result = subprocess.run(cmd, cwd=str(script_dir))
    if result.returncode != 0:
        print(f"\n[ERROR] Rscript execution exited with status code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    print(f"\n[DONE] Finished rendering! Check figures in: {output_dir / 'figures'}")
    print(f"Copy-ready CSV files and run record: {output_dir / 'export'}")


if __name__ == "__main__":
    main()
