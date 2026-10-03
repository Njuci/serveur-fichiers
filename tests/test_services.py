"""Tests des services indépendants du framework (stdlib uniquement).

Lancer :  python -m unittest tests.test_services -v
"""

import asyncio
import io
import tempfile
import unittest
from pathlib import Path

from app import config
from app.services import storage
from app.services.login_guard import LoginGuard
from app.services.notifier import ConnectionManager


class AsyncBytes:
    """Imite UploadFile.read() pour les tests."""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)


class StorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._saved = (config.STORAGE_DIR, config.META_FILE, config.DATA_DIR)
        config.STORAGE_DIR = root / "storage"
        config.DATA_DIR = root / "data"
        config.META_FILE = config.DATA_DIR / "files_meta.json"

    def tearDown(self):
        config.STORAGE_DIR, config.META_FILE, config.DATA_DIR = self._saved
        self._tmp.cleanup()

    async def test_upload_list_owner_delete(self):
        name = await storage.save_file("rapport.pdf", "alice", AsyncBytes(b"abc"), 100)
        self.assertEqual(name, "rapport.pdf")
        files = storage.list_files()
        self.assertEqual([(f["name"], f["size"], f["owner"]) for f in files],
                         [("rapport.pdf", 3, "alice")])
        self.assertEqual(storage.get_owner("rapport.pdf"), "alice")
        storage.delete_file("rapport.pdf")
        self.assertEqual(storage.list_files(), [])
        self.assertIsNone(storage.get_owner("rapport.pdf"))

    async def test_path_traversal_in_upload_name_is_neutralised(self):
        for evil in ["../../etc/passwd", "..\\..\\windows\\win.ini", "/etc/shadow"]:
            name = await storage.save_file(evil, "alice", AsyncBytes(b"x"), 100)
            self.assertNotIn("/", name)
            self.assertNotIn("\\", name)
            self.assertTrue((config.STORAGE_DIR / name).is_file())
        # rien n'a été écrit en dehors du dossier de stockage
        self.assertEqual(
            sorted(p.name for p in Path(self._tmp.name).iterdir()), ["data", "storage"]
        )

    async def test_dangerous_names_rejected(self):
        for bad in ["", None, "..", ".", "...", "   ", "a" * 300]:
            with self.assertRaises(storage.InvalidFilename, msg=repr(bad)):
                await storage.save_file(bad, "alice", AsyncBytes(b"x"), 100)

    async def test_leading_dots_are_stripped_not_rejected(self):
        # un fichier caché ne peut pas être créé : ".htaccess" devient "htaccess"
        name = await storage.save_file(".htaccess", "alice", AsyncBytes(b"x"), 100)
        self.assertEqual(name, "htaccess")

    async def test_names_from_url_must_be_clean(self):
        await storage.save_file("ok.txt", "alice", AsyncBytes(b"x"), 100)
        for bad in ["../ok.txt", "a/../ok.txt", "..", "ok.txt ", "/etc/passwd", "a\\b"]:
            with self.assertRaises(storage.InvalidFilename, msg=bad):
                storage.get_path(bad)
            with self.assertRaises(storage.InvalidFilename, msg=bad):
                storage.delete_file(bad)

    async def test_symlink_pointing_outside_is_refused(self):
        outside = Path(self._tmp.name) / "secret.txt"
        outside.write_text("secret")
        config.STORAGE_DIR.mkdir(parents=True)
        (config.STORAGE_DIR / "lien.txt").symlink_to(outside)
        with self.assertRaises(storage.InvalidFilename):
            storage.get_path("lien.txt")
        self.assertEqual(storage.list_files(), [])

    async def test_duplicate_is_refused_and_original_kept(self):
        await storage.save_file("a.txt", "alice", AsyncBytes(b"1"), 100)
        with self.assertRaises(storage.FileAlreadyExists):
            await storage.save_file("a.txt", "bob", AsyncBytes(b"2"), 100)
        self.assertEqual((config.STORAGE_DIR / "a.txt").read_bytes(), b"1")
        self.assertEqual(storage.get_owner("a.txt"), "alice")

    async def test_too_large_is_refused_and_leaves_no_trace(self):
        with self.assertRaises(storage.FileTooLarge):
            await storage.save_file("gros.bin", "alice", AsyncBytes(b"x" * 101), 100)
        self.assertEqual(list(config.STORAGE_DIR.iterdir()), [])

    async def test_missing_file(self):
        with self.assertRaises(storage.FileNotFound):
            storage.get_path("absent.txt")
        with self.assertRaises(storage.FileNotFound):
            storage.delete_file("absent.txt")


class FakeSocket:
    def __init__(self, fail=False):
        self.fail = fail
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, message):
        if self.fail:
            raise RuntimeError("connexion fermée")
        self.sent.append(message)


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_reaches_everyone_and_drops_dead_clients(self):
        manager = ConnectionManager()
        a, b, dead = FakeSocket(), FakeSocket(), FakeSocket(fail=True)
        for ws in (a, b, dead):
            await manager.connect(ws)
        self.assertTrue(a.accepted)
        self.assertEqual(manager.count, 3)

        await manager.broadcast({"event": "uploaded", "file": "é.pdf", "user": "alice"})

        self.assertEqual(a.sent, b.sent)
        self.assertEqual(
            a.sent, ['{"event": "uploaded", "file": "é.pdf", "user": "alice"}']
        )
        self.assertEqual(manager.count, 2)

    async def test_disconnect_is_idempotent(self):
        manager = ConnectionManager()
        ws = FakeSocket()
        await manager.connect(ws)
        manager.disconnect(ws)
        manager.disconnect(ws)
        self.assertEqual(manager.count, 0)


class LoginGuardTests(unittest.TestCase):
    def test_blocks_after_max_failures_then_recovers(self):
        now = [0.0]
        guard = LoginGuard(max_failures=3, window_seconds=60, clock=lambda: now[0])
        for _ in range(3):
            self.assertFalse(guard.is_blocked("ip|alice"))
            guard.register_failure("ip|alice")
        self.assertTrue(guard.is_blocked("ip|alice"))
        self.assertFalse(guard.is_blocked("ip|bob"))
        now[0] = 61
        self.assertFalse(guard.is_blocked("ip|alice"))

    def test_reset_clears_failures(self):
        guard = LoginGuard(max_failures=2, window_seconds=60)
        guard.register_failure("k")
        guard.register_failure("k")
        self.assertTrue(guard.is_blocked("k"))
        guard.reset("k")
        self.assertFalse(guard.is_blocked("k"))


if __name__ == "__main__":
    unittest.main()
