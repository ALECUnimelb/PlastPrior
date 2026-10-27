"""Verify, or explicitly publish, the user-approved Level 1 composition assets.

No drawing or scoring occurs here. The R-rendered assets are copied byte for
byte. Legacy Fig4 scripts remain untouched for ExtendedDataFig3 reproducibility.
"""
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
MODULE = ROOT / 'Figure/Fig4'
LOCK = MODULE / 'approved_composition.json'
sys.path.insert(0, str(ROOT / 'Figure/_shared'))
from managed import code_hashes, paths_for, replace_pair, sha, update_catalog, verify_sources, write_json


def read_rows(path):
    with path.open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def check_records(records):
    for record in records.values():
        path = ROOT / record['path']
        assert path.is_file() and sha(path) == record['sha256'], ('Changed approved input', record['path'])


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
    manifest = manifest or json.loads((output / 'manifest.json').read_text())
    assert manifest['status'] == 'approved'
    provenance = manifest['approved_asset_import']
    assert provenance['lock_path'] == str(LOCK.relative_to(ROOT))
    assert provenance['lock_sha256'] == sha(LOCK)
    assert provenance['legacy_archive'] == lock['legacy_archive']
    assert manifest['code'] == code_hashes(MODULE), 'Fig4 publication code changed'
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


def publish():
    lock = json.loads(LOCK.read_text())
    output, tables = paths_for('Fig4', 'output')
    catalog_path = ROOT / 'Figure/catalog.json'
    index_path = ROOT / 'Figure/INDEX.md'
    catalog = json.loads(catalog_path.read_text())
    if catalog['figures']['Fig4']['formal'] == 'current':
        print(json.dumps(verify_publication(), indent=2))
        return  # Repeated publication is verification only, never an overwrite.
    assert catalog['figures']['Fig4']['formal'] == 'legacy'
    assert not catalog['figures']['Fig4']['review']
    assert not tables.exists(), 'Unexpected existing formal Fig4 tables'
    profile = verify_sources()
    check_records(lock['images'])
    check_records(lock['tables'])
    check_records(lock['render_provenance'])
    preservation = verify_archive(lock)
    archive = ROOT / lock['legacy_archive']
    assert sha(output / 'manifest.json') == preservation['legacy_output_manifest_sha256']
    for name, digest in preservation['protected_files'].items():
        assert sha(ROOT / name) == digest, ('Protected file changed before publication', name)
    catalog_before, index_before = catalog_path.read_bytes(), index_path.read_bytes()
    tables.parent.mkdir(parents=True, exist_ok=True)
    image_stage = Path(tempfile.mkdtemp(prefix='.building-', dir=MODULE))
    table_stage = Path(tempfile.mkdtemp(prefix='.building-', dir=tables.parent))
    installed = False
    try:
        for name, record in lock['images'].items():
            shutil.copy2(ROOT / record['path'], image_stage / name)
        for name, record in lock['tables'].items():
            shutil.copy2(ROOT / record['path'], table_stage / name)
        facts = verify_tables(table_stage, ROOT / profile['files']['publication']['path'])
        manifest = {
            'schema_version': 2, 'figure': 'Fig4', 'status': 'approved', 'source': profile,
            'source_data_dir': str(tables.relative_to(ROOT)), 'code': code_hashes(MODULE),
            'source_data': {name: sha(table_stage / name) for name in lock['tables']},
            'outputs': {name: sha(image_stage / name) for name in lock['images']},
            'facts': dict(facts, title='Composition of the 101 Level 1 compounds',
                          width_mm=320, height_mm=245),
            'qa': {'adoption': 'Exact approved R exports; no redraw or rescaling'},
            'approved_asset_import': {'lock_path': str(LOCK.relative_to(ROOT)),
                                     'lock_sha256': sha(LOCK), 'legacy_archive': lock['legacy_archive']},
        }
        write_json(image_stage / 'manifest.json', manifest)
        replace_pair(image_stage, table_stage, output, tables)
        installed = True
        update_catalog('Fig4', managed=False, formal='current', review=False,
                       publication_mode='approved_asset_import',
                       entrypoint='Figure/Fig4/publish_approved.py',
                       note='Level 1 用途、结构与监管三联图，已确认；旧敏感性分析已留档')
        qa = verify_publication(manifest)
        for name, digest in preservation['protected_files'].items():
            assert sha(ROOT / name) == digest, ('Protected file changed', name)
        write_json(archive / 'publication_receipt.json', dict(
            qa, protected_files_verified=len(preservation['protected_files']),
            formal_manifest_sha256=sha(output / 'manifest.json'),
            official_outputs=manifest['outputs'], other_figures_unchanged=True))
        print(json.dumps(qa, indent=2))
    except BaseException:
        if installed:
            shutil.rmtree(output)
            shutil.copytree(archive / 'legacy/output', output)
            shutil.rmtree(tables)
            catalog_path.write_bytes(catalog_before)
            index_path.write_bytes(index_before)
        raise
    finally:
        for stage in (image_stage, table_stage):
            if stage.exists():
                shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-approved', action='store_true',
                        help='Install the locked, already user-approved assets as formal Fig4')
    args = parser.parse_args()
    if args.publish_approved:
        publish()
    else:
        print(json.dumps(verify_publication(), indent=2))
