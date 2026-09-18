"""Isolated external project + retained evidence checkout for agent tests."""
from pathlib import Path
import shutil
import tempfile

from lightyear_agent.service import initialize
from lightyear_data.cloudbank_publication import BUNDLE

ROOT = Path(__file__).resolve().parents[1]


def fixture(test):
    temp = tempfile.TemporaryDirectory()
    test.addCleanup(temp.cleanup)
    base = Path(temp.name).resolve()
    root = base / "evidence"
    root.mkdir()
    for name in ("src", "factory/cloudbank", "reference-estates/cloudbank", BUNDLE.as_posix()):
        shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "control-tower").mkdir()
    for name in ("workflow-policy.json", "execution-policy.json"):
        shutil.copyfile(ROOT / "control-tower" / name, root / "control-tower" / name)
    project = base / "customer-repository/lightyear.project.json"
    initialize(project, root, "external-project")
    return root, project


def finish_local(workflow, run_id):
    """Real observation and replay, omitting only subprocess creation in unit tests."""
    from unittest.mock import patch
    from lightyear_workflow.cloudbank import observe
    def worker(root, action, *_):
        return observe(root, action["service"], action["lane"])
    with patch("lightyear_workflow.execution.run_worker", side_effect=worker):
        workflow.work(run_id)
