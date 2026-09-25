# Decoding the next estate

The decoder now handles IBM binary integers with implied decimal scaling,
REDEFINES overlays and one bounded OCCURS DEPENDING ON table. These are byte
readers, not business-equivalence rules. The example is synthetic; no customer
or native mainframe run is claimed.

## Binary fields

COMP, COMPUTATIONAL, COMP-4 and BINARY use the IBM 2/4/8-byte layout for 1–4,
5–9 and 10–18 PIC digits. Signed fields use two's complement. COMP-5 uses the
whole binary storage range. Decimal scaling remains exact, including 64-bit
extremes. Binary byte order must be supplied explicitly. COMP/BINARY also requires
`std` (PIC-limited) or `bin` (storage-limited) truncation interpretation. Nothing
is inferred from the workstation running the decoder. [IBM computational items](https://www.ibm.com/docs/en/cobol-zos/6.5.0?topic=clause-computational-items)
describes the storage and COMP-5 distinction.

## REDEFINES

The compiler allocates the maximum size of the contiguous alternatives once.
Following fields start after that shared area. Each overlay requires an explicit
path-to-name selection; the decoder does not guess which alternative is active.
Different fixed-OCCURS instances can choose different alternatives. Unselected
bytes remain in the original record hex, including unused overlay padding.
Unknown selections, noncontiguous targets and ambiguous FILLER overlays fail.

For the [example copybook](../../spec/mainframe/copybooks/BANKEXT.cpy), the selection is:

```json
{"BANK-RECORD.PAYLOAD": "IDENTIFIER"}
```

## Variable records

The controller must be an unambiguous, preceding, unrepeated integer field.
The count is read from the bytes and checked against the declared lower/upper
bounds. Zero is supported when declared. Active table entries determine where
following fields start. Nested variable tables, ODO inside repeated groups or
overlays, and unknown controllers are rejected.

`record` framing accepts exactly one payload. `rdw` accepts a sequence of IBM
four-byte RDWs whose big-endian lengths include the header. Reserved/segment
bytes must be zero; truncated, padded or spanned records fail. These are unblocked
RDW records, not BDW-containing VB blocks. Fixed framing refuses a variable layout.
The existing fixed-block mock spool envelope remains fixed-block only.

## Run the independent byte fixture

[The golden vectors](../../spec/mainframe/extended-golden.json) include zero and
two entries, binary controllers/identifiers, packed decimal positive/negative
amounts, and a trailing marker whose offset slides with the table length.
The payload lengths are 13 and 19 bytes, and RDW lengths are 17 and 23 bytes.

```sh
python - <<'PY'
import json
from pathlib import Path
f=json.loads(Path('spec/mainframe/extended-golden.json').read_text())
Path('/tmp/bank-records.rdw').write_bytes(bytes.fromhex(''.join(r['rdw_hex']+r['payload_hex'] for r in f['records'])))
Path('/tmp/bank-choices.json').write_text(json.dumps(f['redefines']))
PY
PYTHONPATH=src python -m lightyear_mainframe decode \
  --copybook spec/mainframe/copybooks/BANKEXT.cpy \
  --input /tmp/bank-records.rdw --framing rdw --codec cp037 \
  --binary-byteorder big --binary-truncation std \
  --redefines /tmp/bank-choices.json --output /tmp/bank-decoded.json
```

The output retains the copybook/record hashes, every payload byte, actual offsets,
exact values, selected alternatives and binary settings. Malformed input fails
before a success artifact is written. Existing CardDemo fixed-record manifests
and the public decoding receipt remain unchanged.
