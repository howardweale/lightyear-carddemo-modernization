"""CI-only Windows runtime assembly; no identity, key, signing or activation."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def build(repository, output):
    if sys.platform != "win32" or sys.version_info[:3] != (3, 12, 10):
        raise ValueError("Pinned Windows CPython 3.12.10 required")
    if output.exists():
        raise ValueError("Fresh output directory required")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    output.mkdir(parents=True)
    base = Path(sys.base_prefix)
    python = output / "python"
    python.mkdir()
    # Copy interpreter, DLLs and stdlib; never copy runner-installed site packages.
    for source in base.iterdir():
        if source.is_file() and source.suffix.lower() in {".exe", ".dll", ".zip", ".txt"}:
            shutil.copyfile(source, python / source.name)
    for directory in ("DLLs", "Lib"):
        shutil.copytree(base / directory, python / directory,
                        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "test", "tests", "*.pyc"))
    packages = python / "Lib" / "site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--only-binary=:all:", "--no-compile", "--target", str(packages),
                    "cryptography==46.0.3", "cffi==2.0.0", "pycparser==2.23"], check=True)
    app = output / "app"
    # Git archive extraction admits committed bytes only, never workspace secrets.
    tracked = subprocess.check_output(["git", "ls-files", "-z", "src", "tools/__init__.py",
                                      "tools/import_factory_tower_snapshot.py", "tools/factory_install",
                                      "knowledge/viewer/decision-console.html",
                                      "knowledge/viewer/decision-console.js",
                                      "knowledge/viewer/decision-console.css",
                                      "knowledge/viewer/styles.css"], cwd=repository).decode().split("\0")
    for name in filter(None, tracked):
        entry = subprocess.check_output(["git", "ls-tree", "HEAD", "--", name], cwd=repository).decode()
        if not entry.startswith(("100644 blob ", "100755 blob ")):
            raise ValueError("Nonregular committed source: " + name)
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=repository))
    shutil.copyfile(app / "tools/factory_install/Start-FactoryTower.ps1", output / "Start-FactoryTower.ps1")
    files = []
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise ValueError("Links forbidden")
        if path.is_file():
            data = path.read_bytes()
            files.append({"path": path.relative_to(output).as_posix(), "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema": "factory-install-bundle/1", "source_commit": commit,
                "python": "3.12.10", "dependencies": ["cryptography==46.0.3", "cffi==2.0.0", "pycparser==2.23"],
                "files": files, "keys_created": False, "signed_only_activated": False}
    target = output / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "source_commit": commit, "files": len(files)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.repository.resolve(), args.output.resolve())