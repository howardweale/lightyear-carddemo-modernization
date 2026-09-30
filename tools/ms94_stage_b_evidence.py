"""Verify accepted equipment-04 without reopening or modifying Stage A.

The copied qualification evidence is portable; live execution also requires the
separately frozen Stage B source root and the published full-capture inventory.
"""
import hashlib
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import file_hash
from lightyear_calibration.journey_runtime import read_local
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_equipment_v4 import schedule, AREA

EQUIPMENT_HASH = '77b075d0cafebe41dc33df02e43150a18a72e4601750ca3faa0211884960257e'
ACCEPTANCE_HASH = '0ad73e79fa94f7e74949e0733d655d814c9852c48fd9333643648d1b240480b4'
KEY_HASH = 'c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f'


def stage_a(root, equipment, live=False):
    root, equipment = Path(root), Path(equipment)
    key = (root/'work/ms87/operator/authority.public.pem').read_bytes()
    require(hashlib.sha256(key).hexdigest() == KEY_HASH, 'Unknown qualification authority')
    plan = read_json(equipment/'plan.json'); verify(plan)
    require(plan['content_sha256'] == EQUIPMENT_HASH and plan['revision'] == 4,
            'Stage B requires accepted equipment-04')
    declaration = read_json(equipment/'declaration.json')
    require(verify_envelope(declaration, key) and declaration['plan_sha256'] == EQUIPMENT_HASH,
            'Equipment declaration changed')
    for name, digest in plan['implementation_sha256'].items():
        require(file_hash(root/name) == digest, 'Qualified implementation changed: '+name)
    acceptance = read_json(equipment/'acceptance.json')
    report = read_json(equipment/'report.json')
    require(verify_envelope(acceptance, key) and acceptance['content_sha256'] == ACCEPTANCE_HASH
            and acceptance['stage_a_accepted'] and acceptance['passed']
            and acceptance['plan_sha256'] == EQUIPMENT_HASH, 'Stage A acceptance changed')
    require(verify_envelope(report, key) and report['plan_sha256'] == EQUIPMENT_HASH
            and report['content_sha256'] == acceptance['native_report_sha256'], 'Stage A report changed')
    require(plan['schedule'] == schedule() and len(report['results']) == 62
            and report['status'] == 'native-controls-passed-review-pending'
            and report['unstarted_slots'] == 0 and report['mutation_score'] == 1,
            'Stage A schedule or results incomplete')
    for ordinal, (slot, entry) in enumerate(zip(schedule(), report['results']), 1):
        require(entry['slot'] == ordinal and all(entry[k] == v for k, v in slot.items())
                and entry['qualification_check_passed'] and entry['publication_verified'],
                'Qualification slot changed')
        publication = equipment/'publications'/f'{ordinal:02d}'
        receipt = read_json(publication/'receipt.json')
        replay = read_json(publication/'verification.json')
        require(verify_envelope(receipt, key) and receipt['authority_sha256'] == KEY_HASH
                and receipt['content_sha256'] == entry['publication_receipt_sha256'],
                'Publication receipt changed')
        require(verify_envelope(replay, key) and replay['verified'] and replay['complete_gate_replayed']
                and replay['run_id'] == Path(entry['run_directory']).name
                and replay['status'] == entry['status'], 'Publication replay incomplete')
    reviews = acceptance['reviews']
    require(len(reviews) == 2 and {r['review_kind'] for r in reviews} ==
            {'support-source', 'independent-purchasing-rule-and-reference'}, 'Missing human reviews')
    for review in reviews:
        require(verify_envelope(review, key) and review['accepted'] and review['human_attestation']
                and review['packet_sha256'] == plan['human_review_packet_sha256'], 'Human review changed')
        if review['review_kind'].startswith('independent'):
            require(review['reviewer_is_author'] is False, 'Purchasing review not independent')
    owner = acceptance['owner_decision']
    register = read_json(root/AREA/'private/comparison-register.json')
    require(verify_envelope(owner, key) and owner['accepted'] and owner['human_attestation']
            and owner['explicit_human_acceptance'] and owner['register_sha256'] == register['content_sha256']
            and owner['packet_sha256'] == plan['human_review_packet_sha256'], 'Ownership approval changed')
    if live:
        require(read_local(root) == plan['base_plan']['local'], 'Qualified native runtime changed')
        published = read_json(equipment/'published-assets.json')
        require(verify_envelope(published, key) and published['plan_sha256'] == EQUIPMENT_HASH
                and published['release_published'] is True, 'Full captures have not been published')
        assets = published['assets']
        require(len(assets) == 63 and len({a['name'] for a in assets}) == 63, 'Release assets incomplete')
        expected = read_json(equipment/'release-assets.json')['assets']
        require(len(expected) == 63, 'Release inventory incomplete')
        for item in expected:
            matches = [a for a in assets if a['name'] == item['asset']]
            require(len(matches) == 1 and matches[0]['digest'] == 'sha256:'+item['sha256']
                    and matches[0]['size'] == item['bytes'] and matches[0]['state'] == 'uploaded'
                    and matches[0]['browser_download_url'] == item['url'], 'Published asset differs from frozen index')
        for ordinal in range(1, 63):
            receipt = read_json(equipment/'publications'/f'{ordinal:02d}'/'receipt.json')
            matches = [a for a in assets if a['name'] == f'ms94-equipment-04-pair-{ordinal:02d}.zip']
            require(len(matches) == 1 and matches[0]['digest'] == 'sha256:'+receipt['archive_sha256']
                    and matches[0]['size'] == receipt['archive_bytes'] and matches[0]['state'] == 'uploaded',
                    'Published native archive differs')
    return plan, acceptance
