"""Classify final priority records into structure-based chemical families.

This step is intentionally independent from hazard/exposure/priority scoring. It
uses the standardized SMILES already present in the final table, derives a
charge-neutral parent structure for salts, applies explicit structural rules,
and appends one ``category_labels`` column.

The Stage 7 pipeline calls the in-memory interface before writing final outputs.
A standalone CSV interface is also available; it never overwrites the input by
default. Both interfaces produce a row-level audit and compact JSON summary.
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path


RULE_VERSION = "chemical_family_smarts_v2.0.0"
CATEGORY_COLUMN = "category_labels"
CATEGORY_ORDER = ("PBDE", "PBB", "PCB", "PBDF", "PBDD", "PCDF", "PCDD", "OPE", "PFAS")
SMILES_COLUMNS = ("Smile_std", "SMILES", "Smile", "smiles")
AUDIT_FIELDS = (
    "source_row_number",
    "Inchikey_std",
    "CAS",
    "Name_std",
    "original_smiles",
    "parent_smiles",
    "is_salt",
    "parent_changed",
    "counterion_fragments",
    "category_labels",
    "matched_rules",
    "classification_status",
    "warning",
    "rule_version",
)
RULE_DESCRIPTIONS = {
    "PBDE": "Diphenyl ether; C12; one O; at least one Br; no other heavy atoms.",
    "PBB": "Biphenyl; C12; at least one Br; no other heavy atoms.",
    "PCB": "Biphenyl; C12; at least one Cl; no other heavy atoms.",
    "PBDF": "Dibenzofuran core with at least two Br atoms and no Cl or other heavy atoms.",
    "PBDD": "Dibenzo-p-dioxin core with at least two Br atoms and no Cl or other heavy atoms.",
    "PCDF": "Dibenzofuran core with at least two Cl atoms and no Br or other heavy atoms.",
    "PCDD": "Dibenzo-p-dioxin core with at least two Cl atoms and no Br or other heavy atoms.",
    "OPE": "P(V)=O phosphate with at least one P-O-C ester and no direct P-C bond.",
    "PFAS": "OECD 2021 fully fluorinated CF2 or CF3 structural criterion.",
}

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem.MolStandardize import rdMolStandardize

    RDLogger.DisableLog("rdApp.info")
    RDLogger.DisableLog("rdApp.warning")
    RDKIT_AVAILABLE = True
    RDKIT_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - exercised only without RDKit
    Chem = None
    rdMolStandardize = None
    RDKIT_AVAILABLE = False
    RDKIT_IMPORT_ERROR = exc


def require_rdkit():
    """Fail with a cross-platform, actionable message when RDKit is absent."""
    if RDKIT_AVAILABLE:
        return
    raise RuntimeError(
        "Structure-based family classification requires RDKit. Install it in "
        "the Python environment used to run this step (for example, "
        "`python -m pip install rdkit` or `conda install -c conda-forge rdkit`) "
        "on macOS or Windows, then rerun the command. The original priority "
        "CSV remains unchanged. Import error: {0}".format(RDKIT_IMPORT_ERROR)
    )


def _compile_smarts(smarts):
    query = Chem.MolFromSmarts(smarts)
    if query is None:  # pragma: no cover - static rules are tested at import
        raise RuntimeError("Invalid internal SMARTS rule: {0}".format(smarts))
    return query


def _queries():
    require_rdkit()
    if not hasattr(_queries, "cache"):
        _queries.cache = {
            "diphenyl_ether": _compile_smarts("c1ccccc1Oc2ccccc2"),
            "biphenyl": _compile_smarts("c1ccccc1-c2ccccc2"),
            "dibenzo_p_dioxin": _compile_smarts("c1ccc2c(c1)Oc1ccccc1O2"),
            "dibenzofuran": _compile_smarts("c1ccc2c(c1)oc1ccccc12"),
        }
    return _queries.cache


def _safe_field_size_limit():
    """Raise the CSV field limit without overflowing Windows C long values."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:  # pragma: no cover - platform dependent
            limit //= 10


def _canonical_smiles(mol):
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def _fragment_rank(mol):
    has_carbon = any(atom.GetAtomicNum() == 6 for atom in mol.GetAtoms())
    return (1 if has_carbon else 0, mol.GetNumHeavyAtoms(), mol.GetNumAtoms())


