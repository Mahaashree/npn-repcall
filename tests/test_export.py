from __future__ import annotations
import ast
import hashlib
import json
import os
import pathlib
import unittest
import pandas as pd
import jsonschema

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / 'schema' / 'dashboard_data_contract.json'
REP_MASTER_PATH = BASE_DIR / 'data' / 'rep_master.csv'
DOCTOR_MASTER_PATH = BASE_DIR / 'data' / 'doctor_master.csv'
EXPORT_DIR = BASE_DIR / 'dashboard' / 'data'
MANIFEST_PATH = EXPORT_DIR / 'manifest.json'
BUILD_SCRIPT_PATH = BASE_DIR / 'src' / 'export' / 'build_dashboard_data.py'


class TestExportPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            cls.schema_contract = json.load(f)
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            cls.manifest_data = json.load(f)

    def test_manifest_exists(self):
        self.assertTrue(MANIFEST_PATH.exists(), "manifest.json does not exist in dashboard/data/")

    def test_reps_row_count_matches_master(self):
        rep_master_df = pd.read_csv(REP_MASTER_PATH)
        master_count = len(rep_master_df)

        with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
            reps_data = json.load(f)

        if 'hybrid' in reps_data and 'synthetic' in reps_data:
            total_exported = len(reps_data['hybrid']) + len(reps_data['synthetic'])
        else:
            items = reps_data.get('data', reps_data)
            total_exported = len(items)
        self.assertEqual(total_exported, master_count)

    def test_no_rep_id_dropped(self):
        rep_master_df = pd.read_csv(REP_MASTER_PATH)
        master_rep_ids = set(rep_master_df['rep_id'].unique())

        with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
            reps_data = json.load(f)

        if 'hybrid' in reps_data and 'synthetic' in reps_data:
            exported_rep_ids = {r['rep_id'] for r in reps_data['hybrid']} | {r['rep_id'] for r in reps_data['synthetic']}
        else:
            items = reps_data.get('data', reps_data)
            exported_rep_ids = {r['rep_id'] for r in items}

        missing = master_rep_ids - exported_rep_ids
        self.assertEqual(len(missing), 0, f"Reps silently dropped in export: {missing}")

    def test_schema_conformance(self):
        mappings = [
            ('reps.json', self.schema_contract['properties']['reps']),
            ('ml_results.json', self.schema_contract['properties']['ml_results']),
            ('attribution.json', self.schema_contract['properties']['attribution']),
            ('scatter_points.json', self.schema_contract['properties']['scatter_points']),
            ('coaching_queue.json', self.schema_contract['properties']['coaching_queue']),
            ('pipeline_telemetry.json', self.schema_contract['properties']['pipeline_telemetry']),
        ]

        for filename, subschema in mappings:
            file_path = EXPORT_DIR / filename
            self.assertTrue(file_path.exists(), f"Expected export file {filename} missing")
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)

            data = payload.get('data', payload)
            
            if filename == 'pipeline_telemetry.json' and isinstance(payload, dict) and 'hybrid' in payload:
                validation_target = payload['hybrid']
            elif isinstance(payload, dict) and 'data' not in payload:
                validation_target = {k: v for k, v in payload.items() if k not in ['generated_at', 'data_version']}
            else:
                validation_target = data

            try:
                jsonschema.validate(instance=validation_target, schema=subschema)
            except jsonschema.ValidationError as err:
                self.fail(f"Schema validation failed for {filename}: {err.message}")

    def test_referential_integrity_reps(self):
        rep_master_df = pd.read_csv(REP_MASTER_PATH)
        valid_rep_ids = set(rep_master_df['rep_id'].unique())

        with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
            reps = json.load(f).get('data', [])
        for r in reps:
            self.assertIn(r['rep_id'], valid_rep_ids)

        with open(EXPORT_DIR / 'scatter_points.json', 'r', encoding='utf-8') as f:
            hcps = json.load(f).get('data', [])
        for h in hcps:
            rep_id = h.get('rep_id') or h.get('Sales_Rep')
            if rep_id:
                self.assertIn(rep_id, valid_rep_ids)

        with open(EXPORT_DIR / 'coaching_queue.json', 'r', encoding='utf-8') as f:
            tasks = json.load(f).get('data', [])
        for t in tasks:
            self.assertIn(t['rep_id'], valid_rep_ids)

    def test_referential_integrity_doctors(self):
        doctor_master_df = pd.read_csv(DOCTOR_MASTER_PATH)
        valid_npis = set(doctor_master_df['npi'].astype(str).unique())

        with open(EXPORT_DIR / 'scatter_points.json', 'r', encoding='utf-8') as f:
            hcps = json.load(f).get('data', [])

        for h in hcps:
            npi = str(h.get('npi') or h.get('Prscrbr_NPI'))
            self.assertIn(npi, valid_npis)

    def test_referential_integrity_territories(self):
        rep_master_df = pd.read_csv(REP_MASTER_PATH)
        valid_territories = set(rep_master_df['territory_id'].unique())

        with open(EXPORT_DIR / 'reps.json', 'r', encoding='utf-8') as f:
            reps = json.load(f).get('data', [])
        for r in reps:
            self.assertIn(r['territory_id'], valid_territories)

    def test_no_hardcoded_row_limits_in_export_script(self):
        source_code = BUILD_SCRIPT_PATH.read_text(encoding='utf-8')
        tree = ast.parse(source_code)

        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                if isinstance(node.slice, ast.Slice):
                    upper = node.slice.upper
                    if isinstance(upper, ast.Constant) and isinstance(upper.value, int):
                        expr = ast.unparse(node)
                        if 'hexdigest' in expr or 'sha256' in expr or 'hash' in expr:
                            continue
                        self.fail(f"Found hardcoded upper row limit slice '{expr}' in {BUILD_SCRIPT_PATH}")

        forbidden = ['.head(12)', '.head(10)', '.sample(', 'LIMIT 10', 'LIMIT 12']
        for term in forbidden:
            self.assertNotIn(term, source_code)

    def test_manifest_checksums(self):
        files_meta = self.manifest_data.get('files', [])
        self.assertTrue(files_meta, "Manifest files list is empty")

        for item in files_meta:
            fname = item['filename']
            expected_sha256 = item['sha256']
            expected_bytes = item['byte_size']

            file_path = EXPORT_DIR / fname
            self.assertTrue(file_path.exists(), f"File {fname} in manifest does not exist")

            content = file_path.read_bytes()
            actual_sha256 = hashlib.sha256(content).hexdigest()
            actual_bytes = len(content)

            self.assertEqual(actual_bytes, expected_bytes)
            self.assertEqual(actual_sha256, expected_sha256)


if __name__ == '__main__':
    unittest.main()
