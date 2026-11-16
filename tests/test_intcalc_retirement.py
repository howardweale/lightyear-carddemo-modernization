"""Retirement negatives. No oracle, case bundle, Docker or provider execution."""
import ast
import inspect
import io
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from lightyear_mainframe import intcalc_retirement as retirement

from lightyear_mainframe import intcalc_candidate_gate as _boundary0
from lightyear_factory import intcalc_preview_admission as _boundary1
from lightyear_factory import intcalc_preview_composition as _boundary2
from lightyear_factory import intcalc_preview_build_gate as _boundary3
from lightyear_factory import intcalc_preview_bootstrap as _boundary4
from tools import intcalc_attended_freeze as _boundary5
from tools import qualify_intcalc_attended_freeze as _boundary6
from lightyear_factory import intcalc_preview_transport as _boundary7
from tools import qualify_intcalc_preview_build_gate as _boundary8
MODULES = {
    'tools/qualify_intcalc_preview_build_gate.py': _boundary8,
    'src/lightyear_mainframe/intcalc_candidate_gate.py': _boundary0,
    'src/lightyear_factory/intcalc_preview_admission.py': _boundary1,
    'src/lightyear_factory/intcalc_preview_composition.py': _boundary2,
    'src/lightyear_factory/intcalc_preview_build_gate.py': _boundary3,
    'src/lightyear_factory/intcalc_preview_bootstrap.py': _boundary4,
    'tools/intcalc_attended_freeze.py': _boundary5,
    'tools/qualify_intcalc_attended_freeze.py': _boundary6,
    'src/lightyear_factory/intcalc_preview_transport.py': _boundary7,
}

TARGETS = {'src/lightyear_mainframe/intcalc_candidate_gate.py': ['run', '_run', 'execute_case'], 'src/lightyear_factory/intcalc_preview_admission.py': ['admit_preview'], 'src/lightyear_factory/intcalc_preview_composition.py': ['prepare', 'Composition.run'], 'src/lightyear_factory/intcalc_preview_build_gate.py': ['BuildGateAdapter.build', 'BuildGateAdapter.gate', 'worker_build', 'worker_gate', 'worker_main'], 'src/lightyear_factory/intcalc_preview_bootstrap.py': ['read_only_checks', 'hidden_api_key', 'volume_preflight', 'run_session', 'rehearse', 'configure', 'observe_disk', 'prepare_files', 'Ports.authenticate', 'Ports.admit', 'Ports.build', 'Ports.gate'], 'tools/intcalc_attended_freeze.py': ['bundle_files', 'run_core', 'attended'], 'tools/qualify_intcalc_attended_freeze.py': ['main'], 'src/lightyear_factory/intcalc_preview_transport.py': ['PreviewTransport.complete', 'PreviewTransport._call'], 'tools/qualify_intcalc_preview_build_gate.py': ['run']}


class RetirementTests(unittest.TestCase):
    def test_registry_closes_current_lineage(self):
        with self.assertRaisesRegex(ValueError, "^retired-verifier-set$"):
            retirement.require_current()

    def test_missing_and_tampered_registry_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "registry.json"
            for raw in (None, b"{}", b'{"state":"ACTIVE"}'):
                if raw is not None:
                    p.write_bytes(raw)
                with patch.object(retirement, "ROOT", root), patch.object(retirement, "REGISTRY", p):
                    with self.assertRaisesRegex(ValueError, "^retirement-registry-invalid$"):
                        retirement.require_current()

    def test_no_environment_override(self):
        with patch.dict(os.environ, {"CI":"true", "GITHUB_ACTIONS":"true", "ALLOW_RETIRED":"1"}):
            with self.assertRaisesRegex(ValueError, "^retired-verifier-set$"):
                retirement.require_current()

    def test_registry_link_refused_without_link_creation(self):
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(ValueError, "^retirement-registry-invalid$"):
                retirement.require_current()

    def test_fixed_cli_code(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(retirement.main(), 2)
        self.assertEqual(stream.getvalue(), "retired-verifier-set\n")

    def test_all_entrypoints_refuse_before_effects(self):
        for path, names in TARGETS.items():
            module = MODULES[path]
            for name in names:
                with self.subTest(path=path, function=name):
                    parts = name.split(".")
                    if len(parts) == 2:
                        cls = getattr(module, parts[0])
                        fn = getattr(object.__new__(cls), parts[1])
                    else:
                        fn = getattr(module, name)
                    args, kwargs = [], {}
                    for p in inspect.signature(fn).parameters.values():
                        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD): args.append(None)
                        elif p.kind == p.KEYWORD_ONLY: kwargs[p.name] = None
                    with patch("subprocess.Popen") as spawn, patch("subprocess.run") as run, \
                         patch("urllib.request.urlopen") as network, patch("getpass.getpass") as prompt:
                        with self.assertRaisesRegex(ValueError, "^retired-verifier-set$"):
                            fn(*args, **kwargs)
                        spawn.assert_not_called(); run.assert_not_called()
                        network.assert_not_called(); prompt.assert_not_called()

    def test_guard_is_first_statement(self):
        for path, names in TARGETS.items():
            source = (retirement.ROOT / path).read_text(encoding="utf-8")
            tree = ast.parse(source)
            functions = {n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
            for cls in tree.body:
                if isinstance(cls,ast.ClassDef):
                    functions.update({cls.name+"."+n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)})
            for name in names:
                body = functions[name].body
                first = body[1] if isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str) else body[0]
                self.assertIsInstance(first,ast.Expr)
                self.assertEqual(ast.unparse(first.value.func),"retirement.require_current")


if __name__ == "__main__":
    unittest.main()
