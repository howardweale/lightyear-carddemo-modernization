"""One-shot genuine database-failure hook, restricted to owned qualification resources."""
from datetime import datetime, timezone
from pathlib import Path
from lightyear_calibration.contracts import read_json, verify
from lightyear_calibration.journey_runtime import docker, inspect
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_b06_admission import check, sign_once

TRIGGER = 'first-bound-Doc.post-DB.executeUpdate-entry-after-native-readback'


def matches(event):
    frames = event.get('frames', [])
    return (event.get('kind') == 'method-entry' and len(frames) >= 2 and event.get('document') and
            frames[0]['class'] == 'org.compiere.util.DB' and frames[0]['method'] == 'executeUpdate' and
            frames[1]['class'] == 'org.compiere.acct.Doc' and frames[1]['method'] == 'post')


def inject(runner, lane, item, signer):
    spec = runner.plan.get('native_fault_hook')
    if not spec or spec['lane'] != lane or not matches(item['event']):
        return None
    path = runner.run / 'database-failure-hook.json'
    if path.exists():
        return read_json(path)  # exactly once, never stop a second resource
    check(spec == {'kind': 'owned-database-stop', 'lane': lane, 'trigger': TRIGGER} and
          runner.plan['qualification_only'] is True and runner.plan['model_calls'] == 0,
          'database-fault-hook-not-authorized')
    check(item['readback_sha256'] is not None, 'database-fault-without-before-readback')
    name = runner.owner + '-operations-1-' + lane
    info = inspect('container', name)
    check(info['Name'].lstrip('/') == name and info['Config']['Labels'].get('lightyear.journey') == runner.owner and
          info['Image'] == runner.plan['declaration']['environment']['engines'][lane]['image_digest'] and
          info['State']['Running'] is True, 'database-fault-resource-not-owned')
    # Preserve intent before the side effect. Failed stop/finalization never erases it.
    intent = sign_once(runner.run / 'database-failure-intent.json', {
        'artifact_type': 'ms94-b06-database-fault-intent/1', 'plan_sha256': runner.plan['content_sha256'],
        'run_id': runner.owner, 'lane': lane, 'container_id': info['Id'], 'image': info['Image'],
        'container': name, 'trigger': TRIGGER, 'event_sha256': item['content_sha256'],
        'event_sequence': item['event']['sequence'], 'before_readback_sha256': item['readback_sha256'],
        'real_utc': datetime.now(timezone.utc).isoformat(), 'action': 'stop-owned-database', 'restart': False,
    }, signer)
    docker('stop', '--time', '2', info['Id'])
    stopped = inspect('container', info['Id'])
    check(stopped['Id'] == info['Id'] and stopped['State']['Running'] is False, 'database-fault-stop-not-observed')
    return sign_once(path, {'artifact_type': 'ms94-b06-database-fault-observed/1',
        'plan_sha256': runner.plan['content_sha256'], 'intent_sha256': intent['content_sha256'],
        'container_id': info['Id'], 'stopped': True, 'real_utc': datetime.now(timezone.utc).isoformat(),
        'qualification_credit': False, 'model_calls': 0}, signer)


def replay(run, public_key):
    run = Path(run); plan = read_json(run / 'plan.json'); verify(plan)
    intent = read_json(run / 'database-failure-intent.json'); observed = read_json(run / 'database-failure-hook.json')
    cleanup = read_json(run / 'cleanup.json')
    check(all(verify_envelope(r, public_key) for r in (intent, observed, cleanup)), 'database-fault-signature')
    spec = plan['native_fault_hook']; lane = spec['lane']
    check(spec == {'kind': 'owned-database-stop', 'lane': lane, 'trigger': TRIGGER} and
          intent['plan_sha256'] == observed['plan_sha256'] == cleanup['plan_sha256'] == plan['content_sha256'] and
          intent['run_id'] == run.name and intent['container'] == run.name + '-operations-1-' + lane and
          intent['image'] == plan['declaration']['environment']['engines'][lane]['image_digest'] and
          intent['trigger'] == TRIGGER and intent['action'] == 'stop-owned-database' and intent['restart'] is False and
          observed['intent_sha256'] == intent['content_sha256'] and observed['container_id'] == intent['container_id'] and
          observed['stopped'] is True and cleanup['complete'] is True, 'database-fault-binding')
    import json
    previous = None; hit = None
    for raw in (run / 'posting-observer' / lane / 'events.jsonl').read_bytes().splitlines():
        item = json.loads(raw); verify(item)
        check(item['previous_sha256'] == previous, 'database-fault-partial-chain')
        previous = item['content_sha256']
        if previous == intent['event_sha256']: hit = item
    check(hit is not None and matches(hit['event']) and hit['event']['sequence'] == intent['event_sequence'] and
          hit['readback_sha256'] == intent['before_readback_sha256'], 'database-fault-trigger-binding')
    capture = read_json(run / 'posting-observer' / lane / ('readback-%06d.json' % intent['event_sequence'])); verify(capture)
    check(capture['content_sha256'] == intent['before_readback_sha256'] and
          capture['results']['health']['rows'] == [{'value': 1}], 'database-fault-before-health')
    # Stopped database cannot have a fabricated after capture or complete clock replay.
    return {'database_fault_replayed': True, 'equipment_suspect': True, 'diagnostics': [],
            'complete_gate_replayed': False, 'clock_replayed': False, 'partial_evidence': True}
