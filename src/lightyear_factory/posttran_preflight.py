"""Offline checks only. This module cannot dispatch a model or load credentials."""
from hashlib import sha256
from pathlib import Path
import json

from lightyear_control_tower.decisions import digest
from .posttran_second_opinion import require_inputs, DIRECTORY


def verify_approval(plan, receipt):
    body = {k: v for k, v in plan.items() if k != 'content_sha256'}
    if digest(body) != plan['content_sha256']:
        raise ValueError('plan-seal')
    if (receipt.get('plan_sha256') != plan['content_sha256']
            or receipt.get('approved_phase') != 1
            or receipt.get('approved_limits') != plan['phases']['1']
            or receipt.get('human_answer') != 'Approve Phase 1 budget'):
        raise ValueError('exact-phase1-budget-approval-required')
    # This records the human chat decision; it is not a signed Tower attestation.
    return {'phase1_budget_approved': True, 'phase2_authorized': False}


def check_client(plan, executable):
    actual = sha256(Path(executable).read_bytes()).hexdigest()
    if actual != plan['client']['sha256']:
        raise ValueError('pinned-client-hash-mismatch:' + actual)
    return actual


def stage_packet(root, plan, destination):
    """Stage only sealed public inputs and the sealed work order, never a checkout."""
    require_inputs(plan['inputs'])
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError('packet-destination-already-exists')
    payload = {}
    for relative, expected in plan['inputs'].items():
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('packet-path-boundary')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != expected:
            raise ValueError('packet-input-changed')
        payload[relative] = raw
    name = 'phase1-work-order.md'
    prompt = (DIRECTORY / name).read_bytes()
    if sha256(prompt).hexdigest() != plan['prompts'][name]:
        raise ValueError('packet-work-order-changed')
    destination.mkdir(parents=True)
    for relative, raw in payload.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (destination / name).write_bytes(prompt)
    return {**plan['inputs'], name: sha256(prompt).hexdigest()}


def write_report(path, report):
    value = dict(report)
    value['content_sha256'] = digest(value)
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return value
