# Services and API journey packs

Service journeys are now declarations. A pack names service-relative requests,
inputs, observations, business assertions, branches and bounded recovery steps.
Adding a customer journey does not require a Python scenario method or an entry
in an operations list. The application owner still supplies the business contract;
the engine does not infer correctness from an HTTP success code.

The CloudBank reference pack contains all 18 existing journeys, including
fixture admission, transfers and their participant journals, check delivery and
clearance, retries, concurrent requests, service failure and restart recovery.
`SCENARIOS` and the execution order derive from this one pack. Existing helper
entry points used by qualification and HA drills are thin generated wrappers.
The original adapter still handles HTTP, authentication, queues, Kubernetes and
restoration. No new native CloudBank or customer execution is claimed.

## Validate and plan before access

```bash
PYTHONPATH=src python3 -m lightyear_workflow.service_pack validate spec/service-packs/order-approval.pack.json
PYTHONPATH=src python3 -m lightyear_workflow.service_pack plan spec/service-packs/order-approval.pack.json
PYTHONPATH=src python3 -m lightyear_workflow.service_pack plan src/lightyear_data/packs/cloudbank.services.json
```

These commands do not construct an adapter, obtain credentials or access a
runtime. `plan()` revalidates the immutable pack and walks the reachable macros,
both branches, loops, polling, parallel calls and cleanup. It computes:

- Source capture IDs to retrieve and the source invocation list.
- Target service, HTTP method, path template, credential role, query/header
  field names and whether a request has a body.
- Target controls and the services potentially affected.
- Conservative maximum call counts, including polling and conditional cleanup.

IDs captured at runtime remain named path parameters in a plan; it does not
pretend to know their eventual values. Global controls conservatively cover all
pack services. The CloudBank binding requires its fixed eight-service scope, so
a pack cannot hide a service that its global controls will touch. Control internals, physical hosts, credential-provider resources
and network timeouts belong to the trusted adapter's access configuration.
Unreachable macros are validated but do not inflate the invocation footprint.

## Source observation and target invocation

`SourceLane` receives only a record-reader method. It has no HTTP request,
control, submit or replay method and no client capable of invoking the original
application. It retrieves existing captures, including captured write operations;
it never reissues them. GET is not treated as proof of safety: a GET endpoint can
have side effects, so even GET invocation belongs exclusively to `TargetLane`.

```python
from lightyear_workflow.service_pack import SourceLane, TargetLane, load

pack = load('spec/service-packs/order-approval.pack.json')
# capture_reader.record(journey_id) retrieves an existing, trusted capture.
source = SourceLane(capture_reader).observe(pack)
# approved_client.request(service, method, path, role, body, headers) returns
# a response with integer status, bytes body, and a headers dictionary.
target = TargetLane(approved_client.request)
result = target.replay(pack, {'order_id': 'A1'}, source)
```

A source record must name its `journey` and contain `evidence`; absence is an
error, never an empty successful observation. Production capture acquisition is
adapter work: there is no new production recorder, credential provisioner or
customer connector in this change. Access configuration stays outside the pack.
Adapters must enforce allowed hosts, redirect handling, role-to-credential
bindings, response limits, timeouts and any required resource isolation. In
particular, a read-only reader must actually read stored evidence, not hide an
HTTP replay behind its `record` method.

A target can be given individual control callables (`ready`, `authorize`,
`queue`, `stop`, `start`, `restart`, `crash_stop`, `restart_all`,
`block_delivery`, `restore_delivery`). Missing capabilities are rejected before
execution. Mutating controls also require a `restore` callable. `replay()` calls
restoration on exit, including interruption, and a restoration failure prevents
a passing result. The existing CloudBank entry point retains its signed recovery
journal, outer cleanup and mutation-authorization checks.

Source records and targets default to `simulated`. An adapter may explicitly
supply `local_observed` or `runtime_observed`; the combined class is never stronger
than either lane. These labels propagate adapter provenance, not independent
attestation. A successful target run means its declared assertions passed.
It does **not** mean source/target equivalence: the result explicitly records
`source_target_comparison_performed: false`. A comparator must evaluate both
lanes' evidence under an agreed business and normalization contract. The source
pack identity must match before target replay; source contents are hash-bound in
the result. Input/state equivalence and the authenticity of captures remain
separate admission responsibilities.