def _clean_text(value):
    if value is None:
        return ""
    try:
        if value != value:  # NaN/NaT without importing pandas.
            return ""
    except Exception:
        pass
    return str(value).strip()


def normalize_parent_structure(smiles):
    """Return a charge-neutral parent plus salt/fragment audit information."""
    require_rdkit()
    text = _clean_text(smiles)
    if not text:
        return {
            "status": "missing_smiles",
            "parent_mol": None,
            "classification_mols": [],
            "parent_smiles": "",
            "is_salt": False,
            "parent_changed": False,
            "counterion_fragments": "",
            "warning": "",
        }

    mol = Chem.MolFromSmiles(text)
    if mol is None:
        return {
            "status": "invalid_smiles",
            "parent_mol": None,
            "classification_mols": [],
            "parent_smiles": "",
            "is_salt": False,
            "parent_changed": False,
            "counterion_fragments": "",
            "warning": "RDKit could not parse Smile_std",
        }

    try:
        cleaned = rdMolStandardize.Cleanup(mol)
        fragments = list(Chem.GetMolFrags(cleaned, asMols=True, sanitizeFrags=True))
        parent = rdMolStandardize.ChargeParent(mol)
    except Exception as exc:
        return {
            "status": "normalization_error",
            "parent_mol": None,
            "classification_mols": [],
            "parent_smiles": "",
            "is_salt": False,
            "parent_changed": False,
            "counterion_fragments": "",
            "warning": "{0}: {1}".format(type(exc).__name__, exc),
        }

    if parent is None or parent.GetNumAtoms() == 0:
        return {
            "status": "normalization_error",
            "parent_mol": None,
            "classification_mols": [],
            "parent_smiles": "",
            "is_salt": len(fragments) > 1,
            "parent_changed": False,
            "counterion_fragments": "",
            "warning": "RDKit produced an empty charge parent",
        }

    fragments.sort(key=_fragment_rank, reverse=True)
    fragment_smiles = [_canonical_smiles(fragment) for fragment in fragments]
    counterions = fragment_smiles[1:] if len(fragment_smiles) > 1 else []
    fragment_charges = [
        sum(atom.GetFormalCharge() for atom in fragment.GetAtoms())
        for fragment in fragments
    ]
    is_salt = (
        len(fragments) > 1
        and any(charge > 0 for charge in fragment_charges)
        and any(charge < 0 for charge in fragment_charges)
    )
    organic_fragment_count = sum(
        1 for fragment in fragments
        if any(atom.GetAtomicNum() == 6 for atom in fragment.GetAtoms())
    )
    if organic_fragment_count > 1:
        warning = "multiple_organic_fragments"
    elif len(fragments) > 1 and not is_salt:
        warning = "multicomponent_nonionic"
    else:
        warning = ""
    original_canonical = _canonical_smiles(mol)
    parent_smiles = _canonical_smiles(parent)
    classification_mols = []
    seen_candidate_smiles = set()
    for fragment in fragments:
        if not any(atom.GetAtomicNum() == 6 for atom in fragment.GetAtoms()):
            continue
        try:
            candidate = rdMolStandardize.ChargeParent(fragment)
        except Exception:
            candidate = fragment
        candidate_smiles = _canonical_smiles(candidate)
        if candidate_smiles not in seen_candidate_smiles:
            seen_candidate_smiles.add(candidate_smiles)
            classification_mols.append(candidate)
    if not classification_mols:
        classification_mols = [parent]

    return {
        "status": "ok_with_warning" if warning else "ok",
        "parent_mol": parent,
        "classification_mols": classification_mols,
        "parent_smiles": parent_smiles,
        "is_salt": is_salt,
        "parent_changed": original_canonical != parent_smiles,
        "counterion_fragments": "; ".join(counterions),
        "warning": warning,
    }


def _atomic_numbers(mol):
    return [atom.GetAtomicNum() for atom in mol.GetAtoms()]


def _is_classic_halogenated_family(mol, core_query, halogen_atomic_number, oxygen_count):
    numbers = _atomic_numbers(mol)
    allowed = {6, halogen_atomic_number}
    if oxygen_count:
        allowed.add(8)
    return (
        mol.HasSubstructMatch(core_query)
        and numbers.count(6) == 12
        and numbers.count(8) == oxygen_count
        and numbers.count(halogen_atomic_number) >= 1
        and all(number in allowed for number in numbers)
    )


