"""Sign the unsealed A3 admission body and verify persistence before execution."""
from lightyear_calibration.contracts import read_json, require, verify
from lightyear_calibration.journey_order import save
from lightyear_control_tower.decisions import verify_envelope
from tools.ms94_a3_entry import check


def admit(run, signer):
    path = run / 'a3-entry-admission.json'
    require(not path.exists(), 'Preserve existing entry admission')
    checked = check(run)
    verify(checked)
    require('signature' not in checked and checked.get('passed') is True,
            'Expected unsigned successful entry check')
    body = {k: v for k, v in checked.items() if k != 'content_sha256'}
    envelope = signer.sign(body)
    require(verify_envelope(envelope, signer.public), 'Invalid new entry admission signature')
    require({k: v for k, v in envelope.items() if k not in ('signature', 'content_sha256')} == body,
            'Signer changed entry admission body')
    save(path, envelope)
    persisted = read_json(path)
    require(persisted == envelope and verify_envelope(persisted, signer.public),
            'Persisted entry admission differs')
    return persisted
