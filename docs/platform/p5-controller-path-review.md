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
