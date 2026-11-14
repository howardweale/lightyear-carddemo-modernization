"""CI only: private dual freeze; publish one allowlisted hash-only receipt."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from tools import intcalc_attended_freeze as module


def inventory(root):
    rows = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise module.Refused('output-symlink')
        if p.is_file():
            rows[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    if not rows:
        raise module.Refused('output-empty')
    return rows


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise module.Refused('ci-only-equivalence')
    p = module.Parser()
    p.add_argument('--source', required=True)
    p.add_argument('--scratch')
    p.add_argument('--receipt')
    p.add_argument('--entry-sha256')
    p.add_argument('--source-admission-only', action='store_true')
    a = p.parse_args()
    source = Path(a.source).resolve(strict=True)
    controller_path = source / 'tools/intcalc_attended_freeze.py'
    commit = module.git(source, 'rev-parse', 'HEAD').decode().strip()
    tree = module.git(source, 'rev-parse', 'HEAD^{tree}').decode().strip()
    module.source_admission(str(source), commit, tree)
    if a.source_admission_only:
        print('source-admission-match')
        return
    module.need(all((a.scratch, a.receipt, a.entry_sha256)), 'arguments')
    os.umask(0o077)
    scratch = Path(a.scratch)
    module.need(not os.path.lexists(scratch), 'scratch-exists')
    scratch.mkdir(mode=0o700)
    verifier = scratch / 'verifier'
    verifier.mkdir(mode=0o700)
    # Only network operation in this command: the existing exact bundle asset fetch.
    url = 'https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/full-intcalc-c1-proposal-r3/VERIFIER-CASES.zip'
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read(1024 * 1024 + 1)
    module.need(len(raw) <= 1024 * 1024 and module.sha(raw) == module.BUNDLE_HASH, 'fetch-hash')
    archive = verifier / 'VERIFIER-CASES.zip'
    module.exclusive(archive, raw)
    for name, content in module.bundle_files(str(archive)).items():
        module.exclusive(verifier / name, content)
    original_out, attended_out = scratch / 'ci-frozen', scratch / 'attended-frozen'
    entry = scratch / 'attended-freeze-entry.py'
    module.exclusive(entry, module.build_entry((verifier / 'freeze.py').read_bytes(), controller_path.read_bytes()))
    module.need(module.is_hash(a.entry_sha256) and module.sha(entry.read_bytes()) == a.entry_sha256, 'entry-hash')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join((str(source / 'src'), str(source))))
    # GITHUB_ACTIONS comes from the actual CI runner; never fabricated or forwarded to the attended child.
    private_log = os.open(scratch / 'qualification-private.log', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        result = subprocess.run([sys.executable, '-B', str(verifier / 'freeze.py'), '--root', str(source),
                                 '--output', str(original_out)], stdout=private_log, stderr=private_log,
                                cwd=source, env=env, timeout=595)
        module.need(result.returncode == 0, 'original-freeze-exit')
        module.child(entry, dict(source=str(source), archive=str(archive), output=str(attended_out),
                                 commit=commit, tree=tree), private_log)
    finally:
        os.close(private_log)
    left, right = inventory(original_out), inventory(attended_out)
    module.need(left == right, 'equivalence-difference')
    receipt = dict(schema='c2-attended-freeze-equivalence/2', source_commit=commit, source_tree=tree,
                   source_event=os.environ.get('GITHUB_EVENT_NAME'), source_ref=os.environ.get('GITHUB_REF'),
                   bundle_sha256=module.BUNDLE_HASH, controller_sha256=module.sha(controller_path.read_bytes()),
                   entry_sha256=module.sha(entry.read_bytes()), case_manifest_sha256=left['case-manifest.json'],
                   outputs_sha256=module.sha(module.canonical(left)), equal=True, candidate_executed=False, model_calls=0)
    module.validate_receipt(receipt, require_main=False)
    # No filenames, cases, per-case results or logs in the published receipt.
    receipt_path = Path(a.receipt)
    module.exclusive(receipt_path, module.canonical(receipt))
    print('equivalence-hash-receipt-ready')


if __name__ == '__main__':
    try:
        main()
    except module.Refused as exc:
        print(module.public_code(exc, 'equivalence-refused'))
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        print('operator-interrupted')
        raise SystemExit(130) from None
    except BaseException:
        print('equivalence-refused')
        raise SystemExit(2) from None
