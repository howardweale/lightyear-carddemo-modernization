"""Historical metadata only. PRs consume an exact main observation or disclose a gap."""
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import re
import subprocess
import zipfile

from tools.copau_answer_key import HISTORICAL, encoded, sha
from tools.copau_private_prerequisites import load_json, require


REPO = "howardweale/lightyear-carddemo-modernization"
WORKFLOW = "copau-run-boundary.yml"
MEMBER = "historical-catalog.json"
LIMIT = 2 * 1024 * 1024
UNKNOWN = "deleted-artifacts-assets-and-prior-history-not-enumerated"
GAP = "main-catalog-observation-unavailable"


MAX_AGE_SECONDS = 3600
STALE_GAP = "main-catalog-observation-stale"
EXPIRED_GAP = "main-catalog-observation-expired"


class Unavailable(Exception):
    pass


def utc():
    return datetime.now(timezone.utc)


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() is not None)
    return parsed


def read_api(path):
    """Fixed repository GET. Only remote read failures become unavailable history."""
    try:
        result = subprocess.run(["gh", "api", "repos/" + REPO + "/" + path],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=45)
    except (subprocess.TimeoutExpired, OSError):
        raise Unavailable from None
    if result.returncode:
        raise Unavailable
    require(len(result.stdout) <= LIMIT + 65536)
    return result.stdout


def listing(path, key, get):
    page = load_json(get(path))
    entries = page[key]
    require(type(entries) is list and type(page["total_count"]) is int
            and page["total_count"] == len(entries) and len(entries) <= 1)
    if not entries:
        raise Unavailable
    return entries[0]


def fetch_snapshot(commit, get=read_api):
    # The trusted push run owns the artifact. A matching artifact name in a PR or
    # in another workflow is insufficient. Fetch at most two metadata pages.
    path = ("actions/workflows/" + WORKFLOW + "/runs?branch=main&event=push&head_sha="
            + commit + "&per_page=2")
    run = listing(path, "workflow_runs", get)
    require(run["head_sha"] == commit and run["event"] == "push" and run["head_branch"] == "main"
            and run["path"] == ".github/workflows/" + WORKFLOW
            and run["repository"]["full_name"] == REPO and run["head_repository"]["full_name"] == REPO)
    run_id = run["id"]
    require(type(run_id) is int and run_id > 0)
    name = "copau-catalog-" + commit
    artifact = listing(f"actions/runs/{run_id}/artifacts?name={name}&per_page=2", "artifacts", get)
    require(artifact["name"] == name and type(artifact["expired"]) is bool)
    if artifact["expired"]:
        raise Unavailable(EXPIRED_GAP)
    require(type(artifact["id"]) is int and artifact["id"] > 0
            and type(artifact["size_in_bytes"]) is int and 0 < artifact["size_in_bytes"] <= LIMIT + 65536)
    archive = get(f"actions/artifacts/{artifact['id']}/zip")
    require(len(archive) == artifact["size_in_bytes"] and artifact["digest"] == "sha256:" + sha(archive))
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        require(package.namelist() == [MEMBER])
        info = package.getinfo(MEMBER)
        require(not info.is_dir() and 0 < info.file_size <= LIMIT)
        data = package.read(info)
    snapshot = load_json(data)
    require(encoded(snapshot) == data and snapshot["producer_run_id"] == run_id)
    return snapshot


def absent(reason=GAP):
    return dict(status=HISTORICAL, catalog=[], catalog_sha256=sha(encoded([])),
                observed_count=0, metadata_error_count=1,
                missing=[dict(kind="unknown-history", id=v) for v in (UNKNOWN, reason)])


