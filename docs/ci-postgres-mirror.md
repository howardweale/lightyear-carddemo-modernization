# PostgreSQL CI mirror — October 9, 2026

The `cloudbank-sql-recovery` and `cloudbank-source-build` CI jobs failed while
starting `postgres:16-alpine` on GitHub runners. The SQL job reported Docker Hub's
unauthenticated pull-rate limit; the source-build job's Customer startup check
reported Docker exit 125 while starting that same image.

Both checks now use Docker's official PostgreSQL image from its verified publisher
on [Amazon ECR Public](https://gallery.ecr.aws/docker/library/postgres).
[AWS documents Docker's official-image distribution on ECR Public](https://aws.amazon.com/blogs/containers/docker-official-images-now-available-on-amazon-elastic-container-registry-public/).
This avoids Docker Hub's pull-rate bucket; it does not claim that ECR has no quotas.
No AWS account, registry login or machine-wide Docker configuration is required.

Read-only anonymous registry requests on October 9 compared the complete OCI index
bytes for `docker.io/library/postgres:16-alpine` and
`public.ecr.aws/docker/library/postgres:16-alpine`. Both returned the same SHA-256:

`721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`

Their Linux AMD64 image manifest is also identical:

`sha256:1a66d744c1b459e13b05a8fca341da84cb63383e99ce262210efee5a319d4551`

The two references pin that shared multi-platform index digest. PostgreSQL's
version, image contents, container arguments and test assertions are unchanged.
When updating the pin, compare the official registries again and update both
references together. Do not substitute a third-party PostgreSQL build.

Only these two CI startup paths change. B06's published source commit, frozen
snapshots, runtime image pins, Tower requests and preparation checkout are untouched.
The mirror change was prepared in its own worktree with no local Docker commands
or competing builds. Actual container startup remains a GitHub CI check.

Local validation passed seven focused mocked Customer startup tests in 2.282
seconds, Python syntax validation, equality of the two pinned references and
`git diff --check`. Anonymous HTTP also fetched both the index and Linux AMD64
manifest by digest from ECR and verified their hashes; no image layers were pulled.

## October 10 CI startup diagnostics

The Customer startup job returned Docker exit 125, but its wrapper discarded
stderr. That log alone cannot establish whether acquisition or container creation
failed. Both CI paths now acquire the identical pinned ECR image explicitly before
running with `--pull=never`. Only recognized transient download errors receive up
to three acquisition attempts (2/5-second backoff); permanent errors fail at once.
Container startup and the actual test are never retried. Daemon stderr is retained.
No image digest, runtime configuration or test assertion changes.

Validation: 12 focused mocked image-acquisition and existing Customer startup tests
passed in 2.235 seconds. Actual Docker startup remains a hosted CI check; no local
Docker command was used. The prior exit-125 failure remains recorded.

The repaired source-build/customer-startup job and SQL-recovery job both passed
in hosted run [38084084989](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/38084084989)
on October 10. All 25 checks passed on implementation head
`522e23ed4ad1104ed1e9ca53443c0318e3078ebf`. PR #300 merged after the fixture-attribute
integration described in [the delivery milestone](oct10-rules-evidence-delivery-milestone.md).
This verifies the new startup path; it does not establish the lost stderr from the
historical exit-125 failure.