## Authoring a pack

Start with `spec/service-packs/order-approval.pack.json`. It reads an order,
approves it, reads it again, and checks both the new status and unchanged amount.
No order-specific code is installed in the runner. This is a synthetic example,
not a customer qualification result.

The required top-level fields are `pack_type`, `schema_version`, `pack_id`,
`estate`, `source`, `target`, `services`, `roles`, `inputs`, `state`, `macros`, and
`journeys`. Unknown fields are rejected. Identifiers, services and credential
roles are explicit allowlists. Input types are `identifier`, `integer` and
bounded `string`. Initial state expressions may reference inputs only.

Each journey has an ID, a result label, a macro and its arguments. A macro has
named parameters, steps and a return expression. Optional `defaults` support the
reference helper API; nested calls supply explicit arguments. Each journey must transitively invoke a runtime and contain an assertion or a
polling condition. A label alone never executes a check: the declared conditions
determine success. The loader cannot establish whether those conditions fully
cover the business contract.

Steps use a closed vocabulary:

| Step | Purpose and bound |
| --- | --- |
| `request` | One service-relative HTTP operation with a static method and role |
| `control` | One explicitly supplied operational capability |
| `set` | Local data assignment or explicit assignment to declared shared state |
| `assert` | A boolean condition and a bounded, data-free failure code |
| `call` | Invoke a declared macro with exact named arguments |
| `if` | Choose one of two declared blocks |
| `each` | Iterate a collection with an explicit maximum of 200 items |
| `poll` | Repeat observation steps, at most 181 attempts and within a timeout |
| `parallel` | Up to eight macro calls with isolated locals and no shared-state writes |
| `ensure` | Run declared cleanup even when its body fails or is interrupted |

Expressions are JSON values, `{"$ref":"name.field.0"}`, or a closed operator
form such as `{"$op":"eq","args":[{"$ref":"response.status"},200]}`.
The operators cover strict typed equality and membership; integer arithmetic
and ordering; collection length, sum, sorting, append and index replacement;
object lookup and merge; mapping/filtering; JSON and text decoding; hashing;
ID construction and bounded data-format checks. `$map` and `$filter` declare
`over`, `as` and `value`. There is no eval, import, shell command or arbitrary
regular-expression execution. Decimal business values should use exact integer
units or decimal strings with an explicitly agreed comparison rule, not floats. Response JSON with duplicate keys, nonfinite numbers or fractional
numbers is rejected rather than rounded during parsing.

Absolute URLs, encoded/static path escapes, unknown roles, credential/routing
headers, undeclared source capabilities, duplicate JSON keys, cycles, malformed
references and excessive nesting/size are refused. Dynamic path values are
restricted to one safe segment before any transport call. Header declarations
are limited to `Idempotency-Key`; adapters supply authorization. Packs are
business fixtures and must not contain secrets in payload data.

Poll bodies are checked through the full macro call graph: a nested POST or a
control mutation cannot hide inside a polling helper. Writes are issued once
per declared step, not automatically retried. Parallel branches cannot mutate
shared pack state or run service lifecycle controls. Execution has a shared
100,000-operation/expression budget plus a separate 10,000-operation cleanup
reserve. These limits do not replace adapter network timeouts.

## Validation and compatibility

```bash
PYTHONPATH=src python3 -m unittest tests.test_service_pack tests.test_cloudbank_journeys tests.test_runtime_gate_qualification tests.test_batch_pack -v
```

Tests cover the complete 18-journey reference sequence and its existing fault
cases; mutation of a declaration without changing Python; missing capabilities;
computed versus observed request coverage; simulated evidence propagation;
unsafe declarations; finite polling with a frozen clock; budget exhaustion and
cleanup; and business failure behind HTTP 200. The qualification source manifest
now includes the JSON pack as executable input. New shared-journey observations
bind its hash. Existing signed historical observations remain readable under
their prior contract; an explicit new pack binding must match.

This is an invocation and assertion language, not a universal API discovery or
migration proof. Unsupported protocols and application-specific transport still
need an adapter. Customer business expectations still need to be supplied and
reviewed. The declarations remove handwritten journey handlers, not the need to
understand the customer's business contract.
