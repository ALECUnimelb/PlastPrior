"""Publication projection and browser-sized detail database; never rescore results.

The archive remains the scientific record. This module selects and documents
reader-facing fields, retaining source lexemes and explicit missingness.
"""
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import sqlite3


FORMAT = 'plastprior-publication-v1'
DETAIL_FORMAT = 'plastprior-dashboard-v1'
CONTRACT_PATH = Path(__file__).with_name('publication_fields.json')
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))
FIELDS = tuple(item['field'] for item in CONTRACT)
REQUIRED_FIELDS = frozenset(item['source_field'] for item in CONTRACT)
SOURCE_NAMES = {
    'plastchem': 'PlastChem', 'plasticmap': 'PlasticMAP', 'ucsf': 'UCSF',
    'unep': 'UNEP', 'fccmigex': 'FCCmigex', 'fccprio': 'FCCprio',
    'fcchumon_s1': 'FCChumon S1', 'fcchumon_s2': 'FCChumon S2',
    'icca': 'ICCA', 'litchemplast': 'LitChemPlast', 'mpleach': 'NORMAN MPLEACH',
}


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def project(row):
    """Map only declared fields. Null stays empty; literal text stays literal."""
    missing = REQUIRED_FIELDS - row.keys()
    if missing:
        raise ValueError('Missing publication inputs: ' + ', '.join(sorted(missing)))
    output = {}
    for spec in CONTRACT:
        value = row[spec['source_field']]
        value = '' if value is None else str(value)
        transform = spec.get('transform')
        if transform in ('list', 'sources'):
            values = json.loads(value or '[]')
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise ValueError('Expected a JSON string list: ' + spec['source_field'])
            if transform == 'sources':
                values = [SOURCE_NAMES.get(v, v) for v in values]
            value = '; '.join(dict.fromkeys(values))
        elif transform == 'reasons':
            reasons = json.loads(value or '[]')
            if not isinstance(reasons, list) or any(not isinstance(v, dict) for v in reasons):
                raise ValueError('Expected ranking reason objects.')
            value = '; '.join(f"{r['domain']}/{r['dimension']}: {r['reason']}" for r in reasons)
        output[spec['field']] = value
    return output


def _rows(db):
    # Numeric/boolean lexemes preserve empty, zero and True/False exactly.
    cursor = db.execute('SELECT c.*,l.values_json,f.category_labels FROM compounds c '
                        'JOIN compound_lexemes l USING(inchikey) JOIN chemical_family_audit f USING(inchikey) '
                        'ORDER BY c.Ranking_eligible DESC,c.Priority_rank,c.inchikey')
    fields = [c[0] for c in cursor.description]
    for values in cursor:
        row = dict(zip(fields, values))
        row.update(json.loads(row.pop('values_json')))
        row.pop('_row_number', None)
        yield row


