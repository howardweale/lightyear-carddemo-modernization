# PR262 review follow-up: smoke trust and HTTP transport

October 6, 2026, from main `bf3f72e`. Operator review; not independent
attestation. Zero model calls, Docker commands and native pairs. This is
preparation, not successful transport admission or qualification.

## Smoke gate

The existing r7 three-slot J1 snapshot is preserved. A read-only verification
checked all **2,106 files**, with snapshot hash
`cc2f9522d3be2d7a527780f98de42391ede4d3c7438ddce0dee6cd64fa38b77b`.
The slots remain reference, duplicate invoice line, and candidate null
dereference/direct diagnostic delivery. No slot has been executed here.

`tools/ms94_b06_smoke_request.py` prepares a group only after the operator
confirms the SHA-256 of the existing Tower public-key PEM bytes. It requires
an Ed25519 key distinct from the campaign signer and delegates all snapshot,
slot, image, calendar and input checks to the existing conversion code. It
writes a new group file exclusively. Its request helper requires byte identity
with the public group file before invoking `write_request`.

The tool does not locate authority by guessing, create a signing key, grant a
role, inspect private-key bytes, authorize Docker, or sign an operator decision.
The caller must independently verify the public Git commit; passing arbitrary
bytes to the helper is not evidence of publication.

No existing B06 authority was found. Howard explicitly approved the separate
`lyb06tower` setup and confirmed public fingerprint
`65bcec7f9fb46d5a618cd61b8bcd0a74497b9a0c360738781e269ef2d87a6240`.
The [setup audit](tower-setup-r8.md) verifies actual Windows error 5 on
private-key read-open under both the Codex host identity and builder identity,
with successful public controls and missing-file error 2. No key bytes were
exported. The exact smoke group is public at
`ec639ba6f56940e235e04b41c1cb3f013c25e568` (all 11 files byte-verified),
and its request is in the running Tower inbox. Howard's exact Tower authorization has since been verified; see the
[r8 milestone](milestone-r8.md) for its hash and the inbox deployment repair.

The conditional window remains **October 7, 03:00–09:00 UTC**. The three
7,190-second limits leave only 30 seconds at the extreme bound. No slot may
start without its entire remaining budget, and no extension or replacement
is authorized. If the key/publication/decision gates are not complete, no run.

The review's statement that graph PRs are open predates their merges.
This increment is based on current main and does not change Tower code or a
running Tower. Record the actual Tower executable revision when the authority
is confirmed; do not swap it during an authorized group.

## New HTTP transport implementation

`tools/ms94_b06_http_broker.py` is a host-owned loopback server with an injected
backend. It exposes exactly the five existing builder capabilities through
`ms94_b06_builder_boundary.dispatch`. It neither supplies a production J3
backend nor launches a model. Tests use a public, offline fixture backend.

- Fresh 256-bit bearer token and non-secret session ID per invocation.
- Authentication for every HTTP method; exact loopback Host, no Origin,
  session/protocol binding, bounded JSON, duplicate-key rejection and bounded
  socket reads. No request or token logging, redirects or debug route.
- JSON Streamable HTTP initialize/ping/list/call and initialized notification.
  GET/SSE is unsupported and returns authenticated 405; no streams or server
  notifications are advertised. DELETE revokes the session.
- Serialized dispatch and request-ID deduplication. Identical reconnects return
  the same response without another compile; conflicting reuse fails.
- Compilation and request limits; a tool cannot start unless its declared
  ceiling plus finalization reserve fits. Backend exception or overrun revokes
  the session and records equipment failure with no exception prose.
- Private local hash-chained request/result journal. Independent replay checks
  chain, binding, tool schemas and accounting; delivery verification matches CLI
  MCP events and actual result values against an externally bound head/count.
  The host must sign those terminal bindings; an unsigned journal alone is not
  admission evidence. Journals may contain candidate source and stay local.
- Context-manager cleanup revokes the token and stops the listener.