def _classify_dioxin_or_furan(mol, queries):
    """Return one pure polyhalogenated DD/DF family plus boundary warnings."""
    numbers = _atomic_numbers(mol)
    if numbers.count(6) != 12 or not all(number in {6, 8, 17, 35} for number in numbers):
        return None, None, None

    if numbers.count(8) == 2 and mol.HasSubstructMatch(queries["dibenzo_p_dioxin"]):
        core = "dibenzo-p-dioxin"
        brominated_label = "PBDD"
        chlorinated_label = "PCDD"
    elif numbers.count(8) == 1 and mol.HasSubstructMatch(queries["dibenzofuran"]):
        core = "dibenzofuran"
        brominated_label = "PBDF"
        chlorinated_label = "PCDF"
    else:
        return None, None, None

    chlorine_count = numbers.count(17)
    bromine_count = numbers.count(35)
    if chlorine_count and bromine_count:
        return None, None, "mixed_chlorinated_brominated_{0}".format(core)
    if bromine_count >= 2:
        return (
            brominated_label,
            "{0}:{1}+Br>=2+Cl0+no_other_heavy_atoms".format(brominated_label, core),
            None,
        )
    if chlorine_count >= 2:
        return (
            chlorinated_label,
            "{0}:{1}+Cl>=2+Br0+no_other_heavy_atoms".format(chlorinated_label, core),
            None,
        )
    if chlorine_count + bromine_count == 1:
        return None, None, "monohalogenated_{0}_excluded_from_poly_family".format(core)
    return None, None, None


def _is_organophosphate_ester(mol):
    """Match P(V) phosphate mono/di/triesters, excluding C-P compounds."""
    for phosphorus in (atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 15):
        neighbors = list(phosphorus.GetNeighbors())
        if not neighbors or any(neighbor.GetAtomicNum() != 8 for neighbor in neighbors):
            continue

        has_double_oxygen = False
        ester_oxygen_count = 0
        for oxygen in neighbors:
            bond = mol.GetBondBetweenAtoms(phosphorus.GetIdx(), oxygen.GetIdx())
            if bond.GetBondType() == Chem.BondType.DOUBLE:
                has_double_oxygen = True
                continue
            if any(
                other.GetIdx() != phosphorus.GetIdx() and other.GetAtomicNum() == 6
                for other in oxygen.GetNeighbors()
            ):
                ester_oxygen_count += 1
        if has_double_oxygen and ester_oxygen_count >= 1:
            return True
    return False


def _is_oecd_2021_pfas(mol):
    """Apply the OECD 2021 fully fluorinated methyl/methylene criterion."""
    for carbon in (atom for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6):
        neighbors = list(carbon.GetNeighbors())
        fluorine_count = sum(neighbor.GetAtomicNum() == 9 for neighbor in neighbors)
        prohibited_halogen = any(
            neighbor.GetAtomicNum() in {17, 35, 53} for neighbor in neighbors
        )
        if carbon.GetTotalNumHs() == 0 and fluorine_count >= 2 and not prohibited_halogen:
            return True
    return False


def classify_parent_mol(mol, include_warnings=False):
    """Return ordered category labels and the structural rules that matched."""
    require_rdkit()
    queries = _queries()
    labels = []
    rules = []
    warnings = []

    if _is_classic_halogenated_family(mol, queries["diphenyl_ether"], 35, 1):
        labels.append("PBDE")
        rules.append("PBDE:diphenyl_ether+C12+O1+Br>=1+no_other_heavy_atoms")
    if _is_classic_halogenated_family(mol, queries["biphenyl"], 35, 0):
        labels.append("PBB")
        rules.append("PBB:biphenyl+C12+Br>=1+no_other_heavy_atoms")
    if _is_classic_halogenated_family(mol, queries["biphenyl"], 17, 0):
        labels.append("PCB")
        rules.append("PCB:biphenyl+C12+Cl>=1+no_other_heavy_atoms")
    dioxin_label, dioxin_rule, dioxin_warning = _classify_dioxin_or_furan(mol, queries)
    if dioxin_label:
        labels.append(dioxin_label)
        rules.append(dioxin_rule)
    if dioxin_warning:
        warnings.append(dioxin_warning)
    if _is_organophosphate_ester(mol):
        labels.append("OPE")
        rules.append("OPE:P(V)=O+P-O-C+all_P_neighbors_are_O")
    if _is_oecd_2021_pfas(mol):
        labels.append("PFAS")
        rules.append("PFAS:OECD_2021_fully_fluorinated_CF2_or_CF3")

    ordered = [label for label in CATEGORY_ORDER if label in labels]
    if include_warnings:
        return ordered, rules, warnings
    return ordered, rules


