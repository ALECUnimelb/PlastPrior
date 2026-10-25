"""Portable Figure 6 workflow; the canonical R module owns all scientific logic."""
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
    """Export precisely the four main-panel tables, preserving the R statistics."""
    source = output / "source_data" / "figure"
    destination = output / "export"
    destination.mkdir()
    facts = json.loads((output / "audit" / "caption_facts.json").read_text(encoding="utf-8"))
    population = int(facts["population_total"])
    strong = int(facts["strong_action_endpoint"]["compound_count"])
    stable = int(facts["stable_high_priority_definition"]["stable_outside_strong_action_count"])
    annotation = facts["analytical_annotation"]
    candidates = int(annotation["stable_no_gic_listing_count"])
    matched = int(annotation["norman_matched_count"])
    tables = {
        "a": read_csv(source / "strong_action_prevalence.csv"),
        "b": read_csv(source / "ranking_capture_markers.csv"),
        "c": read_csv(source / "stable_review_context_totals.csv"),
        "d": read_csv(source / "analytical_annotation_gaps.csv"),
    }
    def check(condition, message):
        if not condition:
            raise ValueError(message)
    def ratio(value, numerator, denominator):
        if denominator == 0:
            check(value in ("", "NA", "NaN", "0"), "Undefined proportion must be explicit")
        else:
            check(math.isfinite(float(value)) and abs(float(value) - numerator / denominator) < 1e-10,
                  "Proportion does not match its denominator")
    check(len(tables["a"]) == 3 and len({r["priority_tier"] for r in tables["a"]}) == 3, "Expected three priority tiers")
    check(sum(int(r["compound_count"]) for r in tables["a"]) == population, "Population mismatch")
    check(sum(int(r["strong_action_count"]) for r in tables["a"]) == strong, "Strong-action count mismatch")
    for row in tables["a"]:
        n, count = int(row["compound_count"]), int(row["strong_action_count"])
        check(n >= count >= 0 and int(row["non_strong_action_count"]) == n-count, "Invalid tier counts")
        ratio(row["proportion"], count, n)
        row.update(color=config["priority_palette"][row["priority_tier"]], ci_method="Wilson 95%", or_ci_method="Wald 95%; reference=Low priority")
        row["display_order"] = ["High priority", "Moderate priority", "Low priority"].index(row["priority_tier"]) + 1
    methods = ["Integrated score", "Exposure only", "Integrated, inventory removed", "Hazard only"]
    check(len(tables["b"]) == 4 and {r["method"] for r in tables["b"]} == set(methods), "Expected four ranking methods")
    metrics = {r["method"]: r for r in read_csv(source / "ranking_capture_metrics.csv")}
    high = next(int(r["compound_count"]) for r in tables["a"] if r["priority_tier"] == "High priority")
    tables["b"].sort(key=lambda r: methods.index(r["method"]))
    for row in tables["b"]:
        ratio(row["screened_fraction"], high, population)
        capture = float(row["captured_fraction"])
        check(math.isfinite(capture) and 0 <= capture <= 1, "Invalid capture fraction")
        check(abs(capture-float(metrics[row["method"]]["capture_at_high_priority_fraction"])) < 1e-10, "Capture marker mismatch")
        row.update({k: v for k,v in metrics[row["method"]].items() if k != "method"})
        row.update(color=config["method_palette"][row["method"]], strong_action_total=strong,
                   interpolation="Linear interpolation between complete tied-score group endpoints")
        row["display_order"] = methods.index(row["method"]) + 1
    check(len(tables["c"]) == 3 and len({r["regulatory_context"] for r in tables["c"]}) == 3, "Expected three regulatory contexts")
    check(sum(int(r["context_total"]) for r in tables["c"]) == stable, "Stable review population mismatch")
    for row in tables["c"]:
        count = int(row["context_total"])
        check(count >= 0, "Negative context count")
        row.update(denominator=stable, proportion=count/stable if stable else "", proportion_defined=int(stable > 0))
        contexts = {"Monitoring/reporting or\nhazard classification": "#39798B",
                    "Inventory/registration/use only": "#8AA9B2", "No linked GIC listing": "#C97928"}
        row.update(color=contexts[row["regulatory_context"]], display_order=list(contexts).index(row["regulatory_context"]) + 1)
        if row["regulatory_context"] == "No linked GIC listing":
            check(count == candidates, "Context-to-annotation flow linkage mismatch")
    for scope, denominator in (("All candidates", candidates), ("Matched subset", matched)):
        rows = [r for r in tables["d"] if r["scope"] == scope]
        check(bool(rows) and sum(int(r["compound_count"]) for r in rows) == denominator, "Annotation flow count mismatch")
        for row in rows:
            check(int(row["denominator"]) == denominator and int(row["compound_count"]) >= 0, "Annotation denominator mismatch")
            ratio(row["proportion"], int(row["compound_count"]), denominator)
            row.update(color=config["analytical_palette"].get(row["display_category"], "#AEB7C2"), proportion_defined=int(denominator > 0))
    check(all(r["scope"] in ("All candidates", "Matched subset") for r in tables["d"]), "Unknown annotation scope")
    matched_row = [r for r in tables["d"] if r["scope"] == "All candidates" and r["display_category"] == "SusDat matched"]
    check(len(matched_row) == 1 and int(matched_row[0]["compound_count"]) == matched, "Matched subset linkage mismatch")
    for panel in config["panels"]:
        rows = tables[panel["panel_tag"]]
        for index, row in enumerate(rows, 1):
            row.update(population_total=population, source_order=index)
        write_csv(destination / f"figure6{panel['panel_tag']}_{panel['panel_id']}.csv", rows)


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
    parser = argparse.ArgumentParser(description="Build manuscript Figure 6 and copy-ready CSVs")
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
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("workflow") != "figure6_portable":
            raise ValueError("Refusing to replace a nonempty directory not owned by this workflow.")
    rscript = shutil.which("Rscript")
    if not rscript:
        raise ValueError("Rscript is missing. Install R and add Rscript to PATH; see README.md.")
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Snapshot: {snapshot}", flush=True)
    with tempfile.TemporaryDirectory(prefix=".figure6-", dir=output.parent) as temporary:
        staged = Path(temporary) / "build"
        subprocess.run([rscript, str(MODULE / "build.R"), "--snapshot", str(snapshot),
                        "--output-dir", str(staged)], check=True, cwd=REPO_ROOT)
        config = json.loads((MODULE / "figure.yml").read_text(encoding="utf-8"))
        export_tables(staged, config)
        # Keep the canonical build's relative manifest paths valid; expose the familiar plural directory too.
        shutil.copytree(staged / "figure", staged / "figures")
        manifest = json.loads((staged / "audit" / "figure_manifest.json").read_text(encoding="utf-8"))
        portable = dict(schema_version=1, workflow="figure6_portable", status="success",
                        csv_layout="one_file_per_panel", csv_panels={p["panel_tag"]: p["panel_id"] for p in config["panels"]},
                        generated_at_utc=datetime.now(timezone.utc).isoformat(), snapshot_path=str(snapshot),
                        snapshot=manifest["snapshot"], thresholds=config["thresholds"], export=config["export"],
                        components=config["components"], strong_action_statuses=config["strong_action_statuses"],
                        canonical_code=manifest["code"], wrapper_sha256=sha256(Path(__file__)),
                        qa=manifest["qa"], files={str(p.relative_to(staged)): sha256(p)
                        for p in sorted(staged.rglob("*")) if p.is_file()})
        (staged / "export" / "run_manifest.json").write_text(json.dumps(portable, indent=2) + "\n", encoding="utf-8")
        publish(staged, output)
    print(f"Figure 6: {output / 'figures'}\nCopy-ready CSVs: {output / 'export'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"[ERROR] {error}") from error
