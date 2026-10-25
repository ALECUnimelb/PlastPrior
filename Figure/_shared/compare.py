"""Read-only post-commit audit; writes only an ignored JSON comparison report.

Usage: python Figure/_shared/compare.py Fig2
Requires Pillow for decoded-pixel checks. No figure is modified or redrawn.
CSV cells are compared in full, with absolute numeric tolerance 1e-9; empty
values remain distinct from zero. Pixel differences are reported separately.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageChops, ImageStat
from reproduce import ROOT, FIGURES, sha256, write_json


def csv_equal(left, right):
    def read(path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.reader(stream))
    a, b = read(left), read(right)
    if len(a) != len(b) or not a or a[0] != b[0]:
        return {"equal": False, "reason": "row count or columns differ"}
    differences = []
    for row_no, (x, y) in enumerate(zip(a[1:], b[1:]), 2):
        if len(x) != len(y):
            return {"equal": False, "reason": "row width differs"}
        for column, av, bv in zip(a[0], x, y):
            if av == bv:
                continue
            equivalent = False
            if av.strip() and bv.strip():
                try:
                    an, bn = Decimal(av), Decimal(bv)
                    equivalent = an.is_finite() and bn.is_finite() and abs(an - bn) <= Decimal("1e-9")
                except InvalidOperation:
                    pass
            if not equivalent:
                differences.append({"row": row_no, "column": column, "baseline": av, "new": bv})
    return {"equal": not differences, "data_rows": len(a) - 1,
            "different_cells": len(differences), "examples": differences[:10]}


def pixels(left, right):
    with Image.open(left) as a, Image.open(right) as b:
        dimensions = [list(a.size), list(b.size)]
        if a.size != b.size:
            return {"equal": False, "dimensions": dimensions, "reason": "dimensions differ"}
        difference = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))
        extrema = difference.getextrema()
        equal = all(high == 0 for low, high in extrema)
        return {"equal": equal, "dimensions": dimensions,
                "mean_absolute_channel_difference": ImageStat.Stat(difference).mean,
                "maximum_channel_difference": [high for low, high in extrema]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("figure", choices=FIGURES)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    folder = ROOT / args.figure
    output = args.output_dir or folder / "output"
    png = output / f"{args.figure}.png"
    expected = FIGURES[args.figure][3]
    reference = folder / "reference" / "manuscript.png"
    if sha256(reference) != expected:
        raise ValueError("Reference is not the authenticated manuscript image.")
    git = lambda *parts: subprocess.check_output(["git", "-C", str(ROOT.parent), *parts], text=True).strip()
    commit = git("rev-parse", "HEAD")
    changes = git("status", "--porcelain", "--", str(folder), str(ROOT / "_shared"))
    baseline = folder / "reference" / "baseline"
    csv_checks = {}
    for source in sorted(baseline.rglob("*.csv")):
        relative = source.relative_to(baseline)
        target = output / relative
        csv_checks[str(relative)] = csv_equal(source, target) if target.is_file() else {"equal": False, "reason": "missing generated table"}
    png_checks = {}
    for source in sorted(baseline.rglob("*.png")):
        relative = source.relative_to(baseline)
        target = output / relative
        png_checks[str(relative)] = pixels(source, target) if target.is_file() else {"equal": False, "reason": "missing generated image"}
    source_checks = {}
    source_lock = folder / "source_lock.json"
    if source_lock.exists():
        for relative, expected_hash in json.loads(source_lock.read_text(encoding="utf-8"))["original_sha256"].items():
            source_checks[relative] = sha256(folder / relative) == expected_hash
    target_pixels = pixels(reference, png)
    report = {"figure": args.figure, "commit": commit, "uncommitted_figure_code": changes,
              "reference_sha256": expected, "generated_sha256": sha256(png),
              "mode": "original_asset_restoration" if FIGURES[args.figure][1] is None else "R_statistical_regeneration",
              "original_source_unchanged": source_checks, "target_pixels": target_pixels,
              "source_tables": csv_checks, "panel_pixels": png_checks,
              "visual_review": "separate human/agent inspection required; pixel checks do not assess scientific claims"}
    report["strict_pass"] = (not changes and all(source_checks.values()) and target_pixels["equal"]
                             and all(x["equal"] for x in csv_checks.values())
                             and all(x["equal"] for x in png_checks.values()))
    write_json(folder / "audit" / "comparison.json", report)
    print(json.dumps({"figure": args.figure, "commit": commit, "strict_pass": report["strict_pass"],
                      "source_tables": len(csv_checks), "panel_images": len(png_checks),
                      "target_pixels": target_pixels,
                      "table_failures": {k: v for k, v in csv_checks.items() if not v["equal"]}}, indent=2))
    if not report["strict_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
