"""Independent-machine twin build receipts; comparison never fabricates a second host."""
import argparse
import json
import platform
from pathlib import Path
from lightyear_mainframe.legacy_twin import build, receipt, sha, ROOT, FILES

BASE_IMAGE = 'ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b'


def expected_binaries():
    return {mode + "/" + job + "/bin/" + name
            for mode in ("ascii", "cp037") for job, descriptors in FILES.items()
            for name in ["twin", *(dd for dd, (_, key) in descriptors.items() if key)]}


def sealed(record):
    candidate = dict(record)
    seal = candidate.pop('content_sha256', None)
    if seal != sha(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()):
        raise ValueError('receipt-seal-mismatch')
    return record


def make(output, machine_id, host_kind, commit, base_image):
    if base_image != BASE_IMAGE or host_kind not in ('github-hosted', 'operator-machine'):
        raise ValueError('reproduction-host-or-image-mismatch')
    if not machine_id.strip() or len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('machine-identity-and-exact-commit-required')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    builds = {}
    for mode in ('ascii', 'cp037'):
        result = build(output / mode, cp037_keys=mode == 'cp037')
        builds[mode] = result['content_sha256']
        artifacts.update({mode + '/' + name: digest for name, digest in result['files'].items() if '/bin/' in name})
    if set(artifacts) != expected_binaries():
        raise ValueError('incomplete-compiled-binary-set')
    return receipt(output / 'reproduction.json', phase='independent-machine-build', machine_id=machine_id,
                   host_kind=host_kind, repository_commit=commit, base_image=base_image, platform='linux/amd64',
                   kernel=platform.release(), build_receipt_seals=builds, binaries=artifacts,
                   installer_sha256=sha((ROOT/'tools/legacy_twin/install-pinned.sh').read_bytes()),
                   second_machine_confirmed=False, model_calls=0)


def compare(first, second, output):
    a, b = (sealed(json.loads(Path(p).read_text(encoding='utf-8'))) for p in (first, second))
    if {a.get('host_kind'), b.get('host_kind')} != {'github-hosted', 'operator-machine'} or a.get('machine_id') == b.get('machine_id'):
        raise ValueError('independent-github-and-operator-machines-required')
    for field in ('repository_commit', 'base_image', 'platform', 'installer_sha256'):
        if a.get(field) != b.get(field):
            raise ValueError('reproduction-binding-mismatch:' + field)
    if a.get('base_image') != BASE_IMAGE or set(a.get('binaries', {})) != expected_binaries() or set(b.get('binaries', {})) != expected_binaries():
        raise ValueError('reproduction-artifact-set-mismatch')
    differences = [name for name in sorted(a['binaries']) if a['binaries'][name] != b['binaries'][name]]
    result = receipt(Path(output), phase='two-machine-build-comparison', receipt_seals=[a['content_sha256'], b['content_sha256']],
                     repository_commit=a['repository_commit'], base_image=BASE_IMAGE,
                     binary_count=len(a['binaries']), differences=differences, matched=not differences,
                     second_machine_confirmed=True, scope='Operator-declared machine identities; reproducibility only, not independent attestation or z/OS equivalence')
    if differences:
        raise ValueError('compiled-binary-hashes-differ; comparison-receipt-preserved')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest='command', required=True)
    m = s.add_parser('build')
    for name in ('output', 'machine-id', 'host-kind', 'commit', 'base-image'):
        m.add_argument('--' + name, required=True)
    c = s.add_parser('compare')
    c.add_argument('first'); c.add_argument('second'); c.add_argument('output')
    a = p.parse_args()
    if a.command == 'build':
        make(a.output, a.machine_id, a.host_kind, a.commit, a.base_image)
    else:
        compare(a.first, a.second, a.output)
