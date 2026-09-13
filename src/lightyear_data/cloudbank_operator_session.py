"""Temporary operator settings for uninterrupted, small-checkpoint cloud drills."""
from contextlib import contextmanager
import os
import sys

from .cloudbank_journeys import require


@contextmanager
def operator_session():
    # Small signed checkpoints need neither multiprocessing nor many workers.
    # These overrides apply only to this executor and its children.
    settings = {"CLOUDSDK_STORAGE_PROCESS_COUNT": "1", "CLOUDSDK_STORAGE_THREAD_COUNT": "1"}
    prior = {name: os.environ.get(name) for name in settings}
    power, previous_power = None, None
    try:
        if sys.platform == "win32":
            import ctypes
            power = ctypes.windll.kernel32.SetThreadExecutionState
            power.argtypes = [ctypes.c_uint32]
            power.restype = ctypes.c_uint32
            previous_power = power(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            require(bool(previous_power), "operator-idle-sleep-hold-failed")
        os.environ.update(settings)
        yield
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if power is not None and previous_power:
            power(previous_power | 0x80000000)