def classify_smiles(smiles):
    """Normalize one SMILES string and attach structure-family results."""
    normalized = normalize_parent_structure(smiles)
    labels = []
    rules = []
    classification_warnings = []
    matched_parent_smiles = []
    for candidate in normalized.get("classification_mols", []):
        candidate_labels, candidate_rules, candidate_warnings = classify_parent_mol(
            candidate, include_warnings=True
        )
        if candidate_labels:
            candidate_smiles = _canonical_smiles(candidate)
            if candidate_smiles not in matched_parent_smiles:
                matched_parent_smiles.append(candidate_smiles)
        for label in candidate_labels:
            if label not in labels:
                labels.append(label)
        for rule in candidate_rules:
            if rule not in rules:
                rules.append(rule)
        for warning in candidate_warnings:
            if warning not in classification_warnings:
                classification_warnings.append(warning)
    labels = [label for label in CATEGORY_ORDER if label in labels]
    if matched_parent_smiles:
        normalized["parent_smiles"] = "; ".join(matched_parent_smiles)
    result = dict(normalized)
    result.pop("parent_mol", None)
    result.pop("classification_mols", None)
    result["category_labels"] = "; ".join(labels)
    result["matched_rules"] = "; ".join(rules)
    existing_warning = result.get("warning", "")
    result["warning"] = "; ".join(
        item for item in [existing_warning, *classification_warnings] if item
    )
    if result["warning"] and result.get("status") == "ok":
        result["status"] = "ok_with_warning"
    result["rule_version"] = RULE_VERSION
    return result


def _first_value(row, candidates):
    for key in candidates:
        value = _clean_text(row.get(key))
        if value:
            return value
    return ""


def _build_summary(
    total_rows,
    categorized_rows,
    category_counts,
    overlap_counts,
    status_counts,
    salt_rows,
    parent_changed_rows,
):
    return {
        "rule_version": RULE_VERSION,
        "total_rows": int(total_rows),
        "categorized_rows": int(categorized_rows),
        "category_counts": {
            label: int(category_counts.get(label, 0)) for label in CATEGORY_ORDER
        },
        "overlap_counts": dict(sorted(overlap_counts.items())),
        "classification_status_counts": dict(sorted(status_counts.items())),
        "salt_rows": int(salt_rows),
        "parent_changed_rows": int(parent_changed_rows),
        "rules": dict(RULE_DESCRIPTIONS),
    }


def _audit_row(source_row_number, identity, smiles, result):
    return {
        "source_row_number": source_row_number,
        "Inchikey_std": _first_value(identity, ("Inchikey_std", "Inchikey", "InChIKey")),
        "CAS": _first_value(identity, ("CAS", "cas")),
        "Name_std": _first_value(identity, ("Name_std", "Name", "name")),
        "original_smiles": _clean_text(smiles),
        "parent_smiles": result["parent_smiles"],
        "is_salt": result["is_salt"],
        "parent_changed": result["parent_changed"],
        "counterion_fragments": result["counterion_fragments"],
        "category_labels": result["category_labels"],
        "matched_rules": result["matched_rules"],
        "classification_status": result["status"],
        "warning": result["warning"],
        "rule_version": result["rule_version"],
    }


