"""CI-only bounded registry acquisition of one immutable PostgreSQL digest."""
import subprocess
import sys
import time

DIGEST = 'sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea'
POSTGRES_IMAGE = 'public.ecr.aws/docker/library/postgres@' + DIGEST
IMAGES = ('ghcr.io/howardweale/lightyear-ci-postgres@' + DIGEST,
          POSTGRES_IMAGE, 'docker.io/library/postgres@' + DIGEST)
TRANSIENT = ('toomanyrequests', 'too many requests', '429', 'data limit exceeded',
             '500 internal server error', '502 bad gateway', '503 service unavailable',
             '504 gateway timeout', 'i/o timeout', 'tls handshake timeout',
             'connection reset', 'unexpected eof')
MIRROR_UNAVAILABLE = ('manifest unknown', 'not found', 'denied', 'unauthorized')


def ensure_image(*, run=subprocess.run, sleep=time.sleep, stderr=None):
    """Try each registry at most twice; never retry a container or workload.

    GHCR may not be populated/visible yet. Public registry permanent failures and
    digest integrity failures remain fatal. All successful pulls return the exact
    selected digest reference; callers must run that reference with --pull=never.
    """
    stderr = stderr or sys.stderr
    last = None
    for ordinal, image in enumerate(IMAGES):
        for attempt in range(2):
            try:
                result = run(['docker', 'pull', image], capture_output=True, text=True, timeout=180)
            except subprocess.TimeoutExpired as exc:
                last = exc
                print(f'PostgreSQL registry {ordinal+1} attempt {attempt+1}: pull timeout', file=stderr)
                if attempt == 0:sleep(2)
                continue
            if result.returncode == 0:return image
            detail = ((result.stderr or '') + (result.stdout or '')).lower()
            print(f'PostgreSQL registry {ordinal+1} attempt {attempt+1}: {detail}', file=stderr)
            last = subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
            # A digest mismatch must never be disguised as a mirror availability failure.
            if any(s in detail for s in ('digest mismatch','checksum mismatch','verification failed')):raise last
            if ordinal == 0 and any(s in detail for s in MIRROR_UNAVAILABLE):break
            if not any(s in detail for s in TRANSIENT):raise last
            if attempt == 0:sleep(2)
    raise last


if __name__ == '__main__':
    print(ensure_image())
