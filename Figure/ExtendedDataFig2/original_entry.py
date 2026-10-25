"""Portable Figure S1 workflow; the canonical R module owns all scientific logic."""
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
    """One complete exact-intersection table per panel, with marginal totals."""
    destination = output / "export"
    destination.mkdir()
    facts = json.loads((output / "audit" / "caption_facts.json").read_text(encoding="utf-8"))
    population = int(facts["population_total"])
    if population <= 0:
        raise ValueError("Population must be positive")
    for panel in config["panels"]:
        dimensions = panel["dimensions"]
        source = output / "source_data" / panel["panel_id"]
        rows = read_csv(source / "intersection_summary.csv")
        sets = read_csv(source / "set_summary.csv")
        expected = {format(i, f"0{len(dimensions)}b") for i in range(2 ** len(dimensions))}
        if len(rows) != len(expected) or {r["intersection_mask"] for r in rows} != expected:
            raise ValueError("Exact intersection patterns are incomplete or duplicated")
        if sum(int(r["compound_count"]) for r in rows) != population:
            raise ValueError("Intersection counts do not conserve the population")
        is_hazard = panel["panel_tag"] == "a"
        count_column = "compound_count" if is_hazard else "positive_count"
        set_map = {r["dimension"]: r for r in sets}
        if len(sets) != len(dimensions) or set(set_map) != set(dimensions):
            raise ValueError("Marginal set summary is incomplete")
        for position, dimension in enumerate(dimensions):
            marginal = sum(int(r["compound_count"]) for r in rows if r["intersection_mask"][position] == "1")
            if marginal != int(set_map[dimension][count_column]):
                raise ValueError("Marginal set count mismatch")
        for row in rows:
            mask = row["intersection_mask"]
            count = int(row["compound_count"])
            fraction = float(row["fraction_of_inventory"])
            if count < 0 or not math.isfinite(fraction) or abs(fraction-count/population) > 1e-10:
                raise ValueError("Invalid intersection count or proportion")
            for position, dimension in enumerate(dimensions):
                if row[dimension].lower() not in ("true", "false") or (row[dimension].lower() == "true") != (mask[position] == "1"):
                    raise ValueError("Membership disagrees with intersection mask")
                row[f"set_total_{position+1}"] = set_map[dimension][count_column]
            if not is_hazard:
                displayed = row["displayed_in_figure"].lower() == "true"
                if displayed != ("1" in mask and count > 0):
                    raise ValueError("Exposure display selection mismatch")
            row.update(population_total=population,
                       membership_rule="Non-missing final score, including zero" if is_hazard else "Score > 0; food-contact OR biomonitoring",
                       pattern_id="pattern_" + mask)
        if not is_hazard:
            ranks = sorted(int(r["display_rank"]) for r in rows if r["displayed_in_figure"].lower() == "true")
            if ranks != list(range(1, len(ranks)+1)):
                raise ValueError("Exposure display ranks must be consecutive")
        write_csv(destination / f"figureS1{panel['panel_tag']}_{panel['panel_id']}.csv", rows)


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
    parser = argparse.ArgumentParser(description="Build manuscript Figure S1 and copy-ready CSVs")
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
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("workflow") != "figureS1_portable":
            raise ValueError("Refusing to replace a nonempty directory not owned by this workflow.")
    rscript = shutil.which("Rscript")
    if not rscript:
        raise ValueError("Rscript is missing. Install R and add Rscript to PATH; see README.md.")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Snapshot: {snapshot}", flush=True)
    with tempfile.TemporaryDirectory(prefix=".figureS1-", dir=output.parent) as temporary:
        staged = Path(temporary) / "build"
        subprocess.run([rscript, str(MODULE / "build.R"), "--snapshot", str(snapshot),
                        "--output-dir", str(staged)], check=True, cwd=REPO_ROOT)
        config = json.loads((MODULE / "figure.yml").read_text(encoding="utf-8"))
        export_tables(staged, config)
        # Keep the canonical build's relative manifest paths valid; expose the familiar plural directory too.
        shutil.copytree(staged / "figure", staged / "figures")
        manifest = json.loads((staged / "audit" / "figure_manifest.json").read_text(encoding="utf-8"))
        portable = dict(schema_version=1, workflow="figureS1_portable", status="success",
                        csv_layout="one_file_per_panel", csv_panels={p["panel_tag"]: p["panel_id"] for p in config["panels"]},
                        generated_at_utc=datetime.now(timezone.utc).isoformat(), snapshot_path=str(snapshot),
                        snapshot=manifest["snapshot"], export=config["export"],
                        panel_definitions=config["panels"],
                        canonical_code=manifest["code"], wrapper_sha256=sha256(Path(__file__)),
                        qa=manifest["qa"], files={str(p.relative_to(staged)): sha256(p)
                        for p in sorted(staged.rglob("*")) if p.is_file()})
        (staged / "export" / "run_manifest.json").write_text(json.dumps(portable, indent=2) + "\n", encoding="utf-8")
        publish(staged, output)
    print(f"Figure S1: {output / 'figures'}\nCopy-ready CSVs: {output / 'export'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"[ERROR] {error}") from error
