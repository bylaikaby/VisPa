"""Bounded read-only adaptor checks.

Version: 1.11.0.dev25 (local/unreleased)
Last updated: 2026-10-27
Change history: ../CHANGELOG.md
"""
import tempfile
import json
import hashlib
import unittest
import zipfile
from unittest import mock
from pathlib import Path

from vispa import data_input_adaptor as adaptor
from vispa import sources


def workbook(path, rows):
    sheet_rows = []
    for index, values in enumerate(rows, 1):
        cells = ''.join(f'<c r="{col}{index}" t="inlineStr"><is><t>{value}</t></is></c>'
                        for col, value in zip('ABC', values))
        sheet_rows.append(f'<row r="{index}">{cells}</row>')
    with zipfile.ZipFile(path, 'w') as book:
        book.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Summary" sheetId="1" r:id="rId1"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        book.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(sheet_rows) + '</sheetData></worksheet>')


class AdaptorTests(unittest.TestCase):
    def test_alias_shares_state(self):
        self.assertIs(sources, adaptor)
        marker = lambda: None
        sources.set_iondata_provider_factory(marker)
        self.assertIs(adaptor._provider_factory, marker)
        sources.set_iondata_provider_factory(None)

    def test_exact_workbook_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / '0007'
            sample.mkdir()
            first = sample / '0007_results.xlsx'
            workbook(first, [('SampleID', 'NeuronID', 'Region'), ('0007', '001.swc', 'A')])
            config = {'sources': {'neuron_tables': {'root': str(root), 'layout': 'per_sample'}}}
            result = adaptor.load_summary_neuron('0007', '001.swc', config, inspect=True)
            self.assertEqual(result['row']['Region'], 'A')
            self.assertEqual(len(result['workbook']['source']['sha256']), 64)
            self.assertEqual(adaptor.plan_neuron_resources('0007', '001.swc', config)['resources']['raw_swc'], None)
            second = sample / '0007_results_20261027_000000.xlsx'
            workbook(second, [('SampleID', 'NeuronID'), ('0007', '001.swc')])
            self.assertEqual(adaptor.locate_sample_table('0007', config)['status'], 'ambiguous')
            self.assertEqual(adaptor.locate_sample_table('0007', config, selected=first.name)['selected'], str(first.resolve()))

    def test_duplicate_and_mismatched_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / '0007'
            sample.mkdir()
            path = sample / '0007_results.xlsx'
            config = {'sources': {'neuron_tables': {'root': str(root)}}}
            workbook(path, [('SampleID', 'NeuronID'), ('0007', '001.swc'), ('0007', '001.swc')])
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                adaptor.load_summary_neuron('0007', '001.swc', config)
            workbook(path, [('SampleID', 'NeuronID'), ('0008', '001.swc')])
            with self.assertRaisesRegex(ValueError, 'mismatched'):
                adaptor.load_summary_neuron('0007', '001.swc', config)

    def test_manifest_source_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / 'selected.nii.gz'
            image.write_bytes(b'synthetic source')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'selected_preprocessed_outputs': [
                {'sample': '0007', 'relative_path': image.name,
                 'sha256': hashlib.sha256(image.read_bytes()).hexdigest()}]}), encoding='utf-8')
            result = adaptor.resolve_manifest_selected_ds00('0007', manifest, root,
                                                              expected_relative_path=image.name)
            self.assertEqual(result['source']['sha256'], hashlib.sha256(image.read_bytes()).hexdigest())
            with self.assertRaisesRegex(ValueError, 'differs'):
                adaptor.resolve_manifest_selected_ds00('0007', manifest, root,
                                                        expected_relative_path='other.nii.gz')

    def test_flat_processed_ds00_record_preserves_manifest_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / 'selected.nii.gz'
            image.write_bytes(b'synthetic source')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'run_id': 'fixture-run', 'time': '2026-10-27',
                'selected_preprocessed_outputs': [{
                    'sample': '0007', 'relative_path': image.name,
                    'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                    'repository_candidate_path': '/historical/candidate.nii.gz',
                    'processed_at': '2026-10-20', 'source_historical_path': '/source.nii.gz',
                    'source_sha256': 'source-hash', 'processing_parameters': {'rigid': True},
                    'software_versions': {'tool': 'fixture'}, 'space': 'processed DS00',
                    'status': 'candidate'}]}), encoding='utf-8')
            geometry = {'shape_ijk': [2, 3, 4]}
            record = adaptor.processed_ds00_record('0007', manifest, root, geometry)
            self.assertEqual(record['path'], str(image.resolve()))
            self.assertEqual(record['server_path'], record['path'])
            self.assertEqual(record['bytes'], len(image.read_bytes()))
            self.assertEqual(record['repository_candidate_path'], '/historical/candidate.nii.gz')
            self.assertEqual(record['processed_at'], '2026-10-20')
            self.assertEqual(record['expected_geometry'], geometry)
            self.assertEqual(record['source_acquisition_date'], 'unknown')
            self.assertEqual(record['manifest_run_id'], 'fixture-run')

    def test_manifest_metadata_plan_rejects_ambiguous_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'selected.nii.gz'
            source.write_bytes(b'fixture')
            row = {'sample': '0007', 'relative_path': source.name,
                   'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'selected_preprocessed_outputs': [row, row]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'does not uniquely select'):
                adaptor.plan_manifest_selected_ds00('0007', manifest, root)

    def test_resources_keep_raw_and_processed_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / 'raw' / '0007'
            processed = root / 'processed' / '0007'
            raw.mkdir(parents=True)
            processed.mkdir(parents=True)
            swc = '1 1 0 0 0 1 -1\n'
            (raw / '001.swc').write_text(swc)
            (processed / '001.swc').write_text(swc)
            config = {'samples': {'0007': {'swc_cache': root / 'unverified',
                                           'ds00_processed': root / 'ds00.nii.gz',
                                           'resample_5um': root / '5um.nii.gz'}},
                      'sources': {'legacy_raw_swc_root': raw.parent,
                                  'brain_view': {'processed_swc_root': processed.parent,
                                                 'mesh_path': root / 'brain.obj',
                                                 'coordinate_frame': 'processed-frame',
                                                 'coordinate_units': 'um'},
                                  'atlas': {'path': root / 'atlas.nii.gz',
                                            'coordinate_frame': 'atlas-frame'}}}
            plan = adaptor.plan_neuron_resources('0007', '001.swc', config)
            self.assertEqual(plan['resources']['raw_swc']['path'], str((raw / '001.swc').resolve()))
            self.assertEqual(plan['resources']['processed_swc']['path'], str((processed / '001.swc').resolve()))
            self.assertEqual(plan['resources']['processed_swc']['frame'], 'processed-frame')
            self.assertEqual(plan['resources']['atlas']['frame'], 'atlas-frame')
            self.assertEqual(plan['resources']['ds00_processed']['acquisition_date'], 'unknown')
            self.assertIsInstance(adaptor.load_raw_neuron(config, '0007', '001.swc').root, adaptor.SWCNode)
            (raw / '001.swc').unlink()
            with mock.patch('vispa.sources.urllib.request.urlopen') as urlopen:
                with self.assertRaises(FileNotFoundError):
                    adaptor.load_raw_neuron(config, '0007', '001.swc')
                urlopen.assert_not_called()

    def test_raw_root_accepts_redirected_child_only_with_same_root_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / 'raw'
            child = root / '0007'
            child.mkdir(parents=True)
            swc = child / '001.swc'
            swc.write_text('1 1 0 0 0 1 -1\n')
            config = {'sources': {'legacy_raw_swc_root': root}}
            redirected = base / 'redirected' / '0007' / '001.swc'
            real_resolve = Path.resolve
            real_is_file = Path.is_file
            real_samefile = Path.samefile

            def resolve(path, *args, **kwargs):
                if path == swc:
                    return redirected
                return real_resolve(path, *args, **kwargs)

            def is_file(path):
                return real_is_file(swc) if path == redirected else real_is_file(path)

            def samefile(path, other):
                if path == redirected.parent.parent and other == root:
                    return True
                return real_samefile(path, other)

            with mock.patch.object(Path, 'resolve', resolve), \
                    mock.patch.object(Path, 'is_file', is_file), \
                    mock.patch.object(Path, 'samefile', samefile), \
                    mock.patch('vispa.data_input_adaptor.read_swc') as read:
                read.return_value = adaptor.SWCTree(None, [], [])
                self.assertIs(adaptor.load_raw_neuron(config, '0007', '001.swc'), read.return_value)
                read.assert_called_once_with(redirected)
                with mock.patch.object(Path, 'samefile', return_value=False):
                    with self.assertRaisesRegex(ValueError, 'escapes declared raw root'):
                        adaptor.load_raw_neuron(config, '0007', '001.swc')


if __name__ == '__main__':
    unittest.main()
