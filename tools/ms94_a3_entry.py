"""Replay full entry admission even when a planted runtime throw exits early."""
from lightyear_calibration.contracts import read_json,require,verify,seal
from lightyear_calibration.ms94_v3_journey_verify import entries
from tools.ms94_a3_private_runner import verify_restore


def check(run):
    plan=read_json(run/'plan.json');verify(plan)
    profile=plan['a3_checkpoint_profile'];require(profile in ('admitted','perturbed'),'Unknown A3 checkpoint')
    entry=entries(run,{'operations':run/'cases/operations/1'})
    restores={}
    if profile=='perturbed':
        for lane in ('oracle','postgresql'):restores[lane]=verify_restore(run,lane)['content_sha256']
    else:require(not (run/'checkpoint-restore').exists(),'Base checkpoint unexpectedly mutated')
    return seal({'artifact_type':'ms94-a3-full-entry-admission','checkpoint_profile':profile,
        'checkpoint_sha256':read_json(run/'inputs/checkpoint.json')['content_sha256'],
        'preparation_verification_sha256':plan['a3_preparation_verification_sha256'],
        'native_entry_checks':entry,'restore_sha256':restores,'passed':True})
