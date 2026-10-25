"""Package a completed, verified run as a readable CSV and an auditable SQLite file.

This module does not calculate scores, change policies, or remove stage outputs.
"""
from collections import OrderedDict
from contextlib import closing
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import sqlite3
import tempfile
from uuid import uuid4
import zlib


SCHEMA_VERSION = 2
MANIFESTS = (
    ('stage2', 'source_record_manifest.json'), ('stage2', 'identity_manifest.json'),
    ('stage3', 'qsar_manifest.json'), ('stage3', 'lrtp', 'lrtp_manifest.json'),
    ('stage4', 'evidence_manifest.json'), ('stage4', '4b', 'specialist_manifest.json'),
    ('stage4', '4c', 'annotation_manifest.json'), ('stage5', 'hazard_manifest.json'),
    ('stage5', '5b', 'bt_manifest.json'), ('stage6', '6a', 'exposure_manifest.json'),
    ('stage6', '6b', 'exposure_scoring_manifest.json'),
    ('stage7', '7a', 'priority_manifest.json'), ('stage7', '7b', 'ranking_manifest.json'),
)
SCORES = (
    'Persistence_score', 'Bioaccumulation_score', 'Mobility_score', 'Toxicity_score',
    'Exposure_production_score', 'Exposure_patent_score', 'Exposure_literature_score',
    'Exposure_food_contact_score', 'Exposure_human_biomonitoring_score', 'Exposure_inventory_score',
    'Hazard_score', 'Exposure_score', 'Priority_score',
)
COUNTS = ('Hazard_available_dimensions', 'Exposure_available_dimensions',
          'Priority_rank', 'Priority_tie_size')
FLAGS = ('Priority_eligible', 'Ranking_eligible', 'Top_n_selected',
         'gic_name_review_required', 'gic_multiple_cids', 'gic_multiple_sids',
         'gic_metadata_historical_hash_available', 'gic_shared_identifier_tag_expansion')
REASONS = ('persistence_unavailable_reason', 'bioaccumulation_unavailable_reason',
           'mobility_unavailable_reason', 'toxicity_unavailable_reason',
           'exposure_production_unavailable_reason', 'exposure_patent_unavailable_reason',
           'exposure_literature_unavailable_reason', 'exposure_food_contact_unavailable_reason',
           'exposure_human_biomonitoring_unavailable_reason', 'exposure_inventory_unavailable_reason')
SUMMARY_FIELDS = (
    'inchikey', 'name_resolved', 'cas_reported', 'smiles_isomeric', 'representative_record_id',
    *SCORES, 'Priority_tier', *COUNTS, *FLAGS,
    'Hazard_missing_dimensions', 'Exposure_missing_dimensions',
    'Priority_ineligibility_reasons', 'Ranking_exclusion_reasons', *REASONS,
    'qsar_identity_status', 'qsar_identity_reason', 'gic_match_method',
    'Exposure_patent_data_status', 'Exposure_literature_data_status',
    'Exposure_production_data_status', 'Exposure_inventory_data_status',
    'ranking_result_role',
)
MAIN_TABLES = {
    ('stage7', '7b', 'compound_rankings.csv'): 'compounds',
    ('stage7', '7b', 'historical_priority_order.csv'): 'historical_results',
    ('stage2', 'source_records.csv'): 'source_records',
    ('stage2', 'compound_memberships.csv'): 'compound_memberships',
}
CHUNK_BYTES = 1024 * 1024
# These tables share the final compound identity space. Only unequal fields are stored.
SNAPSHOT_NAMES = frozenset({
    'compound_inventory.csv', 'compound_qsar.csv', 'compound_lrtp.csv',
    'compound_evidence.csv', 'compound_specialist_evidence.csv',
    'compound_annotated_evidence.csv', 'compound_pm_hazard.csv',
    'compound_pbmt_hazard.csv', 'compound_exposure_evidence.csv',
    'compound_exposure_scores.csv', 'compound_priority_assessment.csv',
    'basic_evidence_historical.csv', 'specialist_historical.csv',
    'annotation_historical.csv', 'pm_historical.csv', 'bt_historical.csv',
    'exposure_historical.csv', 'priority_historical.csv', 'lrtp_historical_results.csv',
    'eligible_priority_ranking.csv', 'top_priority_including_ties.csv',
    'unranked_review.csv', 'historical_top100.csv',
})
PATENT_SCOPE_PATH = ('stage6', '6a', 'pubchemlite_patent_records.jsonl')



def _hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _rows(path):
    # The limit fits a signed 32-bit C long on Windows and accommodates audit text.
    previous = csv.field_size_limit(2**31 - 1)
    try:
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError('Missing or duplicate CSV field names: ' + path.name)
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('Malformed CSV record: ' + path.name)
                yield row
    finally:
        csv.field_size_limit(previous)


