# Public clean-control input proposal

This unsigned draft adds a small public arithmetic worker and its work order,
workspace manifest, scope, freeze description and OCI policy. The policy uses
the existing pinned public Python image, no container network, read-only root
and workspace, non-root user and no leased secrets. The sole trust identifier
is the existing PUBLIC PEM SHA-256; no key bytes or proof are included.

The work order permits one scripted planner call, then the deterministic gate.
The expected receipt has no edits and zero repair attempts. The positive pilot
must independently enforce that outcome; scope/freeze JSON are signed byte
inputs, not a new policy interpreter. The USD1 work-order cap is a parser-valid
maximum for this stub-only case, not permission to spend or an actual charge.

After source approval/publication, CI may invoke the new input compiler:

    python -B -m tools.ci.p5_human_case_inputs --source-root SOURCE --output NEW_EXTERNAL_DIRECTORY

It calls the native planner formatter with the native graph-free context and
captures its request before any provider. It writes an exact public output
script, public synthetic isolation canaries, planner request and input proposal.
It never starts the controller, OCI runtime, provider, GitHub reservation or a
signer. Its seven authored CI tests are not yet executed.

The output remains unsigned data. CI must prove the compiler and native pilot
agree on the invocation; the public-output verifier rejects a changed request.
The generated outputs must be reviewed and committed before the executable is
pinned. Neither this compiler nor its tests establish genuine admission.

Still needed: approved source integration and workflow, the final executable,
window and one-use nonce, sealed plan/contract, Howard's genuine public proof,
independent current journal trust, and one successful native CI execution.
No request is ready for signature yet. The pilot remains non-qualifying until
the separate full production receipt route and strict P5 evidence are complete.
