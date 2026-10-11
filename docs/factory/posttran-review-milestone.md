# POSTTRAN operator review ready

Open [the ten-record review page](posttran-human-review.html). Enter your name,
choose accept/reject/investigate and give a reason for every record. Download
the unsigned JSON. It binds the unchanged source review sheet, source lines
and acceptance evidence; it does not grant promotion. No decision is preselected.

After checking that JSON, use the existing `zos_evidence.Signer` operator flow
on your authority host (substitute your own key path; do not send it to Codex):

```powershell
python -B -m lightyear_mainframe.posttran_review sign --decisions posttran-decisions-unsigned.json --reviewer Howard --operator-key YOUR_LOCAL_OPERATOR_KEY --output posttran-review-signed.json
python -B -m lightyear_mainframe.posttran_review verify --decisions posttran-review-signed.json --public-key YOUR_ENROLLED_PUBLIC_KEY --output posttran-review-verification.json
```

Signing rejects missing decisions, wrong record identities, changed evidence
or unnamed reviewers before reading a key. Verification requires the enrolled
public key, exact signed body and all evidence bindings. Reject/investigate
decisions authenticate successfully but do not become acceptance. The page
contains no key field or network request. These are operator reviews, not an
independent attestation. Howard's decisions and signature remain outstanding.

Two focused tests passed: all ten records/source excerpts render, incomplete
decisions refuse, a test operator can sign and verify, and tampering fails.
Only ephemeral test keys were used. B06 and customer data remain untouched.

## 2026-10-11: where Howard reviews and returns decisions

Open [the readable review page](posttran-human-review.html) from a local checkout
in a browser, or use the GitHub file page and download the HTML:
https://github.com/howardweale/lightyear-carddemo-modernization/blob/main/docs/factory/posttran-human-review.html.
GitHub's source preview does not execute the page; no GitHub Pages deployment is claimed.

Enter your name, select accept/reject/investigate and a reason for each of the ten
records, then click **Download my unsigned decisions**. Send the downloaded
`posttran-decisions-unsigned.json` back in this chat. It is a proposed operator
review, not a signature or permission to run. Use the existing operator signing
flow on your authority host only after reviewing the file; never send the key.
