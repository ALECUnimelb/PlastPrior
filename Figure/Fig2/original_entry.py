"""Portable Figure 4 workflow; the canonical R module owns all scientific logic."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
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
    source = output / "source_data" / "figure"
    destination = output / "export"
    destination.mkdir()
    metrics = {r["dimension_id"]: r for r in read_csv(source / "coverage_metrics.csv")}
    agreement_metrics = {r["dimension_id"]: r for r in read_csv(source / "agreement_metrics.csv")}
    coverage = read_csv(source / "coverage_summary.csv")
    bands = read_csv(source / "agreement_band_summary.csv")
    matrices = read_csv(source / "score_pair_matrix.csv")
    for dim in config["dimensions"]:
        key = dim["dimension_id"]
        population = int(metrics[key]["population_total"])
        shared = int(metrics[key]["shared_count"])
        rows = [r for r in coverage if r["dimension_id"] == key]
        if len(rows) != 4 or sum(int(r["count"]) for r in rows) != population:
            raise ValueError(f"Coverage denominator mismatch: {key}")
        for row in rows:
            row.update(population_total=population, category_order=list(config["coverage_palette"]).index(row["category"]) + 1,
                       color=config["coverage_palette"][row["category"]],
                       label_position="none" if int(row["count"]) == 0 else (
                           "inside" if float(row["fraction"]) >= config["thresholds"]["coverage_label_min_fraction"] else "outside"))
        panel_rows = []
        for kind, table, expected in (("agreement", bands, 4), ("matrix", matrices, 20)):
            selected = [dict(r) for r in table if r["dimension_id"] == key]
            if len(selected) != expected or sum(int(r["count"]) for r in selected) != shared:
                raise ValueError(f"Shared denominator mismatch: {key} {kind}")
            maximum_count = max(int(r["count"]) for r in selected)
            maximum_fraction = max(float(r["fraction_of_shared"]) for r in selected)
            for row in selected:
                if int(row["shared_n"]) != shared:
                    raise ValueError(f"Inconsistent shared_n: {key}")
                fraction = float(row["fraction_of_shared"])
                if abs(fraction - (int(row["count"]) / shared if shared else 0)) > 1e-10:
                    raise ValueError(f"Invalid fraction: {key}")
                row.update(population_total=population, mean_absolute_difference=agreement_metrics[key]["mean_absolute_difference"],
                           proportion_defined=int(shared > 0))
                if kind == "agreement":
                    row.update(category_order=list(config["agreement_palette"]).index(row["agreement_band"]) + 1,
                               color=config["agreement_palette"][row["agreement_band"]],
                               label_eligible=int(fraction >= config["thresholds"]["severity_label_min_fraction"]))
                else:
                    row.update(color_low=config["score_pair_palette"]["low"], color_high=config["score_pair_palette"]["high"],
                               fill_min=0, fill_max=maximum_fraction,
                               label_eligible=int(int(row["count"]) >= max(config["thresholds"]["matrix_label_min_count"],
                                   maximum_count * config["thresholds"]["matrix_label_min_max_fraction"])))
            panel_rows.extend({"row_type": kind, **row} for row in selected)
        # One rectangular CSV per manuscript panel; blank cells mean not applicable.
        columns = list(dict.fromkeys(column for row in panel_rows for column in row))
        write_csv(destination / f"figure4{dim['panel_tag']}_{key}.csv",
                  [{column: row.get(column, "") for column in columns} for row in panel_rows])
    for row in coverage:
        if abs(float(row["fraction"]) - int(row["count"]) / int(row["population_total"])) > 1e-10:
            raise ValueError("Invalid coverage fraction")
    write_csv(destination / "figure4a_coverage.csv", coverage)


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
    parser = argparse.ArgumentParser(description="Build manuscript Figure 4 and copy-ready CSVs")
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
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("workflow") != "figure4_portable":
            raise ValueError("Refusing to replace a nonempty directory not owned by this workflow.")
    rscript = shutil.which("Rscript")
    if not rscript:
        raise ValueError("Rscript is missing. Install R and add Rscript to PATH; see README.md.")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Snapshot: {snapshot}", flush=True)
    with tempfile.TemporaryDirectory(prefix=".figure4-", dir=output.parent) as temporary:
        staged = Path(temporary) / "build"
        subprocess.run([rscript, str(MODULE / "build.R"), "--snapshot", str(snapshot),
                        "--output-dir", str(staged)], check=True, cwd=REPO_ROOT)
        config = json.loads((MODULE / "figure.yml").read_text(encoding="utf-8"))
        export_tables(staged, config)
        # Keep the canonical build's relative manifest paths valid; expose the familiar plural directory too.
        shutil.copytree(staged / "figure", staged / "figures")
        manifest = json.loads((staged / "audit" / "figure_manifest.json").read_text(encoding="utf-8"))
        portable = dict(schema_version=2, workflow="figure4_portable", status="success",
                        csv_layout="one_file_per_panel", csv_row_types={"agreement": "4 severity bands", "matrix": "20 score-pair cells"},
                        generated_at_utc=datetime.now(timezone.utc).isoformat(), snapshot_path=str(snapshot),
                        snapshot=manifest["snapshot"], thresholds=config["thresholds"], export=config["export"],
                        canonical_code=manifest["code"], wrapper_sha256=sha256(Path(__file__)),
                        qa=manifest["qa"], files={str(p.relative_to(staged)): sha256(p)
                        for p in sorted(staged.rglob("*")) if p.is_file()})
        (staged / "export" / "run_manifest.json").write_text(json.dumps(portable, indent=2) + "\n", encoding="utf-8")
        publish(staged, output)
    print(f"Figure 4: {output / 'figures'}\nCopy-ready CSVs: {output / 'export'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"[ERROR] {error}") from error