The backend must have its own supervised process deadline. A Python HTTP
thread cannot kill a blocked native backend. The transport detects overruns
and forbids further dispatch; it does not claim native process cleanup.
The six-step **actual lyb06builder/WFP/pinned-client probe** from r7 remains
mandatory. Offline HTTP tests do not substitute for that evidence.

## File authentication and supervised login

The new `ms94_b06_http_transport.arguments()` adds the explicit
`cli_auth_credentials_store="file"` override to the r7 exec draft. It preserves
the pinned 0.160.0 executable, model/reasoning, disabled web search, closed
capabilities, environment-sourced MCP token, and `--ignore-user-config`.
Login uses the same explicit store. Pinned CLI help confirms that ignoring
user config still uses `CODEX_HOME` for authentication; help is not a successful
builder login check.

`ms94_b06_builder_login.ps1` and `ms94_b06_builder_login_child.ps1` provide a
separate supervised login session. Run the parent from an Administrator
PowerShell console. It requires the existing disabled account, a new output
directory, and Howard's newly chosen temporary password entered securely.
It starts the native pinned executable using Windows CreateProcessWithLogonW
under the builder identity, in a visible window for device sign-in. It does not
execute a PowerShell script under the Restricted builder policy. No scheduled task, batch-logon grant, execution-policy bypass,
Defender exception or copied operator auth file is used.

Authentication home is `C:\ProgramData\Lightyear\B06Auth\0.160.0`.
The directory and `auth.json` allow only the builder SID and Administrators;
unexpected read grants, links or user config cause refusal. Only a recognized,
sanitized `login status` classification is saved, never raw output, account
details, credential contents or login transcript. The parent disables the
account and checks owned-process cleanup on exit. Earlier S4U failures and
signed r6 proofs are unchanged. The login script has parsed but **has not
been run under elevation**; its actual login/ACL result remains pending.

Example (Administrator console; choose a fresh attempt name):

```powershell
$repo = 'C:\Users\howar\OneDrive\Documents\ChatGPT\lightyear-carddemo-modernization\work\verify-smoke-kit'
& "$repo\tools\ms94_b06_builder_login.ps1" -Repository $repo -OutputDirectory 'C:\ProgramData\Lightyear\b06-login-r8-attempt1'
```

See the [official authentication documentation](https://learn.chatgpt.com/docs/auth)
and [HTTP MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
Actual 0.160.0 behavior must still pass the final probe. Its executable-level
WFP exception is not a destination-domain allowlist; web search stays disabled.

## Validation and remaining work

- Final complete B06 offline suite: **139 tests passed** on Windows in 28.183
  seconds. Latest full run after the login helper correction: **139 tests
  passed in 29.881 seconds**. Earlier 138-test run passed in 30.408 seconds.
- After stricter journal replay, login failure handling and real MCP SDK
  compatibility, 16 focused tests passed in 5.729 seconds; both new PowerShell
  scripts parsed.
- Real loopback fixture tests include concurrent duplicate requests, all-method
  authentication, Host/Origin/session rejection, budget/deadline rejection,
  backend failure/overrun, terminal-head binding and CLI output equality.
- The installed MCP v2 SDK initialized, listed all five tools, called the offline
  fixture and terminated the session. Its empty `_meta` parameters initially
  exposed an overly strict protocol-envelope check; this was corrected without
  widening tool arguments. A test-side SDK field-name mistake was also fixed.
  The passed SDK check uses no model, native backend or builder account.
- Initial sandbox test execution failed on Windows temporary-directory access
  before reaching test logic; unchanged tests passed outside that sandbox.
- Local pinned-client help emitted temporary PATH-alias access warnings. It was
  not a login, final transport probe, model request or qualification result.

Core-status items 1–2 remain natively unqualified; item 3 has the intact smoke
snapshot and a verified exact Tower authorization; native admission/run remain
pending in the approved window. Item 4 has this
transport implementation but no admitted measurement launcher; item 5 awaits
actual transport evidence and immutable per-journey zero-model preflight.
No B05 evidence, `work/ms94`, template-r1, J1 predicates, or files bound by the
existing signed transport proofs were changed. Keep smoke trust preparation
and transport implementation in separate PRs when publishing.
