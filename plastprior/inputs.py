"""Read source-native tables and describe a local input collection.

Row counts describe parsed records, not unique chemicals. No chemical
identifiers are standardised and no evidence or priority scores are computed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterator
import warnings
import platform
from importlib.metadata import version

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = Path(__file__).with_name("sources.json")
CSV_CHUNK_SIZE = 50_000
REPORTED_FIELDS = ("name_reported", "cas_reported", "smiles_reported", "inchikey_reported")


@dataclass
class InputInspection:
    """File metadata, table dimensions, and supplementary presence checks."""

    sources: pd.DataFrame
    tables: pd.DataFrame
    supporting: pd.DataFrame

    @property
    def sources_passed(self) -> bool:
        """Whether the declared source files and tables pass Stage 1 checks."""
        return all(frame["status"].eq("OK").all() for frame in
                   (self.sources, self.tables))

    @property
    def supporting_present(self) -> bool:
        """Whether all declared auxiliary items are present, without content validation."""
        return bool(self.supporting["status"].eq("OK").all())

    @property
    def passed(self) -> bool:
        """Whether source checks and auxiliary presence checks both pass."""
        return self.sources_passed and self.supporting_present

    def require_sources(self) -> None:
        """Stop Stage 1 when a declared source file or table fails inspection."""
        if not self.sources_passed:
            raise ValueError("Source inspection failed. Review the source and table reports.")

    def require_complete(self) -> None:
        """Require source checks and all auxiliary presence checks to pass.

        This does not certify auxiliary contents or readiness for scoring.
        """
        if not self.passed:
            raise ValueError("Input inspection failed. Review the status and detail columns.")

    def write_reports(self, output_dir: str | Path) -> None:
        """Save full inspection tables, including provenance and observed hashes."""
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        for filename, frame in (("source_inventory.csv", self.sources),
                                ("table_dimensions.csv", self.tables),
                                ("supporting_inputs.csv", self.supporting)):
            frame.to_csv(folder / filename, index=False, encoding="utf-8", lineterminator="\n")


def resolve_data_root(data_root: str | Path = "data") -> Path:
    """Resolve relative input paths from the project root, not the notebook cwd."""
    path = Path(data_root).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_catalog(path: str | Path = DEFAULT_CATALOG) -> dict:
    """Load explicit file, worksheet, header, and provenance declarations."""
    with Path(path).open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    if catalog.get("schema_version") != 1 or not catalog.get("sources"):
        raise ValueError("Expected a non-empty source catalog with schema_version 1.")
    source_ids: set[str] = set()
    table_ids: set[str] = set()
    for source in catalog["sources"]:
        if source["id"] in source_ids:
            raise ValueError("Source identifiers must be unique.")
        source_ids.add(source["id"])
        filename = source["filename"]
        if not filename or any(c in filename for c in ("/", "\\")):
            raise ValueError("Source filenames must be local basenames.")
        if not source.get("tables"):
            raise ValueError("Every source must declare at least one table.")
        for table in source["tables"]:
            if table["id"] in table_ids:
                raise ValueError("Table identifiers must be globally unique.")
            table_ids.add(table["id"])
            if not isinstance(table["header"], int) or table["header"] < 0:
                raise ValueError("Header offsets must be non-negative integers.")
            if not table.get("required_columns"):
                raise ValueError("Each table must declare required column labels.")
    return catalog


def _read_options(path: Path, table: dict) -> dict:
    options = {"header": table["header"], "keep_default_na": False, "dtype": object}
    if path.suffix.lower() == ".csv":
        return {**options, "encoding": "utf-8-sig"}
    engines = {".xlsx": "openpyxl", ".xls": "xlrd"}
    if path.suffix.lower() not in engines:
        raise ValueError("Supported source formats are CSV, XLSX, and XLS.")
    return {**options, "engine": engines[path.suffix.lower()],
            "sheet_name": table["sheet"]}


def _validate_columns(frame: pd.DataFrame, table: dict) -> None:
    missing = set(table["required_columns"]) - set(frame.columns)
    if missing:
        raise ValueError("Missing required column labels: " + ", ".join(sorted(missing)))


def _read_table(path: Path, table: dict, nrows: int | None = None) -> pd.DataFrame:
    options = _read_options(path, table)
    reader = pd.read_csv if path.suffix.lower() == ".csv" else pd.read_excel
    frame = reader(path, nrows=nrows, **options)
    _validate_columns(frame, table)
    return frame


def read_source_table(
    source_id: str,
    table_id: str | None = None,
    *,
    data_root: str | Path = "data",
    catalog_path: str | Path = DEFAULT_CATALOG,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Read one declared table without harmonising identifiers or changing values.

    A table ID is required for multi-table workbooks. Source labels such as
    'NA' remain literal strings. CSV fields are read as strings; Excel cell
    types are retained. Empty cells are represented by empty strings.
    """
    if nrows is not None and (not isinstance(nrows, int) or nrows < 0):
        raise ValueError("nrows must be a non-negative integer or None.")
    sources = {s["id"]: s for s in load_catalog(catalog_path)["sources"]}
    if source_id not in sources:
        raise KeyError(f"Unknown source identifier: {source_id}")
    source = sources[source_id]
    tables = {t["id"]: t for t in source["tables"]}
    if table_id is None:
        if len(tables) != 1:
            raise ValueError("Specify table_id for a source with multiple tables.")
        table_id = next(iter(tables))
    if table_id not in tables:
        raise KeyError(f"Unknown table identifier for {source_id}: {table_id}")
    path = resolve_data_root(data_root) / "SourceDatabase" / source["filename"]
    return _read_table(path, tables[table_id], nrows)


