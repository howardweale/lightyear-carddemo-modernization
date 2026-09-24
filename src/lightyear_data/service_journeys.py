"""Pack-backed CloudBank reference and capability binding, without journey logic."""
from pathlib import Path

from lightyear_workflow.service_pack import TargetLane, load

PACK_PATH = Path(__file__).with_name("packs") / "cloudbank.services.json"


def cloudbank_pack():
    # Reload on construction: edits cannot hide behind a process-level cache.
    return load(PACK_PATH)


def target_lane(runtime):
    controls = {name: getattr(runtime, name) for name in
                ("ready", "authorize", "stop", "start", "crash_stop", "restart", "restart_all")
                if callable(getattr(runtime, name, None))}
    if callable(getattr(runtime, "queue", None)):
        def queue(service, message):
            if service != "checks":
                raise ValueError("CloudBank queue adapter supports only checks")
            return runtime.queue(message)
        controls["queue"] = queue
    for action, method in [("block_delivery", "block_checks_delivery"),
                           ("restore_delivery", "restore_checks_delivery")]:
        if callable(getattr(runtime, method, None)):
            controls[action] = getattr(runtime, method)
    return TargetLane(lambda *args: runtime.request(*args), controls=controls, restore=getattr(runtime, "close", None))


def pack_binding_valid(bindings):
    """Old signed observations predate packs; new bindings must match exactly."""
    return isinstance(bindings, dict) and (
        "journey_pack_sha256" not in bindings or bindings["journey_pack_sha256"] == cloudbank_pack().sha256)
