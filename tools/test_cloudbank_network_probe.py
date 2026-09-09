#!/usr/bin/env python3
"""Recompile the shipped socket probe with JDK 17 and compare exact bytecode."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / "factory/cloudbank/platform-qualification/gke/network-probe"
saved = json.loads((folder / "compiled.json").read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory(prefix="ms67-probe-recompile-") as work:
    subprocess.run(["java", "-m", "jdk.compiler/com.sun.tools.javac.Main", "--release", "17", "-g:none",
                    "-XDstringConcat=inline", "-d", work, str(folder / "NetworkProbe.java")], check=True, timeout=45)
    assert saved["source_sha256"] == hashlib.sha256((folder / "NetworkProbe.java").read_bytes()).hexdigest()
    assert base64.b64decode(saved["class_base64"], validate=True) == (Path(work) / "NetworkProbe.class").read_bytes()
    assert saved["class_sha256"] == hashlib.sha256((Path(work) / "NetworkProbe.class").read_bytes()).hexdigest()
print("MS67_NETWORK_PROBE_SOURCE_AND_BYTECODE=VERIFIED")
