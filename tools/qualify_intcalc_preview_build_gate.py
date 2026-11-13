"""CI-only real ARM fixture path. Never prints private verifier output."""
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time

from lightyear_factory import intcalc_preview_build_gate as b
from lightyear_factory import intcalc_preview_composition as c
from lightyear_mainframe import intcalc_candidate_gate as g

EXPECTED = {'NZ-POSTTRAN': 'DIFFERENT', 'TRUNCATION': 'DIFFERENT',
    'DEFAULT': 'DIFFERENT', 'ZERO-RATE': 'DIFFERENT', 'ACCOUNT-BREAK': 'DIFFERENT',
    'FINAL-ACCOUNT': 'DIFFERENT', 'EMPTY-INPUT': 'MATCH',
    'ERR-NO-RATE': 'REFUSAL_NOT_OBSERVED', 'ERR-NO-ACCOUNT': 'REFUSAL_NOT_OBSERVED',
    'ERR-NO-XREF': 'REFUSAL_NOT_OBSERVED'}


def run():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    assert os.environ.get('RUNNER_ARCH') == 'ARM64'
    assert sys.platform == 'linux' and platform.machine() in ('aarch64', 'arm64')
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    root = temp / 'c2-build-gate-private'
    root.mkdir(mode=0o700)
    manifest = temp / 'intcalc-frozen/case-manifest.json'
    manifest_hash = c.digest(manifest.read_bytes())
    gate_hash = c.digest(Path(g.__file__).read_bytes())
    # Structural CI fixture only: these synthetic joins are never admission or
    # spend evidence. No transport or admission object is constructed.
    packet = {k: '0' * 64 for k in c.HASH_FIELDS}
    packet.update(schema='full-intcalc-composition-packet/1', controller_platform='darwin/arm64',
        runtime_platform='linux/arm64', emulation=False, byte_policy_sha256='STRICT',
        run_budget_seconds=8100, cap_microdollars=c.CAP,
        prerequisites={k: {'status': 'MISSING', 'evidence_sha256': None} for k in c.PREREQUISITES},
        runtime_manifest_sha256=b.JRE, runtime_config_sha256=b.JRE_CONFIG,
        toolchain_manifest_sha256=b.JDK, javac_sha256=b.JAVAC, jar_sha256=b.JAR_TOOL,
        context_sha256=c.CONTEXT_HASH, allowlist_sha256=c.ALLOWLIST_HASH,
        feedback_schema_sha256=c.FEEDBACK_HASH, named_limit_sha256=c.LIMIT_HASH,
        budget_policy_sha256=c.BUDGET_POLICY_SHA256, case_manifest_sha256=manifest_hash,
        gate_manifest_sha256=gate_hash)
    b.pins(packet)
    binding = dict(schema='full-intcalc-c1/2', upstream=g.UPSTREAM,
        case_manifest=dict(path='intcalc-frozen/case-manifest.json', sha256=manifest_hash),
        artifact=dict(path='unused.jar', sha256='0' * 64), runtime_platform='linux/arm64',
        runtime_image='docker.io/library/eclipse-temurin@sha256:' + b.JRE,
        java=g.COMMAND[0], command_template=g.COMMAND, max_elapsed_seconds=600,
        qualified=False, production_controller_receipt=False)
    binding_path = temp / 'c2-ci-binding.json'
    b.exclusive(binding_path, c.canonical(binding))
    # Linux qualification invokes the identical parent/exec-worker methods. The
    # live constructor remains Mac-only; no production platform bypass is added.
    adapter = object.__new__(b.BuildGateAdapter)
    adapter.packet, adapter.root = packet, root
    adapter.config = root / 'docker-config'
    adapter.config.mkdir(mode=0o700)
    adapter.prefix = [str(Path(shutil.which('docker')).resolve()), '--config', str(adapter.config),
                      '--host', 'unix:///var/run/docker.sock']
    adapter.binding, adapter.binding_hash = str(binding_path), c.digest(binding_path.read_bytes())
    adapter.gate_hash, adapter.pid = gate_hash, os.getpid()
    adapter.next_build = adapter.next_gate = 1
    adapter.built = {}
    original = time.monotonic() + 1800
    def window():
        return c.PhaseWindow(min(time.monotonic() + 600, original), original)
    source = Path('tests/fixtures/intcalc-c1/Main.java').read_text(encoding='utf-8')
    built = adapter.build(1, source, window())
    assert not built.compile_failed and built.cleanup_confirmed
    result = adapter.gate(1, built, window())
    private = root / 'gate-1/private-gate'
    report = json.loads((private / 'result.json').read_bytes())
    assert {r['id']: r['verdict'] for r in report['cases']} == EXPECTED
    for case in EXPECTED:
        runtime = json.loads((private / case / 'runtime.json').read_bytes())
        assert runtime['cleanup_confirmed'] and runtime['cleanup_allowance_seconds'] == 18
        assert runtime['runtime_platform'] == runtime['observed_daemon_platform'] == 'linux/arm64'
    invalid = adapter.build(2, 'public class Main { invalid syntax }', window())
    assert invalid.compile_failed and invalid.artifact_sha256 is None
    assert invalid.compiler_exit_code == 1 and invalid.cleanup_confirmed
    c.validate_compile_feedback(dict(schema=c.COMPILE_SCHEMA, kind='compilation-failed',
        javac_stderr=invalid.compiler_stderr, stderr_truncated=invalid.compiler_stderr_truncated))
    cleanup = []
    for name in ('build-1', 'gate-1', 'build-2'):
        registry = b.Registry(root / name / 'resources')
        assert registry.entries() == []
        originals = [p for p in registry.root.iterdir() if not p.name.startswith('removed-')]
        assert originals
        for p in originals:
            row = json.loads(p.read_bytes())
            assert (registry.root / ('removed-' + p.name)).read_bytes() == p.read_bytes()
            probe = b.capture([*adapter.prefix, row['kind'], 'inspect', row['name']],
                              time.monotonic() + 10, time.monotonic() + 12)
            marker = ('no such ' + row['kind']).encode()
            assert probe['rc'] == 1 and marker in probe['stderr'].lower()
            cleanup.append(dict(kind=row['kind'], resource_sha256=c.digest(row['name'].encode()),
                                removal_record_sha256=c.digest(p.read_bytes()), absence_confirmed=True))
        for suffix in ('worker-cleanup.json', 'parent-cleanup.json'):
            assert json.loads((root / name / suffix).read_bytes())['cleanup_confirmed'] is True
    # Closed publication projection: never archive private directories, per-case
    # output, stderr, cases or bundle. Only counts, hashes and cleanup records.
    public = dict(verdict_counts=c.feedback(result.verdicts)['verdict_counts'],
        hashes=dict(source=c.digest(source.encode()), artifact=built.artifact_sha256,
                    gate_source=gate_hash, case_manifest=manifest_hash,
                    build_receipt=built.receipt_sha256, gate_receipt=result.receipt_sha256),
        cleanup=cleanup)
    (temp / 'c2-build-gate-public.json').write_bytes(c.canonical(public))


if __name__ == '__main__':
    try:
        run()
    except BaseException:
        print('C2 ARM QUALIFICATION FAILED; PRIVATE EVIDENCE NOT PRINTED', file=sys.stderr)
        raise SystemExit(2) from None
