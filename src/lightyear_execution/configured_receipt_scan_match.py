"""Classify untrusted native scan locals; this function grants no origin.

The native scanner stops at its first matching decoded view. These labels
describe that stopping view only, not all views or the intended case stimulus.
Return no token, answer window, normalized text or original context bytes.
"""
from lightyear_factory.contracts import ContractError


def classify_stopping_view(tokens,windows,normalized):
    if (type(tokens) is not set or len(tokens)!=3
            or any(type(token) is not str or len(token)<32 for token in tokens)
            or type(windows) is not set
            or any(type(window) is not str or not window for window in windows)
            or type(normalized) is not str):
        raise ContractError('configured-context-scan-match-shape')
    # Exactly the two sets used in native scan's tokens | windows expression.
    # No decoding, new expected-values call, second scan or provider operation.
    canary=any(token in normalized for token in tokens)
    expected=any(window in normalized for window in windows)
    if canary and expected:return 'canary-and-expected-window'
    if canary:return 'canary'
    if expected:return 'expected-window'
    raise ContractError('configured-context-scan-no-native-match')
