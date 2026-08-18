#!/usr/bin/env python3
"""
tests/test_export.py
=====================
Unit test suite verifying dashboard data export compliance, schema validity,
row count integrity against master CSVs, manifest checksum correctness,
referential integrity, code audit assertions, and byte-identical reproducibility.
"""

from __future__ import annotations
import ast
import hashlib
import json
import os
import pathlib
import pytest
import pandas as pd
import jsonschema

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / 'schema' / 'dashboard_data_contract.json'
REP_MASTER_PATH = BASE_DIR / 'data' / 'rep_master.csv'
DOCTOR_MASTER_PATH = BASE_DIR / 'data' / 'doctor_master.csv'
EXPORT_DIR = BASE_DIR / 'dashboard' / 'data'
MANIFEST_PATH = EXPORT_DIR / 'manifest.json'
BUILD_SCRIPT_PATH = BASE_DIR / 'src' / 'export' / 'build_dashboard_data.py'


@pytest.fixture(scope='module')
def schema_contract():
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def manifest_data():
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_manifest_exists():
    """Verify manifest.json is generated in dashboard/data/."""
    assert MANIFEST_PATH.exists(), "manifest.json does not exist in dashboard/data/"


def test_reps_row_count_matches_master():
    """Verify row count in reps.json equals row count in rep_master.csv."""
    rep_master_df = pd.read_csv(REP_MASTER_PATH)
    master_count = len(rep_master_df)

    with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
        reps_data = json.load(f)

    items = reps_data.get('data', reps_data)
    assert len(items) == master_count, (
        f"Row count mismatch in reps.json: expected {master_count}, got {len(items)}"
    )


def test_no_rep_id_dropped():
    """Verify NO rep_id from rep_master.csv is silently dropped in reps.json."""
    rep_master_df = pd.read_csv(REP_MASTER_PATH)
    master_rep_ids = set(rep_master_df['rep_id'].unique())

    with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
        reps_data = json.load(f)

    items = reps_data.get('data', reps_data)
    exported_rep_ids = {r['rep_id'] for r in items}

    missing = master_rep_ids - exported_rep_ids
    assert not missing, f"Reps silently dropped in export: {missing}"


def test_schema_conformance(schema_contract):
    """Verify all exported JSON files conform strictly to the schema contract."""
    mappings = [
        ('reps.json', schema_contract['properties']['reps']),
        ('ml_results.json', schema_contract['properties']['ml_results']),
        ('attribution.json', schema_contract['properties']['attribution']),
        ('scatter_points.json', schema_contract['properties']['scatter_points']),
        ('coaching_queue.json', schema_contract['properties']['coaching_queue']),
        ('pipeline_telemetry.json', schema_contract['properties']['pipeline_telemetry']),
    ]

    for filename, subschema in mappings:
        file_path = EXPORT_DIR / filename
        assert file_path.exists(), f"Expected export file {filename} missing"
        with open(file_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)

        data = payload.get('data', payload)
        
        if isinstance(payload, dict) and 'data' not in payload:
            validation_target = {k: v for k, v in payload.items() if k not in ['generated_at', 'data_version']}
        else:
            validation_target = data

        try:
            jsonschema.validate(instance=validation_target, schema=subschema)
        except jsonschema.ValidationError as err:
            pytest.fail(f"Schema validation failed for {filename}: {err.message}")


def test_referential_integrity_reps():
    """Verify every rep_id in all JSON outputs exists in rep_master.csv."""
    rep_master_df = pd.read_csv(REP_MASTER_PATH)
    valid_rep_ids = set(rep_master_df['rep_id'].unique())

    # Check reps.json
    with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
        reps = json.load(f).get('data', [])
    for r in reps:
        assert r['rep_id'] in valid_rep_ids, f"Invalid rep_id {r['rep_id']} in reps.json"

    # Check scatter_points.json
    with open(EXPORT_DIR / 'scatter_points.json', 'r', encoding='utf-8') as f:
        hcps = json.load(f).get('data', [])
    for h in hcps:
        rep_id = h.get('rep_id') or h.get('Sales_Rep')
        if rep_id:
            assert rep_id in valid_rep_ids, f"Invalid rep_id {rep_id} in scatter_points.json"

    # Check coaching_queue.json
    with open(EXPORT_DIR / 'coaching_queue.json', 'r', encoding='utf-8') as f:
        tasks = json.load(f).get('data', [])
    for t in tasks:
        assert t['rep_id'] in valid_rep_ids, f"Invalid rep_id {t['rep_id']} in coaching_queue.json"


