"""Validate the additive October12 operator record; never activate a threshold."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISION = 'docs/factory/equivalence-operator-acceptance-2026-10-12.json'
HOST = {11, 12, 13, 14, 15, 16, 19, 24, 37, 38, 41}
PENDING = {20, 23, 42}
DEPENDENCIES = {30: 'CBACT04C-FINAL-ACCOUNT-EOF-ELSE', 35: 'REWRITE-109', 36: 'REWRITE-109'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def seal(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(root=ROOT, decision=None, register=None):
    def text(path):
        return (root / path).read_text(encoding='utf-8')
    def bound(row):
        source = text(row['source_path'])
        require(digest(source.encode()) == row['source_sha256'], 'source-binding')
        start = row['source_line']
        end = row.get('source_end_line', start)
        excerpt = '\n'.join(source.splitlines()[start - 1:end])
        require(digest(excerpt.encode()) == row.get('source_lines_sha256', row.get('source_line_sha256')), 'line-binding')
    decision = decision if decision is not None else json.loads(text(DECISION))
    require(seal({k: v for k, v in decision.items() if k != 'content_sha256'}) == decision['content_sha256'], 'decision-seal')
    require(decision['review_class'] == 'AI-assisted operator review' and decision['independent_human_attestation'] is False, 'review-class')
    for name in ('review_packet', 'historical_decisions'):
        b = decision[name]
        require(digest(text(b['path']).encode()) == b['lf_sha256'], 'input-binding')
    b = decision['review_attachment']
    require(digest((root / b['path']).read_bytes()) == b['sha256'], 'attachment-binding')
    history = json.loads(text(decision['historical_decisions']['path']))['accepted_mutants']
    old = {r['id']: r for r in history}
    packet = json.loads(text(decision['review_packet']['path']))['mutants']
    new = decision['new_acceptances']
    refs = decision['existing_acceptance_references']
    all_rows = new + refs
    require(len(new) == 44 and len(refs) == 3 and {r['item'] for r in refs} == {10, 33, 38}, 'deduplication')
    require(len({r['id'] for r in all_rows}) == 47 and {r['item'] for r in all_rows} == set(range(1, 48)), 'population')
    require(not ({r['id'] for r in new} & set(old)), 'duplicate-acceptance')
    register = register if register is not None else json.loads(text('docs/factory/keep-or-fix-register.json'))
    entries = {r['id']: r for r in register['defects']}
    for r in all_rows:
        p = packet[r['item'] - 1]
        require(r['id'] == p['id'] and r['review_packet_record_sha256'] == seal(p) and r['argument_sha256'] == seal(p['argument']), 'packet-binding')
        bound(r)
        require(digest(text(r['program_source_path']).encode()) == r['program_source_sha256'], 'program-binding')
        require(r['scope'] == 'twin' and r['new_zos_facing_acceptance'] is False and r['host_only'] == (r['item'] in HOST), 'scope')
        if r in refs:
            require(r['new_acceptance'] is False and seal(old[r['id']]) == r['existing_entry_sha256'], 'historical-reference')
            continue
        require(r['accepted_by'] == 'Howard' and r['threshold_approved'] is False, 'operator-authority')
        required = DEPENDENCIES.get(r['item'])
        require([x['id'] for x in r['depends_on_register']] == ([required] if required else []), 'dependency-list')
        for dep in r['depends_on_register']:
            e = entries.get(dep['id'])
            require(e and seal(e) == dep['entry_sha256'] and not e.get('fix_authorized') and e['disposition'] == dep['required_disposition'], 'register-changed')
        require(r['effective_for_individual_review'] == (r['item'] not in PENDING), 'conditional-acceptance')
        if r['item'] in PENDING:
            e = r['required_evidence']
            require(e['head'] == '4cc7c1acda70249554938253004187ab8700dba4' and e['run_id'] == 38296048295 and e['pr'] == 328 and e['mutant_id'] == r['id'], 'rerun-binding')
            require(e['required_case_indices'] == list(range(200)) and e['valid_comparisons'] == e['scheduled_comparisons'] == 200 and e['baseline_and_mutant_executed_each_case'] is True and e['refusals_allowed'] == e['refutations_allowed'] == 0 and e['requires_verified_complete_shard_aggregate'] is True and e['satisfaction_receipt'] is None, 'pending-receipt-required')
    constants = decision['constant_field_acceptances']
    require(len(constants) == 7 and {r['source_line'] for r in constants} == {482, 483, 484, 491, 492, 493, 494}, 'constant-population')
    for r in constants:
        bound(r)
        require(r['accepted_by'] == 'Howard' and r['scope'] == 'twin' and not r['new_zos_facing_acceptance'] and r['comparison_required'] and r['mutation_detection_required'], 'constant-scope')
    limits = decision['scope_limits']
    require(limits['new_zos_facing_acceptances'] == 0 and not limits['threshold_approved'] and not limits['release_authorized'] and not limits['runtime_activation'], 'limits')
    proposal = json.loads(text(decision['pending_domain_decision']))
    require(proposal['approved'] is False and proposal['effective'] is False and proposal['approved_by'] is None, 'proposal-not-approved')
    require(seal({k: v for k, v in proposal.items() if k != 'content_sha256'}) == proposal['content_sha256'], 'proposal-seal')
    for row in proposal['bound_sources']:
        require(digest(text(row['path']).encode()) == row['lf_sha256'], 'proposal-source-binding')
    return dict(new_decisions=44, historical_references=3, pending_evidence_items=sorted(PENDING), host_only_items=sorted(HOST), constants=7, new_zos_acceptances=0, threshold_approved=False, proposal_approved=False)


if __name__ == '__main__':
    print(json.dumps(validate(), indent=2))
