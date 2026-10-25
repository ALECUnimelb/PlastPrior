"""Audit the corrected UpSet geometry and unchanged scientific source tables.

Run after committing with a Python environment providing Pillow:
  python Figure/ExtendedDataFig1/audit_alignment.py
Unlike the shared exact-reproduction comparator, this explicitly expects a
layout change. It measures rendered SVG coordinates, including the composite.
"""
from pathlib import Path
import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
from compare import csv_equal, pixels
from reproduce import sha256, write_json


def geometry(path, source_colors, n_columns, n_rows):
    root = ET.parse(path).getroot()
    ns = {"s": "http://www.w3.org/2000/svg"}
    # svglite writes panel coordinates directly; reject an unhandled transform.
    assert not root.findall(".//s:g[@transform]", ns)
    rectangles = root.findall(".//s:rect", ns)
    fill = lambda e: re.search(r"(?:^|;)\s*fill:\s*(#[0-9A-Fa-f]{6})", e.get("style", ""))
    bars = [e for e in rectangles if fill(e) and fill(e)[1].upper() == "#26394C"]
    dots = root.findall(".//s:circle", ns)
    xs = sorted({float(e.get("cx")) for e in dots})
    ys = sorted({float(e.get("cy")) for e in dots})
    centers = sorted(float(e.get("x")) + float(e.get("width")) / 2 for e in bars)
    assert len(centers) == len(xs) == n_columns
    assert len(ys) == n_rows and len(dots) == n_columns * n_rows
    x_error = max(abs(a - b) for a, b in zip(centers, xs))
    rows = [e for e in rectangles if fill(e) and fill(e)[1].upper() in source_colors
            and float(e.get("x", 0)) < min(xs)
            and float(e.get("y", 0)) > min(ys) - 10]
    row_centers = sorted(float(e.get("y")) + float(e.get("height")) / 2 for e in rows)
    assert len(row_centers) == n_rows
    y_error = max(abs(a - b) for a, b in zip(row_centers, ys))
    return {"columns": n_columns, "rows": n_rows,
            "max_column_error_pt": x_error, "max_row_error_pt": y_error,
            "passed": x_error <= 0.02 and y_error <= 0.02}


def main():
    baseline = HERE / "reference" / "baseline"
    output = HERE / "output"
    config = json.loads((HERE / "figure.yml").read_text(encoding="utf-8"))
    with (output / "source_data/source_database_intersections/database_intersections_displayed.csv").open(encoding="utf-8-sig") as f:
        n_columns = len(list(csv.DictReader(f)))
    with (output / "source_data/source_database_intersections/database_set_sizes.csv").open(encoding="utf-8-sig") as f:
        n_rows = len(list(csv.DictReader(f)))
    colors = set(config["source_palette"].values())
    layouts = {}
    for name in ("figure_upset_overlap", "figure_composite_assembly_and_overlap"):
        rel = Path("figures") / (name + ".svg")
        layouts[name] = {"before": geometry(baseline / rel, colors, n_columns, n_rows),
                         "after": geometry(output / rel, colors, n_columns, n_rows)}
    tables = {str(p.relative_to(baseline)): csv_equal(p, output / p.relative_to(baseline))
              for p in baseline.rglob("*.csv")}
    lock = json.loads((HERE / "source_lock.json").read_text(encoding="utf-8"))
    sources = {p: sha256(HERE / p) == lock.get("layout_revision", {}).get("sha256", {}).get(p, h)
               for p, h in lock["original_sha256"].items()}
    sankey = pixels(baseline / "figures/figure_sankey_flow.png", output / "figures/figure_sankey_flow.png")
    git = lambda *args: subprocess.check_output(["git", "-C", str(HERE.parents[1]), *args], text=True).strip()
    clean = not git("status", "--porcelain", "--", str(HERE), str(HERE.parent / "_shared"))
    passed = (clean and all(sources.values()) and all(x["equal"] for x in tables.values())
              and sankey["equal"] and all(x["after"]["passed"] for x in layouts.values())
              and sha256(output / "ExtendedDataFig1.png") == sha256(output / "figures/figure_composite_assembly_and_overlap.png"))
    report = {"mode": "intentional_layout_correction", "commit": git("rev-parse", "HEAD"),
              "passed": passed, "code_committed": clean, "source_hash_checks": sources,
              "layouts": layouts, "source_tables": tables, "sankey_pixels": sankey,
              "png_sha256": sha256(output / "ExtendedDataFig1.png"),
              "original_pixel_parity_expected": False}
    write_json(HERE / "audit" / "comparison.json", report)
    print(json.dumps({"passed": passed, "tables": len(tables), "layouts": layouts,
                      "sankey_unchanged": sankey["equal"]}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
