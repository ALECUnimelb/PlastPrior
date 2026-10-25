"""Keep the daily pair separate from immutable run archives and temporary stages.

On POSIX, results is an atomically replaced directory symlink. Both files therefore
switch generations together; an interrupted publication cannot mix two runs.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

DAILY_NAMES = ('PlastPrior_results.csv', 'PlastPrior_dashboard.sqlite')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def new_workspace(archive_root):
    root = Path(archive_root).expanduser().absolute()
    run = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8])
    (run / 'work').mkdir(parents=True)
    return run / 'work'


def compare_csv(baseline, candidate):
    """Compare all existing publication fields by full identity, including blanks."""
    def read(path):
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            indexed = {row['inchikey']: row for row in rows}
            if len(indexed) != len(rows):
                raise ValueError('Duplicate identities: ' + str(path))
            return reader.fieldnames, indexed
    fields, old = read(baseline)
    new_fields, new = read(candidate)
    if old.keys() != new.keys():
        raise ValueError('Compound universe changed; publication aborted.')
    # Families are a versioned annotation; scores, ranks and all other fields must match.
    compared = [f for f in fields if f != 'category_labels']
    if set(compared) - set(new_fields):
        raise ValueError('Existing publication fields were removed.')
    changes = [(key, field) for key in old for field in compared if old[key][field] != new[key][field]]
    if changes:
        raise ValueError(f'Publication regression: {len(changes)} changed values; examples: {changes[:8]}')
    return dict(status='passed', rows=len(old), compared_fields=compared, changed_values=0,
                baseline_sha256=sha256(baseline), candidate_sha256=sha256(candidate))


def publish_daily(package, results_dir, archive_root, *, baseline_csv=None):
    """Verify first, preserve any legacy directory, then atomically select the pair."""
    requested = Path(results_dir).expanduser().absolute()
    results = requested.parent.resolve() / requested.name  # Resolve parent aliases, not the active link.
    archive = Path(archive_root).expanduser().resolve()
    if archive == results or archive.is_relative_to(results):
        raise ValueError('Audit archives must be outside the daily results directory.')
    if os.name != 'posix':
        raise RuntimeError('Atomic directory-link publication requires POSIX; verified archive retained.')
    directory = Path(package['directory']).resolve()
    if not directory.is_relative_to(archive):
        raise ValueError('Package must be in the separate audit archive.')
    csv_path, detail_path = Path(package['csv']), Path(package['dashboard_sqlite'])
    with sqlite3.connect(f'file:{detail_path}?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Daily database integrity check failed.')
        meta = dict(db.execute('SELECT key,value FROM metadata'))
        if meta['csv_sha256'] != sha256(csv_path):
            raise ValueError('Daily CSV/database mismatch.')
        if int(meta['row_count']) != db.execute('SELECT count(*) FROM compound_audit').fetchone()[0]:
            raise ValueError('Daily row count mismatch.')
    baseline = Path(baseline_csv) if baseline_csv else results / DAILY_NAMES[0]
    regression = compare_csv(baseline, csv_path) if baseline.is_file() else None
    daily = directory / 'daily'
    daily.mkdir()
    for source, name in zip((csv_path, detail_path), DAILY_NAMES):
        # Hard links avoid a second large database while preserving a simple two-file directory.
        try:
            os.link(source, daily / name)
        except OSError:
            shutil.copy2(source, daily / name)
        if sha256(source) != sha256(daily / name):
            raise ValueError('Daily copy verification failed.')
    manifest = dict(run_id=meta['run_id'], daily_files={name: sha256(daily / name) for name in DAILY_NAMES},
                    regression=regression, archive=str(directory), results=str(results))
    (directory / 'delivery_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    results.parent.mkdir(parents=True, exist_ok=True)
    pointer = results.with_name('.' + results.name + '-' + uuid4().hex + '.tmp')
    pointer.symlink_to(os.path.relpath(daily, results.parent), target_is_directory=True)
    legacy = None
    try:
        if results.exists() and not results.is_symlink():
            if not results.is_dir():
                raise ValueError('Daily destination is not a directory.')
            legacy = archive / ('legacy-results-' + uuid4().hex[:8])
            # Same-filesystem rename preserves every byte; never delete old audit records.
            results.rename(legacy)
            (directory / 'legacy_migration.json').write_text(json.dumps({
                'original_path': str(results), 'archived_path': str(legacy),
                'method': 'whole-directory rename; no files deleted or rewritten'}, indent=2) + '\n')
        os.replace(pointer, results)
    except BaseException:
        if legacy is not None and not results.exists() and not results.is_symlink():
            legacy.rename(results)
        raise
    finally:
        pointer.unlink(missing_ok=True)
    return manifest


def finish_run(work, results_dir, archive_root, *, keep_intermediates=False, baseline_csv=None, progress=print):
    from .export import export_results

    work = Path(work).resolve()
    archive = Path(archive_root).expanduser().resolve()
    if work.name != 'work' or not work.is_relative_to(archive):
        raise ValueError('Only a managed run workspace may be cleaned.')
    package = export_results(work, work.parent / 'package', progress=progress)
    publish_daily(package, results_dir, archive, baseline_csv=baseline_csv)
    if not keep_intermediates:
        shutil.rmtree(work)
    return package