def _headers(path):
    with path.open(encoding='utf-8', newline='') as stream:
        fields = next(csv.reader(stream))
    if not fields or len(set(fields)) != len(fields):
        raise ValueError('Missing or duplicate CSV field names: ' + path.name)
    return fields


def _sql_type(field, table):
    if table != 'compounds':
        return 'TEXT'
    if field in FLAGS or field in COUNTS:
        return 'INTEGER'
    return 'REAL' if field in SCORES else 'TEXT'


def _value(field, text, table='compounds'):
    """Type only explicitly declared fields; retain all other source text exactly."""
    kind = _sql_type(field, table)
    if kind == 'TEXT':
        return text
    if text == '':
        return None
    if field in FLAGS:
        if text not in ('True', 'False'):
            raise ValueError(f'Invalid boolean in {field}: {text}')
        return int(text == 'True')
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f'Invalid number in {field}: {text}') from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f'Invalid finite nonnegative value in {field}: {text}')
    if kind == 'INTEGER':
        if number != number.to_integral_value() or number > 2**63 - 1:
            raise ValueError(f'Invalid integer in {field}: {text}')
        return int(number)
    result = float(number)
    if Decimal(str(result)) != number:
        raise ValueError(f'Lossy numeric conversion in {field}: {text}')
    return result


def _inventory(root):
    """Require the complete declared run, with every upstream checksum available."""
    artifacts, manifests = {}, []
    for parts in MANIFESTS:
        path = root.joinpath(*parts)
        digest = _hash(path)
        declaration = json.loads(path.read_text(encoding='utf-8'))
        artifacts[path] = digest
        manifests.append(declaration)
        for name, expected in declaration['output_sha256'].items():
            if Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('Invalid output basename in manifest: ' + name)
            candidate = path.parent / name
            if not candidate.resolve().is_relative_to(root) or _hash(candidate) != expected:
                raise ValueError('Stage artifact fingerprint differs: ' + str(candidate))
            if candidate in artifacts and artifacts[candidate] != expected:
                raise ValueError('Conflicting artifact declarations: ' + str(candidate))
            artifacts[candidate] = expected
    for name in ('source_inventory.csv', 'table_dimensions.csv', 'supporting_inputs.csv'):
        path = root / name
        artifacts[path] = _hash(path)
    observed = set(artifacts.values())
    for manifest in manifests:
        for key, value in manifest.items():
            if key.startswith('upstream'):
                for digest in (value.values() if isinstance(value, dict) else [value]):
                    if digest not in observed:
                        raise ValueError('A required upstream fingerprint is absent: ' + key)
    return artifacts


def _schema(db):
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript("""
        CREATE TABLE run_metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
        CREATE TABLE artifact_contents (
            id INTEGER PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, byte_count INTEGER NOT NULL,
            embedded INTEGER NOT NULL CHECK(embedded IN (0,1)));
        CREATE TABLE artifacts (
            path TEXT PRIMARY KEY, content_id INTEGER NOT NULL REFERENCES artifact_contents,
            role TEXT NOT NULL, query_table TEXT, record_count INTEGER,
            retained_count INTEGER, disposition TEXT NOT NULL, policy_json TEXT NOT NULL);
        CREATE TABLE artifact_chunks (
            content_id INTEGER NOT NULL REFERENCES artifact_contents, chunk_number INTEGER NOT NULL,
            compressed_bytes BLOB NOT NULL, PRIMARY KEY(content_id, chunk_number)) WITHOUT ROWID;
        CREATE TABLE evidence_payloads (
            id INTEGER PRIMARY KEY, digest BLOB UNIQUE NOT NULL, kind TEXT NOT NULL,
            raw_bytes INTEGER NOT NULL, compressed_json BLOB NOT NULL);
        CREATE TABLE audit_records (
            content_id INTEGER NOT NULL REFERENCES artifact_contents, record_number INTEGER NOT NULL,
            inchikey TEXT, source_id TEXT, record_id TEXT, audit_id TEXT, field_path TEXT,
            decision_reason TEXT, selected INTEGER CHECK(selected IN (0,1)),
            payload_id INTEGER NOT NULL REFERENCES evidence_payloads,
            PRIMARY KEY(content_id, record_number)) WITHOUT ROWID;
        CREATE TABLE snapshot_rows (
            content_id INTEGER NOT NULL REFERENCES artifact_contents, record_number INTEGER NOT NULL,
            inchikey TEXT NOT NULL REFERENCES compounds(inchikey),
            overrides_id INTEGER NOT NULL REFERENCES evidence_payloads,
            PRIMARY KEY(content_id, record_number)) WITHOUT ROWID;
        CREATE TABLE omitted_ranges (
            content_id INTEGER NOT NULL REFERENCES artifact_contents, first_record INTEGER NOT NULL,
            last_record INTEGER NOT NULL, reason TEXT NOT NULL,
            PRIMARY KEY(content_id, first_record), CHECK(last_record>=first_record)) WITHOUT ROWID;
        CREATE TABLE compound_lexemes (
            inchikey TEXT PRIMARY KEY REFERENCES compounds(inchikey), values_json TEXT NOT NULL);
        CREATE TABLE field_dictionary (
            table_name TEXT NOT NULL, field_name TEXT NOT NULL, storage_type TEXT NOT NULL,
            unit TEXT, missing_convention TEXT NOT NULL, description TEXT NOT NULL,
            PRIMARY KEY(table_name, field_name));
    """)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


