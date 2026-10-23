# K7 build-profile draft — merge held

This draft is not eligible for merge until the factory run's verification is
complete and after 31 October. It must then be rebased on post-run main and
reviewed at its exact fresh green head. The original frozen-judge check and
freeze records are unchanged; the changed main POM must remain a blocker.
There is no new freeze, unfreeze, exception approval or run authority here.

The four separate map, phone/date, feedback and account-view POMs become
explicit `proof-map`, `proof-phone-date`, `proof-feedback` and
`proof-account-view` profiles. Invoke one proof profile per Maven process.
The default build is byte-identical after removing the profile section. Each
profile retains its exact supplemental test root, PIT version/dependencies,
class list, test list, nonempty condition and 90-percent per-class evaluator.
All original mutation evaluators and production Java remain unchanged.

Each existing group job also runs its original build from the pinned source
baseline `f267fc9ee8d1329529debf4b5edd72bb026b63a5` in a separate CI checkout. A paired gate compares every
mutated class/status count and Maven's effective build. It normalizes only the
checkout path, already-applied `combine.self=override` attributes and plugin
list order; execution order and all configuration remain compared. The result,
both mutation XMLs, baseline JUnit reports and effective POMs are retained.
These are pending CI measurements, not claimed identical counts yet.

The structural guard rejects extra standalone proof POMs, unknown/implicitly
activated profiles, changed default configuration and missing explicit
configuration override. Existing proof-scope checks still compare the complete
per-group configuration, and all original tests remain except two fixture
lists no longer copy the deleted account-view POM.

Maven's documented [profile activation](https://maven.apache.org/guides/introduction/introduction-to-profiles)
and [configuration override](https://maven.apache.org/pom.html) are used here.
No Maven, compiler, tests, model or signing code ran locally. Workflow policy,
XML and Python syntax were reviewed statically; executable lint runs in CI.

Idiomatic-index delta: no engine or Java-source change; four standalone proof
POMs become zero. Mutation/full-proof results await fresh CI. The pending #441
render POM must become an additional profile on the mandatory post-run rebase;
do not merge stale four-profile coverage over that later main.