def classify_priority_dataframe(dataframe, copy=True, show_progress=False):
    """Append category_labels to an in-memory final priority DataFrame.

    The function intentionally uses only a small DataFrame surface so the
    classification module does not need to import pandas itself.
    """
    require_rdkit()
    if not hasattr(dataframe, "columns") or not hasattr(dataframe, "copy"):
        raise TypeError("dataframe must be a pandas-compatible DataFrame.")
    smiles_column = next((key for key in SMILES_COLUMNS if key in dataframe.columns), None)
    if smiles_column is None:
        raise KeyError(
            "Input DataFrame needs one SMILES column from: {0}".format(
                ", ".join(SMILES_COLUMNS)
            )
        )

    output = dataframe.copy() if copy else dataframe
    total_rows = len(output)
    identity_columns = [
        key for key in ("Inchikey_std", "Inchikey", "InChIKey", "CAS", "cas", "Name_std", "Name", "name")
        if key in output.columns
    ]
    identity_values = {key: output[key].tolist() for key in identity_columns}
    smiles_values = output[smiles_column].tolist()

    category_values = []
    audit_rows = []
    category_counts = Counter()
    overlap_counts = Counter()
    status_counts = Counter()
    categorized_rows = 0
    salt_rows = 0
    parent_changed_rows = 0

    for position, smiles in enumerate(smiles_values):
        result = classify_smiles(smiles)
        category_values.append(result["category_labels"])
        labels = [
            label.strip()
            for label in result["category_labels"].split(";")
            if label.strip()
        ]
        for label in labels:
            category_counts[label] += 1
        categorized_rows += int(bool(labels))
        if len(labels) > 1:
            overlap_counts[" + ".join(labels)] += 1
        status_counts[result["status"]] += 1
        salt_rows += int(bool(result["is_salt"]))
        parent_changed_rows += int(bool(result["parent_changed"]))

        identity = {
            key: values[position] for key, values in identity_values.items()
        }
        audit_rows.append(_audit_row(position + 2, identity, smiles, result))
        if show_progress and (position + 1) % 1000 == 0:
            print("Classified {0:,} rows...".format(position + 1), file=sys.stderr)

    output[CATEGORY_COLUMN] = category_values
    summary = _build_summary(
        total_rows,
        categorized_rows,
        category_counts,
        overlap_counts,
        status_counts,
        salt_rows,
        parent_changed_rows,
    )
    return {
        "agg_table": output,
        "audit_rows": audit_rows,
        "summary": summary,
    }


def write_classification_artifacts(audit_rows, summary, audit_path, summary_path):
    """Atomically write the row-level audit CSV and compact JSON summary."""
    audit_path = Path(audit_path).expanduser()
    summary_path = Path(summary_path).expanduser()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    audit_tmp = _temp_path(audit_path)
    summary_tmp = _temp_path(summary_path)
    try:
        with audit_tmp.open("w", encoding="utf-8", newline="") as audit_file:
            writer = csv.DictWriter(audit_file, fieldnames=AUDIT_FIELDS)
            writer.writeheader()
            writer.writerows(audit_rows)
        with summary_tmp.open("w", encoding="utf-8") as summary_file:
            json.dump(summary, summary_file, ensure_ascii=False, indent=2, sort_keys=True)
            summary_file.write("\n")
        os.replace(str(audit_tmp), str(audit_path))
        os.replace(str(summary_tmp), str(summary_path))
    except Exception:
        for temporary_path in (audit_tmp, summary_tmp):
            if temporary_path.exists():
                temporary_path.unlink()
        raise
    return {
        "chemical_family_classification_audit_csv": audit_path,
        "chemical_family_classification_summary_json": summary_path,
    }


def _derive_output_paths(input_path, output_path=None, audit_path=None, summary_path=None):
    stem = input_path.stem
    output = output_path or input_path.with_name(stem + "_categorized.csv")
    audit = audit_path or input_path.with_name(stem + "_category_audit.csv")
    summary = summary_path or input_path.with_name(stem + "_category_summary.json")
    return Path(output), Path(audit), Path(summary)


def _temp_path(path):
    return path.with_name(path.name + ".tmp")


