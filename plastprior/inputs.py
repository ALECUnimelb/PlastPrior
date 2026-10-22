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

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = Path(__file__).with_name("sources.json")
CSV_CHUNK_SIZE = 50_000


@dataclass
class InputInspection:
    """File metadata, table dimensions, and supplementary presence checks."""

    sources: pd.DataFrame
    tables: pd.DataFrame
    supporting: pd.DataFrame

    @property
    def passed(self) -> bool:
        return all(frame["status"].eq("OK").all() for frame in
                   (self.sources, self.tables, self.supporting))

    def require_complete(self) -> None:
        """Stop downstream work when an input is missing or unreadable."""
        if not self.passed:
            raise ValueError("Input inspection failed. Review the status and detail columns.")


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
