"""Promote a reviewed schedule only when all executable admission inputs exist.

No Docker/model calls, signing, approval, retry or replacement authority here.
"""
from pathlib import Path
import re
from lightyear_calibration.contracts import read_json, seal, verify
from lightyear_calibration.journey_order import file_hash
from tools.ms94_b06_admission import check, verify_inputs
from tools.ms94_b06_executable import verify_snapshot, window, validate_native_owner


def convert(root, draft, snapshot_sha256, start_utc, end_utc, *, tower_public_key_sha256=None):
    """Judge qualification has no builder identity or model transport to admit."""
    root = Path(root); verify(draft)
    manifest = verify_snapshot(root, snapshot_sha256)
    check(isinstance(tower_public_key_sha256,str) and
          re.fullmatch('[a-f0-9]{64}',tower_public_key_sha256) is not None,
          'qualification-tower-key-required')
    check(draft.get('model_calls') == 0 and draft.get('measurement_authorized') is False,
          'qualification-only-no-builder')
    check(len(draft['schedule']) == draft['slot_count'] and
          len({s['id'] for s in draft['schedule']}) == draft['slot_count'], 'qualification-slot-inventory')
    by_id = {}
    for name, sha in manifest['slot_plans_sha256'].items():
        p = root / name; plan = read_json(p); verify(plan)
        validate_native_owner(p.parent)
        check(plan['content_sha256'] == sha and plan['journey'] == draft['journey'], 'qualification-slot-binding')
        check(plan['slot_id'] not in by_id, 'qualification-duplicate-slot')
        verify_inputs(p.parent, plan)
        check(plan.get('execution_admission_version') == 3, 'qualification-old-plan-version')
        check(plan['docker_run_window'] == window(plan['calendar'], start_utc, end_utc),
              'qualification-native-window-differs')
        check(plan['local']['runner_image'] == draft['images']['application'] and all(
            plan['declaration']['environment']['engines'][l]['image_digest'] == draft['images'][l]
            for l in ('oracle', 'postgresql')), 'qualification-image-binding')
        by_id[plan['slot_id']] = (name, plan)
    check(set(by_id) == {s['id'] for s in draft['schedule']}, 'qualification-missing-or-extra-slot')
    slots = []
    calendar = None
    for slot in draft['schedule']:
        name, plan = by_id[slot['id']]
        check(plan['harness_sha256'] == slot['source']['sha256'] and plan['control'] == slot['control'] and
              plan['expected'] == slot['expected'], 'qualification-schedule-changed')
        check('frozen_at_utc' in plan['calendar'], 'qualification-calendar-freeze-missing')
        check(plan['calendar']['scenario_date'] == '2026-10-01', 'qualification-scenario-date')
        if calendar is None: calendar = plan['calendar']
        check(calendar == plan['calendar'], 'qualification-calendar-differs')
        slots.append({'id': slot['id'], 'plan_path': name, 'plan_sha256': plan['content_sha256'],
                      'plan_file_sha256': file_hash(root / name), 'expected': slot['expected']})
    return seal({'artifact_type': 'ms94-b06-qualification-executable-plan/1',
                 'review_plan_sha256': draft['content_sha256'], 'snapshot_sha256': snapshot_sha256,
                 'tower_public_key_sha256': tower_public_key_sha256,
                 'authorization_kind': 'b06-qualification-group',
                 'journey': draft['journey'], 'images': draft['images'], 'calendar': calendar,
                 'docker_run_window': window(calendar, start_utc, end_utc), 'slots': slots,
                 'builder_present': False, 'slot_count': len(slots),
                 'model_calls': 0, 'measurement_authorized': False, 'docker_authorized': False,
                 'approval_of_this_plan_commit_required': True,
                 'native_entrypoint': 'tools.ms94_b06_qualification_driver.execute_group',
                 'restarts_allowed': False, 'replacement_slots_allowed': False,
                 'review': 'operator review; not independent attestation'})
