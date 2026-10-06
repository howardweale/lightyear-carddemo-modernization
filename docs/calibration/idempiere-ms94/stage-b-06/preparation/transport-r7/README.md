# B06 host HTTP broker and measurement transport draft

October 5, 2026. Operator review; not independent attestation. Design and
argument draft only: no broker server, measurement launch or new transport
admission is claimed. Zero model calls, Docker commands and native pairs.
The separately approved runtime-resolution window is unchanged.

## Connection and identity

The controller starts a host-owned Streamable HTTP MCP broker, outside the
`lyb06builder` process tree. Only that host process imports repository `tools/`.
The fixed Codex binary runs as the admitted non-admin SID and connects to
`http://127.0.0.1:<host-assigned-port>/mcp`. It does not spawn a Python/stdin
broker. Windows ACL denial of tools/private folders remains mandatory.

Use a fresh 256-bit CSPRNG bearer token for each builder invocation, delivered
only in that child's `B06_MCP_TOKEN` environment. Configure
`bearer_token_env_var="B06_MCP_TOKEN"`; never put the token in arguments, URLs,
prompts, tool output, logs, exports or signed receipts. This is separate from
OpenAI authentication, Tower authorization and signing authority. Record a
non-secret session ID bound to campaign, journey, trial, invocation and the
launched process/SID. Do not reuse tokens across repairs or invocations.
Codex documents HTTP MCP and environment-based bearer authentication in the
[official MCP reference](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

The broker must bind IPv4 loopback only, not wildcard interfaces; reject
non-loopback peers, unexpected Host/Origin headers, redirects, and cross-session
MCP IDs. Authenticate every request (including initialize, GET/SSE and DELETE),
with constant-time token comparison, an invocation deadline and revocation.
Reject absent, wrong, expired and other-session credentials before dispatch.
No anonymous discovery, CORS access, unauthenticated debug route or token logging.
Token possession is a scoped capability, not proof of the process's SID: the
host must separately bind the process identity and admit its OS denial proof.

Expose exactly `public_contract`, `public_api`, `deterministic_support`,
`check_structure`, `compile`, through `ms94_b06_builder_boundary.dispatch`.
No arbitrary filesystem, shell, SQL, capture, expectation or signing endpoint.
Reuse the closed argument/result schemas and hash-chained broker journal;
independently match CLI MCP events to recorded inputs and outputs. The host
backend must serve only admitted public material. The existing v5 broker is
not a completed J3 backend: journey-specific backend qualification remains due.

Each invocation has an exclusive broker session. The controller owns call and
compilation counters, serializes tool requests, and deduplicates request IDs;
reconnection must not duplicate a compilation. The broker enforces body/source
bounds, remaining budgets and the trial deadline including finalization reserve.
Thirty seconds startup and 660 seconds per tool are ceilings; reject a tool
before execution if its bound cannot fit the remaining admitted time. Native
or compilation work remains separately authorized and supervised.

The account-scoped WFP policy continues to deny outbound access for other
builder executables; the pinned Codex app ID is the sole executable exception.
It needs loopback access to this broker and approved OpenAI service access.
This app-ID exception does **not** itself restrict destination hosts. Freeze
the exact network policy and record that limitation; it is not a domain
allowlist. No helper executable gains network access. Verify the actual
loopback behavior under WFP in the final transport probe, rather than infer it.

On completion, timeout, pause or fault, revoke the token, close streams, stop
the owned broker/process tree, and verify cleanup before another invocation.
Broker/authentication/provenance failure is transport/equipment evidence, not
a candidate business verdict. It may not be relabelled as a candidate failure
or silently retried after evaluation.

## Exact argument draft and authentication

[measurement-exec-draft.json](measurement-exec-draft.json) contains the argument
array, using illustrative port 49152 and an empty local working directory.
`tools/ms94_b06_http_transport_draft.py` deterministically constructs it, with
only the host-assigned port and admitted empty directory substituted. It does
not launch anything. Use Windows argument serialization, not a shell-joined
command; source/prompt text goes only to redirected stdin after admission.
Bind the actual array, substitutions, client hash, launcher and broker code in
the final plan. The draft keeps `gpt-6-astra`/`high` and the existing closed
capability flags, adds HTTP MCP configuration, `--ignore-rules` and
`--strict-config`, and preserves read-only sandbox, JSON and ephemeral output.
The CLI sandbox is not an OS confidentiality guarantee.

Set `CODEX_HOME` to the existing authenticated profile of **lyb06builder**;
do not substitute the operator's login or the earlier empty smoke-test home.
Clear inherited API-key/credential overrides and validate the intended auth
store. No credential copying or password reset. Disable config/rule discovery
as drafted, run outside a repository in the empty admitted directory, and
verify the effective tool/config inventory before launch. User config omission
does not establish that managed policies, plugins, instructions or other
discovery paths are absent. Any extra input/tool fails admission.

The actual pinned 0.160.0 `exec --help` was checked without a prompt. It states
that `--ignore-user-config` omits config.toml while authentication still uses
CODEX_HOME. `login status --ignore-user-config` was parser-rejected: that flag
belongs to exec. The zero-model account check must therefore run `login status`
with the same account, profile and explicit credential-store setting intended
for exec. Help/EOF validates neither authentication nor server connectivity.
See the [CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
and [authentication documentation](https://learn.chatgpt.com/docs/auth).

Two actual account-check attempts are preserved locally. Both stopped with
Windows `0x80070005` / Access is denied before Codex login status ran. Attempt 2
identified `Register-ScheduledTask` (S4U) as the failing operation, even after
enabling the account before registration. Both cleanup records report account
disabled, owned task absent and temporary firewall rule absent; no password
was changed. **Login availability is unverified**, not failed authentication.
The helper blocks Codex egress and records classifications only, never raw
status output, tokens or auth.json contents. S4U also would not prove that an
OS-keyring login behaves identically under the final password logon.

The next account check needs a working authorized logon as lyb06builder using
its existing credentials/profile. Do not reset its password or weaken local
security policy to make this check pass. If login is missing, Howard must
authenticate that account interactively before a final transport probe.

## Required final zero-model transport probe

Freeze implementation and argv first, then produce a new signed record binding
the exact client, account SID hash, broker, launcher, config, ACL and WFP policy:

1. Same-account, same-profile login status; only safe status classifications.
2. Actual Codex-to-host MCP initialize and exact five-tool discovery over HTTP,
   with per-session bearer authentication. A separate HTTP test client alone
   does not prove that Codex connects. Use a demonstrated no-model client
   protocol; if it cannot exercise this path without a model, stop and report
   the gap. Do not substitute a model request for a transport check.
3. Missing/wrong/expired/cross-session token rejection on every HTTP method,
   response/journal equality, token-log scan and session teardown.
4. Built-in tools/private read-denial probes inside this exact Codex process
   tree, positive allowed-file and distinct not-found controls, SID binding,
   effective tool/input inventory and actual WFP loopback/egress controls.
5. Exact measurement argument array with closed stdin: no prompt, no model
   request, no compile/tool backend execution or Docker. Preserve this as an
   EOF check only. Assert backend invocation counters remain zero.
6. Deadline and broker-failure paths; cleanup, independent replay and admission
   rejection for changed hashes or missing evidence. No old proof is amended.

The old `ms94_b06_pinned_exec.ps1` and its signed proof are unchanged. This
draft does not satisfy `admit_transport`, replace that proof, or wire a model
launcher into Controller. Full per-journey qualification and immutable
measurement preflight remain separate prerequisites.

## Preparation checks and preserved evidence

Eleven focused tests passed in 1.117 seconds, including the existing capability
and pinned-transport admission tests. Both new PowerShell files parsed. Two
earlier sandbox test invocations each passed ten tests and encountered one
TemporaryDirectory access error; the unchanged tests passed outside that
filesystem sandbox. No security policy was weakened.

The [signed account-check audit](account-check-attempts.json) binds hashes of
both preserved local failure/cleanup records and explicitly records that no
account login result was obtained. Its content hash is
`2bb1fe1a648f85e62b5600c2e60e7b8ed46dc22f833472069c70465651df0478`.
The argument-draft file hash is
`0004bcecd8607e01c06b2b1c08b83f1cb5340c336ff2cf738194f35de5a6e3fb`.
Neither hash grants measurement or transport approval.
