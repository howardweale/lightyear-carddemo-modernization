"""B06 candidate-input boundary; never relabel arbitrary verifier exceptions."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from xml.etree.ElementTree import ParseError

from lightyear_calibration.application_journey import read_trace
from lightyear_calibration.ms94_v3_errors import BusinessViolation, business_require
from lightyear_calibration.native_reconciliation import valid_uuid


class CandidateTimeout(Exception):
    """Trusted execution watchdog expired, distinct from a controller deadline."""
    code = 'candidate-timeout'


def trace_shape(trace, journey):
    # Keep this boundary outside the unchanged J1 and procurement predicates.
    from tools.ms94_b06_footprint import MATERIALS, PURCHASING
    stages = PURCHASING if journey == 'J2' else MATERIALS
    for stage in stages:
        value = trace.get(stage + '.id')
        business_require(value is not None, 'trace-identity-missing')
        business_require(isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,9}', value)
                         and int(value) <= 2147483647, 'trace-identity-invalid')
        value = trace.get(stage + '.uuid')
        business_require(isinstance(value, str) and valid_uuid(value), 'trace-uuid-invalid')
        business_require(trace.get(stage + '.saved') == 'true', 'trace-save-invalid')
    if journey == 'J2':
        for stage in ('purchaseOrder', 'receipt', 'vendorInvoice', 'vendorPayment'):
            business_require(trace.get(stage + '.status') == 'CO', 'trace-status-invalid')
        business_require(trace.get('vendorInvoice.paid') == 'true', 'trace-paid-invalid')
        for field in ('purchaseOrder.net', 'purchaseOrder.total', 'purchaseOrder.priceActual',
                      'purchaseOrder.discount', 'receipt.quantity', 'vendorInvoice.total',
                      'vendorPayment.amount', 'inventory.onHand'):
            value = trace.get(field)
            try:
                valid = isinstance(value, str) and Decimal(value).is_finite()
            except InvalidOperation:
                valid = False
            business_require(valid, 'trace-number-invalid')
    return trace


def candidate_trace(path, journey):
    # Only parse/shape failures of the untrusted candidate file are candidate
    # results. Permission/I/O errors and errors in signed native captures escape.
    try:
        trace, sha = read_trace(Path(path))
    except FileNotFoundError as exc:
        raise BusinessViolation('trace-file-missing') from exc
    except (ParseError, ValueError) as exc:
        raise BusinessViolation('trace-format-invalid') from exc
    trace_shape(trace, journey)
    return trace, sha