class _Payloads:
    """Intern immutable record bodies and large fields without merging source occurrences."""
    def __init__(self, db):
        self.db = db
        self.ids = OrderedDict()
        self.decoded = OrderedDict()

    def put(self, value, kind='value'):
        raw = _canonical(value)
        digest = hashlib.sha256(kind.encode('ascii') + b'\0' + raw).digest()
        if digest in self.ids:
            self.ids.move_to_end(digest)
            return self.ids[digest]
        found = self.db.execute('SELECT id FROM evidence_payloads WHERE digest=?', (digest,)).fetchone()
        if found:
            identifier = found[0]
        else:
            identifier = self.db.execute('INSERT INTO evidence_payloads(digest,kind,raw_bytes,compressed_json) VALUES (?,?,?,?)',
                                        (digest, kind, len(raw), zlib.compress(raw, 6))).lastrowid
        self.ids[digest] = identifier
        if len(self.ids) > 32768:
            self.ids.popitem(last=False)
        return identifier

    def record(self, row):
        # A separate tagged representation prevents collision with source JSON objects.
        if not isinstance(row, dict):
            return self.put(['literal', row], 'record')
        keys = sorted(row)
        values, references = [], []
        for index, key in enumerate(keys):
            value = row[key]
            if len(_canonical(value)) > 512:
                references.append(index)
                values.append(self.put(value))
            else:
                values.append(value)
        return self.put(['mapping', self.put(keys, 'schema'), references, values], 'record')

    def get(self, identifier):
        if identifier in self.decoded:
            self.decoded.move_to_end(identifier)
            return self.decoded[identifier]
        result = self.db.execute('SELECT kind,compressed_json FROM evidence_payloads WHERE id=?', (identifier,)).fetchone()
        if result is None:
            raise ValueError('Missing evidence payload reference.')
        kind, compressed = result
        value = json.loads(zlib.decompress(compressed))
        if kind == 'record':
            if value[0] == 'literal':
                value = value[1]
            elif value[0] == 'mapping':
                keys, references = self.get(value[1]), set(value[2])
                value = {key: self.get(item) if index in references else item
                         for index, (key, item) in enumerate(zip(keys, value[3], strict=True))}
            else:
                raise ValueError('Invalid record representation.')
        self.decoded[identifier] = value
        if len(self.decoded) > 128:
            self.decoded.popitem(last=False)
        return value


def _register_artifact(db, path, digest, embedded=False):
    found = db.execute('SELECT id,embedded FROM artifact_contents WHERE sha256=?', (digest,)).fetchone()
    if found:
        return found[0]
    identifier = db.execute('INSERT INTO artifact_contents(sha256,byte_count,embedded) VALUES (?,?,?)',
                            (digest, path.stat().st_size, int(embedded))).lastrowid
    if embedded:
        observed = hashlib.sha256()
        with path.open('rb') as stream:
            for index, block in enumerate(iter(lambda: stream.read(CHUNK_BYTES), b'')):
                observed.update(block)
                db.execute('INSERT INTO artifact_chunks VALUES (?,?,?)',
                           (identifier, index, zlib.compress(block, 6)))
        if observed.hexdigest() != digest:
            raise ValueError('Provenance file changed while being embedded.')
    return identifier


def _import_table(db, path, table):
    fields = _headers(path)
    definitions = [f'{_quote(field)} {_sql_type(field, table)}' for field in fields]
    definitions.insert(0, '_row_number INTEGER PRIMARY KEY')
    if table in ('compounds', 'historical_results'):
        definitions.append('UNIQUE(inchikey)')
    elif table == 'source_records':
        definitions.append('UNIQUE(record_id)')
    elif table == 'compound_memberships':
        definitions += ['FOREIGN KEY(inchikey) REFERENCES compounds(inchikey)',
                        'FOREIGN KEY(record_id) REFERENCES source_records(record_id)',
                        'UNIQUE(inchikey, record_id)']
    db.execute(f'CREATE TABLE {_quote(table)} ({",".join(definitions)})')
    placeholders = ','.join('?' for _ in range(len(fields) + 1))
    count = 0
    for count, row in enumerate(_rows(path), 1):
        db.execute(f'INSERT INTO {_quote(table)} VALUES ({placeholders})',
                   [count] + [_value(field, row[field], table) for field in fields])
    for field in fields:
        kind = _sql_type(field, table)
        description = field.replace('_', ' ')
        if field in FLAGS:
            description += '; in compounds, 1=true and 0=false'
        unit = 'dimensionless score' if field in SCORES else None
        missing = 'SQL NULL; valid zero is retained' if kind != 'TEXT' else 'Original text; empty string retained'
        db.execute('INSERT INTO field_dictionary VALUES (?,?,?,?,?,?)',
                   (table, field, kind, unit, missing, description))
    return count


