"""Per-run pinned reference qualification and separately authorized PUBLIC freeze.

No registry publication, private seed, hidden suite, answer encryption or model.
The existing comparison runner remains unchanged, including its raw report.
"""
import argparse
import copy
import os
from pathlib import Path
import re
import subprocess

from tools import intcalc_reference_execution as ref
from tools import intcalc_reference_provisional as provisional
from tools import intcalc_reference_provisional_container as container

BINDING = 'spec/reference-qualification/2026-11-17-per-run-r1/BINDING.json'
BUILD_LIMIT = 'reference built per run from pinned public packages; no published image digest'
LIMITS = [ref.LIMIT, ref.SIGN_LIMIT, BUILD_LIMIT]


def require(ok, code):
    ref.require(ok, code)


def read(path):
    require(not path.is_symlink() and path.is_file(), 'qualification-file')
    return ref.bounded(path)


def load_binding():
    raw = read(ref.ROOT / BINDING)
    row = ref.strict(raw)
    require(row['schema'] == 'reference-per-run-binding/1'
            and row['platform'] == 'linux/amd64'
            and row['named_limits'] == LIMITS
            and row['image_publication'] is False
            and row['hidden_freeze'] is False, 'qualification-binding')
    for entry in row['sources']:
        ref.joined(ref.ROOT, entry)
    request = ref.ROOT / row['request']['path']
    ref.joined(ref.ROOT, row['request'])
    req, source, suite, probes, inventory_hash = provisional.check_inputs(request)
    require(inventory_hash == row['package_library_sha256'], 'qualification-inventory-binding')
    require(req['suite']['sha256'] == row['public_suite_sha256'], 'qualification-suite-binding')
    require(ref.sha(ref.joined(ref.ROOT, row['recipe'])) == row['recipe']['sha256'], 'qualification-recipe')
    require(ref.sha(ref.joined(ref.ROOT, row['installer'])) == row['installer']['sha256'], 'qualification-installer')
    return row, ref.sha(raw), req, suite, probes, source


