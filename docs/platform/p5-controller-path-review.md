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
separate evidence. Planned observations grant no signing, spending or run
permission, and no gap is accepted.


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

This closes neither controller recovery nor approved-fallback qualification.
The failure recorder at orchestrator.py:500-515 omits durable model-charge
details; observing the in-memory budget is not a replacement for those receipts.
The production orchestrator is F2-fenced and is unchanged. No gap is accepted.
Strict qualification, all other seven drill functions, all production files,
the existing workflow and all fenced paths are unchanged by this batch.
The full eight-drill set runs again in CI; results and run URL remain pending.