def _chunks(path: Path, table: dict) -> Iterator[pd.DataFrame]:
    if path.suffix.lower() == ".csv":
        with pd.read_csv(path, chunksize=CSV_CHUNK_SIZE,
                         **_read_options(path, table)) as reader:
            for frame in reader:
                _validate_columns(frame, table)
                yield frame
    else:
        yield _read_table(path, table)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_supporting_inputs(root: Path, catalog: dict) -> pd.DataFrame:
    """Check supporting file presence; do not parse or validate their evidence."""
    records = []
    for group in catalog.get("supporting_inputs", []):
        folder = root / group["folder"]
        missing = [item for item in group["required_files"] if not (folder / item).is_file()]
        missing += [item for item in group.get("required_directories", [])
                    if not (folder / item).is_dir()]
        files = [p for p in folder.rglob("*") if p.is_file() and p.name != ".DS_Store"]
        records.append({"input_group": group["label"], "folder": group["folder"],
                        "available_files": len(files),
                        "size_mb": round(sum(p.stat().st_size for p in files) / 1_000_000, 3),
                        "status": "OK" if folder.is_dir() and not missing else "MISSING",
                        "detail": "; ".join(missing) if folder.is_dir() else "Directory not found",
                        "check_scope": "Required item presence only"})
    return pd.DataFrame(records, columns=["input_group", "folder", "available_files",
                        "size_mb", "status", "detail", "check_scope"])


def inspect_inputs(
    data_root: str | Path = "data", *, catalog_path: str | Path = DEFAULT_CATALOG,
) -> InputInspection:
    """Inspect every catalogued source and preserve per-file/table failures.

    File SHA-256 values identify the observed bytes; they are not compared with
    an externally certified reference. Versions and dates are catalog metadata,
    not inferred from filesystem timestamps. Only declared worksheets are read.
    """
    root = resolve_data_root(data_root)
    catalog = load_catalog(catalog_path)
    sources, tables = [], []
    for source in catalog["sources"]:
        path = root / "SourceDatabase" / source["filename"]
        record = {"source_id": source["id"], "source": source["label"],
                  "role": source["role"], "filename": source["filename"],
                  "version": source["version"] or "Not recorded",
                  "snapshot_date": source["snapshot_date"] or "Not recorded",
                  "provenance_note": source["notes"], "reference": source["reference"],
                  "size_mb": None, "sha256": None, "status": "OK", "detail": ""}
        before = None
        try:
            before = path.stat()
            record["size_mb"] = round(before.st_size / 1_000_000, 3)
            record["sha256"] = _file_hash(path)
        except (OSError, ValueError) as exc:
            record.update(status="MISSING" if not path.exists() else "ERROR",
                          detail=f"Unable to read source file ({type(exc).__name__}).")
        source_tables = []
        for table in source["tables"]:
            result = {"source_id": source["id"], "table_id": table["id"],
                      "table_role": table["role"],
                      "sheet": str(table["sheet"]) if table["sheet"] is not None else "Not applicable",
                      "header_row": table["header"] + 1,
                      "parsed_rows": None, "nonempty_rows": None, "columns": None,
                      "reader_warnings": "",
                      "status": record["status"], "detail": record["detail"]}
            if record["status"] == "OK":
                try:
                    rows, nonempty, columns = 0, 0, 0
                    with warnings.catch_warnings(record=True) as reader_warnings:
                        warnings.simplefilter("always")
                        for frame in _chunks(path, table):
                            rows += len(frame)
                            columns = len(frame.columns)
                            blank = frame.replace(r"^\s*$", pd.NA, regex=True).isna().all(axis=1)
                            nonempty += int((~blank).sum())
                    result["reader_warnings"] = "; ".join(dict.fromkeys(
                        str(warning.message) for warning in reader_warnings))
                    if not nonempty:
                        raise ValueError("The selected table contains no non-empty records.")
                    result.update(parsed_rows=rows, nonempty_rows=nonempty, columns=columns)
                except Exception as exc:
                    # A failed source must not conceal the status of other inputs.
                    result.update(status="ERROR", detail=f"{type(exc).__name__}: {exc}")
            source_tables.append(result)
        if before is not None and record["status"] == "OK":
            try:
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("Source file changed during inspection.")
                if any(t["status"] != "OK" for t in source_tables):
                    record.update(status="ERROR", detail="One or more declared tables failed inspection.")
            except (OSError, ValueError) as exc:
                record.update(status="ERROR", detail=str(exc))
                for result in source_tables:
                    result.update(status="ERROR", detail="Source changed during inspection; rerun the check.")
        sources.append(record)
        tables.extend(source_tables)
    table_frame = pd.DataFrame(tables)
    for column in ("parsed_rows", "nonempty_rows", "columns"):
        table_frame[column] = table_frame[column].astype("Int64")
    return InputInspection(pd.DataFrame(sources), table_frame,
                           inspect_supporting_inputs(root, catalog))