def identity():
    def git(*args):
        p = subprocess.run(['git', '-C', str(ref.ROOT), *args], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        require(p.returncode == 0, 'qualification-source')
        return p.stdout.decode('ascii').strip()
    commit, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
    require(re.fullmatch('[a-f0-9]{40}', commit) is not None
            and re.fullmatch('[a-f0-9]{40}', tree) is not None
            and not git('status', '--porcelain', '--untracked-files=no'), 'qualification-source')
    require(os.environ.get('GITHUB_SHA') == commit, 'qualification-head')
    return commit, tree


def attest(report, row, req, suite, probes, source):
    """Recheck exact sets and comparison statuses, never trust summary booleans."""
    require(report['request_sha256'] == req
            and report['public_suite_sha256'] == row['public_suite_sha256']
            and report['package_library_sha256'] == row['package_library_sha256'], 'qualification-join')
    require([p['id'] for p in report['probes']] == [p['id'] for p in probes], 'qualification-probes')
    for actual, expected in zip(report['probes'], probes):
        recomputed = provisional.probe_result(expected, actual['exit'], bytes.fromhex(actual['stdout_hex']),
                                             bytes.fromhex(actual['stderr_hex']), source['reference_findings'])
        require(actual == recomputed, 'qualification-probe-readback')
    require([c['id'] for c in report['cases']] == [c['id'] for c in suite['cases']], 'qualification-cases')
    good = all(p['comparison_criterion_met'] for p in report['probes'])
    for actual, case in zip(report['cases'], suite['cases']):
        files = ref.comparison_policy(case)
        require(actual['compare_output_files'] == files, 'qualification-comparison-policy')
        pairs = actual['comparisons']
        require([p['pair'] for p in pairs] == ['reference-hand', 'reference-python', 'hand-python'], 'qualification-pairs')
        for pair in pairs:
            require(set(pair['channels']) == {'ACCTFILE', 'TRANSACT', 'stdout', 'stderr', 'exit', 'success_class'}, 'qualification-channels')
            for channel, result in pair['channels'].items():
                status = result['status']
                if channel in ('ACCTFILE', 'TRANSACT') and not files:
                    require(status == 'NOT_COMPARED', 'qualification-abend-policy')
                elif pair['pair'] == 'reference-hand':
                    if channel == 'success_class':
                        require(status == 'NOT_COMPARED', 'qualification-success-class')
                    else:
                        require(status in ('MATCH', 'DIFFERENT'), 'qualification-reference-hand')
                        good &= status == 'MATCH'
                elif channel in ('stdout', 'stderr', 'exit'):
                    require(status == 'NOT_MODELLED', 'qualification-python-policy')
                elif status == 'PREREGISTERED_FINDING':
                    digest = ref.sha(ref.canonical(result['difference']))
                    require(digest == result['difference_sha256'] and any(
                        f['pair'] == pair['pair'] and f['channel'] == channel
                        and f['difference_sha256'] == digest
                        and f['finding'] in result['findings'] for f in case.get('python_findings', [])),
                        'qualification-python-finding')
                else:
                    require(status in ('MATCH', 'DIFFERENT'), 'qualification-python-status')
                    good &= status == 'MATCH'
    return bool(good)


def observation_inventory(output, suite, probes):
    """Only fixed PUBLIC observation paths; no recursive collection or private data."""
    paths = ['report.json', 'inventory.json', 'container-cleanup.json']
    for case in suite['cases']:
        channels = ['stdout', 'stderr'] + (['ACCTFILE', 'TRANSACT'] if ref.comparison_policy(case) else [])
        for label in ('reference', 'python', 'hand'):
            paths += ['public/' + case['id'] + '/observations/' + label + '/' + c for c in channels]
        paths.append('public/' + case['id'] + '/observations/reference/stderr.raw')
    for probe in probes:
        paths += ['public/probe-' + probe['id'] + '/observations/' + c for c in ('stdout', 'stderr')]
    return [dict(path=p, sha256=ref.sha(read(output / p)), bytes=len(read(output / p))) for p in sorted(paths)]


def qualify(image, output):
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') == 'refs/heads/main', 'qualification-main-ci-only')
    row, binding_hash, req, suite, probes, source = load_binding()
    before = identity()
    require(not output.exists() and not output.is_symlink(), 'fresh-destination')
    status = container.execute(ref.ROOT / row['request']['path'], image, output)
    report = ref.strict(read(output / 'report.json'))
    inventory = ref.strict(read(output / 'inventory.json'))
    cleanup = ref.strict(read(output / 'container-cleanup.json'))
    require(provisional.inventory_digest(inventory) == row['package_library_sha256'], 'qualification-inventory')
    require(ref.sha(read(output / 'inventory.json')) == report['inventory_sha256'], 'qualification-inventory-join')
    require(cleanup['removed_and_absent'] is True and cleanup['local_image_id'] == image, 'qualification-cleanup')
    good = attest(report, row, row['request']['sha256'], suite, probes, source)
    require((status == 0) == good, 'qualification-exit')
    require(identity() == before and load_binding()[1] == binding_hash, 'qualification-source-changed')
    receipt = dict(schema='intcalc-reference-qualification/1', source_commit=before[0], source_tree=before[1],
        binding_sha256=binding_hash, public_suite_sha256=row['public_suite_sha256'],
        package_library_sha256=row['package_library_sha256'], local_image_id=image,
        image_digest_bound=False, published_image=False, named_limits=LIMITS,
        reference='GnuCOBOL execution of unmodified public COBOL source; never z/OS',
        status='CRITERION_MET' if good else 'DISCREPANCY', comparison_criterion_met=good,
        all_probes_match=all(p['match'] for p in report['probes']),
        qualified=False, adoption_pending=True, freeze_performed=False,
        observations=observation_inventory(output, suite, probes))
    ref.exclusive(output / 'qualification.json', ref.canonical(receipt) + b'\n')
    print('reference-qualification-criterion-met' if good else 'reference-qualification-discrepancy')
    return 0 if good else 2


def approve(receipt, receipt_hash, binding_hash, approval, approved_hash, raw):
    require(ref.sha(raw) == approved_hash and re.fullmatch('[a-f0-9]{64}', approved_hash), 'freeze-approval-hash')
    require(set(approval) == {'schema', 'authority', 'source_commit', 'source_tree', 'binding_sha256',
        'qualification_sha256', 'adopt_reference', 'authorize_public_freeze', 'scope'}, 'freeze-approval-shape')
    require(approval['schema'] == 'reference-adoption-and-public-freeze/1' and approval['authority'] == 'Howard'
        and approval['scope'] == 'PC-01..PC-16 only; no hidden set'
        and approval['adopt_reference'] is True and approval['authorize_public_freeze'] is True
        and approval['binding_sha256'] == binding_hash == receipt['binding_sha256']
        and approval['qualification_sha256'] == receipt_hash
        and approval['source_commit'] == receipt['source_commit']
        and approval['source_tree'] == receipt['source_tree'], 'freeze-approval-join')


def freeze(evidence, destination, approval_path, approved_hash):
    """Separate Howard-approved CI invocation; never automatic after qualification.

    Approval hash is an operator-reviewed input, not a signature or attestation.
    Only the 16 PUBLIC cases are supported. No private output may enter this tool.
    """
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') == 'refs/heads/main', 'freeze-main-ci-only')
    row, binding_hash, req, suite, probes, source = load_binding()
    raw = read(evidence / 'qualification.json'); receipt = ref.strict(raw)
    require(receipt['schema'] == 'intcalc-reference-qualification/1' and receipt['comparison_criterion_met'] is True
        and receipt['status'] == 'CRITERION_MET' and receipt['named_limits'] == LIMITS, 'freeze-criterion')
    approval_raw = read(approval_path)
    approve(receipt, ref.sha(raw), binding_hash, ref.strict(approval_raw), approved_hash, approval_raw)
    require(identity() == (receipt['source_commit'], receipt['source_tree']), 'freeze-source')
    require(observation_inventory(evidence, suite, probes) == receipt['observations'], 'freeze-observations')
    report = ref.strict(read(evidence / 'report.json'))
    require(attest(report, row, row['request']['sha256'], suite, probes, source), 'freeze-criterion')
    require(provisional.inventory_digest(ref.strict(read(evidence / 'inventory.json'))) == row['package_library_sha256'], 'freeze-inventory')
    require(ref.strict(read(evidence / 'container-cleanup.json'))['removed_and_absent'] is True, 'freeze-cleanup')
    require(not destination.exists() and not destination.is_symlink(), 'fresh-destination')
    # Complete all joins before writing. Reference output must equal independent
    # hand bytes exactly; abend output files remain unspecified and are omitted.
    planned = []
    for case in suite['cases']:
        outputs = {}
        for channel, descriptor in case['hand_outputs'].items():
            data = read(evidence / 'public' / case['id'] / 'observations/reference' / channel)
            require(data == ref.joined((ref.ROOT / req['suite']['path']).parent, descriptor), 'freeze-reference-hand')
            relative = case['id'] + '/' + channel
            outputs[channel] = dict(path=relative, sha256=ref.sha(data), bytes=len(data))
            planned.append((relative, data))
        planned.append((case['id'] + '/expected.json', ref.canonical(dict(
            exit=case['hand_exit'], compare_output_files=ref.comparison_policy(case), outputs=outputs)) + b'\n'))
    destination.mkdir(mode=0o700)
    manifest = dict(schema='reference-public-answer-key/1', visibility='public',
        source_commit=receipt['source_commit'], source_tree=receipt['source_tree'],
        qualification_sha256=ref.sha(raw), approval_sha256=approved_hash, binding_sha256=binding_hash,
        public_suite_sha256=row['public_suite_sha256'], named_limits=LIMITS, files=[])
    for relative, data in planned:
        ref.exclusive(destination / relative, data)
        require(read(destination / relative) == data, 'freeze-readback')
        manifest['files'].append(dict(path=relative, sha256=ref.sha(data), bytes=len(data)))
    # Final manifest is written last. A partial failed directory is not admissible.
    ref.exclusive(destination / 'MANIFEST.json', ref.canonical(manifest) + b'\n')
    print('reference-public-freeze-complete')
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('check', 'qualify', 'freeze-public'))
    p.add_argument('--image-id'); p.add_argument('--output', type=Path)
    p.add_argument('--evidence', type=Path); p.add_argument('--approval', type=Path)
    p.add_argument('--approval-sha256')
    args = p.parse_args(argv)
    try:
        if args.mode == 'check':
            load_binding(); print('reference-per-run-binding-match'); return 0
        require(args.output is not None, 'qualification-arguments')
        if args.mode == 'qualify':
            require(args.image_id is not None, 'qualification-arguments')
            return qualify(args.image_id, args.output)
        require(args.evidence is not None and args.approval is not None and args.approval_sha256 is not None, 'qualification-arguments')
        return freeze(args.evidence, args.output, args.approval, args.approval_sha256)
    except ref.Refused as exc:
        print(str(exc)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
