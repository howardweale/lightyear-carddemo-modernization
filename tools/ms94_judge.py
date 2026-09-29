"""MS94 envelope adapter for the unchanged MS93 v3 judge and purchasing rule.

Only established business assertions are reclassified. Unknown exceptions remain
judge errors. No mutation identity is consulted by the judge.
"""
from lightyear_calibration.contracts import read_json, seal
from lightyear_calibration.qualified_judge_v3 import evaluate as original
from lightyear_calibration.journey_order import save

VERSION = 'idempiere-qualified-judge-v3-ms94-envelope-v1'
BUSINESS = (
    'Operations business boundary failed', 'Order net amount differs',
    'Missing reciprocal credit reversal', 'Missing credit or reversal accounting',
    'Retry produced a duplicate business key',
    'Write outside declared footprint or new application issue',
    'Cost detail escaped client/organization/schema', 'Side effect escaped organization',
    'Missing or ambiguous procurement row:', 'Procurement ', 'Vendor invoice ',
    'Purchase order, receipt and invoice line links differ',
    'Receipt not linked to purchase order', 'Sales document substituted for purchasing',
    'Outbound allocation sign or amount differs', 'Missing inbound receipt stock movement',
)


def evaluate(run, **unused):
    scenario = read_json(run/'plan.json')['scenario']
    verifier = None
    if scenario == 'procure-to-pay':
        from tools.qualification_purchasing_comparison import verify_run
        verifier = verify_run
    value = original(run, verifier=verifier)
    error = value.get('error') or {}
    if (value['status'] == 'judge-error' and error.get('stage') == 'combined-native-judge'
            and error.get('type') == 'CalibrationError'
            and error.get('message', '').startswith(BUSINESS)):
        value['status'] = 'business-failure'
    value['judge_version'] = VERSION
    value = seal({k:v for k,v in value.items() if k != 'content_sha256'})
    save(run/'gate.json', value)
    return value
