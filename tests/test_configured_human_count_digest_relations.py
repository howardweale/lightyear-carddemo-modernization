"""CI-only hash-domain regressions; synthetic relations grant no authority."""
import hashlib
import json
import os
import unittest
from copy import deepcopy

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_execution.configured_human_success import check_successful_call_relations
from test_configured_human_success_relations import relations


def native_shaped_relations():
    calls, transports = relations()
    # Same key order and serialization as the native input-token request.
    # Deliberately different from sorted canonical serialization.
    for sequence, call in enumerate(calls):
        body = dict(model='pinned-model', instructions='Synthetic relation only',
                    input=[dict(role='user', content='No external request')],
                    text=dict(format=dict(type='json_schema')))
        raw = json.dumps(body, separators=(',', ':')).encode('utf-8')
        count = transports[2 * sequence]['reservation']
        count['request_sha256'] = hashlib.sha256(raw).hexdigest()
        count['canonical_request_sha256'] = canonical_hash(body)
        call['token_count_request_sha256'] = canonical_hash(body)
        call['content_sha256'] = canonical_hash(call, {'content_sha256'})
    return calls, transports


class ConfiguredCountDigestRelationsTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')

    def test_native_count_key_order_uses_canonical_domain(self):
        calls, transports = native_shaped_relations()
        before = deepcopy((calls, transports))
        self.assertNotEqual(transports[0]['reservation']['request_sha256'],
                            transports[0]['reservation']['canonical_request_sha256'])
        self.assertIsNone(check_successful_call_relations(calls, transports, 'pinned-model'))
        self.assertEqual((calls, transports), before)

    def test_raw_wire_hash_cannot_replace_call_canonical_hash(self):
        calls, transports = native_shaped_relations()
        calls[0]['token_count_request_sha256'] = transports[0]['reservation']['request_sha256']
        calls[0]['content_sha256'] = canonical_hash(calls[0], {'content_sha256'})
        with self.assertRaisesRegex(ContractError, 'request-usage-relations'):
            check_successful_call_relations(calls, transports, 'pinned-model')

    def test_changed_count_projection_rejected_despite_same_wire_hash(self):
        calls, transports = native_shaped_relations()
        transports[0]['reservation']['canonical_request_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ContractError, 'request-usage-relations'):
            check_successful_call_relations(calls, transports, 'pinned-model')

    def test_generation_digest_domain_remains_canonical(self):
        calls, transports = native_shaped_relations()
        calls[0]['request_sha256'] = transports[1]['reservation']['request_sha256']
        calls[0]['content_sha256'] = canonical_hash(calls[0], {'content_sha256'})
        with self.assertRaisesRegex(ContractError, 'request-usage-relations'):
            check_successful_call_relations(calls, transports, 'pinned-model')
