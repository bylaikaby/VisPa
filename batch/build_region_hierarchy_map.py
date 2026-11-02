"""Audit exact NMT level-6 region identities against a declared OBJ manifest.

Version: 1.13.0.dev0 (local/unreleased)
Last updated: 2026-11-02
Change history: ../CHANGELOG.md

This is read-only with respect to hierarchy tables and meshes. Full hierarchy
display names are required: acronym-only collisions can select another anatomy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


_OBJ_ACRONYM = re.compile(r"^(?P<display>.+)\s\((?P<acronym>[^()]+)\)\.obj$", re.IGNORECASE)
_PREFIXES = {'CHARM': ('CL_', 'CR_'), 'SARM': ('SL_', 'SR_')}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path, family: str) -> list[dict]:
    prefix_left, prefix_right = _PREFIXES[family]
    result = {}
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'Level_6', 'Level_6_abbr', 'Level_6_index'}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError(f'{family} table lacks {sorted(required)}')
        for line, row in enumerate(reader, 2):
            full = (row['Level_6_abbr'] or '').strip()
            prefix = next((p for p in (prefix_left, prefix_right) if full.startswith(p)), None)
            if prefix is None:
                raise ValueError(f'{family} row {line}: invalid level-6 prefix {full!r}')
            index_text = (row['Level_6_index'] or '').strip()
            if not index_text.isdecimal() or int(index_text) <= 0:
                raise ValueError(f'{family} row {line}: invalid level-6 index')
            acronym = full[len(prefix):]
            if not acronym or not re.fullmatch(r'[A-Za-z0-9_/-]+', acronym):
                raise ValueError(f'{family} row {line}: invalid level-6 acronym')
            full_name = (row['Level_6'] or '').strip()
            if not full_name.startswith(prefix):
                raise ValueError(f'{family} row {line}: level-6 name/abbr side differs')
            identity = (family, prefix[:2], int(index_text))
            record = {'family': family, 'side': prefix[:2], 'level6_index': int(index_text),
                      'level6_abbr': full, 'acronym': acronym,
                      'level6_name': full_name[len(prefix):]}
            previous = result.get(identity)
            if previous is not None and previous != record:
                raise ValueError(f'{family} row {line}: conflicting level-6 identity {identity}')
            result[identity] = record
    return list(result.values())


def _aliases(path: Path | None, manifest_sha: str) -> dict[tuple[str, int], dict]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    if (payload.get('schema') != 'vispa-nmt-reviewed-nomenclature-aliases.v1' or
            payload.get('manifest_sha256') != manifest_sha or
            not isinstance(payload.get('aliases'), list)):
        raise ValueError('reviewed aliases schema or mesh manifest hash differs')
    result = {}
    for entry in payload['aliases']:
        if not isinstance(entry, dict):
            raise ValueError('invalid reviewed alias')
        family, index = entry.get('family'), entry.get('left_index')
        key = (family, index)
        if (family not in _PREFIXES or not isinstance(index, int) or isinstance(index, bool) or
                index <= 0 or key in result or
                any(not isinstance(entry.get(field), str) or not entry[field]
                    for field in ('acronym', 'level6_name', 'obj_file', 'obj_sha256')) or
                Path(entry['obj_file']).name != entry['obj_file'] or
                not re.fullmatch(r'[0-9a-fA-F]{64}', entry['obj_sha256'])):
            raise ValueError('invalid or duplicate reviewed alias')
        result[key] = entry
    return result


def build_map(charm: Path, sarm: Path, manifest: Path, aliases: Path | None = None) -> dict:
    payload = json.loads(manifest.read_text(encoding='utf-8'))
    files = payload.get('files')
    if payload.get('schema') != 'vispa-region-mesh-dependency-manifest-v1' or not isinstance(files, list):
        raise ValueError('expected VisPa region-mesh dependency manifest v1')
    by_acronym = {}
    by_display = {}
    alias_rows = _aliases(aliases, _sha(manifest))
    used_aliases = set()
    names = set()
    for item in files:
        name, sha = item.get('file'), item.get('sha256')
        if (not isinstance(name, str) or Path(name).name != name or name.casefold() in names or
                not isinstance(sha, str) or re.fullmatch(r'[0-9a-fA-F]{64}', sha) is None):
            raise ValueError('invalid or duplicate OBJ manifest entry')
        names.add(name.casefold())
        match = _OBJ_ACRONYM.fullmatch(name)
        if match:
            by_acronym.setdefault(match.group('acronym').casefold(), []).append(item)
            by_display.setdefault(match.group('display').casefold(), []).append(item)
    entries = []
    for family, table in (('CHARM', charm), ('SARM', sarm)):
        for row in _rows(table, family):
            acronym_matches = by_acronym.get(row['acronym'].casefold(), [])
            display_matches = by_display.get(row['level6_name'].casefold(), [])
            if len(display_matches) == 1:
                matches, match_kind = display_matches, 'exact_display'
            elif len(display_matches) > 1:
                acronym_names = {item['file'].casefold() for item in acronym_matches}
                matches = [item for item in display_matches if item['file'].casefold() in acronym_names]
                match_kind = 'display_and_acronym'
            else:
                matches, match_kind = acronym_matches, 'unverified_alias'
            matches = sorted(matches, key=lambda item: item['file'].casefold())
            state = ('unverified_alias' if match_kind == 'unverified_alias' and matches else
                     'unique' if len(matches) == 1 else 'missing' if not matches else 'ambiguous')
            left_index = row['level6_index'] if row['side'] in ('CL', 'SL') else row['level6_index'] - 500
            alias_key = (family, left_index)
            alias = alias_rows.get(alias_key)
            if alias is not None:
                if state != 'unverified_alias':
                    raise ValueError(f'{family} {left_index}: alias is not needed for an acronym-only mismatch')
                exact = [item for item in matches if item['file'] == alias['obj_file']]
                suffix = _OBJ_ACRONYM.fullmatch(alias['obj_file'])
                if (alias['acronym'] != row['acronym'] or alias['level6_name'] != row['level6_name'] or
                        suffix is None or suffix.group('acronym') != row['acronym'] or
                        len(exact) != 1 or exact[0]['sha256'].lower() != alias['obj_sha256'].lower()):
                    raise ValueError(f'{family} {left_index}: reviewed alias identity or OBJ hash differs')
                matches, match_kind, state = exact, 'reviewed_nomenclature_alias', 'unique'
                used_aliases.add(alias_key)
            entries.append({**row, 'status': state, 'match_kind': match_kind if state == 'unique' else None,
                            'mesh': ({'file': matches[0]['file'], 'sha256': matches[0]['sha256'].lower(),
                                      'bytes': matches[0]['bytes']} if state == 'unique' else None),
                            'candidates': [item['file'] for item in matches]})
    by_identity = {(row['family'], row['side'], row['level6_index']): row for row in entries}
    for row in entries:
        if row['side'] not in ('CL', 'SL'):
            continue
        partner_side = 'CR' if row['side'] == 'CL' else 'SR'
        partner = by_identity.get((row['family'], partner_side, row['level6_index'] + 500))
        if (partner is None or partner['acronym'] != row['acronym'] or
                partner['level6_name'] != row['level6_name']):
            raise ValueError(f"{row['family']} level-6 left/right +500 identity mismatch")
    entries.sort(key=lambda row: (row['family'], row['side'], row['level6_index'], row['acronym'].casefold()))
    ids = [(row['family'], row['side'], row['level6_index']) for row in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate hierarchy level-6 identity')
    if used_aliases != set(alias_rows):
        raise ValueError('reviewed alias is absent from hierarchy or not used on both sides')
    counts = {family: {state: sum(row['family'] == family and row['status'] == state for row in entries)
                       for state in ('unique', 'missing', 'ambiguous', 'unverified_alias')}
              for family in _PREFIXES}
    return {'schema': 'vispa-nmt-level6-region-obj-map.v2',
            'source_sha256': {'CHARM': _sha(charm), 'SARM': _sha(sarm), 'mesh_manifest': _sha(manifest),
                              'reviewed_aliases': _sha(aliases) if aliases else None},
            'coordinate_handling': 'stored mesh coordinates; no inferred side transform',
            'mapping_rule': 'exact full level-6 name or exact reviewed nomenclature alias; acronym-only refused',
            'counts': counts, 'entries': entries}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--charm', type=Path, required=True)
    parser.add_argument('--sarm', type=Path, required=True)
    parser.add_argument('--mesh-manifest', type=Path, required=True)
    parser.add_argument('--aliases', type=Path, help='exact reviewed spelling/punctuation aliases')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('fresh output path required')
    report = build_map(args.charm, args.sarm, args.mesh_manifest, args.aliases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'counts': report['counts']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