@dataclass
class SourceRecords:
    """Source inventory records before chemical identity resolution or deduplication."""

    records: pd.DataFrame
    summary: pd.DataFrame
    mapping: pd.DataFrame
    manifest: dict

    def write_reports(self, output_dir: str | Path) -> None:
        """Save all rows, including exclusions, with mappings and input fingerprints."""
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        outputs = {}
        for name, frame in (("source_records.csv", self.records),
                            ("source_record_summary.csv", self.summary),
                            ("source_field_mapping.csv", self.mapping)):
            path = folder / name
            frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            outputs[name] = _file_hash(path)
        manifest = {**self.manifest, "output_sha256": outputs}
        (folder / "source_record_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _record_mapping(table: dict) -> dict:
    """Validate explicit candidate scope and mappings; never guess field names."""
    mapping = table.get("record_mapping", {})
    scope = mapping.get("scope")
    if scope not in {"candidate_inventory", "identity_reference", "literature_links"}:
        raise ValueError(f"Missing or invalid record scope for table {table['id']}.")
    if scope != "candidate_inventory":
        return mapping
    fields = mapping.get("fields", {})
    if set(fields) != set(REPORTED_FIELDS):
        raise ValueError(f"Declare all four reported fields for table {table['id']}.")
    if not any(fields.values()):
        raise ValueError(f"At least one reported field must be mapped for table {table['id']}.")
    for columns in fields.values():
        if not isinstance(columns, list) or any(not isinstance(c, str) or not c for c in columns):
            raise ValueError(f"Field mappings must be lists of source labels: {table['id']}.")
        if len(columns) != len(set(columns)):
            raise ValueError(f"Duplicate mapped column for table {table['id']}.")
    native = mapping.get("native_id_column")
    if native is not None and (not isinstance(native, str) or not native):
        raise ValueError(f"Invalid native identifier column for table {table['id']}.")
    required = mapping.get("required_for_inclusion", [])
    if not isinstance(required, list) or any(field not in fields or not fields[field] for field in required):
        raise ValueError(f"Invalid inclusion requirement for table {table['id']}.")
    return mapping


def _reported_text(value: object) -> str:
    """Represent a source cell without trimming or changing identifier spelling."""
    return "" if pd.isna(value) else str(value)


def build_source_records(
    data_root: str | Path = "data", *, catalog_path: str | Path = DEFAULT_CATALOG,
) -> SourceRecords:
    """Assemble inventory rows with frozen-file provenance and explicit inclusion rules.

    Availability denotes a supplied value under the declared missing-token rule,
    not a valid chemical identifier. Reference and literature-link tables are
    described in the mapping report but never added to the candidate collection.
    """
    root = resolve_data_root(data_root)
    catalog_hash = _file_hash(Path(catalog_path))
    catalog = load_catalog(catalog_path)
    policy = catalog.get("record_assembly_policy", {})
    tokens = policy.get("missing_tokens")
    if not policy.get("version") or not isinstance(tokens, list) or "" not in tokens or any(
        not isinstance(token, str) for token in tokens
    ):
        raise ValueError("Record assembly requires a versioned policy and explicit missing tokens.")
    missing_tokens = set(tokens)
    declarations = {(s["id"], t["id"]): _record_mapping(t)
                    for s in catalog["sources"] for t in s["tables"]}
    frames, summaries, mappings, input_files = [], [], [], []
    for source in catalog["sources"]:
        path = root / "SourceDatabase" / source["filename"]
        candidates = [t for t in source["tables"]
                      if declarations[source["id"], t["id"]]["scope"] == "candidate_inventory"]
        fingerprint = _file_hash(path) if candidates else None
        for table in source["tables"]:
            mapping = declarations[source["id"], table["id"]]
            fields = mapping.get("fields", {})
            mappings.append({
                "source_id": source["id"], "table_id": table["id"],
                "filename": source["filename"], "sheet": table["sheet"],
                "header_row": table["header"] + 1, "scope": mapping["scope"],
                "scope_reason": "candidate_inventory" if mapping["scope"] == "candidate_inventory"
                                else f"{mapping['scope']}_not_candidate_inventory",
                "native_id_column": mapping.get("native_id_column"),
                **{field: json.dumps(fields.get(field, [])) for field in REPORTED_FIELDS},
                "required_for_inclusion": json.dumps(mapping.get("required_for_inclusion", [])),
            })
            if mapping["scope"] != "candidate_inventory":
                continue
            with warnings.catch_warnings(record=True) as reader_warnings:
                warnings.simplefilter("always")
                frame = _read_table(path, table)
            native_column = mapping.get("native_id_column")
            mapped_columns = list(dict.fromkeys(
                [c for columns in fields.values() for c in columns] + ([native_column] if native_column else [])))
            absent = set(mapped_columns) - set(frame.columns)
            if absent:
                raise ValueError(f"Missing mapped columns in {table['id']}: {', '.join(sorted(absent))}")
            if frame.empty:
                raise ValueError(f"No source records in table {table['id']}.")
            records = []
            for number, values in enumerate(frame[mapped_columns].itertuples(index=False, name=None), 1):
                raw = dict(zip(mapped_columns, map(_reported_text, values)))
                key = json.dumps([source["id"], table["id"], fingerprint, number], separators=(",", ":"))
                record = {
                    "record_id": hashlib.sha256(key.encode("utf-8")).hexdigest(),
                    "source_id": source["id"], "table_id": table["id"],
                    "source_filename": source["filename"], "source_sha256": fingerprint,
                    "source_sheet": table["sheet"], "source_record_number": number,
                    "source_row_number": table["header"] + 1 + number if path.suffix.lower() != ".csv" else None,
                    "source_native_id_column": native_column,
                    "source_native_id": raw.get(native_column, ""),
                    "reported_fields_json": json.dumps(raw, ensure_ascii=False),
                }
                for field, columns in fields.items():
                    selected = next((c for c in columns if raw[c].strip() not in missing_tokens), None)
                    record[field] = raw[selected] if selected is not None else ""
                    record[f"{field}_column"] = selected
                    record[f"{field}_available"] = selected is not None
                missing = [field for field in mapping.get("required_for_inclusion", [])
                           if not record[f"{field}_available"]]
                record["included"] = not missing
                record["exclusion_reason"] = ";".join(f"missing_required_{field}" for field in missing)
                records.append(record)
            assembled = pd.DataFrame(records)
            assembled["source_row_number"] = assembled["source_row_number"].astype("Int64")
            included = assembled.loc[assembled["included"]]
            summaries.append({
                "source_id": source["id"], "table_id": table["id"],
                "parsed_records": len(assembled), "included_records": len(included),
                "excluded_records": len(assembled) - len(included),
                **{field.removesuffix("_reported") + "_available": int(included[f"{field}_available"].sum())
                   for field in REPORTED_FIELDS},
                "availability_denominator": "included_records",
                "reader_warnings": "; ".join(dict.fromkeys(str(w.message) for w in reader_warnings)),
            })
            frames.append(assembled)
        if candidates:
            if fingerprint != _file_hash(path):
                raise ValueError(f"Source changed during record assembly: {source['filename']}")
            input_files.append({"source_id": source["id"], "filename": source["filename"], "sha256": fingerprint})
    if not frames:
        raise ValueError("No candidate inventory tables are declared.")
    if catalog_hash != _file_hash(Path(catalog_path)):
        raise ValueError("Source catalog changed during record assembly.")
    records = pd.concat(frames, ignore_index=True)
    manifest = {
        "schema_version": 1, "policy": policy, "catalog_sha256": catalog_hash,
        "implementation_sha256": _file_hash(Path(__file__)),
        "runtime": {"python": platform.python_version(),
                    **{name: version(name) for name in ("pandas", "openpyxl", "xlrd")}},
        "input_files": input_files, "parsed_records": len(records),
        "included_records": int(records["included"].sum()),
        "excluded_records": int((~records["included"]).sum()),
        "scope": "Source record assembly only; no identity resolution, deduplication or scoring.",
    }
    return SourceRecords(records, pd.DataFrame(summaries), pd.DataFrame(mappings), manifest)
