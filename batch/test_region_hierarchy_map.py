"""Fail-closed NMT level-6 to OBJ mapping tests.

Version: 1.13.0 (local/unreleased)
Last updated: 2026-11-02
Change history: ../CHANGELOG.md
"""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from batch.build_region_hierarchy_map import build_map
from vispa.renderers.swc_brain_view import _plan_region


class RegionHierarchyMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mesh = self.root / 'mesh'
        self.mesh.mkdir()
        names = ['true_area (Foo).obj', 'capsule_of_the_antherior_thalamus (cap).obj',
                 'medial_emminence (MEm).obj']
        files = []
        for name in names:
            path = self.mesh / name
            path.write_text('v 0 0 0\nv 1 1 1\nf 1 2 1\n')
            files.append({'file': name, 'bytes': path.stat().st_size,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'schema': 'vispa-region-mesh-dependency-manifest-v1',
                                             'obj_count': len(files), 'files': files}))
        self.charm = self.root / 'charm.csv'
        self.sarm = self.root / 'sarm.csv'
        for path, rows in ((self.charm, [('CL_true_area', 'CL_Foo', 1),
                                        ('CR_true_area', 'CR_Foo', 501)]),
                           (self.sarm, [('SL_CA1_3_posterior', 'SL_CAP', 1020),
                                        ('SR_CA1_3_posterior', 'SR_CAP', 1520),
                                        ('SL_medial_eminence', 'SL_MEm', 1089),
                                        ('SR_medial_eminence', 'SR_MEm', 1589)])):
            with path.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['Level_6', 'Level_6_abbr', 'Level_6_index'])
                writer.writerows(rows)
        self.map = self.root / 'mapping.json'
        self.data = build_map(self.charm, self.sarm, self.manifest)
        self.map.write_text(json.dumps(self.data))
        self.source = {'region_mesh_root': str(self.mesh), 'region_manifest': str(self.manifest),
                       'region_hierarchy_map': str(self.map), 'region_color': [0.2, 0.4, 0.6]}

    def test_full_name_binds_side_index_and_obj_hash(self):
        self.assertEqual(self.data['counts']['CHARM']['unique'], 2)
        mesh, resolution, _ = _plan_region(self.source, None, 'Foo_1')
        self.assertEqual(mesh['filename'], 'true_area (Foo).obj')
        self.assertEqual(resolution['canonical_region_key']['left_atlas_index'], 1)
        self.assertEqual(resolution['canonical_region_key']['right_atlas_index'], 501)
        self.assertEqual(resolution['neuron_side'], 'unverified by this worker')
        self.assertIsNone(_plan_region(self.source, None, 'Foo_501')[0])

    def test_acronym_collision_and_wrong_index_fail_closed(self):
        self.assertEqual(self.data['counts']['SARM']['unverified_alias'], 4)
        for query in ('CAP_1020', 'CAP_1520', 'Foo_999'):
            with self.subTest(query=query):
                mesh, resolution, _ = _plan_region(self.source, None, query)
                self.assertIsNone(mesh)
                self.assertEqual(resolution['status'], 'unmatched')

    def test_old_schema_and_manifest_drift_reject(self):
        old = dict(self.data, schema='vispa-nmt-level6-region-obj-map.v1')
        self.map.write_text(json.dumps(old))
        with self.assertRaisesRegex(ValueError, 'schema or mesh manifest hash'):
            _plan_region(self.source, None, 'Foo_1')
        self.map.write_text(json.dumps(self.data))
        self.manifest.write_text(self.manifest.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'schema or mesh manifest hash'):
            _plan_region(self.source, None, 'Foo_1')

    def test_left_right_index_pair_is_required(self):
        original = self.sarm.read_text()
        self.sarm.write_text(original.replace('SR_CAP,1520', 'SR_CAP,1521'))
        with self.assertRaisesRegex(ValueError, r'left/right \+500 identity mismatch'):
            build_map(self.charm, self.sarm, self.manifest)

    def test_reviewed_alias_is_exact_and_cap_stays_blocked(self):
        name = 'medial_emminence (MEm).obj'
        target = next(x for x in json.loads(self.manifest.read_text())['files'] if x['file'] == name)
        alias = {'schema': 'vispa-nmt-reviewed-nomenclature-aliases.v1',
                 'manifest_sha256': hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
                 'aliases': [{'family': 'SARM', 'left_index': 1089, 'acronym': 'MEm',
                              'level6_name': 'medial_eminence', 'obj_file': name,
                              'obj_sha256': target['sha256']}]}
        path = self.root / 'aliases.json'
        path.write_text(json.dumps(alias))
        mapped = build_map(self.charm, self.sarm, self.manifest, path)
        self.assertEqual(mapped['counts']['SARM']['unique'], 2)
        self.assertEqual(mapped['counts']['SARM']['unverified_alias'], 2)
        self.assertTrue(all(x['status'] == 'unverified_alias' for x in mapped['entries']
                            if x['acronym'] == 'CAP'))
        alias['aliases'][0]['level6_name'] = 'changed_name'
        path.write_text(json.dumps(alias))
        with self.assertRaisesRegex(ValueError, 'reviewed alias identity'):
            build_map(self.charm, self.sarm, self.manifest, path)
        alias['aliases'][0]['level6_name'] = 'medial_eminence'
        alias['aliases'][0]['obj_sha256'] = '0' * 64
        path.write_text(json.dumps(alias))
        with self.assertRaisesRegex(ValueError, 'reviewed alias identity'):
            build_map(self.charm, self.sarm, self.manifest, path)
        alias['aliases'][0] = {'family': 'SARM', 'left_index': 1020, 'acronym': 'CAP',
                               'level6_name': 'CA1_3_posterior',
                               'obj_file': 'capsule_of_the_antherior_thalamus (cap).obj',
                               'obj_sha256': next(x['sha256'] for x in json.loads(self.manifest.read_text())['files']
                                                  if x['file'].endswith('(cap).obj'))}
        path.write_text(json.dumps(alias))
        with self.assertRaisesRegex(ValueError, 'reviewed alias identity'):
            build_map(self.charm, self.sarm, self.manifest, path)


if __name__ == '__main__':
    unittest.main()
