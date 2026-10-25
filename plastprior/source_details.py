"""Browser projection of frozen source identities; no identity resolution or scoring."""
from collections import defaultdict
import json

SOURCE_SCHEMA = 'plastprior-source-v1'
SCOPE = ('Final compound fields, family annotations, and linked source identity records with '
         'resolution routes. Full intermediate evidence remains in the scientific archive.')
REPORTED = {'Name': 'name_reported', 'CAS': 'cas_reported',
            'Smile': 'smiles_reported', 'Inchikey': 'inchikey_reported'}
LOCATORS = ('source_id', 'table_id', 'source_filename', 'source_sha256', 'source_sheet',
            'source_record_number', 'source_row_number', 'source_native_id_column', 'source_native_id')
RESOLUTION = ('route_tier', 'reported_derived_status', 'identity_key_status',
              'selected_reference_id', 'selected_reference_table', 'selected_reference_record_number')


def source_details(archive):
    """Join by immutable record IDs, retaining every occurrence and original identifiers."""
    from .export import read_artifact_records
    from .publication import SOURCE_NAMES

    cursor = archive.execute('SELECT s.*,m.inchikey AS target_inchikey,m.is_representative '
                             'FROM source_records s JOIN compound_memberships m USING(record_id) '
                             'ORDER BY s._row_number')
    columns = [c[0] for c in cursor.description]
    linked = {}
    for values in cursor:
        row = dict(zip(columns, values))
        if row['record_id'] in linked:
            raise ValueError('Source record linked more than once: ' + row['record_id'])
        linked[row['record_id']] = row
    count = archive.execute('SELECT count(*) FROM compound_memberships').fetchone()[0]
    if len(linked) != count:
        raise ValueError('Missing linked source records.')
    grouped = defaultdict(list)
    seen = set()
    for resolved in read_artifact_records(archive, 'stage2/resolved_records.csv'):
        identifier = resolved['record_id']
        if identifier not in linked:
            continue
        original = linked[identifier]
        if identifier in seen or resolved['inchikey'] != original['target_inchikey']:
            raise ValueError('Source resolution identity mismatch: ' + identifier)
        seen.add(identifier)
        for field in REPORTED.values():
            if resolved[field] != original[field]:
                raise ValueError('Reported source identifier changed: ' + identifier)
        record = dict(source_schema=SOURCE_SCHEMA, record_id=identifier,
                      source_db=SOURCE_NAMES.get(original['table_id'], original['source_id']),
                      **{alias: original[field] for alias, field in REPORTED.items()},
                      **{field: original[field] for field in LOCATORS},
                      **{field: resolved[field] for field in RESOLUTION},
                      resolved_by=resolved['resolution_route'],
                      is_representative=str(original['is_representative']).lower() == 'true',
                      reported_fields=json.loads(original['reported_fields_json']),
                      resolution_attempts=json.loads(resolved['attempts_json']))
        grouped[original['target_inchikey']].append(record)
    if seen != linked.keys():
        raise ValueError('Missing resolved source evidence for linked records.')
    for key, tables in archive.execute('SELECT inchikey,source_tables_json FROM compounds'):
        if {r['table_id'] for r in grouped[key]} != set(json.loads(tables)):
            raise ValueError('Source membership summary mismatch: ' + key)
        grouped[key].sort(key=lambda r: (r['table_id'], int(r['source_record_number']), r['record_id']))
    return dict(grouped)


def add_source_details(archive, detail):
    """Extend a NEW, unpublished browser database; caller owns transaction/publication."""
    records = source_details(archive)
    keys = {r[0] for r in detail.execute('SELECT inchikey_std FROM compound_audit')}
    if keys != records.keys():
        raise ValueError('Source details and browser compound universe differ.')
    detail.execute('ALTER TABLE compound_audit ADD COLUMN source_info_json TEXT')
    for key, rows in records.items():
        value = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
        detail.execute('UPDATE compound_audit SET source_info_json=? WHERE inchikey_std=?', (value, key))
    # Validate parsed round trips, not just populated cells.
    for key, value in detail.execute('SELECT inchikey_std,source_info_json FROM compound_audit'):
        if json.loads(value) != records[key]:
            raise ValueError('Source detail round trip failed: ' + key)
    return dict(schema=SOURCE_SCHEMA, compounds=len(keys),
                linked_records=sum(map(len, records.values())),
                scope='Source-reported identity fields and row locators; not every native database column.',
                tier_semantics='Resolution precedence, not measured identification confidence.')


