"""Bounded F0 probe of pinned public CMS software, independently tested.

Downloads remain under work/cms; CMS source bytes are never rewritten.
This probe does not perform or publish cross-language comparisons.
"""
import argparse
import hashlib
import io
import json
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from tools.cms.f0_policy import compile_outcome, diagnostic_metadata, require_compile, require_java


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("work/cms/f0"))
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--java", action="store_true")
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--expected-failures", type=Path, default=Path("docs/cms/f0-known-compile-limitations.json"))
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    pins = json.loads(args.pins.read_text())
    packages = {}
    for pin in pins:
        name = pin["url"].rsplit("/", 1)[1]
        dest = root / name
        if not dest.exists():
            data = urllib.request.urlopen(pin["url"], timeout=90).read()
            if hashlib.sha256(data).hexdigest() != pin["sha256"]:
                raise ValueError("CMS download changed: " + name)
            dest.write_bytes(data)
        data = dest.read_bytes()
        if len(data) != pin["size_bytes"] or hashlib.sha256(data).hexdigest() != pin["sha256"]:
            raise ValueError("Pinned download verification failed: " + name)
        packages[name] = dest
    if args.compile:
        policy = json.loads(args.expected_failures.read_bytes())
        if policy.get("schema") != "cms-f0-known-compile-limitations/1" or not policy.get("program_inventory"):raise ValueError("unbound compile inventory")
        compile_probe(root, packages, policy["expected_failures"], policy["program_inventory"])
    if args.java:
        java_probe(root, packages, args.claims)


def compile_probe(root, packages, expected=(), inventory=None):
    version = subprocess.check_output(["cobc", "-V"], text=True)
    if "3.1.2" not in version.splitlines()[0]:
        raise ValueError("Expected pinned GnuCOBOL 3.1.2")
    rows = []
    for package in ["files-fy-20215-software-release.zip", "cy-20212-esrd-main-frame-pricing-programs.zip"]:
        src = root / package.removesuffix(".zip")
        src.mkdir(exist_ok=True)
        with zipfile.ZipFile(packages[package]) as archive:
            for member in archive.infolist():
                assert Path(member.filename).name == member.filename
                (src / member.filename).write_bytes(archive.read(member))
        modules = {}
        for path in src.iterdir():
            text = path.read_bytes().decode("cp1252")
            active = "\n".join(line[7:72] for line in text.splitlines() if len(line) > 6 and line[6] not in "*/")
            match = re.search(r"PROGRAM-ID\.\s*([\w-]+)", active, re.I)
            if match:
                modules[match[1].upper()] = (path, active)
        for name, (path, active) in modules.items():
            alias = src / (path.name + ".cob")
            alias.write_bytes(path.read_bytes())
            assert alias.read_bytes() == path.read_bytes()
            calls = sorted(set(re.findall(r"\bCALL\s+['\"]([^'\"]+)['\"]", active, re.I)))
            copies = sorted(set(re.findall(r"\bCOPY\s+([\w-]+)", active, re.I)))
            for dialect in ["ibm", "default", "mf"]:
                command = ["cobc", "-m", "-fixed", "-std=" + dialect, "-I", str(src), "-o", str(src / (name + ".so")), str(alias)]
                start = time.monotonic()
                result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                log = root / "compile-logs" / (package + "-" + name + "-" + dialect + ".txt")
                log.parent.mkdir(exist_ok=True)
                log.write_text(result.stdout + result.stderr, encoding="utf-8")
                rows.append({"package": package, "program": name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "dialect": dialect, "returncode": result.returncode, "elapsed_seconds": round(time.monotonic()-start, 3), "calls": calls, "missing_static_calls": sorted(set(calls)-set(modules)), "copies": copies, "missing_copybooks": [n for n in copies if not (src/n).exists()], "log": str(log.relative_to(root)), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "diagnostic_metadata": diagnostic_metadata(result.stdout + result.stderr, active.splitlines())})
                if result.returncode == 0:
                    break
    outcome = compile_outcome(rows, expected, inventory)
    save(root / "compile-results.json", {"compiler": version, "results": rows, "source_modified": False, "outcome": outcome})
    require_compile(outcome)


def java_probe(root, packages, claims_path=None):
    claims_required = claims_path is not None or (root / "generated-claims.json").exists()
    # Refuse occupied ports; never send synthetic requests to another service.
    for port in (18771, 18772):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    with zipfile.ZipFile(packages["ipps-pricer-2027-0-v2-14-1-executable-jar.zip"]) as archive:
        jar = root / "ipps-pricer-application-2.14.1.jar"
        jar.write_bytes(archive.read(jar.name))
    command = ["java", "-Xmx512m", "--add-opens", "java.base/java.lang=ALL-UNNAMED", "-Ddw.supportedYears=2021", "-Ddw.server.applicationConnectors[0].port=18771", "-Ddw.server.applicationConnectors[0].bindHost=127.0.0.1", "-Ddw.server.adminConnectors[0].port=18772", "-Ddw.server.adminConnectors[0].bindHost=127.0.0.1", "-jar", str(jar), "server"]
    version = subprocess.run(["java", "-version"], capture_output=True, text=True).stderr
    result = {"java_version": version, "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(), "command": command, "synthetic_only": True, "comparisons": "not performed", "claims": []}
    start = time.monotonic()
    with (root / "java-server.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=root)
        try:
            for _ in range(90):
                if process.poll() is not None:
                    raise RuntimeError("Java server exited: " + str(process.returncode))
                try:
                    with urllib.request.urlopen("http://127.0.0.1:18771/openapi.json", timeout=2) as response:
                        schema = json.load(response)
                    break
                except (OSError, ValueError):
                    time.sleep(1)
            else:
                raise RuntimeError("Java startup deadline exceeded")
            save(root / "openapi.json", schema)
            result["paths"] = list(schema["paths"])
            # A supplied synthetic claim is explicit and reviewable. Missing input
            # produces an interface-only probe rather than an invented paid claim.
            claims_path = claims_path or root / "generated-claims.json"
            if claims_path.exists():
                claims = json.loads(claims_path.read_text())
                assert len(claims) == 5
                for claim in claims:
                    request = urllib.request.Request("http://127.0.0.1:18771/v2/price-claim", data=json.dumps(claim).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"})
                    try:
                        with urllib.request.urlopen(request, timeout=15) as response:
                            status, body = response.status, json.load(response)
                    except urllib.error.HTTPError as exc:
                        status, body = exc.code, json.loads(exc.read())
                    result["claims"].append({"input": claim, "http_status": status, "output": body})
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            result["owned_process_stopped"] = process.poll() is not None
            result["elapsed_seconds"] = round(time.monotonic()-start, 3)
            require_java(result, claims_required)
            save(root / "java-results.json", result)
    if not result["complete"]:raise SystemExit("cms-f0-java-incomplete")


if __name__ == "__main__":
    main()
