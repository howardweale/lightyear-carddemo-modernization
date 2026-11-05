"""Public source-index and ciphertext-inventory correspondence, without I/O.

This additive contract does not read source or ciphertext, authenticate an owner,
decrypt, admit, dispatch or qualify a run. The caller supplies expected values
from authenticated, admitted state, never from the returned packets. Hash and
inventory correspondence alone do not establish native or production provenance.
The versioned public index below uses aliases, not private paths or plaintext.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from lightyear_control_tower.decisions import canonical

from .external_signing import SigningRefused, _json
from .helper_route_contract import (
    MAX_ARTIFACTS, MAX_CIPHERTEXT, MAX_PACKET, CiphertextDescriptor,
    HelperRouteBinding, HelperRouteRefused, _name, _require,
)


@dataclass(frozen=True)
class MatchedHelperProvenance:
    """Public correspondence only; this object grants no execution authority."""

    source_index_sha256: str
    inventory_sha256: str
    execution_id: str
    source_ciphertext_pairs: tuple[tuple[str, str], ...]


def _packet(raw: bytes) -> dict:
    try:
        return _json(raw, MAX_PACKET)
    except SigningRefused as exc:
        raise HelperRouteRefused("helper-provenance-packet") from exc


def match_helper_provenance(
    source_index: bytes,
    ciphertext_inventory: bytes,
    *,
    expected_binding: HelperRouteBinding,
    expected_execution_id: str,
    expected_source_names: frozenset[str],
    expected_artifacts: tuple[CiphertextDescriptor, ...],
) -> MatchedHelperProvenance:
    """Match two exact public packets against independently retained expectations.

    source-index/1 maps each expected source alias to exactly one expected
    ciphertext name. helper-ciphertext-inventory/1 binds the complete helper
    binding, execution ID, and exact opaque ciphertext descriptors. Both packets
    must be canonical JSON with sorted rows and no unknown fields. The source
    index's *exact bytes* must match the digest already retained in the binding.

    This function does not consume an attempt or prove freshness: the existing
    exchange/owner remains responsible for original deadlines, authentication
    and durable single-use enforcement. It never constructs expected state from
    either packet.
    """
    _require(type(expected_binding) is HelperRouteBinding,
             "helper-provenance-binding")
    _require(type(expected_execution_id) is str and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", expected_execution_id) is not None,
        "helper-provenance-execution")
    _require(type(expected_source_names) is frozenset and
             1 <= len(expected_source_names) <= MAX_ARTIFACTS,
             "helper-provenance-source-names")
    for name in expected_source_names:
        _name(name)
    _require(type(expected_artifacts) is tuple and
             len(expected_artifacts) == len(expected_source_names) and
             all(type(row) is CiphertextDescriptor for row in expected_artifacts),
             "helper-provenance-artifacts")
    artifact_names = {row.name for row in expected_artifacts}
    _require(len(artifact_names) == len(expected_artifacts),
             "helper-provenance-duplicate-artifact")
    _require(sum(row.ciphertext_bytes for row in expected_artifacts) <= MAX_CIPHERTEXT,
             "helper-provenance-total-size")

    index = _packet(source_index)
    _require(hashlib.sha256(source_index).hexdigest() ==
             expected_binding.source_index_sha256, "helper-provenance-index-digest")
    _require(set(index) == {
        "schema", "source_commit", "execution_id", "attempt_identity_sha256", "sources"
    }, "helper-provenance-index-fields")
    sources = index["sources"]
    _require(type(sources) is list and len(sources) == len(expected_source_names),
             "helper-provenance-source-count")
    pairs = []
    for row in sources:
        _require(type(row) is dict and set(row) == {"source_name", "ciphertext_name"},
                 "helper-provenance-source-row")
        pairs.append((_name(row["source_name"]), _name(row["ciphertext_name"])))
    _require(len({name for name, _ in pairs}) == len(pairs) and
             {name for name, _ in pairs} == expected_source_names,
             "helper-provenance-source-inventory")
    _require(len({name for _, name in pairs}) == len(pairs) and
             {name for _, name in pairs} == artifact_names,
             "helper-provenance-ciphertext-bijection")
    pairs = tuple(sorted(pairs))
    expected_index = dict(
        schema="helper-source-index/1",
        source_commit=expected_binding.source_commit,
        execution_id=expected_execution_id,
        attempt_identity_sha256=expected_binding.attempt_identity_sha256,
        sources=[dict(source_name=source, ciphertext_name=ciphertext)
                 for source, ciphertext in pairs],
    )
    _require(source_index == canonical(expected_index), "helper-provenance-index-binding")

    _packet(ciphertext_inventory)
    expected_inventory = dict(
        schema="helper-ciphertext-inventory/1",
        binding=expected_binding.document(),
        execution_id=expected_execution_id,
        artifacts=[row.document() for row in sorted(expected_artifacts, key=lambda r: r.name)],
    )
    _require(ciphertext_inventory == canonical(expected_inventory),
             "helper-provenance-inventory-binding")
    return MatchedHelperProvenance(
        source_index_sha256=expected_binding.source_index_sha256,
        inventory_sha256=hashlib.sha256(ciphertext_inventory).hexdigest(),
        execution_id=expected_execution_id,
        source_ciphertext_pairs=pairs,
    )
