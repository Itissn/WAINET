import tempfile
from pathlib import Path
import unittest

from server import Store, validate_observation
from test_server import payload
from storage_ops import copy_database, verify, ROOT


class RecoveryTests(unittest.TestCase):
    def test_backup_and_restore_preserve_evidence_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            source = path / "live.sqlite3"
            store = Store(source)
            record = validate_observation(payload(feelings="Recovery fixture"))
            store.insert(record)
            backup = path / "backup.sqlite3"
            restored = path / "restored.sqlite3"
            self.assertEqual(copy_database(source, backup)["observations"], 1)
            self.assertEqual(copy_database(backup, restored)["integrity"], "ok")
            with Store(restored).connect() as db:
                saved = db.execute("SELECT image,feelings FROM observations").fetchone()
                self.assertEqual(saved["image"], record["image"])
                self.assertEqual(saved["feelings"], "Recovery fixture")
            with self.assertRaises(FileExistsError):
                copy_database(source, restored)
            self.assertEqual(verify(restored)["observations"], 1)
            with self.assertRaises(ValueError):
                copy_database(source, ROOT / "docs" / "private.sqlite3")

    def test_missing_or_invalid_database_does_not_create_a_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "missing.sqlite3"
            target = Path(directory) / "backup.sqlite3"
            with self.assertRaises(FileNotFoundError):
                copy_database(source, target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
