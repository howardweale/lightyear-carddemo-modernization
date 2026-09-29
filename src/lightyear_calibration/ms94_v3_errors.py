"""Typed private judge failures. Messages never select the result class."""
from .contracts import CalibrationError


class BusinessViolation(CalibrationError):
    """An observed candidate result violates a declared business/shape constraint."""


def business_require(condition, message):
    if not condition:
        raise BusinessViolation(message)
