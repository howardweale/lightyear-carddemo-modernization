"""CI-only acquisition of the unchanged, digest-pinned official PostgreSQL image."""
import subprocess
import sys
import time

POSTGRES_IMAGE = ('public.ecr.aws/docker/library/postgres:16-alpine@sha256:'
                  '721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea')
TRANSIENT = ('toomanyrequests', 'too many requests', '429', '500 internal server error',
             '502 bad gateway', '503 service unavailable', '504 gateway timeout',
             'i/o timeout', 'tls handshake timeout', 'connection reset', 'unexpected eof')


def ensure_image(*, run=subprocess.run, sleep=time.sleep, stderr=None):
    """Retry downloads only; never retry container creation or a test workload."""
    stderr = stderr or sys.stderr
    for attempt in range(3):
        result = run(['docker', 'pull', POSTGRES_IMAGE], capture_output=True,
                     text=True, timeout=180)
        if result.returncode == 0:
            return POSTGRES_IMAGE
        detail = (result.stderr or '') + (result.stdout or '')
        print(f'PostgreSQL image acquisition attempt {attempt + 1}: {detail}', file=stderr)
        if attempt == 2 or not any(marker in detail.lower() for marker in TRANSIENT):
            raise subprocess.CalledProcessError(result.returncode, result.args,
                                                output=result.stdout, stderr=result.stderr)
        sleep((2, 5)[attempt])


if __name__ == '__main__':
    ensure_image()
