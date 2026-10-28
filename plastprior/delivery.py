"""Validate and replace one current result set; no dated delivery directories."""
import csv
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from .result_storage import install_package

DAILY_NAMES = ('PlastPrior_results.csv', 'PlastPrior_dashboard.sqlite')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def new_workspace(archive_root):
    # The argument name is retained for API compatibility; this is temporary work.
    root = Path(archive_root).expanduser().absolute()
    work = root / 'work'
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f'Previous or active work exists; inspect before retrying: {root}')
    work.mkdir(parents=True)
    return work


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
    """Validate the paired package and replace a fixed, real result directory."""
    results = Path(results_dir).expanduser().absolute()
    work_root = Path(archive_root).expanduser().resolve()
    directory = Path(package['directory']).resolve()
    if results == work_root or work_root.is_relative_to(results):
        raise ValueError('Temporary work must be outside the current result directory.')
    if not directory.is_relative_to(work_root):
        raise ValueError('Package must be in the temporary workspace.')
    csv_path, detail_path = Path(package['csv']), Path(package['dashboard_sqlite'])
    # A Connection context commits/rolls back but does not close the handle.
    # Windows cannot move this database while the read handle remains open.
    with closing(sqlite3.connect(detail_path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Result database integrity check failed.')
        meta = dict(db.execute('SELECT key,value FROM metadata'))
        if meta['csv_sha256'] != sha256(csv_path):
            raise ValueError('Result CSV/database mismatch.')
        if int(meta['row_count']) != db.execute('SELECT count(*) FROM compound_audit').fetchone()[0]:
            raise ValueError('Result row count mismatch.')
    baseline = Path(baseline_csv) if baseline_csv else results / DAILY_NAMES[0]
    regression = compare_csv(baseline, csv_path) if baseline.is_file() else None
    # The low-level export nests the browser projection; the current result
    # directory presents the CSV and both databases together at its root.
    dashboard_target = directory / DAILY_NAMES[1]
    if detail_path.resolve() != dashboard_target:
        shutil.move(str(detail_path), dashboard_target)
        package['dashboard_sqlite'] = dashboard_target
    manifest = dict(run_id=meta['run_id'], daily_files={name:sha256(directory/name) for name in DAILY_NAMES},
                    regression=regression, result=str(results))
    (directory/'delivery_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n', encoding='utf-8')
    install_package(directory, results)
    return manifest


def finish_run(work, results_dir, archive_root, *, keep_intermediates=False, baseline_csv=None,
               priority_migration_baseline=None, progress=print):
    from .export import export_results

    work = Path(work).resolve()
    archive = Path(archive_root).expanduser().resolve()
    if work.name != 'work' or not work.is_relative_to(archive):
        raise ValueError('Only a managed run workspace may be cleaned.')
    if priority_migration_baseline is not None:
        if baseline_csv is not None:
            raise ValueError('Choose exact regression or explicit priority migration, not both.')
    package = export_results(work, work.parent / 'package', progress=progress)
    if priority_migration_baseline is not None:
        from .priority_migration import verify_priority_migration
        report = verify_priority_migration(priority_migration_baseline, package['csv'])
        (Path(package['directory']) / 'priority_migration.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    publish_daily(package, results_dir, archive, baseline_csv=baseline_csv)
    if not keep_intermediates:
        shutil.rmtree(work.parent)
    # Return usable current paths, not the removed temporary package.
    old_directory = Path(package['directory'])
    for key, value in list(package.items()):
        if isinstance(value, Path) and value.is_relative_to(old_directory):
            relative = value.relative_to(old_directory)
            target = Path(results_dir).absolute()/relative
            if not target.exists():
                prefix = 'figure_data/_metadata' if relative.suffix=='.json' else 'figure_data/_dependencies'
                target = Path(results_dir).absolute()/prefix/relative
            package[key] = target
    return package