def _audit_rows(path):
    if path.suffix == '.csv':
        yield from _rows(path)
    else:
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)


def _compound_key(row):
    if not isinstance(row, dict):
        return None
    return next((row[k] for k in ('inchikey', 'compound_key', 'Inchikey_std')
                 if isinstance(row.get(k), str) and row[k]), None)


def _lookup_fields(row):
    mapping = row if isinstance(row, dict) else {}
    def first(*keys):
        return next((mapping[k] for k in keys if isinstance(mapping.get(k), str) and mapping[k]), None)
    reason = next((mapping[k] for k in ('selection_reason', 'exclusion_reason', 'exclusion_reasons',
                  'reason', 'analysis_selection_reason', 'numeric_exclusion_reasons') if mapping.get(k)), None)
    if reason is not None and not isinstance(reason, str):
        reason = _json(reason)
    selected = mapping.get('selected')
    selected = int(selected in (True, 'True')) if isinstance(selected, bool) or selected in ('True', 'False') else None
    return (_compound_key(row), first('source_id', 'db'), first('record_id', 'source_record_id'),
            first('audit_id'), first('field_path', 'field'), reason, selected)


def _omit_scope_row(relative_parts, row, keys):
    # This filter applies only to the Stage 6A patent-reference export. In-scope
    # rejections, conflicts and query failures are always retained.
    return (tuple(relative_parts) == PATENT_SCOPE_PATH and isinstance(row, dict)
            and row.get('eligible') is False
            and row.get('exclusion_reasons') == ['outside_compound_universe']
            and isinstance(row.get('compound_key'), str) and row['compound_key'] not in keys)


