"""Fail-closed cohort-18 attribution over authenticated observer evidence.

The collector and its independent native replay must still be qualified. This
predicate grants no permission to accept candidate-authored provenance. Public
feedback is a closed projection, never the private proof or database identifiers.
"""
import hashlib
from lightyear_calibration.contracts import canonical, require
from lightyear_control_tower.decisions import verify_envelope

LANES = ('oracle', 'postgresql')


def project(proofs, *, public_key, binding, policy, replayed_native_evidence):
    """Caller supplies the exact trusted native replay result, not candidate text."""
    diagnostics = []
    accepted = []
    suspicious = []
    allowed = policy['attribution']
    for lane in LANES:
        proof = proofs.get(lane)
        if proof is None:
            suspicious.append(lane)
            continue
        try:
            require(verify_envelope(proof, public_key), 'Invalid attribution signature')
            require(proof['artifact_type'] == 'ms94-b06-posting-origin-proof/1' and
                    proof['binding'] == {**binding, 'lane': lane}, 'Attribution binding differs')
            replay = replayed_native_evidence[lane]
            require(replay['full_entry_replayed'] is True and replay['observer_replayed'] is True and
                    replay['proof_sha256'] == proof['content_sha256'] and
                    replay['binding'] == proof['binding'], 'Native attribution replay missing')
            events = proof['events']
            require(events and [e['sequence'] for e in events] == list(range(1, len(events)+1)),
                    'Observer sequence gap or duplicate')
            require(proof['observer_complete'] is True and proof['non_candidate_fault_checks_passed'] is True,
                    'Incomplete observer or non-candidate fault')
            failure = events[-1]
            require(failure['kind'] == 'posting-failed' and failure['origin'] == 'support' and
                    failure['step'] in allowed['posting_steps'], 'Unsupported failure')
            document = proof['document_label']
            require(document in allowed['document_labels'], 'Non-public document label')
            previous = [e for e in events[:-1] if e['kind'] in ('posted', 'lock-held') and
                        e['origin'] == 'candidate' and e['document_key'] == failure['document_key'] and
                        e['execution_sha256'] == binding['execution_sha256'][lane]]
            require(previous, 'No candidate-owned prior action on this document')
            prior = previous[-1]
            observed = proof['pre_support_native_readback']
            require(observed['document_key'] == failure['document_key'] and
                    prior['sequence'] < observed['after_event_sequence'] < failure['sequence'] and
                    observed['capture_sha256'] in replay['verified_capture_hashes'],
                    'Independent pre-support document readback missing')
            if prior['kind'] == 'posted':
                require(observed['posted'] is True and observed['accounting_facts_present'] is True,
                        'Prior posting not confirmed natively')
            else:
                require(observed['lock_owner_execution_sha256'] == binding['execution_sha256'][lane] and
                        observed['lock_still_held'] is True, 'Prior candidate lock not confirmed natively')
            accepted.append((lane, document, failure['step']))
        except (KeyError, TypeError, ValueError, AssertionError):
            suspicious.append(lane)
    # Ambiguity on either lane remains an equipment-suspect trial. Partial proof
    # must not send feedback that could teach around a genuine equipment fault.
    if suspicious:
        return {'diagnostics': [], 'equipment_suspect': True, 'route': 'pause',
                'attribution_available': False}
    groups = {}
    for lane, document, step in accepted:
        groups.setdefault((document, step), []).append(lane)
    for (document, step), lanes in sorted(groups.items()):
        item = {'category': 'candidate-posting-sequence-misuse', 'document': document,
                'posting_step': step, 'lanes': 'both' if len(lanes) == 2 else 'one'}
        item['id'] = hashlib.sha256(canonical(item)).hexdigest()
        require(set(item) == set(allowed['closed_fields']), 'Attribution projection changed')
        diagnostics.append(item)
    return {'diagnostics': diagnostics, 'equipment_suspect': False,
            'route': 'builder-direct', 'attribution_available': True}
