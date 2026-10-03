"""Tests de l'API complète (routes, droits, WebSocket) avec le TestClient de FastAPI.

Prérequis :  pip install -r requirements-dev.txt
Lancer    :  python -m unittest tests.test_api -v
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "secret-de-test-" + "x" * 40)

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.auth import guard  # noqa: E402
from app.services import users  # noqa: E402


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._saved = (
            config.DATA_DIR, config.STORAGE_DIR, config.USERS_FILE,
            config.META_FILE, config.MAX_UPLOAD_BYTES,
        )
        config.DATA_DIR = root / "data"
        config.STORAGE_DIR = root / "storage"
        config.USERS_FILE = config.DATA_DIR / "users.json"
        config.META_FILE = config.DATA_DIR / "files_meta.json"
        config.MAX_UPLOAD_BYTES = 1024

        users.save_user("alice", "user", "motdepasse-alice")
        users.save_user("bob", "user", "motdepasse-bob")
        users.save_user("root", "admin", "motdepasse-root")
        guard._failures.clear()

        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        (config.DATA_DIR, config.STORAGE_DIR, config.USERS_FILE,
         config.META_FILE, config.MAX_UPLOAD_BYTES) = self._saved
        self._tmp.cleanup()

    # --- aides ---------------------------------------------------------------

    def token(self, username):
        response = self.client.post(
            "/login", json={"username": username, "password": f"motdepasse-{username}"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]

    def auth(self, username):
        return {"Authorization": f"Bearer {self.token(username)}"}

    def upload(self, username, name="a.txt", content=b"hello"):
        return self.client.post(
            "/files", headers=self.auth(username), files={"file": (name, content)}
        )

    # --- /login --------------------------------------------------------------

    def test_login_success_returns_token_and_role(self):
        response = self.client.post(
            "/login", json={"username": "root", "password": "motdepasse-root"}
        )
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual((body["username"], body["role"]), ("root", "admin"))
        self.assertGreater(body["expires_in"], 0)

    def test_login_trims_username_without_trimming_password(self):
        response = self.client.post(
            "/login",
            json={"username": "  alice  ", "password": "motdepasse-alice"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["username"], "alice")

    def test_login_wrong_password_and_unknown_user_look_identical(self):
        wrong = self.client.post("/login", json={"username": "alice", "password": "non"})
        unknown = self.client.post("/login", json={"username": "zoe", "password": "non"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_login_is_rate_limited(self):
        for _ in range(config.LOGIN_MAX_FAILURES):
            self.client.post("/login", json={"username": "alice", "password": "non"})
        response = self.client.post(
            "/login", json={"username": "alice", "password": "motdepasse-alice"}
        )
        self.assertEqual(response.status_code, 429)

    def test_user_management_is_admin_only(self):
        response = self.client.get("/users", headers=self.auth("alice"))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/users",
            headers=self.auth("alice"),
            json={"username": "new-user", "password": "motdepasse-new", "role": "user"},
        )
        self.assertEqual(response.status_code, 403)

    # --- authentification des routes ----------------------------------------

    def test_routes_require_a_valid_token(self):
        self.assertEqual(self.client.get("/files").status_code, 401)
        self.assertEqual(
            self.client.get("/files", headers={"Authorization": "Bearer nimporte"}).status_code,
            401,
        )
        self.assertEqual(self.client.get("/files/a.txt").status_code, 401)
        self.assertEqual(self.client.delete("/files/a.txt").status_code, 401)
        self.assertEqual(
            self.client.post("/files", files={"file": ("a.txt", b"x")}).status_code, 401
        )

    # --- fichiers ------------------------------------------------------------

    def test_upload_list_download(self):
        response = self.upload("alice", "rapport.txt", b"contenu")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["name"], "rapport.txt")
        self.assertEqual(response.json()["owner"], "alice")

        listing = self.client.get("/files", headers=self.auth("bob")).json()
        self.assertEqual([(f["name"], f["size"], f["owner"]) for f in listing],
                         [("rapport.txt", 7, "alice")])

        download = self.client.get("/files/rapport.txt", headers=self.auth("bob"))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"contenu")
        self.assertIn("attachment", download.headers["content-disposition"])

    def test_duplicate_name_is_409(self):
        self.assertEqual(self.upload("alice").status_code, 201)
        self.assertEqual(self.upload("bob").status_code, 409)

    def test_too_large_is_413(self):
        self.assertEqual(self.upload("alice", content=b"x" * 2048).status_code, 413)
        self.assertEqual(self.client.get("/files", headers=self.auth("alice")).json(), [])

    def test_path_traversal_is_neutralised(self):
        response = self.upload("alice", "../../evil.txt")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "evil.txt")
        self.assertTrue((config.STORAGE_DIR / "evil.txt").is_file())
        self.assertFalse((config.STORAGE_DIR.parent.parent / "evil.txt").exists())

        for evil in ["..%2F..%2Fetc%2Fpasswd", "%2E%2E", "a%5Cb"]:
            response = self.client.get(f"/files/{evil}", headers=self.auth("alice"))
            self.assertIn(response.status_code, (400, 404), evil)

    def test_download_unknown_file_is_404(self):
        response = self.client.get("/files/absent.txt", headers=self.auth("alice"))
        self.assertEqual(response.status_code, 404)

    def test_delete_rules(self):
        self.upload("alice", "alice.txt")
        self.upload("bob", "bob.txt")

        # bob ne peut pas supprimer le fichier d'alice
        response = self.client.delete("/files/alice.txt", headers=self.auth("bob"))
        self.assertEqual(response.status_code, 403)
        # le propriétaire peut
        response = self.client.delete("/files/alice.txt", headers=self.auth("alice"))
        self.assertEqual(response.status_code, 204)
        # l'administrateur peut supprimer le fichier d'un autre
        response = self.client.delete("/files/bob.txt", headers=self.auth("root"))
        self.assertEqual(response.status_code, 204)
        # fichier inexistant
        response = self.client.delete("/files/bob.txt", headers=self.auth("root"))
        self.assertEqual(response.status_code, 404)

    def test_file_without_known_owner_is_admin_only(self):
        config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        (config.STORAGE_DIR / "orphelin.txt").write_text("x")
        self.assertEqual(
            self.client.delete("/files/orphelin.txt", headers=self.auth("alice")).status_code, 403
        )
        self.assertEqual(
            self.client.delete("/files/orphelin.txt", headers=self.auth("root")).status_code, 204
        )

    # --- WebSocket -----------------------------------------------------------

    def test_websocket_rejects_missing_or_bad_token(self):
        for url in ("/ws", "/ws?token=faux"):
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect(url):
                    pass

    def test_websocket_receives_upload_and_delete_events(self):
        bob_token = self.token("bob")
        with self.client.websocket_connect(f"/ws?token={bob_token}") as socket:
            self.upload("alice", "a.txt")
            self.assertEqual(
                socket.receive_json(),
                {"event": "uploaded", "file": "a.txt", "user": "alice"},
            )
            self.client.delete("/files/a.txt", headers=self.auth("alice"))
            self.assertEqual(
                socket.receive_json(),
                {"event": "deleted", "file": "a.txt", "user": "alice"},
            )

    # --- page client ---------------------------------------------------------

    def test_index_page_and_security_headers(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
