"""Join native build-verdict digest references to original receipt sections.

Relationship validation only. This does not recompute the native build verdict,
verify signatures, authenticate a controller or qualify a strict outcome.
"""
from lightyear_factory.contracts import ContractError,canonical_hash
from .configured_receipt_tail import verify_configured_receipt_tail


def verify_configured_terminal_build(receipt,summary,events):
    count=verify_configured_receipt_tail(receipt,summary,events)
    if 'factory_build_receipt' not in receipt:
        return count  # Original early-refusal behavior, no invented sections.
    build=receipt['factory_build_receipt']
    # Native compute_build_receipt hashes the whole intelligence document,
    # including its own content digest. Security/package references instead
    # use their original content_sha256 fields. Preserve that distinction.
    for section,reference,whole in (
        ('intelligence','accounting_sha256',True),
        ('execution_security','execution_security_sha256',False),
        ('candidate_package_finalization','candidate_package_sha256',False)):
        value=receipt.get(section)
        if (type(value) is not dict
                or value.get('content_sha256')!=canonical_hash(value,{'content_sha256'})):
            raise ContractError('configured-build-section-digest')
        expected=canonical_hash(value) if whole else value['content_sha256']
        if build.get(reference)!=expected:
            raise ContractError('configured-build-section-binding')
    return count
