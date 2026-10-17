"""Dated, hash-bound scope decisions; prose is only a consistency tripwire."""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SCOPES = {"twin-and-zos", "host-compiler-scoped"}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


BASELINE = 'claim-scope-decisions-2026-10-15.json'
ACCEPTED_OVERLAYS = frozenset({'3f5f5f84f68d5410bc0070f75e4d3e9b471a3d853233b9658153d4fe76228f6c'})


def _bound_overlay(path):
    value = json.loads(path.read_bytes())
    actual = digest({k:v for k,v in value.items() if k != 'content_sha256'})
    if actual != value.get('content_sha256'):
        raise ValueError('claim-scope-decision-hash')
    if actual not in ACCEPTED_OVERLAYS:
        raise ValueError('claim-scope-decision-unbound')
    for kind in ('arguments', 'acceptances'):
        seen = set()
        for row in value[kind]:
            key = (row['id'], row['record_sha256'], row['source_sha256'])
            if key in seen or row['claim_scope'] not in SCOPES:
                raise ValueError('claim-scope-decision-inventory')
            seen.add(key)
    return value


def load_decisions(root=ROOT, *, public_key=None, trusted_head=None):
    directory = root/'docs/factory'
    paths = sorted(directory.glob('claim-scope-decisions-*.json'))
    if not paths:
        return {'arguments': [], 'acceptances': []}
    value = _bound_overlay(paths[-1])
    # Only this exact previously reviewed transcription is grandfathered.
    baseline = _bound_overlay(directory/BASELINE)
    if baseline['content_sha256'] != '3f5f5f84f68d5410bc0070f75e4d3e9b471a3d853233b9658153d4fe76228f6c':
        raise ValueError('claim-scope-baseline-changed')
    for kind in ('arguments', 'acceptances'):
        old = {(r['id'], r['record_sha256'], r['source_sha256']):r['claim_scope'] for r in baseline[kind]}
        for row in value[kind]:
            key = (row['id'], row['record_sha256'], row['source_sha256'])
            if row['claim_scope'] != 'twin-and-zos' or old.get(key) == 'twin-and-zos':
                continue
            if public_key is None or trusted_head is None:
                raise ValueError('claim-scope-signed-review-required')
            from lightyear_control_tower.factory_policy import FactoryDecisions
            from lightyear_factory.tower_authority import proof_contract
            matches = [p for p in value.get('scope_reviews', []) if p['kind']==kind and p['id']==row['id']]
            if len(matches) != 1:raise ValueError('claim-scope-signed-review-required')
            proof = matches[0]['proof']; contract = proof_contract(proof)
            binding = {name:row[name] for name in ('id','record_sha256','source_sha256','claim_scope')}
            binding['kind'] = kind
            if (contract['details']['items'] != [row['id']] or contract['details']['claim_scope'] != 'zos-facing'
                or contract['details']['packet_sha256'] != digest(binding)):
                raise ValueError('claim-scope-review-binding')
            decision = FactoryDecisions(public_key,trusted_head).verify(proof,'equivalence-review',contract,('accept',))
            if decision['validation']['items'][row['id']]['outcome'] != 'accept':
                raise ValueError('claim-scope-review-not-accepted')
    return value


def declared_scope(records, identifier, record, source):
    matches = [r for r in records if (r["id"], r["record_sha256"], r["source_sha256"]) ==
               (identifier, digest(record), source)]
    return matches[0]["claim_scope"] if len(matches) == 1 else None


def check_consistency(argument, scope):
    text = argument.get("argument", "")
    host = bool(argument.get("compiler_storage_semantics") or argument.get("compiler_runtime_contract"))
    host |= bool(re.search(r"not (?:native )?z/OS(?!-specific)|host CEE3ABD terminating shim", text))
    if host and scope != "host-compiler-scoped":
        raise ValueError("claim-scope-host-semantics-unclassified")
