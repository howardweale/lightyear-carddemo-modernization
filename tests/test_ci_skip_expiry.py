"""Named skip exception lifecycle; synthetic files and clock, no external access."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import ci_test_execution as policy


class NamedSkipExpiryTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'tests/test_fixture.py'; source.parent.mkdir()
        source.write_bytes(b'# synthetic test\n')
        gate = root / 'gate.py'; gate.write_bytes(b'# retired boundary\n')
        self.entry = dict(selector='test_fixture.Example', scope='class', reason='named gap',
            rationale='Named synthetic test exception', platforms=['Linux', 'Windows'],
            exception=dict(name='SYNTHETIC_EXCEPTION', expires_at='2030-05-07T00:00:00-07:00',
                valid_while_sources={'gate.py':hashlib.sha256(gate.read_bytes()).hexdigest()}))
        self.value = dict(schema='ci-test-skip-policy/1', allowances=[self.entry],
            sources={'tests/test_fixture.py':hashlib.sha256(source.read_bytes()).hexdigest()})
        self.path = root / 'policy.json'
        return gate

    def load(self, root, instant):
        self.path.write_text(json.dumps(self.value), encoding='utf-8')
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return instant.astimezone(tz)
        with patch.object(policy, 'datetime', Clock):
            return policy.load_policy(self.path, root)

    def test_before_boundary_accepts_and_exact_instant_expires(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.fixture(root)
            self.assertEqual(self.load(root, datetime(2030,5,7,6,59,59,tzinfo=timezone.utc)), self.value)
            for instant in (datetime(2030,5,7,7,tzinfo=timezone.utc), datetime(2030,5,8,tzinfo=timezone.utc)):
                with self.subTest(instant=instant), self.assertRaisesRegex(ValueError, 'skip-policy-exception-expired'):
                    self.load(root, instant)

    def test_gate_replacement_ends_before_date(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); gate=self.fixture(root); gate.write_bytes(b'# reference-backed gate\n')
            with self.assertRaisesRegex(ValueError, 'skip-policy-exception-ended'):
                self.load(root, datetime(2030,5,1,tzinfo=timezone.utc))

    def test_missing_gate_and_empty_sources_refuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); gate=self.fixture(root); gate.unlink()
            with self.assertRaisesRegex(ValueError, 'skip-policy-exception-source'):
                self.load(root, datetime(2030,5,1,tzinfo=timezone.utc))
            self.entry['exception']['valid_while_sources']={}
            with self.assertRaisesRegex(ValueError, 'skip-policy-exception-sources'):
                self.load(root, datetime(2030,5,1,tzinfo=timezone.utc))

    def test_naive_or_invalid_expiry_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.fixture(root)
            for value in ('2030-05-07', '2030-05-07T00:00:00', 'invalid', None):
                self.entry['exception']['expires_at']=value
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'skip-policy-exception-expiry'):
                    self.load(root, datetime(2030,5,1,tzinfo=timezone.utc))

    def test_path_escape_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.fixture(root)
            for name in ('../gate.py', '/gate.py', 'a//gate.py', 'C:/gate.py'):
                self.entry['exception']['valid_while_sources']={name:'a'*64}
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'skip-policy-exception-path'):
                    self.load(root, datetime(2030,5,1,tzinfo=timezone.utc))

    def test_ordinary_allowance_retains_prior_behavior(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.fixture(root); del self.entry['exception']
            self.assertEqual(self.load(root, datetime(2031,1,1,tzinfo=timezone.utc)), self.value)


if __name__ == '__main__': unittest.main()
