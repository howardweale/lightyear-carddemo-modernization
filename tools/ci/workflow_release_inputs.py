"""One producer and fixed, content-addressed inputs for three public CI workflows."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

from tools.ci.github_read_budget import ReadBudget, ReadRefused


REPOSITORY = "howardweale/lightyear-carddemo-modernization"
PROFILES = {
    "codecs": ("cobol-codecs.yml", "full-intcalc-cobol-runtime-slice1a-implementation-proposal-20261115-r2", {
        "codecs-independent-claude.json": (36463, "8c422ad1bce09625fc025bd2d1c8c0c1f4060ff497dc59a22a882d2b9f8c789d"),
    }),
    "composition": ("intcalc-preview-composition.yml", "full-intcalc-context-r2", {
        "MODEL-CONTEXT.zip": (13846, "38712491400e8839d99fe6bfbee77dd278633bd9f42e0bce614d699e770ac767"),
        "MODEL-ALLOWLIST.json": (4377, "7591a32fa00320d970e9a10a5e9f2be2a82d06907cc36c537f8ab1c2ddf7e3cb"),
    }),
    "graph": ("intcalc-graph-repair-controller.yml", "full-intcalc-graph-review-bindings-20261117-r2", {
        "CURRENT-CONTEXT.json": (69808, "4f25b42be20c5e4bb0a82030e3172b5c6751c7dfb5b36aa1f1bb42dee25a5a52"),
    }),
}
RECEIPT = "public-release-inputs.json"


def require(value, code):
    if not value:
        raise ReadRefused(code)


def positive(value):
    require(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value), "release-id")
    return value


def receipt(profile, attempt, env):
    workflow, tag, members = PROFILES[profile]
    repo = env["GITHUB_REPOSITORY"]
    workflow_ref = env["GITHUB_WORKFLOW_REF"]
    require(repo == REPOSITORY and workflow_ref.startswith(f"{repo}/.github/workflows/{workflow}@refs/"),
            "release-workflow-identity")
    head = env["GITHUB_SHA"]
    require(re.fullmatch(r"[a-f0-9]{40}", head), "release-head")
    current = positive(env["GITHUB_RUN_ATTEMPT"])
    require(int(positive(attempt)) <= int(current), "release-producer-attempt")
    data = dict(schema="public-ci-release-inputs/1", profile=profile, repository=repo,
                workflow_ref=workflow_ref, run=positive(env["GITHUB_RUN_ID"]), head=head,
                producer_attempt=attempt, tag=tag,
                members={n: dict(bytes=size, sha256=h) for n, (size, h) in members.items()})
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def check_bytes(raw, size, expected):
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == expected, "release-member-hash")


def fresh(path):
    require(not path.is_symlink() and not path.exists(), "release-output-exists")


def precheck(path, artifact, producer_attempt, profile, env):
    positive(artifact)
    receipt(profile, producer_attempt, env)
    fresh(path)


def regular_stat(path):
    info = path.lstat()
    require(not (getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)),
            "release-reparse-point")
    return info


def verify(path, profile, attempt, env):
    expected_receipt = receipt(profile, attempt, env)
    members = PROFILES[profile][2]
    require(stat.S_ISDIR(regular_stat(path).st_mode), "release-directory")
    require({p.name for p in path.iterdir()} == {RECEIPT, *members}, "release-member-set")
    for name, (size, digest) in {**members, RECEIPT: (len(expected_receipt), hashlib.sha256(expected_receipt).hexdigest())}.items():
        f = path / name
        meta = regular_stat(f)
        require(stat.S_ISREG(meta.st_mode) and meta.st_size == size, "release-member-type-size")
        with f.open("rb") as reader:
            check_bytes(reader.read(size + 1), size, digest)


def produce(path, profile, env, reader):
    attempt = env["GITHUB_RUN_ATTEMPT"]
    envelope = receipt(profile, attempt, env)
    fresh(path)
    path.mkdir(mode=0o700)
    _, tag, members = PROFILES[profile]
    for name, (size, digest) in members.items():
        data = reader.get(f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}", size)
        check_bytes(data, size, digest)
        with (path / name).open("xb") as f:
            f.write(data)
    with (path / RECEIPT).open("xb") as f:
        f.write(envelope)
    verify(path, profile, attempt, env)
    return attempt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("produce", "precheck", "verify"))
    parser.add_argument("profile", choices=PROFILES)
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "produce":
            attempt = produce(args.path, args.profile, os.environ, ReadBudget())
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
                f.write(f"producer_attempt={attempt}\n")
        elif args.mode == "precheck":
            precheck(args.path, os.environ["INPUT_ARTIFACT_ID"], os.environ["INPUT_PRODUCER_ATTEMPT"],
                     args.profile, os.environ)
        else:
            positive(os.environ["INPUT_ARTIFACT_ID"])
            verify(args.path, args.profile, os.environ["INPUT_PRODUCER_ATTEMPT"], os.environ)
    except ReadRefused as e:
        print(str(e), file=sys.stderr)
        return 2
    except (KeyError, OSError, ValueError):
        print("release-input-unavailable", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
