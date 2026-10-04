"""Bound disclosure and installation identities; no candidate-controlled policy."""

import shutil
from pathlib import Path
from lightyear_toolkit.workspace import sha


def disclosure(config):
    if type(config.get("fixture", False)) is not bool:
        raise ValueError("fixture-boolean-required")
    mode = config.get(
        "disclosure_mode", "field" if config.get("fixture") else "confidential"
    )
    if mode not in {"field", "confidential"}:
        raise ValueError("disclosure-mode-invalid")
    if not config.get("fixture", False) and mode != "confidential":
        raise ValueError("confidential-data-requires-confidential-mode")
    return mode


def project(diagnostics, mode):
    if mode == "field":
        return diagnostics
    if mode != "confidential":
        raise ValueError("disclosure-mode-invalid")
    # Exactly one bit per bound output dataset; no kinds, fields, bands or counts.
    allowed = {"STEP15/ACCTFILE", "STEP15/TRANSACT"}
    names = {d["dataset"] for d in diagnostics}
    if not names <= allowed:
        raise ValueError("diagnostic-dataset-unbound")
    return [{"dataset": name, "kind": "differs"} for name in sorted(names)]


def fingerprint(source=None):
    source = source or Path(__file__).resolve().parents[1]
    result = {}
    for package in (
        "lightyear_judge",
        "lightyear_toolkit",
        "lightyear_mainframe",
        "lightyear_control_tower",
    ):
        for p in sorted((source / package).rglob("*.py")):
            result[str(p.relative_to(source))] = sha(p.read_bytes())
    for p in sorted((source.parent / "spec/mainframe").rglob("*")):
        if p.is_file():
            result[str(p.relative_to(source.parent))] = sha(p.read_bytes())
    for name in ("bwrap", "java"):
        located = shutil.which(name)
        if not located:
            raise ValueError("sandbox-runtime-unavailable")
        binary = Path(located).resolve()
        result[name + ":path"] = str(binary)
        result[name + ":binary"] = sha(binary.read_bytes())
        if name == "java":
            # Follow packaged JVM configuration symlinks as well as modules/libraries.
            pending = [(binary.parent.parent, "")]
            visited = set()
            while pending:
                p, label = pending.pop()
                if p.is_symlink():
                    result["java-link:" + label] = str(p.readlink())
                if p.is_file():
                    result["java:" + label] = sha(p.read_bytes())
                elif p.is_dir():
                    if p.resolve() in visited:
                        continue
                    visited.add(p.resolve())
                    pending.extend(
                        (child, label + "/" + child.name)
                        for child in sorted(p.iterdir())
                    )
    return result
