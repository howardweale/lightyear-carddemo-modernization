# CloudBank Credit Decision and AI boundary

MS #64 completes the remaining-service wave without turning a demo random number or an unevaluated
model response into a production claim. The generated target carries the MS #57 PostgreSQL Customer
service and the MS #63 five-service target into one isolated eight-service package. It explicitly
records `azn-server`, `checks`, `testrunner`, `creditscore`, and `chatbot` as migrated, regenerates
each target workcell, and executes a dedicated Java test class for every one in the MS #64 lane.

The lane also executes Account and Transfer probe-security tests. Its **37 Java tests** include
16 HTTP filter-chain checks across Account, Transfer, Credit Score, and Chatbot: the exact health,
liveness, and readiness paths permit anonymous probes; business endpoints still require a token
and the correct scope; other actuator paths remain protected. These tests use test token decoders
and handler stubs to isolate authorization, while MS62 supplies native JWT validation evidence.
The probe corrections are applied only when composing the MS64 target, preserving MS57/MS63 inputs.

The generated parent POM pins HttpCore (`httpcore5` and `httpcore5-h2`) to **5.4.3**,
embedded Tomcat to **10.1.59**, and PostgreSQL JDBC to **42.7.12** across the eight services.
These updates address the six findings reported by the MS67 Authorization Server image scan:
CVE-2026-54399, CVE-2026-54428, CVE-2026-65182, CVE-2026-65905, CVE-2026-68525,
and CVE-2026-54291. The pinned Oracle source checkout is preserved.

Release references: [HttpCore 5.4.3](https://hc.apache.org/news.html),
[Tomcat security fixes](https://tomcat.apache.org/security-10.html), and
[PostgreSQL JDBC 42.7.12](https://jdbc.postgresql.org/changelogs/2026-06-29-42.7.12-release/).
Tomcat 10.1.58, listed by the scanner as a fixed version, failed its release vote; 10.1.59
is the released version containing those fixes.

The generated parent also updates the Spring AI BOM from **1.0.5** to **1.0.7**. This keeps
Chatbot's Spring AI modules aligned and addresses its three HIGH findings across
`spring-ai-client-chat` and `spring-ai-model`: [CVE-2026-41712](https://spring.io/security/cve-2026-41712)
and [CVE-2026-41713](https://spring.io/security/cve-2026-41713). Spring confirms both fixes in the
[1.0.7 release](https://spring.io/blog/2026/05/08/spring-ai-1-0-7-1-1-6-2-0-0-M6-available-now).
Generation requires exactly the expected source BOM property and rejects missing, duplicate,
or changed declarations before writing the parent POM.

The dependency versions are bound into the MS64 execution plan and signed receipt. After updating
these pins, run MS64 again in a fresh output directory using the existing signed MS57/MS63 inputs.
Use that new MS64 receipt and its generated workspace to rebuild the service images. The MS67
image builder still requires fresh signature, provenance, and zero-high/zero-critical scan results
for every image before producing its image lock.

Credit Score requires an issuer-, audience-, lifetime-, signature-, and scope-valid JWT. It replaces
the random demo response with a stable, subject-and-date-bound HMAC result labelled `synthetic-v1`.
The runtime pepper is never persisted. This proves the application boundary, not a real credit-bureau
decision or regulated scoring model.

Chatbot uses a distinct audience and rejects blank, oversized, and recognizable instruction-override
inputs before invoking the model. It filters unsafe and oversized outputs, rate-limits by authenticated
subject, returns safe failures without upstream details, and permits model egress only to an allowlisted
HTTPS host or an explicitly allowlisted loopback HTTP endpoint. Raw prompts, responses, tokens, and
secrets are not written to receipts.

Run deterministic verification:

```bash
./cloudbank-edge-ai.sh verify
./cloudbank-edge-ai.sh verify-source ../cloudbank-upstream
./cloudbank-edge-ai.sh materialize ../cloudbank-upstream work/cloudbank-ms64
```

An authorized signed run also requires the operator-held MS #63 and MS #57 receipts created with the
same evidence key and PostgreSQL image:

```bash
export LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY='operator-held-value'
./cloudbank-edge-ai.sh run ../cloudbank-upstream /secure/ms63-receipt.json \
  /secure/ms57-receipt.json work/cloudbank-ms64-run operator-name
```

A passing receipt qualifies all five remaining target workcells and the eight-service target package.
It does not call a credit bureau or external model, qualify model-answer quality, establish
whole-application Oracle/PostgreSQL equivalence, complete a migration, authorize promotion, or prove
production readiness.
