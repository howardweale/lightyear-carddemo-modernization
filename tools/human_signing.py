"""Human-only DarkFactory PIV command. Never invoked by factory code or CI.

The device adapter is imported only inside the attended, bounded child process.
CI exercises public format/policy seams with disposable fixtures; never a token.
"""
import argparse
from datetime import datetime, timezone
import getpass
from importlib.metadata import version
import logging
import multiprocessing
import os
from pathlib import Path
import socket
import stat
import sys
import time
import warnings

from cryptography.hazmat.primitives import serialization

from lightyear_control_tower.decisions import canonical
from lightyear_execution.external_signing import SigningRefused, _sha, _time
from lightyear_execution.human_signing_packet import REQUEST_LIMIT, prepare_packet
from lightyear_execution.signing_key_a import PUBLIC_KEYS, prepare_key_a_designation


def require_human_host():
    if (sys.platform != "darwin" or os.geteuid() == 0 or 80 in os.getgroups()
            or socket.gethostname().split(".")[0].casefold() != "darkfactory"
            or any(os.environ.get(n) for n in ("CI", "GITHUB_ACTIONS", "CODEX_THREAD_ID"))
            or not all(s.isatty() for s in (sys.stdin, sys.stdout, sys.stderr))):
        raise SigningRefused("attended-DarkFactory-standard-account-terminal-required")


def read_public(path, maximum):
    # No symlinks, devices, FIFOs or unbounded reads from supplied packet paths.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise SigningRefused("regular-public-file-required")
        raw = stream.read(maximum + 1)
    if not 0 < len(raw) <= maximum:
        raise SigningRefused("public-file-size")
    return raw


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(Path(path).parent)


def reserve_attempt(root, packet):
    """A persistent tombstone precedes any hardware call, including failures.

    Scope excludes request/context/expiry: changing those cannot re-enable the
    same source/work-order/run/case/attempt/role. Never delete to retry.
    """
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = root.lstat()
    if (root.resolve() != root.absolute() or not stat.S_ISDIR(st.st_mode)
            or st.st_uid != os.getuid() or st.st_mode & 0o077):
        raise SigningRefused("private-owned-journal-required")
    binding = packet.binding
    name = _sha(canonical(dict(
        source_commit=binding.source_commit, work_order_sha256=binding.work_order_sha256,
        run_id=binding.run_id, case_id=binding.case_id, attempt=binding.attempt,
        purpose=packet.purpose)))
    attempt = root / name
    attempt.mkdir(mode=0o700)  # Atomic cross-process no-retry boundary.
    sync_dir(root)
    write_new(attempt / "intent.json", canonical(dict(
        request_sha256=packet.request_sha256, context_sha256=packet.context_sha256,
        binding=binding.document(packet.purpose, packet.key_sha256),
        state="CONSUMED_BEFORE_HARDWARE")))
    return attempt


def require_slot(metadata, purpose):
    pem = metadata.public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    if (metadata.key_type.name != "ED25519" or not metadata.generated
            or metadata.pin_policy.name != "ONCE"
            or metadata.touch_policy.name != "ALWAYS"
            or pem != PUBLIC_KEYS[purpose][0]):
        raise SigningRefused("device-slot-public-key-or-policy-mismatch")


def hardware_worker(pipe, purpose, message, wall_deadline, monotonic_deadline):
    """No key export, certificate, management authentication or configuration."""
    try:
        # Suppress library diagnostic dumps: they may contain device identifiers.
        logging.disable(logging.CRITICAL)
        if version("yubikey-manager") != "5.9.2":
            raise SigningRefused("reviewed-yubikey-manager-5.9.2-required")
        from ykman.device import list_all_devices
        from yubikit.core.smartcard import SmartCardConnection
        from yubikit.piv import PivSession, SLOT, KEY_TYPE

        def live():
            if datetime.now(timezone.utc) >= _time(wall_deadline) or time.monotonic() >= monotonic_deadline:
                raise SigningRefused("human-signing-window-closed")

        live()
        devices = list_all_devices([SmartCardConnection])
        if len(devices) != 1:
            raise SigningRefused("exactly-one-key-required")
        device, info = devices[0]
        if tuple(info.version) != (5, 8, 0):
            raise SigningRefused("reviewed-firmware-5.8.0-required")
        with device.open_connection(SmartCardConnection) as connection:
            piv = PivSession(connection)
            for role, slot in (("controller-receipt", SLOT.SIGNATURE),
                               ("candidate-commit", SLOT.AUTHENTICATION)):
                require_slot(piv.get_slot_metadata(slot), role)
            live()
            # Read the current PIN only from the controlling terminal. Refuse
            # getpass's echoing fallback. No arguments/environment/files/IPC PIN.
            with open("/dev/tty", "w") as terminal, warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                pin = getpass.getpass("Current PIV PIN (one attempt): ", stream=terminal)
                live()
                try:
                    piv.verify_pin(pin)  # Exactly once; never guess/retry.
                finally:
                    pin = None
                terminal.write("Touch lightyear-A once for the displayed request.\n")
                terminal.flush()
                live()
                slot = SLOT.SIGNATURE if purpose == "controller-receipt" else SLOT.AUTHENTICATION
                signature = piv.sign(slot, KEY_TYPE.ED25519, message, None)
                live()
        pipe.send_bytes(signature)
    except BaseException:
        # Deliberately do not serialize exception text, PINs, serials or dumps.
        try:
            pipe.send_bytes(b"")
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()