def test_referential_integrity_doctors():
    """Verify every doctor NPI in scatter_points.json exists in doctor_master.csv."""
    doctor_master_df = pd.read_csv(DOCTOR_MASTER_PATH)
    valid_npis = set(doctor_master_df['npi'].astype(str).unique())

    with open(EXPORT_DIR / 'scatter_points.json', 'r', encoding='utf-8') as f:
        hcps = json.load(f).get('data', [])

    for h in hcps:
        npi = str(h.get('npi') or h.get('Prscrbr_NPI'))
        assert npi in valid_npis, f"Orphan prescriber NPI {npi} in scatter_points.json not found in doctor_master.csv"


def test_referential_integrity_territories():
    """Verify every territory_id in export outputs is valid."""
    rep_master_df = pd.read_csv(REP_MASTER_PATH)
    valid_territories = set(rep_master_df['territory_id'].unique())

    with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
        reps = json.load(f).get('data', [])
    for r in reps:
        assert r['territory_id'] in valid_territories, f"Unknown territory {r['territory_id']} in reps.json"


def test_no_hardcoded_row_limits_in_export_script():
    """Audit code AST of build_dashboard_data.py to verify no hardcoded dataset row slicing or limits exist."""
    source_code = BUILD_SCRIPT_PATH.read_text(encoding='utf-8')
    tree = ast.parse(source_code)

    # Inspect AST slice nodes for hardcoded limits on datasets
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                upper = node.slice.upper
                if isinstance(upper, ast.Constant) and isinstance(upper.value, int):
                    expr = ast.unparse(node)
                    # Ignore string hash truncations like h.hexdigest()[:16] or sha256[:12]
                    if 'hexdigest' in expr or 'sha256' in expr or 'hash' in expr:
                        continue
                    pytest.fail(f"Found hardcoded upper row limit slice '{expr}' in {BUILD_SCRIPT_PATH}")

    # Check for hardcoded dataset row limit calls
    forbidden = ['.head(12)', '.head(10)', '.sample(', 'LIMIT 10', 'LIMIT 12']
    for term in forbidden:
        assert term not in source_code, f"Forbidden hardcoded limit pattern '{term}' found in export script"


def test_manifest_checksums(manifest_data):
    """Verify manifest checksums and file metadata are correct."""
    files_meta = manifest_data.get('files', [])
    assert files_meta, "Manifest files list is empty"

    for item in files_meta:
        fname = item['filename']
        expected_sha256 = item['sha256']
        expected_bytes = item['byte_size']

        file_path = EXPORT_DIR / fname
        assert file_path.exists(), f"File {fname} in manifest does not exist"

        content = file_path.read_bytes()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        actual_bytes = len(content)

        assert actual_bytes == expected_bytes, (
            f"Byte size mismatch for {fname}: expected {expected_bytes}, got {actual_bytes}"
        )
        assert actual_sha256 == expected_sha256, (
            f"SHA256 mismatch for {fname}: expected {expected_sha256}, got {actual_sha256}"
        )


def test_reproducibility():
    """Verify script is re-runnable and produces byte-identical output given fixed timestamp."""
    os.environ['EXPORT_TIMESTAMP'] = '2026-08-17T00:00:00Z'
    
    import subprocess
    cmd = [os.sys.executable, str(BUILD_SCRIPT_PATH)]
    subprocess.run(cmd, check=True, cwd=str(BASE_DIR))

    file_hashes = {}
    for fname in ['reps.json', 'ml_results.json', 'attribution.json', 'scatter_points.json', 'coaching_queue.json', 'pipeline_telemetry.json', 'manifest.json']:
        file_hashes[fname] = hashlib.sha256((EXPORT_DIR / fname).read_bytes()).hexdigest()

    subprocess.run(cmd, check=True, cwd=str(BASE_DIR))

    for fname, prev_hash in file_hashes.items():
        new_hash = hashlib.sha256((EXPORT_DIR / fname).read_bytes()).hexdigest()
        assert new_hash == prev_hash, f"Determinism failure: {fname} output changed on second run!"