def write_publication(db, directory, run_id):
    """Called inside the unpublished export staging directory, after archive QA."""
    directory = Path(directory)
    from .family_export import annotate_archive
    family_summary = annotate_archive(db)
    csv_path = directory / 'PlastPrior_results.csv'
    db.execute('CREATE TABLE publication_results (' + ','.join(
        _quote(f) + (' TEXT PRIMARY KEY' if f == 'inchikey' else ' TEXT NOT NULL')
        for f in FIELDS) + ')')
    dashboard = directory / 'dashboard'
    dashboard.mkdir()
    detail_path = dashboard / 'PlastPrior_dashboard.sqlite'
    n = 0
    with closing(sqlite3.connect(detail_path)) as detail:
        detail.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        source_fields = [r[1] for r in db.execute('PRAGMA table_info(compounds)') if r[1] != '_row_number']
        # Keep every final compound field, plus display aliases; no giant audit history.
        detail_fields = list(dict.fromkeys(['inchikey_std', *source_fields, *FIELDS]))
        detail.execute('CREATE TABLE compound_audit (' + ','.join(
            _quote(f) + (' TEXT PRIMARY KEY' if f == 'inchikey_std' else ' TEXT')
            for f in detail_fields) + ')')
        insert_detail = 'INSERT INTO compound_audit VALUES (' + ','.join('?' for _ in detail_fields) + ')'
        insert_publication = 'INSERT INTO publication_results VALUES (' + ','.join('?' for _ in FIELDS) + ')'
        with csv_path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator='\n')
            writer.writeheader()
            for row in _rows(db):
                projected = project(row)
                writer.writerow(projected)
                db.execute(insert_publication, [projected[f] for f in FIELDS])
                # Preserve original JSON reason fields for detail audit. The publication
                # projection is separate; only display aliases absent upstream are added.
                merged = {**projected, **row, 'inchikey_std': row['inchikey']}
                detail.execute(insert_detail, [merged.get(f) for f in detail_fields])
                n += 1
        # Small, queryable documentation and family evidence travel with the daily pair.
        detail.execute('CREATE TABLE data_dictionary (field TEXT PRIMARY KEY, specification_json TEXT NOT NULL)')
        detail.executemany('INSERT INTO data_dictionary VALUES (?,?)',
                           [(item['field'], json.dumps(item, ensure_ascii=False)) for item in CONTRACT])
        family_schema = db.execute("SELECT sql FROM sqlite_master WHERE name='chemical_family_audit'").fetchone()[0]
        detail.execute(family_schema.replace(' REFERENCES compounds(inchikey)', ''))
        family_rows = db.execute('SELECT * FROM chemical_family_audit')
        detail.executemany('INSERT INTO chemical_family_audit VALUES (' + ','.join('?' for _ in family_rows.description) + ')', family_rows)
        detail_metadata = {
            'format': DETAIL_FORMAT, 'schema_version': '1', 'run_id': run_id,
            'row_count': str(n), 'csv_sha256': _hash(csv_path),
            'publication_format': FORMAT, 'priority_policy': 'priority-complete-domains-v1',
            'scope': 'All final compound fields and family annotations; full source occurrences and intermediate records remain in the separately archived PlastPrior_results.sqlite.',
            'chemical_families': json.dumps(family_summary),
            'readme': _readme(run_id, n),
        }
        detail.executemany('INSERT INTO metadata VALUES (?,?)', detail_metadata.items())
        detail.commit()
        if detail.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Dashboard detail database integrity failed.')
        # Verify every final field and every display alias, not only row counts.
        for row in _rows(db):
            expected = {**project(row), **row, 'inchikey_std': row['inchikey']}
            actual = detail.execute('SELECT * FROM compound_audit WHERE inchikey_std=?',
                                    (row['inchikey'],)).fetchone()
            if actual != tuple(None if expected.get(f) is None else str(expected[f]) for f in detail_fields):
                raise ValueError('Dashboard final-field round trip failed: ' + row['inchikey'])
    if detail_path.stat().st_size >= 768 * 1024**2:
        raise ValueError('Dashboard database exceeds the conservative 768 MiB import budget.')
    with csv_path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(FIELDS):
            raise ValueError('Publication field order differs.')
        for source in _rows(db):
            actual = next(reader, None)
            if actual != project(source):
                raise ValueError('Publication field round trip failed: ' + source['inchikey'])
            stored = db.execute('SELECT * FROM publication_results WHERE inchikey=?',
                                (source['inchikey'],)).fetchone()
            if stored != tuple(actual[f] for f in FIELDS):
                raise ValueError('Publication CSV/archive projection differs.')
        if next(reader, None) is not None:
            raise ValueError('Extra publication rows.')
    dictionary_path = directory / 'PlastPrior_data_dictionary.csv'
    with dictionary_path.open('w', encoding='utf-8', newline='') as stream:
        columns = ['field', 'source_field', 'type', 'unit', 'definition', 'missing', 'transform']
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(CONTRACT)
    summary = {
        'format': FORMAT, 'schema_version': 1, 'run_id': run_id, 'rows': n,
        'chemical_families': family_summary,
        'columns': len(FIELDS), 'csv_sha256': _hash(csv_path),
        'dictionary_sha256': _hash(dictionary_path),
        'dashboard_path': 'dashboard/' + detail_path.name,
        'dashboard_bytes': detail_path.stat().st_size, 'dashboard_sha256': _hash(detail_path),
        'checks': ['all publication fields and order', 'all dashboard final fields and aliases',
                   'CSV/archive projection equality', 'dashboard SQLite integrity'],
    }
    db.execute('INSERT INTO run_metadata VALUES (?,?)', ('publication', json.dumps(summary)))
    (directory / 'README.md').write_text(_readme(run_id, n), encoding='utf-8')
    return summary