def classify_priority_csv(input_path, output_path=None, audit_path=None, summary_path=None):
    """Stream a final priority CSV and append structure-based family labels."""
    require_rdkit()
    _safe_field_size_limit()
    input_path = Path(input_path).expanduser()
    output_path, audit_path, summary_path = _derive_output_paths(
        input_path,
        Path(output_path).expanduser() if output_path else None,
        Path(audit_path).expanduser() if audit_path else None,
        Path(summary_path).expanduser() if summary_path else None,
    )
    if not input_path.is_file():
        raise FileNotFoundError("Input CSV does not exist: {0}".format(input_path))
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Output must be different from the original input CSV.")

    for path in (output_path, audit_path, summary_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    output_tmp = _temp_path(output_path)
    audit_tmp = _temp_path(audit_path)
    summary_tmp = _temp_path(summary_path)
    temporary_paths = (output_tmp, audit_tmp, summary_tmp)

    category_counts = Counter()
    overlap_counts = Counter()
    status_counts = Counter()
    total_rows = 0
    salt_rows = 0
    parent_changed_rows = 0
    categorized_rows = 0

    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise ValueError("Input CSV has no header row.")
            smiles_column = next((key for key in SMILES_COLUMNS if key in reader.fieldnames), None)
            if smiles_column is None:
                raise KeyError(
                    "Input CSV needs one SMILES column from: {0}".format(
                        ", ".join(SMILES_COLUMNS)
                    )
                )

            output_fields = list(reader.fieldnames)
            if CATEGORY_COLUMN not in output_fields:
                output_fields.append(CATEGORY_COLUMN)

            with output_tmp.open("w", encoding="utf-8", newline="") as destination, audit_tmp.open(
                "w", encoding="utf-8", newline=""
            ) as audit_file:
                writer = csv.DictWriter(destination, fieldnames=output_fields, extrasaction="ignore")
                audit_writer = csv.DictWriter(audit_file, fieldnames=AUDIT_FIELDS)
                writer.writeheader()
                audit_writer.writeheader()

                for source_row_number, row in enumerate(reader, start=2):
                    total_rows += 1
                    result = classify_smiles(row.get(smiles_column, ""))
                    row[CATEGORY_COLUMN] = result["category_labels"]
                    writer.writerow(row)

                    labels = [label.strip() for label in result["category_labels"].split(";") if label.strip()]
                    for label in labels:
                        category_counts[label] += 1
                    categorized_rows += int(bool(labels))
                    if len(labels) > 1:
                        overlap_counts[" + ".join(labels)] += 1
                    status_counts[result["status"]] += 1
                    salt_rows += int(bool(result["is_salt"]))
                    parent_changed_rows += int(bool(result["parent_changed"]))

                    audit_writer.writerow(
                        _audit_row(source_row_number, row, row.get(smiles_column, ""), result)
                    )

                    if total_rows % 1000 == 0:
                        print("Classified {0:,} rows...".format(total_rows), file=sys.stderr)

        summary_payload = _build_summary(
            total_rows,
            categorized_rows,
            category_counts,
            overlap_counts,
            status_counts,
            salt_rows,
            parent_changed_rows,
        )
        summary_payload.update({
            "input_csv": str(input_path),
            "output_csv": str(output_path),
            "audit_csv": str(audit_path),
        })
        with summary_tmp.open("w", encoding="utf-8") as summary_file:
            json.dump(summary_payload, summary_file, ensure_ascii=False, indent=2, sort_keys=True)
            summary_file.write("\n")

        os.replace(str(output_tmp), str(output_path))
        os.replace(str(audit_tmp), str(audit_path))
        os.replace(str(summary_tmp), str(summary_path))
        return {
            "output_csv": output_path,
            "audit_csv": audit_path,
            "summary_json": summary_path,
            "summary": summary_payload,
        }
    except Exception:
        for temporary_path in temporary_paths:
            if temporary_path.exists():
                temporary_path.unlink()
        raise


def build_parser():
    parser = argparse.ArgumentParser(
        description="Append structure-based PBDE/PBB/PCB/PBDF/PBDD/PCDF/PCDD/OPE/PFAS labels to a final priority CSV."
    )
    parser.add_argument("input_csv", type=Path, help="Existing final compound_priority_table.csv")
    parser.add_argument("--output", type=Path, help="Categorized CSV path (defaults beside the input)")
    parser.add_argument("--audit", type=Path, help="Row-level audit CSV path")
    parser.add_argument("--summary", type=Path, help="JSON summary path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    result = classify_priority_csv(
        args.input_csv,
        output_path=args.output,
        audit_path=args.audit,
        summary_path=args.summary,
    )
    print("Categorized CSV: {0}".format(result["output_csv"]))
    print("Audit CSV: {0}".format(result["audit_csv"]))
    print("Summary JSON: {0}".format(result["summary_json"]))
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
