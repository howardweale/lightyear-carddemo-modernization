"""Retain CI component journals; this collector cannot qualify a factory run."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from lightyear_factory.contracts import canonical_hash
from tools.ci import p5_configured_exit_retention as probe

SOURCES = (
    'tools/ci/p5_configured_exit_collector.py',
    'tools/ci/p5_configured_exit_retention.py',
    'tests/test_p5_configured_exit_collector.py',
    'tests/test_p5_configured_exit_retention.py',
    'tests/test_p5_configured_count_component.py',
    'src/lightyear_factory/orchestrator.py',
    'src/lightyear_factory/providers.py',
    'src/lightyear_factory/transport_journal.py',
    'src/lightyear_factory/controller_count_accounting.py',
    'src/lightyear_factory/count_charge_account.py',
    'src/lightyear_factory/count_request_bound.py',
    'src/lightyear_factory/flex_billing.py',
    'src/lightyear_factory/budgeted_providers.py',
    'src/lightyear_factory/contracts.py',
    'src/lightyear_factory/ledger.py',
    'src/lightyear_factory/model_config.py',
    'src/lightyear_factory/model_versions.py',
    'src/lightyear_factory/additional_providers.py',
    'src/lightyear_factory/routing.py',
    'src/lightyear_factory/provider_secrets.py',
    'src/lightyear_factory/model_admission.py',
)
DOCUMENTS = ('attempt.jsonl', 'stub-sends.jsonl', 'models.json', 'child-result.json')


def collect(repository, output):
    repository, output = Path(repository), Path(output)
    if os.environ.get('GITHUB_ACTIONS') != 'true' or output.exists():
        raise ValueError('p5-configured-collector-ci-exclusive-output')
    source_hashes = {name: hashlib.sha256((repository/name).read_bytes()).hexdigest()
                     for name in SOURCES}
    output.mkdir(parents=True)
    report = dict(schema='p5-configured-exit-collection/1',
                  commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
                  scope=probe.SCOPE, source_sha256=source_hashes,
                  strict_qualified=False, production_controller_receipt=False,
                  admission_verified=False, signing=False, real_model_calls=0,
                  gaps=['Synthetic component identity and generation bounds; no admitted full-controller outcome.',
                        'Provider billing assumption COUNT-REQUEST-BOUND-01 remains unaccepted.'],
                  cases=[], original_documents={})
    for mode in probe.MODES:
        row = dict(id='configured-'+mode, mode=mode, expectation_met=False)
        directory = output/mode
        try:
            row['observed'] = probe.observe(repository, directory, mode)
            row['expectation_met'] = (probe.validate(row['observed']) is True
                                      and row['observed'].get('mode') == mode)
        except Exception as error:
            row['harness_error'] = type(error).__name__+': '+str(error)
        # Retain diagnostics even when observe refuses. The child uses only fixed
        # public synthetic inputs; never substitute these for an admitted receipt.
        for name in DOCUMENTS:
            path = directory/name
            if not path.exists():
                continue
            try:
                before = path.lstat()
                if path.is_symlink() or not path.is_file() or not 0 < before.st_size <= probe.LIMIT:
                    raise ValueError('p5-configured-collector-document')
                raw = path.read_bytes()
                after = path.lstat()
                fields = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if fields(before) != fields(after) or len(raw) != before.st_size:
                    raise ValueError('p5-configured-collector-document-changed')
                report['original_documents'][mode+'/'+name] = dict(
                    base64=base64.b64encode(raw).decode('ascii'),
                    sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            except Exception as error:
                row['expectation_met'] = False
                row.setdefault('retention_errors', []).append(type(error).__name__+': '+str(error))
        if row['expectation_met']:
            for name, retained in row['observed']['documents'].items():
                archived = report['original_documents'].get(mode+'/'+name)
                if archived is None or archived != retained:
                    row['expectation_met'] = False
                    row.setdefault('retention_errors', []).append('observed-original-mismatch:'+name)
        report['cases'].append(row)
    report['expectations_met'] = all(row['expectation_met'] for row in report['cases'])
    report['content_sha256'] = canonical_hash(report)
    (output/'observations.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n',
                                           encoding='utf-8')
    return report['expectations_met']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    raise SystemExit(0 if collect(Path(__file__).resolve().parents[2], arguments.output) else 1)
