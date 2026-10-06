"""Prepare the r7 smoke's public hash-only group after operator key confirmation.

Never load a Tower private key, grant a role, sign a decision, or run Docker.
Publication and the subsequent exact Tower decision are separate gates.
"""
import argparse
import hashlib
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from lightyear_calibration.contracts import canonical, read_json
from lightyear_control_tower.status_export import atomic_new
from tools.ms94_b06_qualification_plan import convert
from tools.ms94_b06_group_decision import write_request


def confirmed_key(public_file, fingerprint, campaign_public):
    raw = Path(public_file).read_bytes()
    if hashlib.sha256(raw).hexdigest() != fingerprint:
        raise ValueError('Tower public key differs from operator-confirmed fingerprint')
    if raw == campaign_public or not isinstance(load_pem_public_key(raw), Ed25519PublicKey):
        raise ValueError('A distinct Ed25519 Tower authority is required')
    return raw


def prepare(snapshot, draft_file, public_file, fingerprint, campaign_public, output):
    confirmed_key(public_file, fingerprint, campaign_public)
    manifest = read_json(Path(snapshot)/'b06-executable-snapshot.json')
    group = convert(snapshot, read_json(draft_file), manifest['content_sha256'],
                    '2026-10-07T03:00:00Z', '2026-10-07T09:00:00Z',
                    tower_public_key_sha256=fingerprint)
    if group['journey'] != 'J1' or group['slot_count'] != 3:
        raise ValueError('Expected exact three-slot J1 smoke')
    atomic_new(Path(output), group)
    return group


def published_request(tower_root, group_file, commit, public_bytes):
    """Caller obtains public_bytes via git cat-file at verified public commit."""
    group = read_json(group_file)
    if public_bytes != Path(group_file).read_bytes() or public_bytes != canonical(group):
        raise ValueError('Public group bytes differ')
    return write_request(tower_root, group, commit)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--draft',type=Path,required=True)
    parser.add_argument('--tower-public-key',type=Path,required=True)
    parser.add_argument('--confirmed-fingerprint',required=True)
    parser.add_argument('--campaign-public-key',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = prepare(args.snapshot,args.draft,args.tower_public_key,args.confirmed_fingerprint,
                     args.campaign_public_key.read_bytes(),args.output)
    print(result['content_sha256'])
