"""Reproduce the frozen Nature v2 figures, without using current analysis scores.

Preparation (once per figure, from the separately retained research collection):
  python Figure/_shared/reproduce.py prepare Fig1 --source-project PATH
Generation:
  python Figure/Fig1/run_plot.py

Inputs and all generated artifacts are ignored by Git. Statistical modules use
their original R implementation. Fig1 and ExtendedDataFig4 restore authenticated
publication assets; they do not reconstruct a schematic or dashboard from code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUN = "20261006T233429Z"
SNAPSHOT = ROOT / "inputs" / RUN / "analysis_snapshot"
FIGURES = {
    "Fig1": (1, None, None, "736a911691b22b1f5964838b959837d24002102042db1d3ca9931a53365f2c42"),
    "Fig2": (2, "3. PBMT_PlastChem_Concordance", "figures/pbmt_plastchem_concordance.png", "6068cd3df1644201b57a830ec75990c4da34a3a6a676f607d75fd070a9ec415f"),
    "Fig3": (3, "2. Priority_Landscape", "figures/figure_priority_landscape.png", "dc10f493b7f66a207b193522fbe1de6546bb58aec901bf3fbae81220314b9d40"),
    "Fig4": (4, "4. Priority_Sensitivity_Robustness", "figures/priority_sensitivity_and_robustness.png", "73c8d4fdc3c2b57af79f827d4a9fbe2dd48a662421e9cb9a1901d03df69f4624"),
    "Fig5": (5, "5. Policy_Concordance_Review_Gaps", "figures/policy_concordance_and_review_gaps.png", "4a801985cf2c8d9bbb71ece55bb3a7d3fb93b58b0034ed0d51f3f6d9a1f818a4"),
    "ExtendedDataFig1": (6, "1. SourceAssembly_Flow", "figures/figure_composite_assembly_and_overlap.png", "e39c7036a9023b54bce859e766cc8dec84d0c657c2bba1c52585afa43f81da92"),
    "ExtendedDataFig2": (7, "S1. Evidence_Overlap_Patterns", "figures/evidence_overlap_patterns.png", "8954ce41ab4588f45541c1cfe9f9851947d5aa77addc2d180b7a3c547ba96fa2"),
    "ExtendedDataFig3": (8, "4. Priority_Sensitivity_Robustness", "supplementary/positive_input_context.png", "23c6e668a08835fb49727d86a1cf2feb38c78413b9579b006d98c657721e9e68"),
    "ExtendedDataFig4": (9, None, None, "de0290a012c35539cd148415a8c828767613aaade860b7cec1123c70cb00cea4"),
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def freeze_bytes(path, content):
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to replace a different frozen input: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def verify_snapshot():
    manifest_path = SNAPSHOT / "analysis_manifest.json"
    lock = json.loads((SNAPSHOT.parent / "input_lock.json").read_text(encoding="utf-8"))
    for name, expected in lock["sha256"].items():
        if sha256(SNAPSHOT / name) != expected:
            raise ValueError(f"Frozen snapshot checksum mismatch: {name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["analysis_run_id"] != RUN:
        raise ValueError("The figure requires the manuscript's frozen analysis run.")
    for record in manifest["files"].values():
        name = record["path"]
        if name not in ("ChemicalPrio_compounds.csv", "ChemicalPrio_audit.sqlite"):
            raise ValueError("Unexpected snapshot file declaration.")
        if lock["sha256"][name] != record["sha256"]:
            raise ValueError(f"Manifest checksum mismatch: {name}")


def prepare(figure, source):
    """Freeze authentic manuscript media and matching statistical source data."""
    index, module, relative_png, expected = FIGURES[figure]
    destination = ROOT / figure
    manuscript = source / "SCI" / "drafts" / "Manuscript_Nature_v2.docx"
    with zipfile.ZipFile(manuscript) as archive:
        media = archive.read(f"word/media/image{index}.png")
    if hashlib.sha256(media).hexdigest() != expected:
        raise ValueError("Manuscript image does not match the approved reproduction target.")
    freeze_bytes(destination / "reference" / "manuscript.png", media)
    if module is None:
        freeze_bytes(destination / "inputs" / "original.png", media)
    else:
        original_snapshot = source / "Result" / RUN / "07. Prioritization" / "analysis_snapshot"
        manifest = json.loads((original_snapshot / "analysis_manifest.json").read_text(encoding="utf-8"))
        if manifest["analysis_run_id"] != RUN:
            raise ValueError("Unexpected source snapshot run ID.")
        SNAPSHOT.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for name in ("ChemicalPrio_compounds.csv", "ChemicalPrio_audit.sqlite", "analysis_manifest.json"):
            original, copied = original_snapshot / name, SNAPSHOT / name
            expected_hash = sha256(original)
            if not copied.exists():
                shutil.copyfile(original, copied)
            if sha256(copied) != expected_hash:
                raise ValueError(f"Frozen input differs from original: {name}")
            hashes[name] = expected_hash
        lock_path = SNAPSHOT.parent / "input_lock.json"
        lock = {"analysis_run_id": RUN, "sha256": hashes}
        freeze_bytes(lock_path, (json.dumps(lock, indent=2) + "\n").encode("utf-8"))
        verify_snapshot()
        baseline = source / "Result" / RUN / "Figures" / module
        if sha256(baseline / relative_png) != expected:
            raise ValueError("Baseline plot differs from the image embedded in the manuscript.")
        for path in sorted(baseline.rglob("*")):
            if path.is_file() and path.suffix.lower() in (".csv", ".png", ".svg"):
                freeze_bytes(destination / "reference" / "baseline" / path.relative_to(baseline), path.read_bytes())
    write_json(destination / "audit" / "preparation.json", {
        "figure": figure, "run": RUN, "manuscript_sha256": sha256(manuscript),
        "embedded_member": f"word/media/image{index}.png", "image_sha256": expected,
        "mode": "original_asset_restoration" if module is None else "R_statistical_regeneration",
    })
    print(f"Prepared {figure}; original inputs remain unchanged.")


def run(folder):
    figure = folder.name
    _, module, relative_png, expected = FIGURES[figure]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=folder / "output")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be new or empty; use --output-dir for a new reproduction.")
    if module is None:
        original = folder / "inputs" / "original.png"
        if sha256(original) != expected:
            raise ValueError("Original asset checksum mismatch.")
        output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, output / f"{figure}.png")
    else:
        verify_snapshot()
        subprocess.run([sys.executable, str(folder / "original_entry.py"),
                        "--snapshot", str(SNAPSHOT), "--output-dir", str(output)],
                       check=True, cwd=ROOT.parent)
        shutil.copyfile(output / relative_png, output / f"{figure}.png")
    print(f"{figure}: {output / (figure + '.png')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare"])
    parser.add_argument("figure", choices=FIGURES)
    parser.add_argument("--source-project", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.figure, args.source_project.resolve())
