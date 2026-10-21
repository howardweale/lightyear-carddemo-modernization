"""Release evidence checks; call only after verifying the judge verdict signature.

Snapshots are judge-attested, hash-bound observations, not live GitHub queries.
The production review key designation is external trust, never an input-packet field.
"""
from datetime import datetime
from hashlib import sha256
import json
import re

from lightyear_control_tower.requests import confined

NAMES = (
    'qualified-oracle-required',
    'release-run-required',
    'verified-retained-evidence-required',
    'protected-main-campaign-required',
    'production-review-proofs-required',
    'supported-claim-scope-required',
)
SHA = re.compile(r'[0-9a-f]{64}')
HEAD = re.compile(r'[0-9a-f]{40}')


def _need(value):
    if not value:
        raise ValueError('release-grade-evidence')


def _record(root, ref):
    _need(root is not None and isinstance(ref, dict) and set(ref) == {'path', 'sha256'})
    _need(isinstance(ref['sha256'], str) and SHA.fullmatch(ref['sha256']))
    raw = confined(root, ref['path']).read_bytes()
    _need(sha256(raw).hexdigest() == ref['sha256'])
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _campaign(verdict, grade, root):
    row = _record(root, grade['campaign'])
    _need(row['schema'] == 'release-grade-campaign/1')
    _need(row['repository'] == 'howardweale/lightyear-carddemo-modernization')
    _need(HEAD.fullmatch(row['head']) and row['head'] == verdict['evidence_head'])
    _need(row['branch'] == 'main' and row['event'] == 'push')
    _need(type(row['run_id']) is int and row['run_id'] > 0)
    _need(datetime.fromisoformat(row['observed_at'].replace('Z', '+00:00')).tzinfo is not None)
    _need(row['protection']['strict'] is True)
    required = {(x['name'], x['app_id']) for x in row['protection']['required_checks']}
    _need({('required-ci', 15368), ('documentation-and-lint', 15368)} <= required)
    checks = row['checks']
    _need(checks and all(x['head'] == row['head'] and x['status'] == 'completed'
                        and x['conclusion'] == 'success' for x in checks))
    _need(required <= {(x['name'], x['app_id']) for x in checks})
    expected = row['applicable_workflows']
    workflows = row['workflows']
    _need(expected and len(set(expected)) == len(expected))
    _need(len(workflows) == len(expected) and {x['path'] for x in workflows} == set(expected))
    _need(row['run_id'] in {x['run_id'] for x in workflows})
    for workflow in workflows:
        _need(workflow['head'] == row['head'] and workflow['event'] == 'push'
              and workflow['branch'] == 'main' and workflow['status'] == 'completed'
              and workflow['conclusion'] == 'success')
        jobs = workflow['applicable_jobs']
        _need(jobs and all(j['status'] == 'completed' and j['conclusion'] == 'success' for j in jobs))
        for job in jobs:
            steps = job['applicable_steps']
            _need(steps and all(step['status'] == 'completed' and step['conclusion'] == 'success' for step in steps))
    return row


def _retained(verdict, grade, root):
    manifest = _record(root, grade['retention_manifest'])
    receipt = _record(root, grade['retention_verification'])
    _need(manifest['schema'] == 'public-evidence-retention/1')
    _need(manifest['repository'] == 'howardweale/lightyear-carddemo-modernization')
    _need(manifest['scope'] == 'public CardDemo only')
    _need(manifest['source_head'] == verdict['evidence_head'])
    _need(receipt['schema'] == 'public-evidence-retention-verification/1')
    _need(receipt['manifest_sha256'] == grade['retention_manifest']['sha256'])
    expected = manifest['assets']
    actual = receipt['assets']
    _need(expected and len(expected) == len(actual))
    _need(len({x['url'] for x in expected}) == len(expected))
    _need(len({x['url'] for x in actual}) == len(actual))
    observed = {x['url']: x for x in actual}
    for asset in expected:
        _need(asset['url'].startswith('https://github.com/'+manifest['repository']+'/releases/download/'))
        _need(type(asset['bytes']) is int and asset['bytes'] > 0 and SHA.fullmatch(asset['sha256']))
        checked = observed[asset['url']]
        _need(checked['verified'] is True and checked['bytes'] == asset['bytes']
              and checked['sha256'] == asset['sha256'])
    campaign = _record(root, grade['campaign'])
    _need(manifest['source_run'] == campaign['run_id'] and manifest['source_head'] == campaign['head'])


def checklist(verdict, *, root=None, scope=None, review_key=None,
              production_review_key_sha256=None, reviews_verified=False):
    """Never verifies signatures itself; release() supplies already-verified facts.

    No default key is production. Its fingerprint must be designated by the
    operator outside the verdict/bundle, like the existing trusted journal head.
    A native claim remains blocked until a typed native release verifier exists.
    """
    grade = verdict.get('release_grade', {})
    if not isinstance(grade, dict):
        grade = {}
    checks = {name: False for name in NAMES}
    checks[NAMES[0]] = verdict.get('oracle_status') == 'qualified'
    checks[NAMES[1]] = verdict.get('run_class') == 'release'
    for name, verifier in ((NAMES[2], _retained), (NAMES[3], _campaign)):
        try:
            verifier(verdict, grade, root)
            checks[name] = True
        except (KeyError, TypeError, ValueError, OSError, AttributeError):
            pass
    checks[NAMES[4]] = bool(
        reviews_verified and isinstance(review_key, bytes)
        and isinstance(production_review_key_sha256, str)
        and SHA.fullmatch(production_review_key_sha256)
        and sha256(review_key).hexdigest() == production_review_key_sha256
        and verdict.get('fixture_only') is False
        and verdict.get('disposable_ci_signatures_only') is False)
    checks[NAMES[5]] = bool(scope == 'twin' and grade.get('claim_scope') == scope
                           and grade.get('native_runtime_claimed') is False)
    return checks


def reasons(checks):
    return [name for name in NAMES if not checks[name]]


def paragraph(checks):
    missing = reasons(checks)
    return ('Release evidence checklist: '+('; '.join(missing) if missing else 'all items satisfied')
            +'. Scenario, signature and threshold gates still apply.')
