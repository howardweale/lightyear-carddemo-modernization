"""Fail closed on CMS artifact upload scope; never reads artifact contents."""
from pathlib import Path
import yaml

ALLOWED = "work/cms/f0/public/receipt.json"


def check(config):
    uploads = 0
    for job in config.get("jobs", {}).values():
        for step in job.get("steps", []):
            uses = step.get("uses", "").lower()
            if "upload-artifact" not in uses:
                continue
            uploads += 1
            options = step.get("with", {})
            paths = options.get("path", "").splitlines()
            # Exact allowlist also refuses directories, globs, expressions and
            # exclusions that might accidentally include raw diagnostics.
            if [p.strip() for p in paths if p.strip()] != [ALLOWED]:
                raise ValueError("cms-upload-path-not-allowlisted")
            if str(options.get("retention-days")) != "1":
                raise ValueError("cms-upload-retention-must-be-one-day")
            if options.get("if-no-files-found") != "error":
                raise ValueError("cms-upload-missing-receipt-must-fail")
    if not uploads:
        raise ValueError("cms-upload-step-missing")


def check_repository(root):
    paths = []
    for path in sorted((Path(root) / ".github/workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        if "cms" in path.name.lower() or "tools/cms/" in text or "tools.cms." in text:
            check(yaml.load(text, Loader=yaml.BaseLoader))
            paths.append(path)
    if not paths:
        raise ValueError("cms-workflow-missing")
    return paths


if __name__ == "__main__":
    for path in check_repository(Path.cwd()):
        print(str(path) + ": metadata receipt only; one-day retention")
