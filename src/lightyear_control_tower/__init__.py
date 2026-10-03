"""Live, read-only operational evidence plane for the LIGHTYEAR Control Tower."""

__version__ = "0.19.2"
from .verification import verify_decision, DecisionVerificationError

__all__ = ["verify_decision", "DecisionVerificationError"]
