"""Exercise the existing batch lanes against loopback z/OSMF, with retained bytes."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path

from lightyear_runtime.mock_zosmf import RunningMockZosmf, load_mock_fixture
from lightyear_runtime.zosmf import HttpClientTransport, ZosmfClient, ZosmfConfig, ZosmfCredentials
from lightyear_workflow.batch_pack import SourceLane, TargetLane, load, plan
from lightyear_workflow.zosmf_reader import ZosmfReader

from .records import load_copybook, decode_fixed, decode_spool
from .source import sha


def dry_run(config_path: Path):
    config_path = config_path.resolve()
    base = config_path.parent
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    if config.get('schema_version') != '1.0' or config.get('evidence_class') != 'simulated':
        raise ValueError('arrival dry-run requires a versioned simulated kit')
    pack_path = base/config['pack']
    pack = load(pack_path)
    if set(config['jobs']) != {j.jobname for j in pack.jobs}:
        raise ValueError('kit bindings must cover every job in the pack exactly')
    manifest = {config_path.name: sha(config_bytes), config['pack']: sha(pack_path.read_bytes())}
    results, requests, submissions = [], [], []
    for job in pack.jobs:
        settings = config['jobs'][job.jobname]
        bindings = settings['bindings']
        if set(bindings) != {c.dataset for c in job.compare}:
            raise ValueError('output bindings must exactly match pack comparisons')
        for binding in bindings.values():
            if binding.get('transport') != 'lightyear-fb-hex-v1':
                raise ValueError('translated spool bytes cannot represent a binary dataset')
        layouts = {name: load_copybook(base/binding['copybook']) for name, binding in bindings.items()}
        for filename in [settings['mapping'], settings['source'], settings['target']] + [b['copybook'] for b in bindings.values()]:
            manifest[filename] = sha((base/filename).read_bytes())
        with ExitStack() as stack:
            readers, mocks, fixtures = {}, {}, {}
            for lane in ('source', 'target'):
                fixture = load_mock_fixture(base/settings[lane])
                if fixture['job']['jobname'] != job.jobname:
                    raise ValueError('mock fixture job identity mismatch')
                fixtures[lane] = fixture
                mock = stack.enter_context(RunningMockZosmf(fixture))
                mocks[lane] = mock
                client_config = ZosmfConfig(mock.base_url, f'arrival-mock-{lane}', allow_loopback_http=True)
                client = ZosmfClient(HttpClientTransport(client_config), ZosmfCredentials())
                readers[lane] = ZosmfReader(client, client_config, base/settings['mapping'], datasets=bindings)
            source_lane = SourceLane(readers['source'])
            source = source_lane.observe(job)

            def submit(name, inputs):
                if name != job.jobname or inputs != list(job.inputs):
                    raise ValueError('unexpected target invocation')
                submissions.append(dict(jobname=name, inputs=inputs, evidence_class='simulated',
                                        mode='select-fixture-completion', staged_inputs=False))
                return fixtures['target']['job']['jobid']

            target = TargetLane(readers['target'], submit).replay(job, source)
            lane_receipts = {}
            for lane, receipt in [('source', source), ('target', target)]:
                if receipt['completed'] != 'CC 0000' or receipt['evidence_class'] != 'simulated':
                    raise ValueError('mock completion failed or evidence label changed')
                decoded = {}
                for name, payload in receipt['outputs'].items():
                    binding = bindings[name]
                    matches = [f for f in fixtures[lane]['files'] if all(f.get(k) == binding.get(k) for k in ('ddname', 'stepname', 'procstep'))]
                    decoded[name] = dict(binding=binding, jobname=job.jobname, jobid=fixtures[lane]['job']['jobid'],
                                         spool_file_id=matches[0]['id'], transport_sha256=sha(payload),
                                         layout=layouts[name].manifest(),
                                         records=decode_spool(payload, layouts[name], codec=binding['codec'], sign_policy=binding['sign_policy']))
                lane_receipts[lane] = dict(run=receipt['run'], completed=receipt['completed'],
                                          evidence_class=receipt['evidence_class'], submitted_by_us=receipt['submitted_by_us'],
                                          decoded_outputs=decoded, evidence=receipt['evidence'])
                for request in mocks[lane].server.requests:
                    requests.append(dict(lane=lane, jobname=job.jobname, **request))
            results.append(dict(job=job.id, lanes=lane_receipts,
                                raw_output_equal={name: source['outputs'][name] == target['outputs'][name] for name in bindings},
                                equivalence_verdict='not-assessed'))
            if hasattr(source_lane, 'submit') or hasattr(readers['source'], 'submit'):
                raise ValueError('source unexpectedly has a submission capability')
    if any(r['method'] != 'GET' for r in requests):
        raise ValueError('mock transport unexpectedly mutated a job')
    probe = config['packed_probe']
    for filename in probe.values(): manifest[filename] = sha((base/filename).read_bytes())
    probe_layout = load_copybook(base/probe['copybook'])
    packed = decode_fixed(probe_layout, bytes.fromhex((base/probe['hex']).read_text().strip()))
    return dict(schema_version='1.0', evidence_class='simulated', status='invocation-and-decoding-passed',
                plan=plan(pack), artifacts=manifest, jobs=results, requests=requests, submissions=submissions,
                packed_probe=packed, normalization_rules_applied=[], equivalence_verdict='not-assessed',
                mainframe_equivalent=False, runtime_branch_coverage=None,
                source_has_submit_capability=False, limitations=config.get('limitations', []))
