"""CI-only regression coverage for measured P5 boundary failures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from lightyear_execution.admission import AdmissionNonceStore
from lightyear_execution.contracts import ExecutionContractError


def hold_reader(path, entered, release):
    original = Path.read_text
    def read(item, *args, **kwargs):
        result = original(item, *args, **kwargs)
        if item == Path(path):
            entered.set()
            if not release.wait(30):
                raise RuntimeError("synthetic-reader-timeout")
        return result
    with patch.object(Path, "read_text", read):
        AdmissionNonceStore(Path(path)).consume("synthetic-nonce")


class FailureRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


    def test_legacy_consumed_hashes_and_new_nonce_survive(self):
        path = self.root / "nonces"
        first = hashlib.sha256(b"legacy").hexdigest()
        path.write_text(first + "\n", encoding="ascii")
        store = AdmissionNonceStore(path)
        with self.assertRaises(ExecutionContractError):
            store.consume("legacy")
        store.consume("synthetic-new")
        with self.assertRaises(ExecutionContractError):
            AdmissionNonceStore(path).consume("synthetic-new")
        self.assertEqual([first, hashlib.sha256(b"synthetic-new").hexdigest()], path.read_text().splitlines())

    def test_overlapping_threads_have_one_admission(self):
        path = self.root / "threads"
        path.write_text("", encoding="ascii")
        entered, release = threading.Event(), threading.Event()
        read = Path.read_text
        def interleave(item, *args, **kwargs):
            value = read(item, *args, **kwargs)
            if item == path and not entered.is_set():
                entered.set()
                if not release.wait(20):
                    raise RuntimeError("synthetic-reader-timeout")
            return value
        def consume():
            try:
                AdmissionNonceStore(path).consume("synthetic-nonce")
                return True
            except ExecutionContractError:
                return False
        with patch.object(Path, "read_text", interleave), ThreadPoolExecutor(max_workers=8) as pool:
            first = pool.submit(consume)
            try:
                self.assertTrue(entered.wait(20))
                rest = [pool.submit(consume) for _ in range(7)]
                self.assertEqual(0, sum(f.result(timeout=20) for f in rest))
            finally:
                release.set()
            self.assertTrue(first.result(timeout=20))
        self.assertEqual(1, len(path.read_text().splitlines()))

    def test_process_lock_survives_contention_and_releases_after_kill(self):
        path = self.root / "processes"
        path.write_text("", encoding="ascii")
        context = multiprocessing.get_context("spawn")
        entered, release = context.Event(), context.Event()
        child = context.Process(target=hold_reader, args=(str(path), entered, release))
        child.start()
        try:
            self.assertTrue(entered.wait(30))
            with self.assertRaises(ExecutionContractError):
                AdmissionNonceStore(path).consume("synthetic-nonce")
        finally:
            child.terminate()
            child.join(30)
        self.assertFalse(child.is_alive())
        AdmissionNonceStore(path).consume("synthetic-nonce")
        with self.assertRaises(ExecutionContractError):
            AdmissionNonceStore(path).consume("synthetic-nonce")

    def test_short_write_and_partial_ledger_never_admit(self):
        path = self.root / "partial"
        write = os.write
        def short(fd, data):
            return write(fd, data[:5] if len(data) == 65 else data)
        with patch("lightyear_execution.admission.os.write", short):
            with self.assertRaises(ExecutionContractError):
                AdmissionNonceStore(path).consume("synthetic-nonce")
        with self.assertRaises(ExecutionContractError):
            AdmissionNonceStore(path).consume("different-nonce")

    def test_link_refusal_before_ledger_write(self):
        path = self.root / "linked"
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ExecutionContractError):
                AdmissionNonceStore(path).consume("synthetic-nonce")
        self.assertFalse(path.exists())