def _import_audit(db, path, content_id, store, keys, relative_parts):
    count = retained = 0
    omitted_digest = hashlib.sha256()
    first_omitted = last_omitted = None
    def flush():
        if first_omitted is not None:
            db.execute('INSERT INTO omitted_ranges VALUES (?,?,?,?)',
                       (content_id, first_omitted, last_omitted, 'outside_compound_universe'))
    for count, row in enumerate(_audit_rows(path), 1):
        if _omit_scope_row(relative_parts, row, keys):
            omitted_digest.update(_canonical([count, row]) + b'\n')
            if first_omitted is None:
                first_omitted = count
            last_omitted = count
            continue
        flush()
        first_omitted = last_omitted = None
        db.execute('INSERT INTO audit_records VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (content_id, count, *_lookup_fields(row), store.record(row)))
        retained += 1
    flush()
    return count, retained, {'omission_rule': 'Stage 6A patent rows explicitly outside the final compound universe only',
                             'omitted_records': count-retained,
                             'omitted_records_sha256': omitted_digest.hexdigest()}


def _import_snapshot(db, path, content_id, store, final_rows):
    fields = _headers(path)
    seen, count, differences = set(), 0, 0
    for count, row in enumerate(_rows(path), 1):
        key = row.get('inchikey')
        if key not in final_rows or key in seen:
            raise ValueError('Snapshot requires unique final compound keys: ' + path.name)
        seen.add(key)
        overrides = {field: value for field, value in row.items() if final_rows[key].get(field) != value}
        differences += len(overrides)
        db.execute('INSERT INTO snapshot_rows VALUES (?,?,?,?)',
                   (content_id, count, key, store.record(overrides)))
    return count, {'columns': fields, 'base_table': 'compounds', 'override_fields': differences,
                   'interpretation': 'Original parsed fields and row order are reconstructible; CSV byte formatting is not embedded.'}


def _views(db):
    fields = ','.join(_quote(field) for field in SUMMARY_FIELDS)
    db.executescript(f"""
        CREATE VIEW results AS SELECT {fields} FROM compounds;
        CREATE VIEW eligible_ranking AS SELECT * FROM results WHERE Ranking_eligible=1;
        CREATE VIEW top_priority AS SELECT * FROM results WHERE Top_n_selected=1;
        CREATE VIEW unranked_review AS SELECT * FROM results WHERE Ranking_eligible=0;
        CREATE VIEW evidence AS
            SELECT a.path AS artifact_path, r.record_number, r.inchikey, r.source_id,
                   r.record_id, r.audit_id, r.field_path, r.decision_reason, r.selected, r.payload_id
            FROM artifacts a JOIN audit_records r ON a.content_id=r.content_id;
        CREATE INDEX audit_compound ON audit_records(inchikey) WHERE inchikey IS NOT NULL;
        CREATE INDEX audit_source_record ON audit_records(record_id) WHERE record_id IS NOT NULL;
        CREATE INDEX audit_identifier ON audit_records(audit_id) WHERE audit_id IS NOT NULL;
        CREATE INDEX compound_ranking ON compounds(Ranking_eligible, Priority_rank, inchikey);
    """)


def archived_bytes(db, artifact_path):
    """Read embedded provenance, or a schema-v1 archive, without external files."""
    if db.execute('PRAGMA user_version').fetchone()[0] < 2:
        match = db.execute('SELECT sha256 FROM artifacts WHERE path=?', (artifact_path,)).fetchone()
        if match is None:
            raise KeyError(artifact_path)
        query = 'SELECT compressed_bytes FROM artifact_chunks WHERE sha256=? ORDER BY chunk_number'
    else:
        match = db.execute('SELECT a.content_id,c.embedded FROM artifacts a JOIN artifact_contents c ON a.content_id=c.id WHERE a.path=?', (artifact_path,)).fetchone()
        if match is None:
            raise KeyError(artifact_path)
        if not match[1]:
            raise ValueError('Compact export retains parsed records, not original file bytes; use read_artifact_records().')
        match = match[:1]
        query = 'SELECT compressed_bytes FROM artifact_chunks WHERE content_id=? ORDER BY chunk_number'
    for (block,) in db.execute(query, match):
        yield zlib.decompress(block)


def read_audit_payload(db, payload_id):
    """Decode an exact semantic audit record; source strings remain unchanged."""
    return _Payloads(db).get(payload_id)


def _database_compounds(db):
    columns = [r[1] for r in db.execute('PRAGMA table_info(compounds)') if r[1] != '_row_number']
    query = ('SELECT ' + ','.join('c.' + _quote(c) for c in columns) +
             ',l.values_json FROM compounds c JOIN compound_lexemes l USING(inchikey) ORDER BY c._row_number')
    for values in db.execute(query):
        row = dict(zip(columns, values[:-1]))
        row.update(json.loads(values[-1]))
        yield row


def read_artifact_records(db, artifact_path):
    """Yield retained parsed rows. Scope-excluded rows are documented in omitted_ranges."""
    match = db.execute('SELECT content_id,query_table,policy_json FROM artifacts WHERE path=?', (artifact_path,)).fetchone()
    if match is None:
        raise KeyError(artifact_path)
    content_id, table, policy = match
    store = _Payloads(db)
    if table == 'audit_records':
        for (payload,) in db.execute('SELECT payload_id FROM audit_records WHERE content_id=? ORDER BY record_number', (content_id,)):
            yield store.get(payload)
    elif table == 'snapshot_rows':
        fields = json.loads(policy)['columns']
        base = {r['inchikey']: r for r in _database_compounds(db)}
        for key, payload in db.execute('SELECT inchikey,overrides_id FROM snapshot_rows WHERE content_id=? ORDER BY record_number', (content_id,)):
            overrides = store.get(payload)
            yield {c: overrides[c] if c in overrides else base[key][c] for c in fields}
    elif table == 'compounds':
        yield from _database_compounds(db)
    elif table in MAIN_TABLES.values():
        cursor = db.execute('SELECT * FROM ' + _quote(table) + ' ORDER BY _row_number')
        columns = [c[0] for c in cursor.description][1:]
        for row in cursor:
            yield dict(zip(columns, row[1:]))
    else:
        raise ValueError('This artifact is embedded provenance, not a record table.')


def _validate(db, root, csv_path, artifacts):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('SQLite integrity check failed.')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('SQLite source-link integrity check failed.')
    store = _Payloads(db)
    for content_id, digest, size in db.execute('SELECT id,sha256,byte_count FROM artifact_contents WHERE embedded=1'):
        observed, length = hashlib.sha256(), 0
        for (block,) in db.execute('SELECT compressed_bytes FROM artifact_chunks WHERE content_id=? ORDER BY chunk_number', (content_id,)):
            raw = zlib.decompress(block)
            observed.update(raw)
            length += len(raw)
        if observed.hexdigest() != digest or length != size:
            raise ValueError('Embedded provenance failed round-trip verification.')
    for identifier, digest, kind, size, block in db.execute('SELECT id,digest,kind,raw_bytes,compressed_json FROM evidence_payloads'):
        raw = zlib.decompress(block)
        if len(raw) != size or hashlib.sha256(kind.encode('ascii') + b'\0' + raw).digest() != digest:
            raise ValueError('Evidence payload fingerprint differs.')
        value = json.loads(raw)
        if kind == 'record' and value[0] == 'mapping':
            if db.execute('SELECT kind FROM evidence_payloads WHERE id=?', (value[1],)).fetchone() != ('schema',):
                raise ValueError('Broken shared field-name schema.')
            keys = store.get(value[1])
            if len(keys) != len(value[3]) or len(keys) != len(set(keys)):
                raise ValueError('Evidence record fields differ from its shared schema.')
            for index in value[2]:
                if not isinstance(index, int) or not 0 <= index < len(keys):
                    raise ValueError('Invalid evidence reference position.')
                found = db.execute('SELECT kind FROM evidence_payloads WHERE id=?', (value[3][index],)).fetchone()
                if found != ('value',):
                    raise ValueError('Broken evidence-body reference.')
    for parts, table in MAIN_TABLES.items():
        path = root.joinpath(*parts)
        fields = _headers(path)
        cursor = db.execute(f'SELECT {",".join(map(_quote, fields))} FROM {_quote(table)} ORDER BY _row_number')
        count = 0
        for count, row in enumerate(_rows(path), 1):
            if tuple(_value(field, row[field], table) for field in fields) != cursor.fetchone():
                raise ValueError('Database field mismatch: ' + table)
        if cursor.fetchone() is not None:
            raise ValueError('Unexpected database rows: ' + table)
    final_rows = {row['inchikey']: row for row in _rows(root / 'stage7' / '7b' / 'compound_rankings.csv')}
    if list(_database_compounds(db)) != list(final_rows.values()):
        raise ValueError('Original numeric/boolean field text was not preserved.')
    verified = set()
    for relative, content_id, table, total, retained, policy_json in db.execute(
            "SELECT path,content_id,query_table,record_count,retained_count,policy_json FROM artifacts WHERE query_table IN ('audit_records','snapshot_rows')"):
        if content_id in verified:
            continue
        verified.add(content_id)
        parts = PurePosixPath(relative).parts
        path = root.joinpath(*parts)
        policy = json.loads(policy_json)
        count = kept = 0
        if table == 'snapshot_rows':
            cursor = db.execute('SELECT record_number,inchikey,overrides_id FROM snapshot_rows WHERE content_id=? ORDER BY record_number', (content_id,))
            fields = policy['columns']
            if fields != _headers(path):
                raise ValueError('Snapshot field order differs: ' + relative)
            for count, row in enumerate(_rows(path), 1):
                actual = cursor.fetchone()
                if actual is None or actual[:2] != (count, row['inchikey']):
                    raise ValueError('Snapshot row membership/order differs: ' + relative)
                overrides = store.get(actual[2])
                reconstructed = {c: overrides[c] if c in overrides else final_rows[row['inchikey']][c] for c in fields}
                if reconstructed != row:
                    raise ValueError('Snapshot field differs: ' + relative)
            if count != total or count != retained or cursor.fetchone() is not None:
                raise ValueError('Snapshot row count differs.')
        else:
            cursor = db.execute('SELECT record_number,inchikey,source_id,record_id,audit_id,field_path,decision_reason,selected,payload_id FROM audit_records WHERE content_id=? ORDER BY record_number', (content_id,))
            ranges = iter(db.execute('SELECT first_record,last_record,reason FROM omitted_ranges WHERE content_id=? ORDER BY first_record', (content_id,)))
            interval = next(ranges, None)
            omitted = hashlib.sha256()
            for count, row in enumerate(_audit_rows(path), 1):
                is_omitted = _omit_scope_row(parts, row, final_rows)
                in_range = interval is not None and interval[0] <= count <= interval[1]
                if is_omitted != in_range:
                    raise ValueError('Omitted record coverage differs: ' + relative)
                if is_omitted:
                    if interval[2] != 'outside_compound_universe':
                        raise ValueError('Omission reason differs.')
                    omitted.update(_canonical([count, row]) + b'\n')
                    if count == interval[1]:
                        interval = next(ranges, None)
                    continue
                actual = cursor.fetchone()
                if actual is None or actual[:-1] != (count, *_lookup_fields(row)) or store.get(actual[-1]) != row:
                    raise ValueError('Retained audit field or lookup key differs: ' + relative)
                kept += 1
            if (cursor.fetchone() is not None or interval is not None or count != total or kept != retained
                    or count-kept != policy['omitted_records'] or omitted.hexdigest() != policy['omitted_records_sha256']):
                raise ValueError('Audit coverage or omission fingerprint differs: ' + relative)
    del final_rows
    cursor = db.execute('SELECT ' + ','.join(map(_quote, SUMMARY_FIELDS)) +
                        ' FROM compounds ORDER BY Ranking_eligible DESC, Priority_rank, inchikey')
    csv_count = 0
    for csv_count, row in enumerate(_rows(csv_path), 1):
        if tuple(_value(field, row[field]) for field in SUMMARY_FIELDS) != cursor.fetchone():
            raise ValueError('CSV and SQLite summary differ.')
    if cursor.fetchone() is not None:
        raise ValueError('CSV row count differs.')
    expected_rank = list(_rows(root / 'stage7' / '7b' / 'eligible_priority_ranking.csv'))
    expected_top = list(_rows(root / 'stage7' / '7b' / 'top_priority_including_ties.csv'))
    for view, expected in [('eligible_ranking', expected_rank), ('top_priority', expected_top)]:
        actual = db.execute(f'SELECT inchikey, Priority_rank, Priority_tie_size, Top_n_selected FROM {view} ORDER BY Priority_rank, inchikey').fetchall()
        wanted = [tuple(_value(c, row[c]) for c in ('inchikey', 'Priority_rank', 'Priority_tie_size', 'Top_n_selected')) for row in expected]
        if actual != wanted:
            raise ValueError('Ranking order or Top-N membership differs: ' + view)
    if any(_hash(path) != digest for path, digest in artifacts.items()):
        raise ValueError('Source files changed during export; no package published.')
    return {'status': 'passed', 'compounds': csv_count, 'eligible_compounds': len(expected_rank),
            'top_n_compounds': len(expected_top), 'unranked_compounds': csv_count - len(expected_rank),
            'inventoried_artifacts': len(artifacts), 'summary_fields': len(SUMMARY_FIELDS),
            'retained_audit_records': db.execute('SELECT count(*) FROM audit_records').fetchone()[0],
            'scope_omitted_records': db.execute('SELECT coalesce(sum(last_record-first_record+1),0) FROM omitted_ranges').fetchone()[0],
            'factored_snapshot_rows': db.execute('SELECT count(*) FROM snapshot_rows').fetchone()[0],
            'checks': ['embedded provenance bytes', 'shared payload fingerprints and references',
                       'all retained audit fields and lookup keys', 'scope omission coverage and digest',
                       'all reconstructed snapshot fields and row order', 'all primary table fields', 'CSV/SQLite fields',
                       'ranking order and boundary ties', 'foreign keys', 'SQLite integrity',
                       'input artifact preservation']}


def export_results(results_dir, output_dir=None, *, progress=None):
    """Export to a new directory; publish both files only after verification.

    Existing destinations are never replaced. Stage artifacts remain untouched.
    """
    root = Path(results_dir).expanduser().resolve()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    destination = (Path(output_dir).expanduser().resolve() if output_dir is not None
                   else root / 'final' / run_id)
    if destination.exists():
        raise FileExistsError('Choose a new export directory: ' + str(destination))
    project = Path(__file__).resolve().parent.parent
    forbidden = [project / 'data', project / 'plastprior', project / 'tests', project / 'docs']
    forbidden += [root / ('stage' + str(i)) for i in range(2, 8)]
    if (destination == root or destination in root.parents or
            any(destination == p or destination.is_relative_to(p) for p in forbidden)):
        raise ValueError('Export must not write into scientific inputs, code, or stage directories.')
    notify = progress or (lambda message: None)
    notify('Verifying the complete stage-output inventory.')
    artifacts = _inventory(root)
    stage_count = len(artifacts)
    # Preserve the actual local implementation/configuration, including uncommitted changes.
    software = sorted(p for p in (project / 'plastprior').iterdir() if p.suffix in ('.py', '.json'))
    for path in software:
        artifacts[path] = _hash(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.export-', dir=destination.parent) as temporary:
        staging = Path(temporary) / 'package'
        staging.mkdir()
        csv_path = staging / 'PlastPrior_results.csv'
        db_path = staging / 'PlastPrior_results.sqlite'
        with closing(sqlite3.connect(db_path)) as db:
            _schema(db)
            db.execute('PRAGMA user_version=2')
            main_paths = {root.joinpath(*parts): table for parts, table in MAIN_TABLES.items()}
            final_rows = {row['inchikey']: row for row in _rows(root / 'stage7' / '7b' / 'compound_rankings.csv')}
            store = _Payloads(db)
            imported, snapshots = {}, {}
            # Main-table order ensures membership foreign keys can be enforced.
            ordered = list(main_paths) + [p for p in sorted(artifacts) if p not in main_paths]
            for index, path in enumerate(ordered, 1):
                digest = artifacts[path]
                is_software = path in software
                relative = (Path('software') / 'plastprior' / path.name if is_software else path.relative_to(root)).as_posix()
                notify(f'Packaging {index}/{len(ordered)}: {relative}')
                embedded = is_software or path.suffix in ('.json', '.txt')
                content_id = _register_artifact(db, path, digest, embedded)
                table, count, retained, policy = main_paths.get(path), None, None, {}
                if table:
                    count = retained = _import_table(db, path, table)
                    disposition = 'complete_primary_table'
                    if table == 'compounds':
                        for key, row in final_rows.items():
                            lexemes = {c: v for c, v in row.items() if _sql_type(c, table) != 'TEXT'}
                            db.execute('INSERT INTO compound_lexemes VALUES (?,?)', (key, _json(lexemes)))
                elif path.suffix == '.csv' and path.name in SNAPSHOT_NAMES:
                    table, disposition = 'snapshot_rows', 'final_values_plus_sparse_overrides'
                    if content_id not in snapshots:
                        snapshots[content_id] = _import_snapshot(db, path, content_id, store, final_rows)
                    count, policy = snapshots[content_id]
                    retained = count
                elif path.suffix in ('.csv', '.jsonl'):
                    table, disposition = 'audit_records', 'shared_evidence_bodies'
                    if content_id not in imported:
                        imported[content_id] = _import_audit(db, path, content_id, store, final_rows, path.relative_to(root).parts)
                    count, retained, policy = imported[content_id]
                    if count != retained:
                        disposition = 'in_scope_evidence_with_explicit_exclusion_coverage'
                else:
                    disposition = 'embedded_provenance'
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?)',
                           (relative, content_id, 'software' if is_software else 'stage_output', table,
                            count, retained, disposition, _json(policy)))
                db.commit()
            del final_rows, store
            fields = _headers(root / 'stage7' / '7b' / 'compound_rankings.csv')
            if set(SUMMARY_FIELDS) - set(fields):
                raise ValueError('Required summary fields are absent.')
            _views(db)
            # Preserve original CSV field text, with a deterministic user-facing order.
            rows = list(_rows(root / 'stage7' / '7b' / 'compound_rankings.csv'))
            rows.sort(key=lambda row: (row['Ranking_eligible'] != 'True',
                                      _value('Priority_rank', row['Priority_rank']) or 0, row['inchikey']))
            with csv_path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, extrasaction='ignore', lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
            del rows
            notify('Verifying every retained field, factored snapshot, evidence reference and scoped exclusion.')
            validation = _validate(db, root, csv_path, artifacts)
            metadata = {
                'schema_version': SCHEMA_VERSION, 'run_id': run_id,
                'exported_at_utc': datetime.now(timezone.utc).isoformat(),
                'runtime': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version},
                'csv_sha256': _hash(csv_path), 'summary_fields': SUMMARY_FIELDS,
                'validation': validation, 'stage_artifact_count': stage_count,
                'scope': 'Complete final results, source links, shared audit bodies and factored stage values; original data inputs are distributed separately.',
                'retention_policy': 'compact-v2; no whole-file backups of stage tables; only explicitly out-of-universe Stage 6A PubChemLite patent rows omit bodies.',
                'historical_role': 'Historical reproduction only; use compounds/results for audited analysis.',
                'ordering': 'Use ORDER BY Priority_rank, inchikey for ranked views; SQL row order is not implicit.',
                'missingness': 'Declared numeric/boolean fields use NULL for empty input; other fields retain exact text.',
                'archive_codec': 'Only small provenance files are embedded as independently zlib-compressed chunks.',
                'payload_codec': 'Canonical UTF-8 JSON compressed with zlib; tagged record templates reference immutable shared value payloads. Use read_audit_payload/read_artifact_records.',
                'audit_payload': 'Retained CSV fields preserve exact strings and JSONL records preserve JSON values; source occurrences remain distinct even when bodies are shared.',
                'external_references': 'Original inputs and stage-file bytes are not embedded. Their paths and hashes are inventoried; retained parsed stage values are reconstructible. Scope exclusions have explicit row ranges, counts and a sequence digest.',
            }
            db.executemany('INSERT INTO run_metadata VALUES (?,?)', [(k, _json(v)) for k, v in metadata.items()])
            from .publication import write_publication, FIELDS
            notify('Writing and verifying the concise publication CSV and browser detail projection.')
            publication = write_publication(db, staging, run_id)
            db.execute('UPDATE run_metadata SET value_json=? WHERE key=?',
                       (_json(_hash(csv_path)), 'csv_sha256'))
            db.execute('UPDATE run_metadata SET value_json=? WHERE key=?',
                       (_json(FIELDS), 'summary_fields'))
            validation['archive_summary_fields'] = validation['summary_fields']
            validation['summary_fields'] = len(FIELDS)
            validation['publication'] = publication
            db.execute('UPDATE run_metadata SET value_json=? WHERE key=?',
                       (_json(validation), 'validation'))
            db.commit()
        # Rename a new directory on the same filesystem after closing SQLite (Windows-safe).
        if destination.exists():
            raise FileExistsError('Export destination appeared during packaging.')
        staging.rename(destination)
    notify('Verified final package: ' + str(destination))
    return {'directory': destination, 'csv': destination / csv_path.name,
            'sqlite': destination / db_path.name,
            'dashboard_sqlite': destination / 'dashboard' / 'PlastPrior_dashboard.sqlite',
            'dictionary': destination / 'PlastPrior_data_dictionary.csv', **validation}