def _readme(run_id, count):
    policy = json.loads(Path(__file__).with_name('priority_policy.json').read_text())
    exposure = json.loads(Path(__file__).with_name('exposure_policy.json').read_text())
    return f'''# PlastPrior publication results

Run: `{run_id}`. Publication format: `{FORMAT}`. {count:,} compounds, {len(FIELDS)} columns.

## Files and use

- `PlastPrior_results.csv`: one row per full InChIKey, including unranked compounds.
- `PlastPrior_data_dictionary.csv`: definitions, units, missingness and archive field mappings.
- `PlastPrior_results.sqlite`: complete compact scientific archive and source traceability.
- `dashboard/PlastPrior_dashboard.sqlite`: browser detail projection, containing every final
  compound field. Load the publication CSV first, then this smaller SQLite in the updated
  ChemicalPrioDashboard. CSV bytes are paired by SHA-256; editing/re-saving the CSV invalidates
  that pairing. Do not upload the full archive into the browser's in-memory SQLite reader.

The main CSV is independently readable. Import CAS and all identifiers as text in Excel.
Use `pandas.read_csv(path, keep_default_na=False)` to preserve literal source text such as NA.
Name, CAS and SMILES are display aliases of name_resolved, cas_reported and smiles_isomeric;
CAS is source-reported, not independently confirmed. No names or evidence were invented.
Source memberships are not independent corroborating studies. Function and regulatory
annotations describe the frozen evidence, not current legal advice or proof of absence.

## Interpretation

Blank numeric cells mean unavailable, never zero. A numeric zero is an available zero
under the frozen policy. Complete priority requires all four hazard and all five exposure
dimensions. Six exposure indicators are grouped into five dimensions because food contact
and human biomonitoring share one dimension. Unranked compounds remain visible and must
not be interpreted as low priority or assigned a fallback total.

Hazard = 2*P + 2*B + M + 3*T (range 0–16). Exposure is the sum of six indicators
(range 0–10). Priority = hazard + exposure only when both domains are complete (0–26).
Policy: `{policy['policy_version']}`. High priority requires total >=12, hazard >=4,
exposure >=4; moderate requires total >=6, hazard >=2, exposure >=2; otherwise low.
These are screening priorities, not measured risk or evidence of safety.

Exposure thresholds (minimum input, score):
{json.dumps(exposure['thresholds'], ensure_ascii=False, indent=2)}

Production/market evidence can include heterogeneous metrics and time periods. The chosen
numeric proxy is not necessarily global production, a current-year value or a point estimate;
metric, value status, jurisdiction and period must accompany it. Bounds and competing records
remain in the archive. Patent/literature counts and inventory listings are proxies, not measured
exposure. Literature count refers to its named scoring source, not an interchangeable database.
Food-contact and biomonitoring scores preserve their distinct evidence rules.

Ranks are competition ranks within the eligible pool, with full boundary ties included in
Top-N. InChIKey breaks display ties only. Scores, identities, eligibility and ranking have not
been recomputed by the exporter. Missing-dimension lists and reason objects are flattened to
semicolon-delimited text without truncation; original JSON remains in `compounds`.

## Traceability and reproducibility

Use the same InChIKey across CSV, `publication_results`, `compounds`, `compound_memberships`
and `evidence`. The dashboard projection is not the complete source/intermediate archive.
Final CSV SHA-256 and export validation are in `run_metadata`; publication metadata includes
the dictionary and dashboard checksums. Frozen software, policies, input hashes and source
versions are embedded under `artifacts`. Consult the project's data-access documentation
for source citations and distribution scope before public deposition. Generating this package
does not assert that every upstream source can be redistributed without conditions.

Example read-only audit (standard Python, no PlastPrior installation needed for final fields):

```python
import sqlite3
from pathlib import Path
path = Path("PlastPrior_results.sqlite").resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
    row = db.execute("SELECT * FROM compounds WHERE inchikey = ?", ("FULL-INCHIKEY",)).fetchone()
    links = db.execute("SELECT * FROM compound_memberships WHERE inchikey = ?", ("FULL-INCHIKEY",)).fetchall()
    sources = db.execute("SELECT s.* FROM source_records s JOIN compound_memberships m USING(record_id) WHERE m.inchikey = ?", ("FULL-INCHIKEY",)).fetchall()
```

For compressed occurrence-level evidence use `plastprior.export.read_audit_payload` and
`read_artifact_records` from the matching software version. The compact-v2 codec is unchanged.
Paper-specific figure source data and scientific sensitivity analyses are separate from
this export. This package is a documented result dataset, not a guarantee of journal acceptance.
'''