def validate_history(history):
    require(set(history) == {"status", "catalog", "catalog_sha256", "observed_count",
                             "metadata_error_count", "missing"})
    require(history["status"] == HISTORICAL and type(history["catalog"]) is list
            and type(history["observed_count"]) is int and history["observed_count"] == len(history["catalog"])
            and history["catalog_sha256"] == sha(encoded(history["catalog"]))
            and type(history["metadata_error_count"]) is int and history["metadata_error_count"] >= 0
            and type(history["missing"]) is list
            and dict(kind="unknown-history", id=UNKNOWN) in history["missing"])
    for rows, missing in ((history["catalog"], False), (history["missing"], True)):
        for row in rows:
            require(type(row) is dict and set(row) == {"kind", "id"})
            if missing and row["kind"] == "unknown-history":
                require(type(row["id"]) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", row["id"]))
            else:
                require(row["kind"] in ("artifact","release-asset") and type(row["id"]) is int and row["id"] > 0)


def describe(snapshot, commit, now):
    require(set(snapshot) == {"schema", "main_commit", "producer_run_id", "producer_attempt",
                              "capture_start", "capture_end", "history"})
    require(snapshot["schema"] == "copau-historical-catalog/1" and snapshot["main_commit"] == commit
            and type(snapshot["producer_run_id"]) is int and snapshot["producer_run_id"] > 0
            and type(snapshot["producer_attempt"]) is int and snapshot["producer_attempt"] == 1)
    validate_history(snapshot["history"])
    start, end = timestamp(snapshot["capture_start"]), timestamp(snapshot["capture_end"])
    require(start <= end <= now)
    age = (now - end).total_seconds()
    stale = age > MAX_AGE_SECONDS
    return dict(main_commit=commit, producer_run_id=snapshot["producer_run_id"], producer_attempt=1,
                capture_start=snapshot["capture_start"], capture_end=snapshot["capture_end"],
                status="stale" if stale else "observed", age_seconds=int(age),
                gaps=[STALE_GAP] if stale else [],
                used_at=now.isoformat(), observation_sha256=sha(encoded(snapshot)))


def capture(commit, output, scan, *, env, clock=utc):
    """Only the first push attempt of the trusted main workflow may write."""
    require(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit))
    require(env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_REF") == "refs/heads/main"
            and env.get("GITHUB_REPOSITORY") == REPO and env.get("GITHUB_SHA") == commit
            and env.get("GITHUB_RUN_ATTEMPT") == "1"
            and env.get("GITHUB_WORKFLOW_REF") == f"{REPO}/.github/workflows/{WORKFLOW}@refs/heads/main")
    require(not (output / MEMBER).exists())
    started = clock()
    history = scan()
    snapshot = dict(schema="copau-historical-catalog/1", main_commit=commit,
                    producer_run_id=int(env["GITHUB_RUN_ID"]), producer_attempt=1,
                    capture_start=started.isoformat(), capture_end=clock().isoformat(), history=history)
    observation = describe(snapshot, commit, clock())
    raw = encoded(snapshot)
    require(len(raw) <= LIMIT)
    with (output / MEMBER).open("xb") as stream:
        stream.write(raw)
    return history, observation


def unavailable_observation(commit, reason, now):
    return dict(main_commit=commit, producer_run_id=None, producer_attempt=None,
                capture_start=None, capture_end=None, status="unavailable", age_seconds=None,
                gaps=[reason], used_at=now.isoformat(), observation_sha256=None)


def observe(commit, *, fetch=fetch_snapshot, clock=utc):
    """Both main and PR consumers can only read the trusted main record."""
    require(type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit))
    try:
        snapshot = fetch(commit)
    except Unavailable as exc:
        reason = EXPIRED_GAP if exc.args == (EXPIRED_GAP,) else GAP
        return absent(reason), unavailable_observation(commit, reason, clock())
    return snapshot["history"], describe(snapshot, commit, clock())


def reuse(boundary, commit, now=None):
    """Same captured bytes in both outputs. Recompute age at the child's use."""
    now = utc() if now is None else now
    history, obs = boundary["historical"], boundary["historical_observation"]
    validate_history(history)
    require(set(obs) == {"main_commit","producer_run_id","producer_attempt","capture_start",
                         "capture_end","status","age_seconds","gaps","used_at","observation_sha256"}
            and obs["main_commit"] == commit and timestamp(obs["used_at"]) <= now)
    if obs["status"] == "unavailable":
        require(obs["gaps"] in ([GAP], [EXPIRED_GAP]))
        require(history == absent(obs["gaps"][0]) and all(obs[k] is None for k in
                ("producer_run_id","producer_attempt","capture_start","capture_end","age_seconds","observation_sha256")))
        return history, dict(obs, used_at=now.isoformat())
    snapshot = dict(schema="copau-historical-catalog/1", main_commit=commit, history=history,
                    **{k:obs[k] for k in ("producer_run_id","producer_attempt","capture_start","capture_end")})
    require(describe(snapshot, commit, timestamp(obs["used_at"])) == obs)
    return history, describe(snapshot, commit, now)


if __name__ == "__main__":
    from tools.copau_public_corpus_index import historical_metadata
    capture(os.environ["GITHUB_SHA"], Path(os.environ["RUNNER_TEMP"]), historical_metadata, env=os.environ)
