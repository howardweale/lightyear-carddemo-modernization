#!/usr/bin/env bash
# Run ONLY on the dedicated approved Linux VM. Builds/parses; never runs databases.
set -euo pipefail
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "Requires the dedicated x86_64 Linux VM." >&2; exit 2;
}
: "${TSQL_VM_APPROVED:?Set TSQL_VM_APPROVED=yes only after Howard approves this VM}"
[[ "$TSQL_VM_APPROVED" == yes ]] || exit 2
command -v dotnet >/dev/null
command -v python3 >/dev/null
dotnet --list-sdks | grep -q '^8\.' || { echo ".NET 8 SDK required" >&2; exit 2; }
TSQL_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TSQL_OUT="${1:?Usage: build-linux.sh /absolute/new/build-result-directory}"
[[ "$TSQL_OUT" == /* && ! -e "$TSQL_OUT" ]] || {
  echo "Output must be an absolute new path; preserve previous build results." >&2; exit 2;
}
mkdir -p -- "$(dirname -- "$TSQL_OUT")"
mkdir -- "$TSQL_OUT"
cd -- "$TSQL_REPO"
dotnet --info > "$TSQL_OUT/dotnet-info.txt"
dotnet restore tools/tsql_scriptdom/TsqlInventory.csproj --use-lock-file \
  2>&1 | tee "$TSQL_OUT/restore.log"
dotnet build tools/tsql_scriptdom/TsqlInventory.csproj --no-restore -c Release \
  --output "$TSQL_OUT/bin" 2>&1 | tee "$TSQL_OUT/build.log"
python3 - "$TSQL_REPO" "$TSQL_OUT" <<'PY'
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

root, out = map(Path, sys.argv[1:])
start = datetime.now(timezone.utc).isoformat()
clock = time.monotonic()
sha = lambda b: hashlib.sha256(b).hexdigest()
manifest_path = root / "data-modernization/tsql-procedures/corpus.json"
manifest_raw = manifest_path.read_bytes()
manifest = json.loads(manifest_raw)
results = []
dll = out / "bin/TsqlInventory.dll"
for item in manifest["procedures"]:
    asset = item["assets"]["source"]
    path = (root / asset["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("corpus-path-escaped")
    raw = path.read_bytes()
    if sha(raw) != asset["sha256"]:
        raise ValueError("corpus-source-changed")
    result = {"id": item["id"], "source_sha256": sha(raw), "passed": False}
    try:
        process = subprocess.run(["dotnet", str(dll)], input=raw,
                                 capture_output=True, timeout=30, check=False)
        (out / (item["id"] + ".stdout.json")).write_bytes(process.stdout)
        (out / (item["id"] + ".stderr.txt")).write_bytes(process.stderr)
        body = json.loads(process.stdout)
        result.update(exit_code=process.returncode,
                      stdout_sha256=sha(process.stdout), stderr_sha256=sha(process.stderr))
        result["passed"] = (
            process.returncode == 0 and body.get("schema") == "tsql-scriptdom/1"
            and body.get("input_sha256") == sha(raw) and body.get("parsed") is True
            and body.get("procedure_count") == 1 and body.get("errors") == []
            and bool(body.get("ast_nodes")) and bool(body.get("version"))
        )
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        result["failure_type"] = type(exc).__name__
    results.append(result)
report = {
    "schema": "tsql-scriptdom-build-check/1", "started_utc": start,
    "finished_utc": datetime.now(timezone.utc).isoformat(),
    "elapsed_seconds": round(time.monotonic() - clock, 3),
    "corpus_file_sha256": sha(manifest_raw), "bridge_sha256": sha(dll.read_bytes()),
    "package_lock_sha256": sha((root / "tools/tsql_scriptdom/packages.lock.json").read_bytes()),
    "parser_checks": results, "passed": len(results) == 42 and all(r["passed"] for r in results),
    "native_pairs": 0, "model_calls": 0,
    "claim": "Parser build and syntax only; no semantic qualification",
}
(out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": report["passed"], "procedures": len(results),
                  "report": str(out / "report.json"), "model_calls": 0}))
raise SystemExit(0 if report["passed"] else 1)
PY
