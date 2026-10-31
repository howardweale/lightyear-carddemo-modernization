"""Prepare external PUBLIC trust inputs; no signing or execution admission."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

PUBLIC_KEY = 'docs/factory/posttran-key-change-2026-10-23/authority.public.pem'
PUBLIC_KEY_SHA256 = '658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a'
PLAN = 'docs/factory/p5-human-clean-control/configured-build-control/plan.json'
REPOSITORY = 'howardweale/lightyear-carddemo-modernization'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate_public_configuration(environment, actual_head, plan):
    """Configuration checks only; native proof verification is still required."""
    require(environment.get('GITHUB_ACTIONS') == 'true'
            and environment.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and environment.get('GITHUB_REF') == 'refs/heads/main'
            and environment.get('GITHUB_SHA') == actual_head
            and environment.get('GITHUB_WORKFLOW_SHA') == actual_head
            and environment.get('GITHUB_RUN_ATTEMPT') == '1'
            and environment.get('GITHUB_REPOSITORY') == REPOSITORY,
            'configured-trust-ci-scope')
    head = environment.get('P5_CONFIGURED_RECEIPT_APPROVED_HEAD', '')
    seal = environment.get('P5_CONFIGURED_RECEIPT_APPROVED_PLAN', '')
    journal = environment.get('P5_CONFIGURED_RECEIPT_JOURNAL_HEAD', '')
    require(re.fullmatch('[0-9a-f]{40}', head) is not None and actual_head == head,
            'configured-trust-approved-head')
    require(re.fullmatch('[0-9a-f]{64}', seal) is not None
            and re.fullmatch('[0-9a-f]{64}', journal) is not None,
            'configured-trust-independent-config')
    require(type(plan) is dict and plan.get('schema') == 'factory-build-plan/1',
            'configured-trust-plan-schema')
    digest = sha256(json.dumps({k: v for k, v in plan.items() if k != 'content_sha256'},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(plan.get('content_sha256') == seal == digest, 'configured-trust-approved-plan')
    # Do not load the proof here. A proof's asserted head is not independent trust.
    return dict(scope='factory', public_key='factory-authority.public.pem',
                journal_head_sha256=journal)


def prepare(root, target, environment):
    from lightyear_execution.configured_human_dispatch import _independent_source
    root = _independent_source(root)
    target = Path(target)
    require(not any(part.casefold()=='onedrive' for part in target.parts), 'configured-trust-onedrive-output')
    require(target.is_absolute() and not target.exists() and target.parent.is_dir()
            and not target.resolve().is_relative_to(root), 'configured-trust-new-external-directory')
    require(all(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
                for p in (target, *target.parents)), 'configured-trust-output-link')
    command = ['git', '--no-optional-locks', '-C', str(root)]
    require(not subprocess.check_output(command + ['status', '--porcelain=v1', '--untracked-files=all']),
            'configured-trust-dirty-source')
    head = subprocess.check_output(command + ['rev-parse', 'HEAD']).decode().strip()

    def committed(relative):
        path = root / relative
        require(all(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
                    for p in (path, *path.parents)), 'configured-trust-input-link')
        require(path.is_file() and path.stat().st_nlink == 1
                and path.stat().st_size <= 1048576, 'configured-trust-input-size')
        raw = path.read_bytes()
        require(len(raw) <= 1048576 and raw == subprocess.check_output(command + ['show', head + ':' + relative]),
                'configured-trust-committed-input')
        return raw

    public = committed(PUBLIC_KEY)
    require(sha256(public).hexdigest() == PUBLIC_KEY_SHA256, 'configured-trust-public-key-hash')
    config = validate_public_configuration(environment, head, json.loads(committed(PLAN)))
    target.mkdir()
    for name, raw in [('factory-authority.public.pem', public),
                      ('trust.json', (json.dumps(config, sort_keys=True) + '\n').encode())]:
        with (target / name).open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    require(not subprocess.check_output(command + ['status', '--porcelain=v1', '--untracked-files=all'])
            and subprocess.check_output(command + ['rev-parse', 'HEAD']).decode().strip() == head,
            'configured-trust-source-changed')
    return dict(status='public-trust-inputs-only', execution_authorized=False,
                proof_verified=False, nonce_consumed=False, signatures_created=0,
                approved_head=head, public_key_sha256=PUBLIC_KEY_SHA256)


def main(argv=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'configured-trust-ci-only')
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    result = prepare(args.source_root, args.output, os.environ)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
