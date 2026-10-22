"""Validate the unsigned review inventory, without creating requests or authority."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from lightyear_control_tower.decisions import digest
from lightyear_control_tower.factory_order import body_hash
from lightyear_control_tower.factory_policy import validate_contract
from lightyear_control_tower.factory_selection import load_selection
from lightyear_control_tower.factory_supersessions import overlaps, reject_content_superseded

PACKET = 'docs/factory/intcalc-review-packet-2026-10-22.json'
ORDER = 'docs/factory/intcalc-signing-order-2026-10-17.json'
SELECTION = 'docs/factory/appl-result-contract-selection-2026-10-18.json'
ROOT = Path(__file__).resolve().parents[1]


def require(ok, code):
    if not ok:
        raise ValueError('intcalc-review-' + code)


def path_at(root, name):
    require(isinstance(name, str) and '\\' not in name, 'path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and ':' not in name,
            'path')
    require(name.startswith('docs/factory/'), 'path')
    target = (Path(root) / name).resolve()
    require(target.is_relative_to(Path(root).resolve()), 'path')
    return target


def bound_json(root, ref):
    require(set(ref) == {'path', 'sha256'}, 'reference')
    raw = path_at(root, ref['path']).read_bytes()
    require(sha256(raw).hexdigest() == ref['sha256'], 'file-hash')
    return json.loads(raw)


def detail_hashes(value, prefix='details'):
    """Expose every embedded content/evidence digest, including condition IDs."""
    if isinstance(value, dict):
        return [row for key, item in sorted(value.items())
                for row in detail_hashes(item, prefix + '.' + key)]
    if isinstance(value, list):
        return [row for i, item in enumerate(value)
                for row in detail_hashes(item, prefix + '.' + str(i))]
    if isinstance(value, str) and re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value):
        return [dict(field=prefix, value=value)]
    return []


def validate(root=ROOT, packet_path=PACKET):
    packet = json.loads(path_at(root, packet_path).read_bytes())
    require(packet.get('schema') == 'intcalc-unsigned-review-packet/1', 'schema')
    require(packet.get('program') == 'INTCALC' and packet.get('prepared_on') == '2026-10-22', 'identity')
    for flag in ('signed', 'ready_for_signing', 'execution_authorized', 'release_authorized'):
        require(packet.get(flag) is False, 'authority')
    require(packet.get('live_overlap_status') == 'unknown-not-read', 'live-claim')
    require(packet['order']['path'] == ORDER and packet['selection']['path'] == SELECTION,
            'selected-index')
    order = bound_json(root, packet['order'])
    selected = bound_json(root, packet['selection'])
    require(selected == load_selection(root), 'selection-not-current')
    chosen = next(row for row in selected['records'] if row['program'] == 'INTCALC')
    require(order['signed'] is False and order['release_authorized'] is False
            and order['effective'] is False, 'order-authority')
    rows = packet.get('requests', [])
    require(len(rows) == len(order['items']) == 6, 'six-requests')
    contracts = []
    verified_sources = set()
    for position, (row, original) in enumerate(zip(rows, order['items']), 1):
        require(row['order'] == original['order'] == position, 'order')
        require(row['contract'] == dict(path=original['path'], sha256=original['sha256']), 'template')
        contract = bound_json(root, row['contract'])
        require(contract['program'] == 'INTCALC' and contract['kind'] == original['kind'] == row['kind'], 'kind')
        require(row['queue_sha256'] == digest(contract), 'queue-hash')
        require(row['sources'] == contract['sources'] and row['detail_hashes'] == detail_hashes(contract['details']),
                'evidence-inventory')
        require(row['authorization'] == 'none-unsigned-review-only', 'authority')
        require(isinstance(row['decision_scope'], str) and bool(row['decision_scope'].strip()), 'scope')
        require(row['does_not_authorize'] == ['execution', 'model-spend', 'native-claim', 'release'], 'exclusions')
        require(row['predecessor_binding_required'] is (position > 1), 'predecessor')
        if position < 6:
            validate_contract(contract, check_evidence=False)
        else:
            require(len(contract['details']['conditions']) == 4 and all(
                item['state'] == 'not-met' and item['evidence'] is None
                for item in contract['details']['conditions']), 'conditions')
            try:
                validate_contract(contract, check_evidence=False)
            except ValueError as error:
                require(str(error) == 'threshold-conditions-unmet', 'unexpected-refusal')
            else:
                raise ValueError('intcalc-review-unexpected-signability')
        for source in row['sources']:
            path_at(root, source['path'])
            require(re.fullmatch('[0-9a-f]{40}', source['commit']) is not None, 'source-commit')
            require(re.fullmatch('[0-9a-f]{64}', source['sha256']) is not None, 'source-hash')
            key = (source['commit'], source['path'], source['sha256'])
            if key not in verified_sources:
                raw = subprocess.check_output(['git', 'show', source['commit'] + ':' + source['path']], cwd=root)
                require(sha256(raw).hexdigest() == source['sha256'], 'source-bytes')
                verified_sources.add(key)
        contracts.append(contract)
    require(rows[1]['contract'] == dict(path=chosen['path'], sha256=chosen['file_sha256'])
            and rows[1]['queue_sha256'] == chosen['template_queue_sha256'], 'I2-choice')
    bodies = [body_hash(contract) for contract in contracts]
    for i, contract in enumerate(contracts):
        require(contract['signing_order'] == dict(packet_sha256=digest(bodies), position=i+1,
                predecessor_contract_sha256=bodies[i-1] if i else None,
                predecessor_decision_sha256=None), 'packet-binding')
        require(not any(overlaps(contract, prior) for prior in contracts[:i]), 'internal-overlap')
    return packet, contracts


def check_current_overlaps(contracts, *, repository, root, journal, public_key, trusted_head):
    """Read-only prerequisite, not an intake/signing API or a reusable clearance.

    Actual intake repeats the existing guard against its then-current state.
    The CLI below deliberately never reads installed Tower state or invokes this.
    """
    for contract in contracts:
        reject_content_superseded(contract, repository, root=root, journal=journal,
                                  public_key=public_key, trusted_head=trusted_head)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    packet, contracts = validate(args.root)
    print(json.dumps(dict(schema='intcalc-unsigned-review-validation/1',
        packet_sha256=sha256(path_at(args.root, PACKET).read_bytes()).hexdigest(),
        templates_verified=len(contracts), sources_verified=True,
        ready_for_signing=False, live_overlap_status=packet['live_overlap_status'],
        signed=False, execution_authorized=False, release_authorized=False), indent=2))


if __name__ == '__main__':
    main()
