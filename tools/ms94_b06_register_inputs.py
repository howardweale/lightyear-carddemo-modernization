"""Journey-specific comparison inputs, validated by their unchanged judges."""
from datetime import date
import json
from pathlib import Path
from lightyear_calibration.contracts import read_json, verify
from tools.ms94_b06_admission import check


def register_path(journey):
    check(journey in ('J1', 'J2', 'J3'), 'register-unknown-journey')
    return Path('factory/idempiere/repeatability/comparison-register.json' if journey == 'J1'
                else 'factory/idempiere/qualification-ms94-v3/private/comparison-register.json')


def validate(journey, register, inventory, assessed_on, expected_sha256=None):
    verify(register); verify(inventory)
    if expected_sha256 is not None:
        check(register['content_sha256'] == expected_sha256, 'comparison-register-changed')
    if journey == 'J1':
        from lightyear_calibration.declared_rules import validate_register
    else:
        check(journey in ('J2', 'J3'), 'register-unknown-journey')
        from tools.ms94_v3_register import validate_register
    return validate_register(register, inventory, date.fromisoformat(assessed_on))


def validate_files(journey, files, assessed_on, expected_sha256=None):
    return validate(journey, json.loads(files['comparison-register.json']),
                    json.loads(files['datatype-inventory.json']), assessed_on, expected_sha256)


def selected_files(root, journey, assessed_on):
    """Select original register bytes; never relabel a purchasing register as J1."""
    root = Path(root)
    files = {'comparison-register.json': (root / register_path(journey)).read_bytes(),
             'datatype-inventory.json': (root / 'docs/calibration/idempiere-boundaries/mappings.json').read_bytes()}
    validate_files(journey, files, assessed_on)
    return files


def admit(run, plan):
    folder = Path(run) / 'inputs'
    return validate(plan['journey'], read_json(folder / 'comparison-register.json'),
                    read_json(folder / 'datatype-inventory.json'), plan['assessed_on'],
                    plan['comparison_register_sha256'])
