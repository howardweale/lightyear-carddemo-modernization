"""Offline inventory of runtime identities. Enumeration is not class resolution."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, seal
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_admission import check
from tools.ms94_b06_posting_replay import FRAMEWORK, TERMINAL

CLASSES = sorted(FRAMEWORK | {TERMINAL, 'org.junit.platform.engine.support.hierarchical.NodeTestTask'})


def inventory(extraction):
    rows = []
    for name in CLASSES:
        member = name.replace('.', '/') + '.class'
        copies = [c for c in extraction['classes'] if c['member'] == member]
        application = [c for c in copies if c['origin'].startswith('/application/')]
        hashes = {c['sha256'] for c in application}
        check(len(hashes) == 1, 'classpath-application-copy-ambiguous')
        expected = next(iter(hashes))
        cache = [c for c in copies if c['origin'].startswith('/root/.m2/')]
        rows.append({'class': name, 'application_sha256': expected,
                     'application_origins': sorted(c['origin'] for c in application),
                     'm2_copies': sorted(cache, key=lambda c: c['origin']),
                     'differing_m2_copies': sorted((c for c in cache if c['sha256'] != expected),
                                                  key=lambda c: c['origin']),
                     'resolved_origin': None, 'loaded_copy_confirmed': False})
    return rows


def audit(path):
    path = Path(path); extraction = read_json(path)
    return seal({'artifact_type': 'ms94-b06-offline-classpath-audit/1',
                 'extraction_file_sha256': file_hash(path),
                 'classes': inventory(extraction), 'runtime_resolution_confirmed': False,
                 'blocker': 'Resolved Tycho/Surefire and OSGi classpath evidence was not captured.',
                 'docker_runs': 0, 'model_calls': 0, 'native_pairs': 0,
                 'review': 'operator review; not independent attestation'})
