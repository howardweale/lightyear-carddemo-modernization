# MS66 governed Oracle source hardening

MS66 never edits or relabels the pinned Oracle CloudBank checkout. The build first verifies commit
`4f41b16d00c45503f691836fee8138010c969e86`, its repository tree, and the `cloudbank-v5` subtree.
It then copies that subtree into a fresh workspace and applies `source-hardening.patch` only after
the patch SHA-256 and changed-path set match `oracle-hardening-contract.json`.

The bounded patch adds the controls needed to execute the common 18-scenario journey contract:

- restart-safe synthetic fixtures;
- Oracle AQ/JMS message identity and a processing ledger;
- account journal command deduplication;
- a 422/no-mutation insufficient-funds outcome whose no-effect LRA callbacks are idempotent; and
- an explicit Checks-to-Account endpoint for controlled dependency failure.

The resulting application identity is `pinned-source-plus-governed-hardening`, not unchanged
upstream. Native Oracle Free, Oracle AQ/JMS, and Oracle MicroTx LRA remain the source-lane runtime.
All eight built images and both native runtime images are resolved to digests and bound into the
signed source image lock before Kubernetes resources are created.

Changing this patch requires an intentional contract update: review the diff against the exact
pinned source, update the patch SHA-256 and changed-file count in the Python contract, regenerate
the committed MS66 artifacts, and rerun the full tests. A build with any unmatched value fails
closed before provisioning the isolated lane.
