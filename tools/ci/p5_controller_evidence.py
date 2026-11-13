"""Retain disposable controller evidence; never confer qualification or authority."""
import hashlib
import json
import re

from lightyear_factory.contracts import canonical_hash


def validate(value, *, run_id, work_order_sha256):
    """Check the retained bytes and bindings, separately from strict P5 qualification."""
    def require(condition):
        if not condition:
            raise ValueError('p5-retained-controller-evidence-invalid')

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    def document(text, limit):
        require(isinstance(text, str) and 0 < len(text.encode('utf-8')) <= limit)
        def unique(pairs):
            result = {}
            for key, item in pairs:
                require(key not in result)
                result[key] = item
            return result
        result = json.loads(text, object_pairs_hook=unique)
        require(isinstance(result, dict))
        require(result.get('content_sha256') == canonical_hash(result, {'content_sha256'}))
        return result

    require(value.get('schema') == 'p5-retained-controller-evidence/1')
    require(value.get('origin') == 'disposable CI controller with stub transport')
    require(value.get('run_id') == run_id and value.get('work_order_sha256') == work_order_sha256)
    receipt = document(value['receipt_utf8'], 65536)
    identity = document(value['identity_utf8'], 16384)
    require(receipt.get('status') == 'blocked' and receipt.get('qualifies_for_factory_receipt') is False)
    require(receipt.get('reason') == 'factory-isolation-run-refused')
    require(receipt.get('work_order_sha256') == identity.get('work_order_sha256') == work_order_sha256)
    require(identity.get('schema') == 'factory-attempt-identity/1' and identity.get('attempt_id') == run_id)
    for field in ('consumed_nonce_sha256', 'sealed_workspace_sha256', 'admission_receipt_sha256',
                  'workspace_inventory_sha256', 'work_order_sha256'):
        require(isinstance(identity.get(field), str) and re.fullmatch('[0-9a-f]{64}', identity[field]))
    before, after = value['attempt_files_before'], value['attempt_files_after']
    require(isinstance(before, dict) and before == after and bool(before))
    require(all(isinstance(path, str) and isinstance(item, str) and re.fullmatch('[0-9a-f]{64}', item)
                for path, item in before.items()))
    for filename, field in (('receipt.json', 'receipt'), ('attempt-identity.json', 'identity')):
        actual = digest(value[field+'_utf8'].encode('utf-8'))
        require(value[field+'_sha256'] == before.get(filename) == after.get(filename) == actual)
    nonce = value['consumed_nonce_store_utf8']
    require(isinstance(nonce, str) and 0 < len(nonce) <= 16384 and nonce.endswith('\n'))
    nonce_rows = nonce.splitlines()
    require(all(re.fullmatch('[0-9a-f]{64}', row) for row in nonce_rows))
    require(len(nonce_rows) == len(set(nonce_rows)) and identity['consumed_nonce_sha256'] in nonce_rows)
    require(value['nonce_before_sha256'] == value['nonce_after_sha256'] == digest(nonce.encode('ascii')))
    require(value.get('duplicate_transport_calls') == 0 and type(value['duplicate_transport_calls']) is int)
    accounting = receipt.get('failure_accounting', {})
    require(accounting.get('schema') == 'factory-sanitized-accounting/1' and accounting.get('calls') == 1)
    require(value.get('transport_calls_before_reentry') == accounting['calls'])
    return True
