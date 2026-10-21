"""Compare account class receipt claims with raw PIT XML, without publication authority."""
import json
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize

GROUPS = {
    'account_input_java': ('AccountInputRules',),
    'account_text_money_java': ('AccountTextRules', 'AccountMoneyRule', 'CobolNumber'),
    'account_ssn_fico_java': ('AccountSsnRule', 'AccountFicoRule'),
    'account_location_java': ('AccountLocationRules',),
}


def verify_account_classes(raw_xml, mutation_gate):
    """Verify seven class summaries for the four account groups; callers must separately verify the complete proof."""
    root = ET.fromstring(raw_xml)
    if root.tag != 'mutations' or not isinstance(mutation_gate, dict):
        raise ValueError('account-class-proof-shape')
    nodes = root.findall('mutation')
    if any(not node.get('status') for node in nodes):
        raise ValueError('account-class-proof-status')
    if {key for key in mutation_gate if isinstance(key, str) and key.startswith('account_')} != set(GROUPS):
        raise ValueError('account-class-proof-group-inventory')
    future_classes = {'AccountValidationModel'}
    if any(node.findtext('mutatedClass', '').split('.')[-1].split('$')[0] in future_classes for node in nodes):
        raise ValueError('account-class-proof-unpublished-scope')
    verified = {}
    for key, classes in GROUPS.items():
        actual = summarize(nodes, classes)
        claimed = mutation_gate.get(key)
        if not isinstance(claimed, dict) or set(claimed) != set(classes):
            raise ValueError('account-class-proof-classes')
        # Serialized comparison also rejects bool/int and int/float substitutions.
        expected_json = json.dumps(actual, sort_keys=True, allow_nan=False)
        claimed_json = json.dumps(claimed, sort_keys=True, allow_nan=False)
        if claimed_json != expected_json or not all(row['passed'] for row in actual.values()):
            raise ValueError('account-class-proof-denominator')
        verified.update(actual)
    return verified