def refresh_browser_projection(archive_path, csv_path, database_path, destination):
    """Create a separate generation from an existing pair, without touching its archive.

    CSV bytes and all existing scientific fields/tables must remain identical. The caller
    may publish the returned package with delivery.publish_daily after reviewing QA.
    """
    from contextlib import closing
    from pathlib import Path
    import shutil
    import sqlite3
    from .delivery import sha256

    archive_path, csv_path, database_path = map(Path, (archive_path, csv_path, database_path))
    destination = Path(destination)
    baseline = {str(p.resolve()): sha256(p) for p in (archive_path, csv_path, database_path)}
    destination.mkdir(parents=True, exist_ok=False)
    output_csv = destination / 'PlastPrior_results.csv'
    output_db = destination / 'dashboard' / 'PlastPrior_dashboard.sqlite'
    output_db.parent.mkdir()
    shutil.copy2(csv_path, output_csv)
    shutil.copy2(database_path, output_db)  # Never mutate hard-linked historical files.
    with closing(sqlite3.connect(archive_path.resolve().as_uri() + '?mode=ro', uri=True)) as archive, \
            closing(sqlite3.connect(output_db.resolve().as_uri(), uri=True)) as detail:
        meta = dict(detail.execute('SELECT key,value FROM metadata'))
        if meta.get('format') != 'plastprior-dashboard-v1' or meta['csv_sha256'] != sha256(output_csv):
            raise ValueError('Source detail refresh requires an original paired CSV and browser database.')
        summary = add_source_details(archive, detail)
        detail.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('source_details', json.dumps(summary)))
        detail.execute('UPDATE metadata SET value=? WHERE key=?', (SCOPE, 'scope'))
        detail.commit()
        detail.execute('VACUUM')
        if detail.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Refreshed browser database integrity failed.')
        detail.execute('ATTACH DATABASE ? AS previous', (database_path.resolve().as_uri() + '?mode=ro',))
        compared = {}
        for table in ('compound_audit', 'chemical_family_audit', 'data_dictionary'):
            columns = [r[1] for r in detail.execute(f'PRAGMA previous.table_info({table})')]
            fields = ','.join('"' + c.replace('"', '""') + '"' for c in columns)
            old, new = f'SELECT {fields} FROM previous.{table}', f'SELECT {fields} FROM main.{table}'
            if detail.execute(new + ' EXCEPT ' + old).fetchone() or detail.execute(old + ' EXCEPT ' + new).fetchone():
                raise ValueError('Existing scientific data changed: ' + table)
            compared[table] = dict(columns=len(columns), rows=detail.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
    if output_db.stat().st_size >= 768 * 1024**2:
        raise ValueError('Refreshed database exceeds the 768 MiB browser import budget.')
    if sha256(output_csv) != baseline[str(csv_path.resolve())]:
        raise ValueError('CSV bytes changed.')
    if any(sha256(p) != digest for p, digest in baseline.items()):
        raise ValueError('An original artifact changed during refresh.')
    report = dict(status='passed', source_details=summary, unchanged_tables=compared,
                  baseline_sha256=baseline, csv_sha256=sha256(output_csv),
                  dashboard_sha256=sha256(output_db), dashboard_bytes=output_db.stat().st_size,
                  scientific_archive=str(archive_path.resolve()), changed_existing_values=0)
    (destination / 'source_details_verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return dict(directory=destination, csv=output_csv, dashboard_sqlite=output_db, verification=report)
