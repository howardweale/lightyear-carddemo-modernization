"""Scratch-only component runner. Results never grant execution or qualification."""
import json
import os
from pathlib import Path
import sys
import unittest

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("scratch-ci-only")
    if os.environ.get("GITHUB_HEAD_REF") != "codex/scratch-configured-route-wip":
        raise SystemExit("scratch-branch-required")
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY", "FACTORY_TRANSPORT_KEY",
                 "FACTORY_CANDIDATE_SIGNING_KEY"):
        if os.environ.get(name):
            raise SystemExit("scratch-credential-present")
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / "tools/ci/scratch_configured_tests.json").read_bytes())
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in manifest["modules"])
    count = suite.countTestCases()
    suite.addTests(loader.loadTestsFromName('test_scratch_disposable_trust'))
    trust_count = suite.countTestCases() - count
    publisher_suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in manifest["publisher_modules"])
    publisher_count = publisher_suite.countTestCases()
    suite.addTests(publisher_suite)
    integration_suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in manifest["integration_modules"])
    integration_count = integration_suite.countTestCases()
    suite.addTests(integration_suite)
    total = suite.countTestCases()
    print(f"DISPOSABLE SCRATCH ONLY: configured={count}/419; trust regressions={trust_count}/2; publisher components={publisher_count}/120; controller integration={integration_count}/109; no qualification authority", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"scratch_only": True, "discovered": count, "publisher_discovered": publisher_count, "integration_discovered": integration_count, "run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "skipped": len(result.skipped), "qualification_evidence": False}), flush=True)
    return 0 if result.wasSuccessful() and count == 419 and trust_count == 2 and publisher_count == 120 and integration_count == 109 and total == 650 and not loader.errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
