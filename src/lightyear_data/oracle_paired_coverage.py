"""Read-only catalog overlay from signed paired campaigns; no legacy receipt rewrite.

Admission is specific to the bounded probe contract and Oracle 26ai. The older
wallet-based, two-Oracle-version gate is a different contract and is not advanced.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from lightyear_control_tower.decisions import digest, verify_envelope
from lightyear_data.contracts import content_hash
from lightyear_workflow import campaign_engine as engine, campaign_journals, paired_types as suite

PUBLISHED_KEY = '36fdf4766568b1880c1bddef92f450c6a41279d01ff11c0abd6f78e2215c6552'
BASELINE = Path('data-modernization/oracle-schema-structured-coverage/schema-structured.receipt.json')


def read_json(path):
    from lightyear_workflow.policy import _unique_object
    if path.is_symlink() or path.stat().st_size > 4_000_000:
        raise ValueError('Invalid coverage evidence file')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)


def admitted(root, auth, events, terminal, key):
    """Replay signed evidence and verify its catalog/SQL binding, not just totals."""
    engine.checked_authorization(auth, key)
    if (not verify_envelope(terminal, key) or terminal.get('record_type') != 'paired-campaign-summary'
            or terminal.get('run_id') != auth['run_id'] or terminal.get('authorization_sha256') != auth['content_sha256']):
        raise ValueError('Coverage summary signature or scope invalid')
    campaign_journals.exported(events, auth, key)
    if not events or events[-1]['type'] != 'terminal' or terminal['journal_head_sha256'] != events[-1]['content_sha256']:
        raise ValueError('Coverage requires a terminal journal matching its signed summary')
    selected = engine.campaign_cases(root, auth['campaign_id'])
    for case, bound in zip(selected, auth['plan']['cases'], strict=True):
        if bound['id'] != case['id'] or bound['behavior_id'] != case['behavior_id']:
            raise ValueError('Coverage catalog binding differs')
        for lane in ('oracle', 'alloydb'):
            if bound[lane + '_sql_sha256'] != hashlib.sha256(suite.render(case, lane).encode()).hexdigest():
                raise ValueError('Coverage SQL contract differs')
        if auth['campaign_id'] == suite.CAMPAIGN:
            if (bound['family'] != case['topic'] or bound['catalog_expectation_sha256'] != digest(case['expected'])
                    or bound['probe_contract_sha256'] != digest({lane: suite.expected(case, lane) for lane in ('oracle', 'alloydb')})):
                raise ValueError('Coverage expectation binding differs')
    value = engine.project(root, auth, events)
    for field in ('status', 'source_completed', 'target_completed', 'matched', 'cleanup', 'evidence_class'):
        if terminal[field] != value[field]:
            raise ValueError('Coverage summary differs from journal replay')
    if value['evidence_class'] != 'native-database-observed':
        return None  # The weakest evidence class wins, including an unlabelled lane.
    source, target = value['identities']['oracle'], value['identities']['alloydb']
    if (source.get('image') != auth['plan']['profile']['oracle_image'] or source.get('container') != 'FREEPDB1'
            or not source.get('version', '').startswith('23.26.') or '26ai' not in source.get('banner', '')
            or target.get('endpoint_verified') is not True or not target.get('version', '').startswith('16.')
            or target.get('resource') != 'projects/lightyear-ms67-nonproduction/locations/us-west1/clusters/cloudbank-ms71-alloydb/instances/primary'):
        raise ValueError('Native identity differs from paired coverage contract')
    return value


def evidence(root):
    """Pinned published keys and installed local trust, with duplicate run detection."""
    collected = {}
    def put(auth, events, terminal, key):
        prior = collected.get(auth['run_id'])
        if prior and (prior[0] != auth or prior[2] != terminal or prior[1] != events):
            raise ValueError('Conflicting evidence for one run')
        collected[auth['run_id']] = (auth, events, terminal, key)

    for manifest_path in sorted((root / 'docs/receipts').glob('oracle26ai-alloydb-*/manifest.json')):
        folder = manifest_path.parent
        manifest = read_json(manifest_path)
        key = (folder / 'public-key.pem').read_bytes()
        if hashlib.sha256(key).hexdigest() != PUBLISHED_KEY:
            raise ValueError('Untrusted published campaign key')
        for name, expected in manifest['files'].items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('Published evidence file missing or changed')
        for name in manifest['files']:
            if name.endswith('/authorization.json'):
                prefix = str(Path(name).parent).replace('\\', '/')
                if any(prefix + '/' + filename not in manifest['files'] for filename in ('journal.json', 'summary.json')):
                    raise ValueError('Incomplete published campaign')
                folder_run = folder / Path(name).parent
                put(read_json(folder_run / 'authorization.json'), read_json(folder_run / 'journal.json')['events'],
                    read_json(folder_run / 'summary.json'), key)
    # Active runs are displayed in The run; only terminal evidence enters coverage.
    if (root / engine.INDEX).exists():
        key = engine.public_key(root)
        for row in engine.records(root):
            if row['terminal']:
                auth = row['authorization']
                put(auth, engine.verified_events(root, auth), row['terminal'], key)
    return list(collected.values())


def project(root, entries):
    baseline = read_json(root / BASELINE)
    if baseline['content_sha256'] != content_hash(baseline):
        raise ValueError('Catalog baseline hash differs')
    latest, runs, excluded = {}, [], 0
    for auth, events, terminal, key in sorted(entries, key=lambda row: (datetime.fromisoformat(row[0]['authorized_at']), row[0]['run_id'])):
        value = admitted(root, auth, events, terminal, key)
        if value is None:
            excluded += 1
            continue
        runs.append(auth['run_id'])
        catalog = {c['id']: c for c in engine.campaign_cases(root, auth['campaign_id'])}
        # A later native observation supersedes a pass. A run with no observation
        # cannot erase an earlier measurement; simulations cannot supersede native.
        for item in value['case_results']:
            if item['oracle'] is not None or item['alloydb'] is not None:
                case = catalog[item['case_id']]
                latest[item['case_id']] = {**item, 'behavior_id': case['behavior_id'], 'family': case['topic'],
                                           'source_verified': item['oracle'] == suite.expected(case, 'oracle'), 'run_id': auth['run_id']}
    behaviors = {}
    for case in suite.cases(root):
        behaviors.setdefault(case['behavior_id'], []).append(case['id'])
    source_count = sum(v['oracle'] is not None for v in latest.values())
    source_verified = sum(v['source_verified'] for v in latest.values())
    paired_count = sum(bool(v['comparison'] and v['comparison']['equivalent']) for v in latest.values())
    native_behaviors = sum(all(i in latest and latest[i]['source_verified'] for i in ids) for ids in behaviors.values())
    paired_behaviors = sum(all(i in latest and latest[i]['comparison'] and latest[i]['comparison']['equivalent'] for i in ids) for ids in behaviors.values())
    return {'status': 'verified-paired-catalog-overlay', 'contract': 'bounded-paired-probes-v1',
            'catalogued_behavior_count': baseline['catalogued_behavior_count'],
            'catalogued_case_count': baseline['catalogued_case_specification_count'],
            'bounded_model_verified_behavior_count': baseline['bounded_model_verified_behavior_count'],
            'oracle26ai_executed_case_count': source_count, 'oracle26ai_verified_case_count': source_verified,
            'oracle26ai_verified_behavior_count': native_behaviors,
            'alloydb_equivalent_case_count': paired_count, 'alloydb_equivalent_behavior_count': paired_behaviors,
            'native_run_ids': runs, 'excluded_simulated_or_unclassified_runs': excluded,
            'cases': list(latest.values()), 'alloydb_platform_qualified': False,
            'coverage_statement': f"{baseline['bounded_model_verified_behavior_count']}/{baseline['catalogued_behavior_count']} behaviours have bounded-model coverage. Under the paired probe contract: {source_count} unique Oracle 26ai cases observed, {native_behaviors} behaviours verified, and {paired_count} unique cases equivalent on AlloyDB. NUMBER reruns are deduplicated.",
            'gate_note': 'The legacy 4,000-execution gate requires 2,000 cases on each of Oracle 19c and 26ai under its wallet receipt contract. This overlay does not alter that gate; AlloyDB executions never count as Oracle executions. No platform qualification.',
            'trust_note': 'Verified Ed25519 campaign authority, SQL bindings, journal chains and comparator replay. This is operator-signed evidence, not independent vendor certification. Latest native observation per case supersedes an earlier result.'}


def report(root):
    try:
        return project(root, evidence(root))
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, ImportError):
        return {'status': 'unavailable', 'coverage_statement': 'Catalog coverage could not be verified. Counts are unknown; no zero or previous pass is assumed.',
                'oracle26ai_executed_case_count': None, 'alloydb_equivalent_case_count': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    value = report(args.root.resolve())
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value['status'] == 'verified-paired-catalog-overlay' else 1)
