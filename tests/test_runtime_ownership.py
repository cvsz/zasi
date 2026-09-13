from __future__ import annotations

import socket
import unittest
from pathlib import Path

from backend.runtime import RuntimeOwnershipError, bind_runtime_socket


class RuntimeOwnershipTests(unittest.TestCase):
    def test_listener_owns_configured_endpoint(self) -> None:
        listener = bind_runtime_socket("127.0.0.1", 0)
        try:
            host, port = listener.getsockname()[:2]
            self.assertEqual(host, "127.0.0.1")
            self.assertGreater(port, 0)
            with socket.create_connection((host, port), timeout=1):
                pass
        finally:
            listener.close()

    def test_duplicate_runtime_ownership_fails_closed(self) -> None:
        owner = bind_runtime_socket("127.0.0.1", 0)
        try:
            host, port = owner.getsockname()[:2]
            with self.assertRaisesRegex(RuntimeOwnershipError, "already owned"):
                bind_runtime_socket(host, port)
        finally:
            owner.close()

    def test_container_uses_authoritative_runtime_launcher(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn('CMD ["python3", "-m", "backend.runtime"]', dockerfile)
        self.assertNotIn('CMD ["uvicorn", "backend.app:create_app"', dockerfile)


if __name__ == "__main__":
    unittest.main()
