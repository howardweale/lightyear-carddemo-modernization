![LIGHTYEAR](brand/assets/lightyear-primary.svg)

# LIGHTYEAR modernization factory

LIGHTYEAR combines a dark factory that builds modernization candidates, a
deterministic verifier that compares behavior, and receipts binding each result
to its inputs. Human approvals and signatures are recorded in the Factory Tower.
Evidence establishes a bounded claim; twin proof is not native z/OS equivalence
or permission to execute an approved plan.

Start with the [architecture](ARCHITECTURE.md), [documentation index](docs/index.md),
[contribution rules](CONTRIBUTING.md), [milestones](docs/milestones/), and
[current evidence status](docs/factory/current-status.md). Status has the scope and
evaluation time stated in its underlying records; it is not a live CI dashboard.

## Ten-minute orientation

1. Clone the repository and read this map (two minutes):

   ~~~sh
   git clone https://github.com/howardweale/lightyear-carddemo-modernization.git
   cd lightyear-carddemo-modernization
   ~~~

2. Read the [target layers and current gaps](ARCHITECTURE.md) (three minutes).
3. Follow a [CardDemo proof](factory/carddemo-web/README.md) from its work order
   to the linked receipt, then inspect the [current status](docs/factory/current-status.md)
   and its evidence links (three minutes).
4. Read [verification boundaries](docs/verify/README.md) and the
   [contribution checklist](CONTRIBUTING.md) before changing code (two minutes).

This reading path requires no credentials, model calls, signature or workload.
Use the [existing command catalog](SCRIPTS.md) for the appropriate scoped runbook.
Development verification runs in CI. Commands that consume attempts or launch
native workloads require their own approved plan.

## Repository map

| Folder | Purpose |
| --- | --- |
| [.github/](.github/) | CI workflows and review ownership. |
| [LICENSES/](LICENSES/) | Third-party license and attribution bytes. |
| [audit/](audit/) | Audit inputs and review specifications. |
| [brand/](brand/) | Brand assets and existing presentations. |
| [candidate-java/](candidate-java/) | Candidate Java implementations. |
| [control-tower/](control-tower/) | Operator policies and UI configuration. |
| [data-modernization/](data-modernization/) | Data migration contracts and corpora. |
| [deploy/](deploy/) | Deployment definitions. |
| [docs/](docs/) | Runbooks, milestones, receipts and historical evidence. |
| [examples/](examples/) | Example integrations and inputs. |
| [extensions/](extensions/) | Extension contracts and runtime packages. |
| [factory/](factory/) | Work orders, estate campaigns and candidate projects. |
| [infra/](infra/) | Infrastructure definitions. |
| [knowledge/](knowledge/) | Knowledge graph inputs and contracts. |
| [pilot/](pilot/) | Pilot specifications and examples. |
| [readiness/](readiness/) | Readiness contracts and conformance fixtures. |
| [reference-estates/](reference-estates/) | Pinned source estates and inventories. |
| [skills/](skills/) | Repository-specific agent guidance. |
| [spec/](spec/) | Pinned specifications, source and schemas. |
| [src/](src/) | Python implementation packages. |
| [tests/](tests/) | Verification and boundary regression tests. |
| [tools/](tools/) | CI, evidence, retention and operational entry points. |
| [verify/](verify/) | Verifier configurations and proof contracts. |

The previous README is preserved byte-for-byte in
[the historical README](docs/history/README-history-2026-10-17.md).
Its original relative links resolve from the repository root; see the
[forwarding note](docs/history/README-forwarding-2026-10-18.md).
