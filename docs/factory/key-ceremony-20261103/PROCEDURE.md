# YubiKey ceremony report and rehearsal correction — 3 November 2026

Howard's report covers 06:30–08:20 PST on 3 November in the dedicated standard ceremony account: both keys set up, one test-file decryption per key, and shared ciphertext decrypted with each key alone, followed by account logout. See the [human report](human-report.json#sha256=874c13d5eca0271a47652a575a0184ff7e5179165b6e125069c38f00bb6e645c).
This is a human attestation about public canaries, not machine evidence of production execution, process ownership, private-answer handling or signer authority.
The [public recipient file](public-recipients.txt) contains A first and B second, with names lightyear-A and lightyear-B.
Its SHA-256 is `48acf98df36a967bc60e2041475afa22f89553d593975171129a643ece30532d`.
The reported policies are PIN `once` and touch `always` for both keys.

## Procedure corrections

These notes supersede the setup wording in the 1 November PIV preflight and 2 November rehearsal package. They do not instruct a repeat ceremony on the completed keys.

1. Install ykman from the admin account. Return to the dedicated standard ceremony account for token setup. Keep private prompts and identity files there.
2. Howard's devices began with AES-192 PIV management keys. The plugin refusal was `custom unprotected non-TDES management keys are not supported`.
3. For new-key setup in that condition, the human compatibility step before age-plugin-yubikey is:

```sh
ykman piv access change-management-key --algorithm TDES --generate --protect
```

This is a management-key change, not a change to the age encryption recipient algorithm. It generates a management key and protects it on the token with the PIN. Do not supply secrets through command-line flags or copy prompt output into this repository.
[Yubico's command reference](https://docs.yubico.com/software/yubikey/tools/ykman/PIV_Commands.html#ykman-piv-access-change-management-key-options) describes AES-192 defaults on firmware 5.7 and the TDES, generate and protect options.

4. The first age-plugin-yubikey prompt requests the **CURRENT PIN**, not a new PIN. For an untouched factory-state device that means its factory-default PIN. The next prompt requests the current PUK. Then enter **one new value that becomes both PIN and PUK**. Do not publish any of those values.
5. Howard reports that A needed a PIV reset after a mis-entry, before any generation. A reset destroys existing PIV material: this historical fact is not a recovery step for A or B now. Stop on uncertainty rather than guessing or looping retries.
6. Preserve the actual settings: names lightyear-A / lightyear-B, PIN once, touch always. Older notes saying PIN/touch ALWAYS do not describe these devices. The production custody assessment must address the actual policy. No gate is waived by this report.

## Rehearsal script

The superseding [script](mac-software-rehearsal.sh) adds a display-only `ceremony-notes` mode containing the corrections above.
The existing `exercise` and `verify-logout` modes remain software-only and unchanged in behavior. Keep both YubiKeys unplugged during the dummy exercise.
Only Howard operates the exercise. Agents and CI must not execute it.
Logout alone does not prove absence of ceremony-account processes or ownership during a private-input window.

## Public and private boundaries

The public file contains only encryption recipients and A/B labels. The adjacent human report contains non-secret procedure facts and explicit evidence limits.
No PINs, PUKs, serials, identity files, private keys or plaintext expected answers are needed by agents, CI or this PR.
Identity files remain in the ceremony account even if a tool describes them as metadata.
Planned final-freeze registration must bind the exact public recipient bytes and the final source/runtime identities in the single freeze packet.
Planned Tower and receipt signing roles require their own designation. These encryption recipients do not create that designation.

## Earliest P5 production-controller receipt

Planned earliest first qualifying receipt against final E: **14 November 2026**, conditional on the 13 November freeze and all prerequisite integration, native proof, admissions and approvals.
Planned complete 19-case evidence: 16 November, followed by eight-gate qualification on 17–18 November. These are conditional planning dates, not appointments or evidence of readiness.
Earlier public-canary or component experiments cannot substitute for final-E production-controller evidence.

Planned human sequence for each controller attempt:

1. Review the exact final-E packet, case identifier, original deadline, one-use admission, fresh window, expected recipient hashes and designated signing identities. Complete the GitHub Environment approval and any separately required spend approval.
2. Log into the isolated standard custody account under the reviewed native-owner procedure, with unrelated agent/factory access excluded. Confirm the pinned tools and fixed command from the final operator packet.
3. Insert the intended key. Enter the PIN locally when prompted and touch for each private-key operation. Use the local identity file only. Ordinary decryption does not require both keys at once.
4. Start the one fixed controller attempt. The native owner must establish ownership before private input and prove cleanup/quiescence on every exit within the original deadline. An uncertain result remains REFUSED/UNKNOWN, with no automatic retry.
5. Perform local signing actions only with the separately designated receipt/Tower signer. The controller receipt must bind the case, attempt, final E and result. Direct Tower append needs an authenticated acknowledgment for that exact receipt. Under a human-carried alternative, transfer only the public envelope and return the authenticated acknowledgment within the same original deadline.
6. Preserve only public receipts, hashes and acknowledgment in the evidence path. Unplug and log out after containment/cleanup. A late acknowledgment or later logout cannot turn a failed attempt into success.

Not yet ready: the production Mac owner and Tower delivery choice (A direct append, B human-carried public envelope) still require a decision and implementation.
Not yet established: production helper integration, authenticated admission/replay handling, complete-route native failure/cleanup proof, actual PIN-once custody compatibility and separate signing-role designation.
Not yet complete: metrics collector/emitter and final-freeze source/control registration, Required/P5 closure, and the fresh per-attempt windows, admissions and Environment approvals.
Not yet proved: external provider billing behavior. The conservative reservation contract remains the accounting rule, not native provider proof.
No private material needs to leave Howard's ceremony account to resolve these dependencies.
