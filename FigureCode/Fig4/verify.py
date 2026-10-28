"""Verify the accepted composition export and its retained scientific evidence."""
from pathlib import Path
from collections import Counter
from decimal import Decimal
import argparse
import csv
import json
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'FigureCode/Fig4'
LOCK = MODULE / 'approved_composition.json'
sys.path.insert(0, str(ROOT / 'FigureCode/_shared'))
from managed import code_hashes, paths_for, replace_pair, sha, update_catalog, verify_sources, write_json
from result_paths import relocated, verify_code, verify_digest, manifest_path


def read_rows(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def check_records(records):
    for record in records.values():
        path = ROOT / record['path']
        assert path.is_file(), record['path']
        verify_digest(path, record['sha256'])


def verify_tables(folder, publication):
    rows = read_rows(folder / 'compound_membership.csv')
    ids = [row['inchikey'] for row in rows]
    assert len(ids) == len(set(ids)) == 101, 'Expected 101 unique compounds'
    full = {row['inchikey']: row for row in read_rows(publication)}
    expected = {key for key, row in full.items()
                if Decimal(row['Hazard_score']) >= 12 and Decimal(row['Exposure_score']) >= 12}
    assert set(ids) == expected, 'Five-level Level 1 cohort changed'
    identity = {row['inchikey']: row for row in read_rows(folder / 'compound_identity.csv')}
    uses = {row['inchikey']: row for row in read_rows(folder / 'primary_use_annotations.csv')}
    assert set(identity) == set(uses) == expected
    for row in rows:
        source = full[row['inchikey']]
        for field in ('Name', 'CAS', 'SMILES', 'Hazard_score', 'Exposure_score',
                      'Priority_score', 'Priority_rank', 'GIC_regulatory_status'):
            assert row[field] == source[field], (row['inchikey'], field)
        assert row['Top_n_selected'].lower() == source['Top_n_selected'].lower()
        assert row['Figure_priority_level'] == '1'
        assert row['structure_group'] == identity[row['inchikey']]['structure_group']
        assert row['primary_use'] == uses[row['inchikey']]['primary_use']
    for filename, field, categories in (
        ('use_counts.csv', 'primary_use', 16),
        ('structure_counts.csv', 'structure_group', 9),
        ('reg_counts.csv', 'GIC_regulatory_status', 5),
    ):
        counts = read_rows(folder / filename)
        assert len(counts) == len({row['category'] for row in counts}) == categories
        assert {row['category']: int(row['n']) for row in counts} == Counter(row[field] for row in rows)
        assert sum(int(row['n']) for row in counts) == 101
    classification = json.loads((folder / 'classification.json').read_text())
    assert classification['group_counts'] == Counter(row['structure_group'] for row in rows)
    return {'cohort': 101, 'panel_categories': [16, 9, 5], 'panel_totals': [101, 101, 101],
            'scores_ranks_top_n_unchanged': True, 'classification_assignments_unchanged': True}


def verify_archive(lock):
    archive = ROOT / lock['legacy_archive']
    preservation = json.loads((archive / 'preservation.json').read_text())
    for name, digest in preservation['archive_files'].items():
        assert sha(archive / name) == digest, ('Changed sensitivity archive', name)
    return preservation


def verify_publication(manifest=None):
    from pypdf import PdfReader
    lock = json.loads(LOCK.read_text())
    output, tables = paths_for('Fig4', 'output')
    manifest = relocated(manifest or json.loads(manifest_path('Fig4').read_text()))
    assert manifest['status'] == 'approved'
    provenance = manifest['approved_asset_import']
    assert provenance['lock_path'] == str(LOCK.relative_to(ROOT))
    verify_digest(LOCK, provenance['lock_sha256'])
    assert provenance['legacy_archive'] == lock['legacy_archive']
    verify_code(manifest['code'], code_hashes(MODULE))
    check_records(lock['images'])
    check_records(lock['tables'])
    check_records(lock['render_provenance'])
    assert set(manifest['outputs']) == set(lock['images']) == {'Fig4.png', 'Fig4.pdf'}
    for name, record in lock['images'].items():
        assert manifest['outputs'][name] == record['sha256'] == sha(output / name), name
    assert set(manifest['source_data']) == set(lock['tables'])
    for name, record in lock['tables'].items():
        assert manifest['source_data'][name] == record['sha256'] == sha(tables / name), name
    facts = verify_tables(tables, ROOT / manifest['source']['files']['publication']['path'])
    document = PdfReader(output / 'Fig4.pdf')
    assert len(document.pages) == 1
    page = document.pages[0]
    # Cairo stores the page box in integer points; allow that original export
    # quantisation while requiring the published PDF to match its exact hash.
    one_point_mm = 25.4 / 72
    assert abs(float(page.mediabox.width) * 25.4 / 72 - 320) < one_point_mm
    assert abs(float(page.mediabox.height) * 25.4 / 72 - 245) < one_point_mm
    compact = lambda value: re.sub(r'\s', '', value)
    text = compact(page.extract_text())
    for filename in ('use_counts.csv', 'structure_counts.csv', 'reg_counts.csv'):
        for row in read_rows(tables / filename):
            assert compact(row['label']) in text, row['label']
    verify_archive(lock)
    return dict(facts, approved_image_bytes_preserved=True, editable_pdf_labels_verified=True,
                width_mm=320, height_mm=245, legacy_sensitivity_preserved=True)


if __name__ == '__main__':
    print(json.dumps(verify_publication(),indent=2))