def stop_worker(process):
    if process.is_alive():
        process.terminate()
        process.join(1)
    if process.is_alive():
        process.kill()
        process.join(1)
    if process.is_alive():
        raise SigningRefused("worker-cleanup-unconfirmed-unplug-key")
    process.close()


def hardware_signature(packet):
    packet.check()
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    deadline = min(packet.window.monotonic_deadline, time.monotonic() + 120,
                   time.monotonic() + (_time(packet.revocations_expires_at)
                   - datetime.now(timezone.utc)).total_seconds())
    wall_deadline = min(_time(packet.binding.expires_at), _time(packet.revocations_expires_at)).isoformat()
    process = context.Process(target=hardware_worker, args=(
        send, packet.purpose, packet.signing_bytes(), wall_deadline, deadline))
    process.daemon = True
    started = False
    try:
        process.start()
        started = True
        send.close()
        # Bounded joins keep the parent responsive to cancellation and both clocks.
        while process.is_alive():
            packet.check()
            if time.monotonic() >= deadline:
                raise SigningRefused("human-signing-window-closed")
            process.join(min(0.1, max(0, deadline - time.monotonic())))
        packet.check()
        signature = receive.recv_bytes(64) if receive.poll() else b""
        if process.exitcode != 0 or len(signature) != 64:
            raise SigningRefused("hardware-failed-no-retry-unplug-key")
        return signature
    finally:
        send.close()
        receive.close()
        if started:
            stop_worker(process)


def execute(packet, output, journal):
    packet.check()
    print("Role:", packet.purpose, "slot:", "9c" if packet.purpose == "controller-receipt" else "9a")
    print("Run/case/attempt:", packet.binding.run_id, packet.binding.case_id, packet.binding.attempt)
    print("Source:", packet.binding.source_commit, "work order:", packet.binding.work_order_sha256)
    print("Payload SHA256:", _sha(packet.payload), "expires:", packet.binding.expires_at)
    phrase = "SIGN " + packet.purpose + " " + packet.request_sha256
    if input("After reviewing the exact payload and approval, type " + phrase + ":\n") != phrase:
        raise SigningRefused("human-confirmation-required")
    packet.check()
    attempt = reserve_attempt(journal, packet)
    # Reserve output before touching a token. A failure leaves a consumed intent
    # and an empty/partial file: it must never be treated as a reply or retried.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        signature = hardware_signature(packet)
        reply = packet.reply(signature)  # Independent public verification.
        packet.check()
        stream.write(reply)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(Path(output).parent)
    packet.check()
    write_new(attempt / "result.json", canonical(dict(
        state="PUBLIC_SIGNATURE_VERIFIED", request_sha256=packet.request_sha256,
        reply_sha256=_sha(reply), payload_sha256=_sha(packet.payload),
        native_qualified=False, admission_granted=False)))
    packet.check()
    print("Public reply SHA256:", _sha(reply))
    print("Unplug all keys before logout. No automatic return, import or retry.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare-designation", help="public-only unsigned scoped record")
    sign = sub.add_parser("sign", help="Howard-only attended one-shot PIV signing")
    for part in (prepare, sign):
        part.add_argument("--source-commit", required=True)
        part.add_argument("--work-order-sha256", required=True)
        part.add_argument("--output", type=Path, required=True)
    for name in ("request", "designation", "revocations"):
        sign.add_argument("--" + name, type=Path, required=True)
        sign.add_argument("--" + name + "-sha256", required=True)
    sign.add_argument("--context-sha256", required=True)
    sign.add_argument("--role", choices=("controller-envelope", "candidate-commit"), required=True)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "prepare-designation":
            prepared = prepare_key_a_designation(
                source_commit=args.source_commit, work_order_sha256=args.work_order_sha256)
            write_new(args.output, prepared.record)
            print("Unsigned scoped designation SHA256:", prepared.sha256)
            return 0
        require_human_host()
        packet = prepare_packet(
            read_public(args.request, REQUEST_LIMIT), read_public(args.designation, 16384),
            read_public(args.revocations, 16384), request_sha256=args.request_sha256,
            designation_sha256=args.designation_sha256,
            revocations_sha256=args.revocations_sha256,
            purpose="controller-receipt" if args.role == "controller-envelope" else args.role,
            source_commit=args.source_commit, work_order_sha256=args.work_order_sha256,
            context_sha256=args.context_sha256)
        journal = Path.home() / "Library/Application Support/Lightyear/human-signing-attempts"
        execute(packet, args.output, journal)
        return 0
    except (Exception, KeyboardInterrupt):
        print("STOP: no retry or automatic return. Retain intent; unplug all keys. "
              "A partial reply is not completion.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
