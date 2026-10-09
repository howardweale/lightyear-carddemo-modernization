# B06 Tycho runtime closure r5 — offline correction

Operator review; not independent attestation. Zero Docker and model calls.

## Change and source

The separate `tycho_runtime` reader implements the property shape emitted by
[Tycho 4.0.8 AbstractEclipseTestMojo](https://github.com/eclipse-tycho/tycho/blob/tycho-4.0.8/tycho-surefire/tycho-surefire-plugin/src/main/java/org/eclipse/tycho/surefire/AbstractEclipseTestMojo.java),
`createSurefireProperties` and `createCommandLine`. Official source bytes were
read from that tag; SHA-256:
`34befc1b5e2a0b6d43454af2d6f1658051d25254510cc7588a44f20534bbfdbe`.
The suite-list prefix `testSuiteXmlFiles` and contiguous numeric suffixes follow
[Surefire 3.2.5 BooterConstants](https://github.com/apache/maven-surefire/blob/surefire-3.2.5/surefire-booter/src/main/java/org/apache/maven/surefire/booter/BooterConstants.java)
and [PropertiesWrapper.addList](https://github.com/apache/maven-surefire/blob/surefire-3.2.5/surefire-booter/src/main/java/org/apache/maven/surefire/booter/PropertiesWrapper.java).

The worker retains all existing capture directories and copies
`target/surefire.properties` exactly into `results/runtime/surefire.properties`.
Missing or duplicate copies refuse admission, including duplicate identical
files. The reader supports Java Properties.store escaping, requires the declared
Tycho keys, permits only `__provider.*` and the indexed suite XML keys in addition,
and refuses unknown keys or duplicate decoded keys. It records every value,
testprovider and exact input hashes. `testpluginname` must be
`org.idempiere.test`, with exactly one matching observed resolved test bundle.

Observation /2 records bundle symbolic names, installation area and the fork's
actual argv through ProcessHandle; it does not reconstruct argv from the Maven
log. The single observed java.class.path entry must be the Equinox launcher
JAR, present and hash-bound in the measured inventory. Fork `-jar`,
`-testproperties`, `-install`, `-configuration` and Java executable are checked
against the observed/captured inputs. The original testproperties path is fixed
to `/application/org.idempiere.test/target/surefire.properties`.

The unchanged measured Maven command, separate closure Maven command and actual
fork command are independently hash-bound in launch receipt /3. Resolution /3
uses `boot_classpath`; the old reader and legacy producer behavior remain for
/2 history. Independent replay rebuilds /3 from captured bytes, command,
inventory and verified receipt. No native admission claim is added.

The saved configuration also demonstrates escaped `file\:` values, relative
Equinox locations resolved against the bound installation directory, and one
duplicate configured test bundle path. The new reader checks exact normalized
configuration/observation path-set equality; it retains all configured entries
and explicitly records duplicates. Observed duplicate identities/paths refuse.

## Preserved-attempt offline check

The exact failure and stage are recorded in [core-status](../core-status.md).
The new layout parser accepted saved config.ini, /1 observation and the fork
command corroborated by the preserved Maven log: 350 configured entries, 349
observed non-system bundles, with `/application/org.idempiere.test` configured
twice. Measured Maven arguments match the unchanged worker. The log-derived
command is diagnostic corroboration only, not promoted into a signed observation.

`target/surefire.properties` was NOT preserved. New fork/symbolic-name observation
fields, measured runtime inventory and a successful launch receipt also do not
exist. Complete /3 producer replay is blocked, not passed. Only a new separately
authorized window can supply these artifacts. No historical receipt, capture,
snapshot, failed slot or verdict was rewritten.

Offline review content hash:
`c64b78115d23d4b2df81e3572ecb86c4caeac6442efcd9775167ee74eb46247f`.

## Validation and next gate

54 focused offline tests passed, including a source-shaped Tycho fixture,
missing/duplicate file, unknown key, wrong/missing/unresolved test bundle, zero
or multiple boot entries, unmeasured launcher, mismatched/duplicate fork options,
config disagreement, changed receipt inputs, successful synthetic /3 replay
and unchanged /2 history. The Java closure agent compiled with host Corretto JDK
21.0.10. These are implementation tests, not native qualification.

Howard selected October 8 10:15–11:15 PDT for the prospective window, latest
start 10:20 PDT. A fresh snapshot/plan and exact Tower request must bind the
corrected code and public commit. No Docker starts without a new signed Tower
decision; no automatic retry, census, native pairs or model calls.
