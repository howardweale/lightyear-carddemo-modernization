"""Qualified v5/observer-v4 base plus one prospective invoice-type requirement."""
from pathlib import Path
from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.journey_order import save, file_hash
from tools.ms94_v4_gate import evaluate as base_evaluate
from tools.ms94_invoice_type_v5 import evaluate as invoice_type

VERSION = 'idempiere-qualified-judge-v6-order-derived-invoice-ms94'


def evaluate(run, **unused):
    run = Path(run)
    plan = read_json(run/'plan.json'); verify(plan)
    # Refuse to overwrite an earlier declaration's verdict with a new rule.
    require(plan['judge_version'] == VERSION and plan['scenario'] == 'operations',
            'Invoice-type extension requires its own prospective operations plan')
    require(file_hash(run/'inputs/invoice-type-contract.json') == plan['inputs_sha256']['invoice-type-contract.json'],
            'Prospective public contract changed')
    value = base_evaluate(run)
    value = {k:v for k,v in value.items() if k != 'content_sha256'}
    value['judge_version'] = VERSION
    # Preserve execution failure, evidence insufficiency and judge errors. Only
    # evaluate the added business relationship after complete native verification.
    if value['status'] in ('passed', 'business-failure') and 'combined' in value['checks']:
        try:
            check = invoice_type(run)
            value['checks']['invoice_type_retention'] = check
            if not check['passed']:
                value.update(status='business-failure', passed=False)
        except FileNotFoundError as exc:
            value.update(status='insufficient-evidence', passed=False,
                         error={'stage':'invoice-type-retention','type':type(exc).__name__,'message':str(exc)})
        except Exception as exc:
            value.update(status='judge-error', passed=False,
                         error={'stage':'invoice-type-retention','type':type(exc).__name__,'message':str(exc)})
    value = seal(value); save(run/'gate.json', value)
    return value
