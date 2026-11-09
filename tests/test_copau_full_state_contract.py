"""Public synthetic CI for irreversible stage ordering; no private operation."""
import unittest

from lightyear_execution import copau_full_state_contract as stage


class MemoryStore:
    """Exclusive in-memory CI double, not a custody implementation."""
    def __init__(self):
        self.files = {}

    def absent(self, *names):
        if any(n in self.files for n in names):
            raise stage.Refused('already-present')

    def write(self, name, raw):
        self.absent(name)
        if not 0 < len(raw) <= 262144:
            raise stage.Refused('store-limit')
        self.files[name] = bytes(raw)

    def read(self, name):
        if name not in self.files:
            raise stage.Refused('missing-stage')
        return self.files[name]


class FullStateStageTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.bindings = {'frozen-test-source': 'a' * 64}
        self.commitment = stage.stage_inputs(self.store, {'public': [1, 2, 3]},
            context_sha256='b' * 64, producer_bindings=self.bindings)

    def ack(self):
        stage.acknowledge(self.store, b'PUBLIC SYNTHETIC ACK',
                          verifier=lambda _: self.commitment)

    def consume(self, **kwargs):
        return stage.consume(self.store, verifier=lambda _: self.commitment,
                              producer_bindings=kwargs.get('bindings', self.bindings))

    def test_missing_ack_cannot_consume(self):
        with self.assertRaises(stage.Refused):
            self.consume()
        self.assertNotIn('n1-consumed.json', self.store.files)

    def test_boolean_or_changed_context_cannot_ack(self):
        for authenticated in (True, False, self.commitment + b' ', b'approved'):
            with self.subTest(authenticated=type(authenticated).__name__), self.assertRaises(stage.Refused):
                stage.acknowledge(self.store, b'public', verifier=lambda _: authenticated)
        self.assertNotIn('n1-ack.json', self.store.files)

    def test_ack_reauthenticated_and_consumed_once(self):
        self.ack()
        with self.assertRaises(stage.Refused):
            stage.consume(self.store, verifier=lambda _: b'changed', producer_bindings=self.bindings)
        inputs, binding = self.consume()
        self.assertEqual(inputs, {'public': [1, 2, 3]})
        self.assertEqual(binding['commitment_sha256'], stage.sha(self.commitment))
        with self.assertRaises(stage.Refused):
            self.consume()

    def test_input_replacement_refused_after_ack(self):
        self.ack()
        self.store.files['n1-input-0.json'] = stage.encoded({'hex': b'wrong'.hex()})
        with self.assertRaises(stage.Refused):
            self.consume()
        self.assertNotIn('n1-consumed.json', self.store.files)

    def test_source_drift_refused_before_consume(self):
        self.ack()
        with self.assertRaises(stage.Refused):
            self.consume(bindings={'frozen-test-source': 'c' * 64})
        self.assertNotIn('n1-consumed.json', self.store.files)

    def test_large_blob_chunks_preserve_all_bytes_and_no_overwrite(self):
        raw = bytes(range(256)) * 2049
        digest = stage.put_blob(self.store, 'public-fixture', raw)
        self.assertEqual(stage.get_blob(self.store, 'public-fixture'), raw)
        self.assertEqual(digest, stage.sha(raw))
        with self.assertRaises(stage.Refused):
            stage.put_blob(self.store, 'public-fixture', raw)
        self.store.files.pop('public-fixture-2.json')
        with self.assertRaises(stage.Refused):
            stage.get_blob(self.store, 'public-fixture')

    def test_duplicate_json_and_nonfinite_numbers_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(stage.Refused):
                stage.decoded(raw)

    def test_authentication_exception_is_redacted(self):
        def failed(_):
            raise RuntimeError('PRIVATE SENTINEL')
        with self.assertRaisesRegex(stage.Refused, '^ack-authentication-failed$'):
            stage.acknowledge(self.store, b'public', verifier=failed)

    def test_reprepare_cannot_replace_input_commitment(self):
        with self.assertRaises(stage.Refused):
            stage.stage_inputs(self.store, {'different': True}, context_sha256='c' * 64,
                               producer_bindings=self.bindings)
        self.assertEqual(self.store.read('n1-commitment.json'), self.commitment)
