"""Resolve source records and aggregate by full, structure-derived InChIKey.

The migration policy preserves historical matching decisions. Route tiers
describe precedence, not measured identification confidence. No desalting,
tautomer normalisation, name matching, QSAR filtering or scoring is performed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import platform
import re
import warnings

import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import inchi

from .inputs import (DEFAULT_CATALOG, SourceRecords, _file_hash, load_catalog,
                     read_source_table, resolve_data_root)


POLICY_VERSION = "identity-migration-v1"
REQUIRED_RDKIT = "2026.3.1"
KEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
CAS_PATTERN = re.compile(r"(?<!\d)([1-9]\d{1,6}-\d{2}-\d)(?!\d)")
REFERENCE_ORDER = ("pubchemlite", "plastchem", "norman_susdat")
REFERENCE_LABELS = {"pubchemlite": "pubchemlite", "plastchem": "plastchem",
                    "norman_susdat": "norman"}
STRUCTURE_FIELDS = ("smiles_standard", "smiles_isomeric", "inchikey", "connectivity_key",
                    "qsar_inchikey", "stereo_status")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest()


def _strict_smiles(text: str) -> bool:
    return bool(text) and "." not in text and "*" not in text


def _standardize(smiles: str) -> dict | None:
    """Canonicalise a molecule while keeping stereochemistry in its identity key."""
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        plain = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False)
        isomeric = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        key = inchi.MolToInchiKey(mol)
        qsar_mol = Chem.MolFromSmiles(plain)
        if qsar_mol is None:
            raise ValueError("RDKit could not parse its own canonical SMILES.")
        qsar_key = inchi.MolToInchiKey(qsar_mol)
        stereo = [str(item.specified).split(".")[-1].lower()
                  for item in Chem.FindPotentialStereo(mol)]
    specified = "specified" in stereo
    unspecified = "unspecified" in stereo
    status = ("not_stereogenic" if not stereo else "partially_specified"
              if specified and unspecified else "specified" if specified else "unspecified")
    return dict(zip(STRUCTURE_FIELDS, (plain, isomeric, key, key.split("-")[0], qsar_key, status)))


def _agreement(reported: str, derived: str) -> str:
    if not KEY_PATTERN.fullmatch(derived):
        return "derived_key_unavailable"
    if not reported:
        return "missing_reported_inchikey"
    if not KEY_PATTERN.fullmatch(reported):
        return "invalid_reported_inchikey"
    if reported == derived:
        return "exact_match"
    return ("same_connectivity_full_inchikey_difference"
            if reported.split("-")[0] == derived.split("-")[0] else "different_connectivity")


def _load_references(data_root: str | Path, catalog_path: Path, catalog: dict):
    """Read declared reference fields, retaining frozen-file row identifiers."""
    tables, manifests, summaries = {}, [], []
    tokens = set(catalog["record_assembly_policy"]["missing_tokens"])
    for source in catalog["sources"]:
        for table in source["tables"]:
            mapping = table.get("identity_reference_mapping")
            if mapping is None:
                continue
            if set(mapping["fields"]) != {"name", "cas", "smiles", "inchikey"}:
                raise ValueError(f"Invalid identity reference mapping: {table['id']}")
            path = resolve_data_root(data_root) / "SourceDatabase" / source["filename"]
            fingerprint = _file_hash(path)
            with warnings.catch_warnings(record=True) as notes:
                warnings.simplefilter("always")
                raw = read_source_table(source["id"], table["id"], data_root=data_root,
                                        catalog_path=catalog_path)
            if fingerprint != _file_hash(path):
                raise ValueError(f"Reference file changed while reading: {source['filename']}")
            required = [c for c in mapping["fields"].values() if c]
            native = mapping.get("native_id_column")
            if native:
                required.append(native)
            if set(required) - set(raw.columns):
                raise ValueError(f"Missing mapped reference columns: {table['id']}")
            frame = pd.DataFrame(index=raw.index)
            for field, column in mapping["fields"].items():
                # Historical reference readers interpret exact NA tokens before trimming.
                values = raw[column].map(str) if column else pd.Series("", index=raw.index)
                frame[field] = values.mask(values.isin(tokens), "").str.strip()
            frame["inchikey"] = frame["inchikey"].str.upper()
            frame["reference_record_number"] = range(1, len(raw) + 1)
            frame["reference_native_id"] = raw[native].map(str) if native else ""
            if mapping.get("require_inchikey"):
                frame = frame.loc[frame["inchikey"].ne("")].copy()
            if frame.empty:
                raise ValueError(f"Reference table has no eligible records: {table['id']}")
            frame["reference_id"] = [hashlib.sha256(_json(
                [source["id"], table["id"], fingerprint, n]).encode("utf-8")).hexdigest()
                for n in frame["reference_record_number"]]
            frame["reference_table"] = table["id"]
            tables[table["id"]] = frame
            manifests.append({"source_id": source["id"], "table_id": table["id"],
                              "filename": source["filename"], "sha256": fingerprint,
                              "sheet": table["sheet"], "header": table["header"], "mapping": mapping})
            summaries.append({"table_id": table["id"], "parsed_records": len(raw),
                              "reference_records": len(frame),
                              "reader_warnings": "; ".join(dict.fromkeys(str(w.message) for w in notes))})
    if set(tables) != set(REFERENCE_ORDER):
        raise ValueError("Declare exactly the PubChemLite, PlastChem and NORMAN reference mappings.")
    return tables, manifests, pd.DataFrame(summaries)


def _lookups(tables: dict, standardize):
    """Retain first reference rows for key lookup and require full-key CAS agreement."""
    keys, candidates, audits = {}, defaultdict(list), []
    for name in REFERENCE_ORDER:
        rows = tables[name].to_dict("records")
        key_index, duplicates = {}, defaultdict(list)
        for row in rows:
            key = row["inchikey"]
            if key:
                if key in key_index:
                    duplicates[key].append(row)
                else:
                    key_index[key] = row
            if name != "pubchemlite" and row["cas"] and _strict_smiles(row["smiles"]):
                structure = standardize(row["smiles"])
                if structure is not None:
                    candidates[row["cas"]].append({**row, "derived_key": structure["inchikey"]})
        keys[name] = key_index
        for key, later in sorted(duplicates.items()):
            first = key_index[key]
            audits.append({"issue": "duplicate_reference_inchikey", "table_id": name,
                           "lookup_value": key, "selected_reference_id": first["reference_id"],
                           "candidates_json": _json([first] + later)})
    unique, ambiguous = {}, {}
    for cas, rows in sorted(candidates.items()):
        derived = sorted({r["derived_key"] for r in rows})
        if len(derived) != 1:
            ambiguous[cas] = derived
            audits.append({"issue": "ambiguous_reference_cas", "table_id": "",
                           "lookup_value": cas, "selected_reference_id": "",
                           "candidates_json": _json(rows)})
        else:
            unique[cas] = min(rows, key=lambda r: (REFERENCE_ORDER.index(r["reference_table"]),
                                                   r["smiles"], r["name"]))
    return keys, unique, ambiguous, pd.DataFrame(audits, columns=[
        "issue", "table_id", "lookup_value", "selected_reference_id", "candidates_json"])


def _resolve_row(row: dict, keys: dict, cas_unique: dict, cas_ambiguous: dict, standardize) -> dict:
    result = {field: "" for field in STRUCTURE_FIELDS}
    result.update(name_resolved="", resolution_route="unresolved", route_tier="E",
                  reported_smiles_status="missing", structure_parse_status="no_selected_structure",
                  identity_key_status="not_generated", aggregation_eligible=False,
                  reported_derived_status="", selected_reference_id="", selected_reference_table="",
                  selected_reference_record_number="", selected_smiles="", attempts_json="[]")
    if not row["included"]:
        result.update(resolution_route="excluded", route_tier="", reported_smiles_status="not_evaluated",
                      structure_parse_status="not_evaluated", identity_key_status="not_evaluated")
        return result
    smiles = str(row["smiles_reported"]).strip()
    key = str(row["inchikey_reported"]).strip().upper()
    cas = str(row["cas_reported"]).strip().lstrip("'")
    name = str(row["name_reported"]).strip()
    attempts = []

    def select(structure, route, tier, selected_name, selected_smiles, reference=None):
        result.update(structure)
        derived = structure["inchikey"]
        valid = bool(KEY_PATTERN.fullmatch(derived))
        result.update(name_resolved=selected_name, resolution_route=route, route_tier=tier,
                      structure_parse_status="parsed", aggregation_eligible=valid,
                      identity_key_status="valid" if valid else "missing" if not derived else "invalid",
                      reported_derived_status=_agreement(key, derived), selected_smiles=selected_smiles)
        if reference is not None:
            result.update(selected_reference_id=reference["reference_id"],
                          selected_reference_table=reference["reference_table"],
                          selected_reference_record_number=reference["reference_record_number"])
        attempts.append({"route": route, "outcome": "selected", "identity_key_status": result["identity_key_status"]})

    structure = None
    if _strict_smiles(smiles):
        structure = standardize(smiles)
        result["reported_smiles_status"] = "parsed" if structure is not None else "invalid"
    elif smiles:
        result["reported_smiles_status"] = "rejected_multicomponent_or_wildcard"
    if structure is not None:
        select(structure, "reported_smile", "A", name, smiles)
    else:
        attempts.append({"route": "reported_smile", "outcome": result["reported_smiles_status"]})
        if KEY_PATTERN.fullmatch(key):
            for reference_table in REFERENCE_ORDER:
                hit = keys[reference_table].get(key)
                route = REFERENCE_LABELS[reference_table] + "_inchikey"
                structure = standardize(hit["smiles"]) if hit and hit["smiles"] else None
                if structure is not None:
                    selected_name = hit["name"] or (name if reference_table == "plastchem" else "")
                    select(structure, route, "B" if reference_table == "pubchemlite" else "C",
                           selected_name, hit["smiles"], hit)
                    break
                attempts.append({"route": route, "outcome": "invalid_or_missing_structure" if hit else "no_hit",
                                 "reference_id": hit["reference_id"] if hit else ""})
        if structure is None and cas:
            if cas in cas_ambiguous:
                attempts.append({"route": "cas", "outcome": "ambiguous_full_keys",
                                 "candidate_keys": cas_ambiguous[cas]})
            hit = cas_unique.get(cas)
            if hit:
                candidate = standardize(hit["smiles"])
                if KEY_PATTERN.fullmatch(key) and candidate["inchikey"] != key:
                    attempts.append({"route": "cas", "outcome": "reported_key_mismatch",
                                     "candidate_key": candidate["inchikey"], "reference_id": hit["reference_id"]})
                else:
                    select(candidate, REFERENCE_LABELS[hit["reference_table"]] + "_cas", "D",
                           hit["name"] or name, hit["smiles"], hit)
            elif cas not in cas_ambiguous:
                attempts.append({"route": "cas", "outcome": "no_hit"})
    result["attempts_json"] = _json(attempts)
    return result


def _valid_cas_values(value: str) -> tuple[str, ...]:
    matches = CAS_PATTERN.findall(value)
    return tuple(dict.fromkeys(cas for cas in matches if sum(
        int(digit) * weight for weight, digit in enumerate(reversed(cas.replace("-", "")[:-1]), 1)
    ) % 10 == int(cas[-1])))


def _cas_audit(records: pd.DataFrame) -> pd.DataFrame:
    mappings = defaultdict(lambda: {"keys": set(), "tables": set(), "count": 0})
    for row in records.to_dict("records"):
        for cas in _valid_cas_values(row["cas_reported"]):
            mapping = mappings[cas]
            mapping["keys"].add(row["inchikey"])
            mapping["tables"].add(row["table_id"])
            mapping["count"] += 1
    rows = []
    for cas, mapping in sorted(mappings.items()):
        keys = sorted(mapping["keys"])
        blocks = sorted({key.split("-")[0] for key in keys})
        status = ("one_to_one" if len(keys) == 1 else "same_connectivity_multiple_full_inchikeys"
                  if len(blocks) == 1 else "multiple_connectivity_conflict")
        rows.append({"cas": cas, "mapping_status": status, "inchikey_count": len(keys),
                     "connectivity_count": len(blocks), "source_record_count": mapping["count"],
                     "inchikeys_json": _json(keys), "connectivity_keys_json": _json(blocks),
                     "source_tables_json": _json(sorted(mapping["tables"]))})
    return pd.DataFrame(rows, columns=["cas", "mapping_status", "inchikey_count", "connectivity_count",
                                      "source_record_count", "inchikeys_json", "connectivity_keys_json",
                                      "source_tables_json"])


def _aggregate(records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = records.loc[records["aggregation_eligible"]]
    rows, memberships = [], []
    for key, group in eligible.groupby("inchikey", sort=True):
        # Stable ties retain catalog table order and then original parsed row order.
        group = group.sort_values("route_tier", kind="stable")
        representative = group.iloc[0]
        rows.append({**{f: representative[f] for f in STRUCTURE_FIELDS},
                     **{f: representative[f] for f in ("name_resolved", "resolution_route", "route_tier",
                                                       "reported_derived_status")},
                     "representative_record_id": representative["record_id"],
                     "cas_reported": representative["cas_reported"].strip().lstrip("'"),
                     "n_records": len(group), "source_tables_json": _json(sorted(set(group["table_id"]))),
                     "reported_derived_statuses_json": _json(sorted(set(group["reported_derived_status"])))})
        for record_id in group["record_id"]:
            memberships.append({"inchikey": key, "record_id": record_id,
                                "is_representative": record_id == representative["record_id"]})
    return (pd.DataFrame(rows, columns=[*STRUCTURE_FIELDS, "name_resolved", "resolution_route", "route_tier",
                                       "reported_derived_status", "representative_record_id", "cas_reported",
                                       "n_records", "source_tables_json", "reported_derived_statuses_json"]),
            pd.DataFrame(memberships, columns=["inchikey", "record_id", "is_representative"]))


@dataclass
class IdentityResult:
    """Record identities, compound inventory, member links and review diagnostics."""

    records: pd.DataFrame
    compounds: pd.DataFrame
    memberships: pd.DataFrame
    cas_audit: pd.DataFrame
    reference_audit: pd.DataFrame
    reference_summary: pd.DataFrame
    summary: pd.DataFrame
    manifest: dict

    def write_reports(self, output_dir: str | Path) -> None:
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in (("resolved_records", self.records), ("compound_inventory", self.compounds),
                            ("compound_memberships", self.memberships), ("cas_mapping_audit", self.cas_audit),
                            ("reference_lookup_audit", self.reference_audit),
                            ("reference_summary", self.reference_summary), ("identity_summary", self.summary)):
            path = folder / (name + ".csv")
            frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            outputs[path.name] = _file_hash(path)
        (folder / "identity_manifest.json").write_text(
            json.dumps({**self.manifest, "output_sha256": outputs}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")


def resolve_identities(source_records: SourceRecords, data_root: str | Path = "data", *,
                       catalog_path: str | Path = DEFAULT_CATALOG) -> IdentityResult:
    """Resolve a fresh source assembly without importing historical runtime code."""
    if version("rdkit") != REQUIRED_RDKIT:
        raise RuntimeError(f"This identity policy requires RDKit {REQUIRED_RDKIT}; install requirements.txt.")
    catalog_path = Path(catalog_path)
    catalog_hash = _file_hash(catalog_path)
    if catalog_hash != source_records.manifest["catalog_sha256"]:
        raise ValueError("Source catalog differs from the assembled-record catalog; rebuild source records.")
    catalog = load_catalog(catalog_path)
    records = source_records.records.copy()
    if records["record_id"].eq("").any() or records["record_id"].duplicated().any():
        raise ValueError("Source record identifiers must be non-empty and unique.")
    if not records["included"].map(lambda v: isinstance(v, bool)).all():
        raise ValueError("Use Boolean inclusion flags from build_source_records(), not CSV text flags.")
    table_order = source_records.mapping.loc[source_records.mapping["scope"].eq("candidate_inventory"), "table_id"]
    order = {name: i for i, name in enumerate(table_order)}
    if set(records["table_id"]) - set(order):
        raise ValueError("Source records contain undeclared candidate tables.")
    records = records.assign(_order=records["table_id"].map(order)).sort_values(
        ["_order", "source_record_number"], kind="stable").drop(columns="_order").reset_index(drop=True)
    tables, reference_inputs, reference_summary = _load_references(data_root, catalog_path, catalog)
    standardize = lru_cache(maxsize=None)(_standardize)
    keys, cas_unique, cas_ambiguous, reference_audit = _lookups(tables, standardize)
    resolved = pd.DataFrame([_resolve_row(row, keys, cas_unique, cas_ambiguous, standardize)
                             for row in records.to_dict("records")])
    resolved = pd.concat([records, resolved], axis=1)
    compounds, memberships = _aggregate(resolved)
    cas_audit = _cas_audit(resolved.loc[resolved["aggregation_eligible"]])
    summary = resolved.groupby(["table_id", "resolution_route", "identity_key_status"], sort=True).agg(
        records=("record_id", "size"), aggregation_eligible=("aggregation_eligible", "sum")).reset_index()
    input_files = {}
    for item in source_records.manifest["input_files"] + reference_inputs:
        previous = input_files.setdefault(item["filename"], item["sha256"])
        if previous != item["sha256"]:
            raise ValueError(f"Inventory and reference fingerprints differ: {item['filename']}")
    for filename, fingerprint in input_files.items():
        if _file_hash(resolve_data_root(data_root) / "SourceDatabase" / filename) != fingerprint:
            raise ValueError(f"Input changed since source assembly or reference reading: {filename}")
    if _file_hash(catalog_path) != catalog_hash:
        raise ValueError("Source catalog changed during identity resolution.")
    manifest = {
        "schema_version": 1, "policy_version": POLICY_VERSION, "catalog_sha256": catalog_hash,
        "implementation_sha256": _file_hash(Path(__file__)),
        "source_records_sha256": _frame_hash(source_records.records),
        "source_assembly_manifest": source_records.manifest, "reference_inputs": reference_inputs,
        "runtime": {"python": platform.python_version(), **{p: version(p) for p in
                    ("rdkit", "pandas", "numpy", "openpyxl", "xlrd")}},
        "policy": {"reference_priority": list(REFERENCE_ORDER), "reference_key_ties": "first frozen-file row",
                   "cas_agreement": "all parseable strict-SMILES reference candidates share one full key",
                   "aggregation_key": "full derived InChIKey",
                   "representative_order": "route tier A-D, catalog table order, parsed row number",
                   "empty_key": "retain selected structure and route, exclude from compound aggregation",
                   "stereo": "retain full identity; non-isomeric QSAR key is a separate annotation",
                   "scope": "No QSAR eligibility screening, prediction merging or scoring"},
        "counts": {"source_records": len(resolved), "included_records": int(resolved["included"].sum()),
                   "aggregation_eligible_records": len(memberships), "unique_compounds": len(compounds),
                   "parsed_without_valid_key": int((resolved["structure_parse_status"].eq("parsed") &
                                                      ~resolved["aggregation_eligible"]).sum()),
                   "cas_lookup_unique": len(cas_unique), "cas_lookup_ambiguous": len(cas_ambiguous)},
    }
    return IdentityResult(resolved, compounds, memberships, cas_audit, reference_audit,
                          reference_summary, summary, manifest)
