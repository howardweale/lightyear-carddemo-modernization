# Main-side factory package verification

The `Factory main package verification` workflow runs on every push to `main`.
It reads committed Git objects, verifies candidate commit signatures against
externally configured public trust, and compares the complete published package
with the candidate's signed tree. It never checks out or executes candidate code,
uses a private signing key, publishes a package, or authorizes a factory run.

An approved future publisher places each package under
`factory/candidate-publications/<run_id>/package/`, preserving its relative paths,
bytes and executable modes, alongside `publication.json` with exactly these fields:

- `schema`: `factory-main-publication/1`.
- `run_id`: the same identifier as the signed commit's Factory-Run trailer.
- `candidate_base`: the approved run-start commit ID.
- `candidate_commit`: the final signed candidate commit ID.
- `candidate_tree`: that commit's Git tree ID (not the controller's SHA-256 tree digest).
- `source_receipt_sha256`: the final controller receipt's SHA-256 reference.

The signed candidate history must be preserved on the repository remote so the
main job can read or fetch the exact commit as Git data. The declared baseline is
reviewed with the publication record. Every subsequent commit, including empty
or reverted edits, must form a linear chain of at most three commits, carry the
same run identity and increasing attempt numbers, and verify with factory trust.
Publications are append-only: later main commits cannot remove or rewrite their
manifests. Byte, path, mode, signature, or unbound-file mismatches produce an
`intervention` result and fail the workflow. No unverified package is accepted.

Howard must separately designate the factory public trust before a real package
is submitted. The workflow reads repository variable
`LIGHTYEAR_FACTORY_ALLOWED_SIGNERS`: one OpenSSH allowed-signers line for
`factory@lightyear.invalid` with an SSH public key using the Edwards-curve algorithm required by the verifier. No value is provisioned
by this change. Missing trust fails closed when packages exist; a repository with
no submitted packages reports `no-candidates`, not factory acceptance.

This checks publication bytes and signatures. The receipt hash is a reference,
not a substitute for the controller's approval, ledger, encrypted transport,
accounting, scan and authorship audits. Output always sets
`factory_run_acceptance: false`; this check alone cannot authorize or prove a
complete factory run. Signature boundaries in the offline CI fixtures are mocked;
no cryptographic acceptance is claimed for those fixtures. Actual publication,
signing authority and final merge still require Howard's approval. The new main
workflow cannot enforce its own initial introduction before that approved merge.
