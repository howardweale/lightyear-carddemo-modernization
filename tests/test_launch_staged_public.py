"""Synthetic wiring and refusal checks. Never spawn the real key owner or Docker."""
import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tools import launch_staged_public as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.gate = Mock()
        self.storage, self.adapter, self.retainer = Mock(), Mock(), Mock()
        self.wire = Mock(return_value=(self.storage, self.adapter, self.retainer))
        self.ports = launcher.Ports(self.gate, self.wire, 100)
        self.owner = self.enterContext(patch.object(launcher.provider, "KeyOwner"))
        self.provider = self.enterContext(patch.object(launcher.provider, "ProviderPorts"))
        self.models = self.provider.return_value
        self.models.closed = True
        self.models.failed = False

    def admit(self):
        return self.ports.admit(b"binding", 150)

    def test_failed_admission_never_constructs_an_owner_or_worker(self):
        self.gate.admit.side_effect = ValueError("refused")
        with self.assertRaises(ValueError):
            self.admit()
        self.owner.assert_not_called()
        self.wire.assert_not_called()
        with self.assertRaisesRegex(ValueError, "launcher-state"):
            self.admit()

    def test_successful_admission_only_installs_local_ports(self):
        self.assertIs(self.admit(), self.gate.admit.return_value)
        self.gate.admit.assert_called_once_with(b"binding", 100)
        self.owner.assert_not_called()

    def test_count_before_admission_refuses(self):
        with self.assertRaisesRegex(ValueError, "launcher-state"):
            self.ports.count({}, 90)
        self.owner.assert_not_called()

    def test_first_count_starts_one_owner_and_preserves_earlier_deadline(self):
        self.admit()
        self.ports.count({"role": "planner"}, 75)
        self.ports.count({"role": "builder"}, 110)
        self.owner.assert_called_once_with(75)
        self.models.count.assert_called_with({"role": "builder"}, 100)

    def test_owner_reaped_on_provider_assembly_error(self):
        self.admit()
        self.provider.side_effect = ValueError()
        with self.assertRaises(ValueError):
            self.ports.count({}, 90)
        self.owner.return_value.close.assert_called_once_with(90)

    def test_generate_requires_count_and_open_models(self):
        self.admit()
        with self.assertRaises(ValueError):
            self.ports.generate({}, 90)
        self.ports.count({}, 90)
        self.ports.generate({}, 120)
        self.models.generate.assert_called_once_with({}, 100)
        self.ports.close_models()
        with self.assertRaises(ValueError):
            self.ports.generate({}, 90)

    def test_close_is_single_use_even_on_failure(self):
        self.admit()
        self.ports.count({}, 90)
        self.models.close_models.side_effect = ValueError()
        self.models.failed = True
        with self.assertRaises(ValueError):
            self.ports.close_models()
        self.ports.close_models()
        with self.assertRaisesRegex(ValueError, "launcher-closure"):
            self.ports.retain_selected_jar({}, {}, "hash", 100)
        self.models.close_models.assert_called_once()

    def test_retention_only_after_closure(self):
        self.admit()
        self.ports.count({}, 90)
        with self.assertRaises(ValueError):
            self.ports.retain_selected_jar({}, {}, "hash", 120)
        self.ports.close_models()
        self.ports.retain_selected_jar({"round": 2}, {}, "hash", 120)
        self.retainer.retain_selected_jar.assert_called_once_with({"round": 2}, {}, "hash", 100)
        self.assertFalse(hasattr(self.ports, "evaluate_hidden"))

    def test_original_deadline_reaches_build_and_evaluator(self):
        self.admit()
        self.ports.build("source", 1, 105)
        self.ports.evaluate_public({}, "suite", 99)
        self.adapter.build.assert_called_once_with("source", 1, 100)
        self.adapter.evaluate_public.assert_called_once_with({}, "suite", 99)

    def test_result_readback_includes_ledger_newline(self):
        self.admit()
        row = {"status": "PUBLIC_FAIL"}
        self.storage.record.return_value = launcher.ctl.digest(row)
        with self.assertRaisesRegex(ValueError, "launcher-readback"):
            self.ports.record("result", row)
        digest = launcher.ctl.sha(launcher.ctl.canonical(row) + b"\n")
        self.storage.record.return_value = digest
        self.assertEqual(self.ports.record("result", row), digest)

    def test_separate_receipts_share_same_durable_store(self):
        self.assertTrue(issubclass(launcher.Storage, launcher.staged.StagedDurablePorts))
        self.assertTrue(issubclass(launcher.Storage, launcher.provider.ProviderEvidence))
        sink = Mock()
        sink._operation.side_effect = lambda fn: fn()
        launcher.Storage.retain_evaluation(sink, b"bound")
        sink._write.assert_called_once_with("evaluation-" + launcher.ctl.sha(b"bound") + ".json", b"bound")

    def test_early_failure_has_fixed_public_readback(self):
        error = io.StringIO()
        with patch.object(launcher, "launch", side_effect=ValueError("sensitive path")), contextlib.redirect_stderr(error):
            self.assertEqual(launcher.main(["--bundle", str(Path.cwd()), "--approval-sha256", "a"*64]), 2)
        self.assertEqual(error.getvalue(), "staged-launch-stopped-no-resume\n")

    def test_controller_through_launcher_wiring_returns_retained_pending(self):
        import test_public_repair_staged as fixture
        fake = fixture.StagedPorts()
        raw = launcher.ctl.canonical
        def record(name, row):
            fake.record(name, row)
            return launcher.ctl.sha(raw(row) + b"\n")
        self.storage.record.side_effect = record
        self.storage.retain_artifact.side_effect = fake.retain_artifact
        self.gate.admit.side_effect = fake.admit
        self.adapter.build.side_effect = fake.build
        self.adapter.evaluate_public.side_effect = fake.evaluate_public
        self.retainer.retain_selected_jar.side_effect = fake.retain_selected_jar
        self.models.count.side_effect = fake.count
        self.models.generate.side_effect = fake.generate
        self.models.close_models.side_effect = fake.close_models
        self.ports.deadline = 1000000
        result = launcher.staged.StagedController(
            self.ports, fixture.binding(), fixture.CONTEXT, fixture.Clock()).run()
        self.assertEqual(result["status"], "PUBLIC_COMPLETE_HIDDEN_PENDING")
        self.assertEqual(result["hidden"]["status"], "PENDING")
        self.assertEqual(result["retained_jar"]["jar_sha256"], launcher.ctl.sha(fixture.JAR))
        self.assertFalse(fake.hidden_calls)
        self.owner.assert_called_once()
