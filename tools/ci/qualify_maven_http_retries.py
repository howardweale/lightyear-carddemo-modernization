"""CI-only check of the installed Maven client against an isolated synthetic repository."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import time


PARENT_PATH = "/local/probe/parent/1/parent-1.pom"
PARENT = b"""<project><modelVersion>4.0.0</modelVersion><groupId>local.probe</groupId>
<artifactId>parent</artifactId><version>1</version><packaging>pom</packaging></project>"""
CHILD = """<project><modelVersion>4.0.0</modelVersion><parent><groupId>local.probe</groupId>
<artifactId>parent</artifactId><version>1</version><relativePath/></parent>
<artifactId>child</artifactId><packaging>pom</packaging></project>"""


def distribution():
    info = subprocess.check_output(["mvn", "--version"], text=True, timeout=20)
    info = re.sub(r"\x1b\[[0-9;]*m", "", info)
    version = re.search(r"^Apache Maven (\S+)", info, re.MULTILINE).group(1)
    lib = Path(re.search(r"^Maven home: (.+)$", info, re.MULTILINE).group(1).strip()) / "lib"
    api, = lib.glob("maven-resolver-api-*.jar")
    resolver = api.stem.removeprefix("maven-resolver-api-")
    artifact, transporter, prefix = {
        "1": ("http", "HttpTransporter", "aether.connector.http"),
        "2": ("apache", "ApacheTransporter", "aether.transport.http"),
    }[resolver.split(".")[0]]
    jar = lib / f"maven-resolver-transport-{artifact}-{resolver}.jar"
    if not jar.is_file():
        raise ValueError("Maven distribution lacks the expected HTTP transport")
    print(f"Maven {version}, Resolver {resolver}, {jar.name}, namespace {prefix}", flush=True)
    properties = {"count": "3", "interval": "5000", "intervalMax": "30000",
                  "serviceUnavailable": "429,500,502,503,504"}
    central_backoff = (version, resolver) == ("3.9.11", "1.9.24")
    if central_backoff:
        properties.update({"count.central": "6", "intervalMax.central": "60000"})
    policy = " ".join(f"-D{prefix}.retryHandler.{k}={v}" for k, v in properties.items())
    return transporter, central_backoff, policy


def qualify(folder, name, statuses, transporter, env, *, bad_checksum=False,
            retry_after=None, retry_after_at=None, repository_id="probe", timeout=85):
    folder.mkdir()
    events = []

    class Repository(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == PARENT_PATH:
                status = statuses[min(len(events), len(statuses) - 1)]
                events.append((status, time.monotonic()))
                body = PARENT if status == 200 else b""
                if bad_checksum:
                    body += b" "
            elif self.path == PARENT_PATH + ".sha1":
                status = 200
                body = hashlib.sha1(PARENT).hexdigest().encode()
            else:
                status, body = 404, b""
            self.send_response(status)
            if (retry_after and status in (429, 503)
                    and (retry_after_at is None or len(events) == retry_after_at)):
                self.send_header("Retry-After", retry_after)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Repository) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/"
            settings = (f"<settings><mirrors><mirror><id>{repository_id}</id><mirrorOf>*</mirrorOf>"
                        f"<url>{url}</url></mirror></mirrors></settings>")
            (folder / "settings.xml").write_text(settings, encoding="utf-8")
            (folder / "global.xml").write_text("<settings/>", encoding="utf-8")
            (folder / "pom.xml").write_text(CHILD, encoding="utf-8")
            run = subprocess.run(
                ["mvn", "-B", "-X", "-C", "-gs", "global.xml", "-s", "settings.xml",
                 f"-Dmaven.repo.local={folder / 'local'}", "validate"],
                cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=timeout, check=False)
        finally:
            server.shutdown()
            thread.join()

    codes = [code for code, _ in events]
    gaps = [b[1] - a[1] for a, b in zip(events, events[1:])]
    print(json.dumps(dict(case=name, status_codes=codes, gaps_s=[round(g, 3) for g in gaps],
                          maven_exit=run.returncode)), flush=True)
    if f"Using transporter {transporter}" not in run.stdout or url not in run.stdout:
        raise ValueError(f"{name}: expected HTTP transport was not observed")
    if bad_checksum:
        # Resolver may re-fetch bytes for checksum validation independently of HTTP retries.
        if not codes or set(codes) != {200} or run.returncode == 0 or "checksum validation failed" not in run.stdout.lower():
            raise ValueError(f"{name}: strict checksum refusal missing")
        return
    if codes != statuses or (run.returncode == 0) != (statuses[-1] == 200):
        raise ValueError(f"{name}: wrong HTTP sequence or Maven result")
    for index, gap in enumerate(gaps, 1):
        expected = index * 5
        if retry_after is not None and (retry_after_at is None or retry_after_at == index):
            expected = int(retry_after)
        if gap < expected - 0.25:
            raise ValueError(f"{name}: retry backoff too short on request {index}")


def main():
    transporter, central_backoff, policy = distribution()
    production_repo = {"repository_id": "central"} if central_backoff else {}
    # Maven's bin/mvn consumes MAVEN_ARGS in both the direct and inherited-child paths.
    env = dict(os.environ, MAVEN_ARGS=policy)
    with TemporaryDirectory() as tmp:
        cases = [
            ("transient", [429, 500, 200], production_repo),
            ("persistent", [503] * 4, {}),
            ("missing", [404], production_repo),
            ("over-budget-retry-after", [503], {"retry_after": "31"}),
            ("altered-bytes", [200], {**production_repo, "bad_checksum": True}),
        ]
        if central_backoff:
            cases.extend([
                ("central-429-recovery", [429] * 5 + [200],
                 {**production_repo, "retry_after": "60", "retry_after_at": 5, "timeout": 140}),
                ("central-503-exhaustion", [503] * 7, {**production_repo, "timeout": 135}),
                ("central-over-budget-429", [429], {**production_repo, "retry_after": "61"}),
            ])
        for name, statuses, extra in cases:
            qualify(Path(tmp) / name, name, statuses, transporter, env, **extra)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        print(f"maven_args={policy}", file=output)


if __name__ == "__main__":
    main()
