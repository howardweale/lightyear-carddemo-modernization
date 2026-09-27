# Complete MS90 captures

This lossless archive contains 7,379 files, including all 7,364 native source
artifacts pinned by MS90 and the complete versioned assessment. It preserves the
original failed gate and the separately passing v2 comparison. No new model calls
or native executions were used to create or verify this package.

From the repository root, with project dependencies installed and `src` on
PYTHONPATH:

```powershell
python -m tools.publish_declared_evidence verify --output docs/calibration/idempiere-judge-v2-captures --trusted-key-sha256 c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f
```

The verifier checks the trusted public key, signatures, every reconstructed file
hash and the original implementation, then reruns the native business gate and
versioned comparison using the raw captures. It starts no databases and makes no
model calls. The fingerprint here identifies the operator key; establish trust
in it independently when assessing a third-party copy. Operator-signed evidence
is not independent attestation.

Expected result: `verified-complete-native-captures`, original gate false,
versioned comparison true, full native gate replayed true.
