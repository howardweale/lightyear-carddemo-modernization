"""Readers cannot see an uninitialized SQLite journal during worker startup."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
import sqlite3
import tempfile
from threading import Event, current_thread, main_thread
import unittest
from unittest.mock import patch

from lightyear_workflow.run_store import RunStore


class JournalInitializationTests(unittest.TestCase):
    def test_reader_during_schema_creation_sees_no_journal_then_committed_events(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as cleanup:
            directory = Path(folder)
            opened, release = Event(), Event()
            connect = sqlite3.connect

            def pause_after_sqlite_creates_file(*args, **kwargs):
                db = connect(*args, **kwargs)
                if current_thread() is not main_thread():
                    opened.set()
                    if not release.wait(10):
                        db.close()
                        raise TimeoutError("CI did not release journal initialization")
                return db

            with patch("lightyear_workflow.run_store.sqlite3.connect", side_effect=pause_after_sqlite_creates_file):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(RunStore, directory)
                    try:
                        self.assertTrue(opened.wait(10))
                        reader = RunStore(directory, read_only=True)
                        self.assertEqual([], reader.events())
                        self.assertFalse((directory / "events.sqlite3").exists())
                    finally:
                        release.set()
                        writer = future.result(timeout=10)
                        cleanup.callback(writer.close)
            self.assertEqual([], reader.events())
            event = writer.append("fixture", {"committed": True})
            self.assertEqual([event], reader.events())
            writer.close()
            self.assertEqual([], list(directory.glob(".events-*")))

    def test_existing_journal_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            writer = RunStore(directory)
            event = writer.append("fixture", {"retained": True})
            writer.close()
            with patch("lightyear_workflow.run_store.os.replace", side_effect=AssertionError("Existing journal must not be replaced")):
                reopened = RunStore(directory)
                try:
                    self.assertEqual([event], reopened.events())
                finally:
                    reopened.close()

    def test_failed_publication_leaves_no_visible_database_and_releases_lease(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch("lightyear_workflow.run_store.os.replace", side_effect=OSError("CI publication failure")):
                with self.assertRaises(OSError):
                    RunStore(directory)
            self.assertFalse((directory / "events.sqlite3").exists())
            self.assertEqual([], list(directory.glob(".events-*")))
            writer = RunStore(directory)
            writer.close()

    def test_readers_still_refuse_existing_missing_schema_and_corrupt_journals(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            path = directory / "events.sqlite3"
            for raw in (b"", b"not a SQLite journal"):
                path.write_bytes(raw)
                with self.assertRaises(sqlite3.Error):
                    RunStore(directory, read_only=True).events()
                self.assertEqual(raw, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
