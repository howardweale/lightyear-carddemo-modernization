# P5 controller path review — 24 October 2026

Source review targets `588dd5f24425a5eaa651ce12d538bdebdfb33043`.
Runtime evidence for the added regressions is pending CI.

| Entry | Exact source | Consequence |
| --- | --- | --- |
| Configured provider | [cli.py:676](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/cli.py#L676) | ModelAgentSet wraps the configured TaskRouter. |
| Controller | [cli.py:698](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/cli.py#L698) | The launch constructs FactoryOrchestrator with execution and model admission. |
| Routed binding | [orchestrator.py:213](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/orchestrator.py#L213), [routing.py:94](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/routing.py#L94), [routing.py:105](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/routing.py#L105) | RoutedBudget constructs AccountedModelProvider with the same order and admission callbacks. |
| Direct binding | [orchestrator.py:216](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/orchestrator.py#L216) | Direct providers also receive AccountedModelProvider. |
| Call boundary | [agents.py:520](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/agents.py#L520), [agents.py:537](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/agents.py#L537) | Non-scripted providers require the exact accounted wrapper and identical order object. |
| Deadline | [budgeted_providers.py:20](https://github.com/howardweale/lightyear-carddemo-modernization/blob/588dd5f24425a5eaa651ce12d538bdebdfb33043/src/lightyear_factory/budgeted_providers.py#L20) | Direct deadline comparison refuses equality and later times. |

The bare BoundedModelProvider fallback in agents.py:555–556 is behind the
non-scripted binding refusal. It serves scripted compatibility handling; it is
not an admitted F2 route. The historical providers.py bytes remain unchanged.

## CI probes and limits

Planned: two new regression methods run under the existing Windows and Linux
P5 discovery. They use real disposable admission and the actual controller.
The direct and configured routes must construct exactly AccountedModelProvider;
substituting the bare class must fail before transport. The construction probe
injects an assembly exception after provider binding and requires the actual
controller's blocked receipt, canonical hash, summary linkage, exception
redaction, zero stub calls and preservation on same-directory re-entry.

These are construction, catch-path and same-directory refusal probes. They do
not establish recovery after abrupt process termination, a complete controller
budget/outage/context drill, or full factory qualification. No gap is waived.
The eight-drill inventory and --qualify remain unchanged. A future P5 launch
refusal case depends on the separately reviewed #459 guard reaching main.

The ordinary controller refuses an existing run directory at orchestrator.py:183.
Its exception recorder starts at orchestrator.py:500. A process killed before
that catch handler cannot be assumed to have a controller receipt. The durable
queue recovery command is a separate path and cannot stand in for this evidence.
Abrupt-stop recovery and its receipts remain the first qualification gap.

Not authorized: merge, production signing, private generation, model calls,
spending or a factory run. The request remains not ready. F2 binding recomputation
must use the eventual exact merge commit. The Tuesday 27 October 09:00 Pacific
checkpoint and Wednesday 28 October 18:00 Pacific go/no-go remain in force.

## Abrupt-controller observation prepared 24 October

Planned CI evidence: the kill-mid-build drill now targets the real controller,
using a synthetic expected-value bundle outside its executable and run roots.
An ordinary blocked run is the positive control: it must reach both planner and
builder transports and retain a canonical controller receipt. The kill probe
must reach builder transport before the parent terminates its process.
A second invocation with fresh disposable admission must refuse the existing
run directory before any stub call and preserve every retained file hash.

The probe records actual receipt presence, controller receipt hashes, retained
inventory counts and hashes, and re-entry results. It does not implement resume
or manufacture a missing controller recovery receipt. Any missing recovery path
remains an explicit qualification gap; strict --qualify is unchanged. Runtime
results and the run URL are pending CI. The other seven drill functions are
unchanged, as are production, authority checks, frozen paths and workflows.

This measures the first controller-level gap. Dollar/token/fallback, operator
API outage, assembled context and attempt-identity closure still need their
separate evidence. Planned observations grant no signing, spending or run permission.
Not accepted: any gap, except the first-run human-attestation gap accepted separately [operator-chat receipt](../factory/f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e).


## Controller budget subcases prepared 24 October

The next synthetic CI batch retains the call-cap observation and adds six real
controller cases: an ordinary blocked positive control; dollar and token
preflight refusals before transport; over-budget returned dollar and token usage
that must remain accounted; and a failed primary through the real TaskRouter
with no authority to call an available secondary. Each checks the actual
controller-created blocked receipt and exact WorkOrder binding. Case results
retain counts, simulated accounting, receipt hashes and call evidence hashes.
No real model transport or spending occurs.

Both direct and routed controller paths must construct AccountedModelProvider.
A separate mutation control substitutes the bare BoundedModelProvider at the
controller constructor and requires the observation to refuse that path.
All real signature and runtime admission verification remains in place.

Not yet closed: controller recovery or approved-fallback qualification.
The failure recorder at orchestrator.py:500-515 omits durable model-charge
details; observing the in-memory budget is not a replacement for those receipts.
The production orchestrator is F2-fenced and is unchanged. Not accepted: any gap, except the first-run human-attestation gap accepted separately [operator-chat receipt](../factory/f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e).
Strict qualification, all other seven drill functions, all production files,
the existing workflow and all fenced paths are unchanged by this batch.
The full eight-drill set runs again in CI; results and run URL remain pending.


## Planned CI evidence: signed fallback controller cases prepared 24 October

Two additional synthetic CI cases use the actual routing-policy compiler and a
separate disposable Tower authority. Synthetic 35-pair matrix cells are fixture
inputs, not benchmark results. No approval or signature verifier is mocked.
Planned CI evidence: the first case fails the primary, admits an approved secondary with the same
F2-bound provider/model identity, and must refuse the next builder transport at
the shared two-call limit. The failed primary remains charged. The second uses
a valid routing decision for a different secondary model: the independent F2
model admission must still refuse that transport, retaining the primary charge.
Neither changes or authorizes the first COPAU run's provider/model selection.

Both inspect the real controller's blocked receipt and WorkOrder binding.
Durable failure-accounting and abrupt-stop reconciliation remain open; the
controller is fenced and unchanged. Strict qualification and the other seven
drill functions remain unchanged. Runtime results await CI on this revision.
