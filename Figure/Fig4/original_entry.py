"""Portable Figure 5 workflow; the canonical R module owns all scientific logic."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MODULE = SCRIPT_DIR
REQUIRED = ("ChemicalPrio_compounds.csv", "ChemicalPrio_audit.sqlite", "analysis_manifest.json")


def find_latest_result_snapshot(repo_root: Path) -> Path:
    candidates = []
    for run in (repo_root / "Result").iterdir():
        snapshot = run / "07. Prioritization" / "analysis_snapshot"
        if re.fullmatch(r"\d{8}T\d{6}Z", run.name) and all((snapshot / name).is_file() for name in REQUIRED):
            candidates.append(snapshot)
    if not candidates:
        raise ValueError("No complete timestamped analysis snapshot found; use --snapshot.")
    return max(candidates, key=lambda p: p.parent.parent.name)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_tables(output: Path, config: dict) -> None:
    """Keep the R statistics verbatim, adding denominators and plotting metadata."""
    source = output / "source_data" / "figure"
    destination = output / "export"
    destination.mkdir()
    facts = json.loads((output / "audit" / "caption_facts.json").read_text(encoding="utf-8"))
    population = int(facts["population_total"])
    baseline_high = int(facts["baseline_high_count"])
    if not 0 < baseline_high <= population:
        raise ValueError("Invalid baseline population or high-priority denominator")
    metrics = ("rank_spearman", "tier_agreement", "high_priority_retention", "high_priority_jaccard")
    components = {item["component"]: item for item in config["components"]}
    scenarios = {item["scenario_id"]: item for item in config["scenarios"]}
    for tag, table, key, expected in (
        ("a", "leave_one_input_out", "component", components),
        ("b", "scenario_sensitivity", "scenario_id", scenarios),
    ):
        rows = read_csv(source / f"{table}.csv")
        if len(rows) != len(expected) or {row[key] for row in rows} != set(expected):
            raise ValueError(f"Incomplete or duplicate rows: {table}")
        for order, row in enumerate(rows, 1):
            values = {metric: float(row[metric]) for metric in metrics}
            if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values.values()):
                raise ValueError(f"Invalid similarity metric: {table}")
            changed = int(row["changed_tier_count"])
            perturbed_high = int(row["perturbed_high_count"])
            retained = values["high_priority_retention"] * baseline_high
            if not (0 <= changed <= population and 0 <= perturbed_high <= population):
                raise ValueError(f"Invalid counts: {table}")
            if abs(values["tier_agreement"] - (1 - changed / population)) > 1e-10:
                raise ValueError(f"Tier agreement denominator mismatch: {table}")
            if abs(retained - round(retained)) > 1e-7 or not 0 <= round(retained) <= min(baseline_high, perturbed_high):
                raise ValueError(f"High-priority retention denominator mismatch: {table}")
            union = baseline_high + perturbed_high - round(retained)
            if abs(values["high_priority_jaccard"] - round(retained) / union) > 1e-10:
                raise ValueError(f"High-priority Jaccard mismatch: {table}")
            if "retained_high_count" in row and int(row["retained_high_count"]) != round(retained):
                raise ValueError("Retained high-priority count mismatch")
            row.update(population_total=population, baseline_high_count=baseline_high, display_order=order)
            row.update(priority_tier_policy_version=facts["priority_tier_policy_version"],
                       moderate_component_min=facts["component_gates"]["moderate"],
                       high_component_min=facts["component_gates"]["high"])
            if tag == "a":
                spec = components[row[key]]
                row.update(score_column=spec["score_column"], multiplier=spec["multiplier"],
                           low_threshold=config["thresholds"]["low_priority_upper"],
                           high_threshold=config["thresholds"]["high_priority_lower"],
                           rule="Subtract weighted input from its domain and total; fixed total thresholds and domain gates; no rescaling",
                           high_priority_retention_color=config["metric_palette"]["High-priority compounds retained"],
                           rank_spearman_color=config["metric_palette"]["Rank correlation (Spearman rho)"])
            else:
                spec = scenarios[row[key]]
                if any(float(row[field]) != float(spec[field]) for field in ("low_threshold", "high_threshold")):
                    raise ValueError("Scenario threshold mismatch")
        if tag == "b":
            # Match the three metrics and shared colour range in the canonical heatmap.
            plotted_metrics = ("rank_spearman", "tier_agreement", "high_priority_jaccard")
            fill_min = min(float(row[metric]) for row in rows for metric in plotted_metrics)
            for row in rows:
                row.update(fill_min=fill_min, fill_max=1)
                row.update({f"fill_color_{i}": color for i, color in enumerate(config["heatmap_palette"], 1)})
        write_csv(destination / f"figure5{tag}_{table}.csv", rows)


def publish(staged: Path, output: Path) -> None:
    """Replace only a workflow-owned output, restoring it if publication fails."""
    backup = staged.parent / "previous"
    if output.exists():
        output.rename(backup)
    try:
        staged.rename(output)
    except OSError:
        if backup.exists():
            backup.rename(output)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manuscript Figure 5 and copy-ready CSVs")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--output-dir", type=Path, help="Defaults to the snapshot run / Figures / module directory")
    args = parser.parse_args()
    snapshot = (args.snapshot or find_latest_result_snapshot(REPO_ROOT)).resolve()
    output = (args.output_dir or snapshot.parent.parent / "Figures" / SCRIPT_DIR.name).resolve()
    if not all((snapshot / name).is_file() for name in REQUIRED):
        raise ValueError("Snapshot requires compounds CSV, audit SQLite and analysis_manifest.json.")
    if output == snapshot or output in snapshot.parents or snapshot in output.parents:
        raise ValueError("Output must be separate from the input snapshot.")
    marker = output / "export" / "run_manifest.json"
    if output.exists() and any(output.iterdir()):
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("workflow") != "figure5_portable":
            raise ValueError("Refusing to replace a nonempty directory not owned by this workflow.")
    rscript = shutil.which("Rscript")
    if not rscript:
        raise ValueError("Rscript is missing. Install R and add Rscript to PATH; see README.md.")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Snapshot: {snapshot}", flush=True)
    with tempfile.TemporaryDirectory(prefix=".figure5-", dir=output.parent) as temporary:
        staged = Path(temporary) / "build"
        subprocess.run([rscript, str(MODULE / "build.R"), "--snapshot", str(snapshot),
                        "--output-dir", str(staged)], check=True, cwd=REPO_ROOT)
        config = json.loads((MODULE / "figure.yml").read_text(encoding="utf-8"))
        export_tables(staged, config)
        # Keep the canonical build's relative manifest paths valid; expose the familiar plural directory too.
        shutil.copytree(staged / "figure", staged / "figures")
        manifest = json.loads((staged / "audit" / "figure_manifest.json").read_text(encoding="utf-8"))
        portable = dict(schema_version=1, workflow="figure5_portable", status="success",
                        csv_layout="one_file_per_panel", csv_panels={"a": "leave_one_input_out", "b": "scenario_sensitivity"},
                        generated_at_utc=datetime.now(timezone.utc).isoformat(), snapshot_path=str(snapshot),
                        snapshot=manifest["snapshot"], thresholds=config["thresholds"], export=config["export"],
                        components=config["components"], scenarios=config["scenarios"],
                        canonical_code=manifest["code"], wrapper_sha256=sha256(Path(__file__)),
                        qa=manifest["qa"], files={str(p.relative_to(staged)): sha256(p)
                        for p in sorted(staged.rglob("*")) if p.is_file()})
        (staged / "export" / "run_manifest.json").write_text(json.dumps(portable, indent=2) + "\n", encoding="utf-8")
        publish(staged, output)
    print(f"Figure 5: {output / 'figures'}\nCopy-ready CSVs: {output / 'export'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"[ERROR] {error}") from error
