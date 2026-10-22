# Workflow import path coverage

The CI guard compares exact base and head Git objects. For each workflow's PR
and push path filters, it follows literal Python entrypoints, unittest selectors
and discovery, shell/PowerShell wrappers, package initializers, relative imports,
and transitive repository imports. It reads source as data; it never imports the
programs it inspects. Cycles terminate and ambiguous repository import roots
are conservatively included.

A new uncovered dependency fails CI. Narrowing a filter or introducing a
workflow with uncovered dependencies also fails. Repair the trigger for both
events; do not remove the test or import to silence the guard. This PR also
covers the shared mainframe source/record modules and package initializers used
by the phone/date and typed-feedback proof workflows.

The guard is a regression check, **not a claim that every existing workflow
already has complete coverage**. Its artifact separately lists inherited gaps,
resolved gaps, new gaps, and unresolved dynamic/inline Python entrypoints.
Existing gaps are compared against the actual base commit, not a hand-edited
allow-list. New unresolved dynamic imports fail; inherited unresolved imports
remain visible. Frozen workflow files remain unchanged. Repairing all existing
trigger debt, including frozen workflows, is separate work.

Scope is static Python dependencies and literal workflow commands. This is not
a runtime trace, proof of non-Python dependency coverage, evaluation of job-level
conditions or branch filters, or a complete shell/Python dynamic-code analyser.
Imports under conditional branches are included conservatively. Nonliteral
loader calls that the scanner recognizes are reported explicitly.

The always-triggered import coverage workflow runs synthetic adversarial tests
and writes `work/ci/import-path-coverage.json`, retained as an Actions artifact.
The required CI gate automatically selects that workflow. Source syntax errors,
missing Git objects, invalid base SHAs and incomplete batch object reads fail
the job. The full Python suite continues discovering the guard's tests; R2's
execution-report and skip-policy work is independent.
