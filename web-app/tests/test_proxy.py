"""Build and test the isolated nginx -> web-app -> backend proxy chain."""

import http.client
import json
import subprocess
import sys
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import uuid4


def docker(*args: str) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


class Backend(BaseHTTPRequestHandler):
    posts = 0

    def do_GET(self) -> None:
        self.respond({"status": "ok", "posts": Backend.posts, "path": self.path})

    def do_POST(self) -> None:
        size = len(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        Backend.posts += 1
        self.respond({"bytes": size, "path": self.path})

    def respond(self, value: dict) -> None:
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args: object) -> None:
        pass


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.containers = []
        cls.images = []
        cls.network = "dvizh-proxy-test-" + uuid4().hex
        cls.network_created = False
        cls.addClassCleanup(cls.cleanup)
        root = Path(__file__).resolve().parents[2]
        web_image = cls.network + "-web"
        edge_image = cls.network + "-edge"
        for name, context in ((web_image, "web-app"), (edge_image, "nginx")):
            print(f"Building isolated {context} test image...", flush=True)
            docker("build", "--tag", name, str(root / context))
            cls.images.append(name)
        docker("network", "create", cls.network)
        cls.network_created = True
        cls.start(
            "backend", "python:3.12-slim",
            [
                "--mount",
                f"type=bind,source={Path(__file__).resolve()},target=/test_proxy.py,readonly",
            ],
            ["python", "/test_proxy.py", "--backend"],
        )
        cls.ports = []
        for alias, image, port in (("web-app", web_image, 8002), ("edge", edge_image, 80)):
            name = cls.start(
                alias, image,
                ["--env", "MEDIA_MAX_MIB=1", "--publish", f"127.0.0.1::{port}"], [],
            )
            mapping = docker("port", name, f"{port}/tcp")
            if not mapping.startswith("127.0.0.1:") or "\n" in mapping:
                raise RuntimeError(f"Unexpected test port mapping: {mapping}")
            cls.ports.append(int(mapping.rsplit(":", 1)[1]))
        for port in cls.ports:
            for _attempt in range(75):
                try:
                    status, _body = cls.request(port, "GET", "/api/health")
                    if status == 200:
                        break
                except OSError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Isolated proxy chain did not become ready")

    @classmethod
    def start(cls, alias: str, image: str, options: list[str], command: list[str]) -> str:
        name = cls.network + "-" + alias
        docker(
            "run", "--detach", "--rm", "--pull", "never", "--name", name,
            "--network", cls.network, "--network-alias", alias, *options, image, *command,
        )
        cls.containers.append(name)
        return name

    @classmethod
    def cleanup(cls) -> None:
        for name in reversed(cls.containers):
            subprocess.run(["docker", "stop", name], capture_output=True)
        if cls.network_created:
            subprocess.run(["docker", "network", "rm", cls.network], capture_output=True)
        for image in cls.images:
            subprocess.run(["docker", "image", "rm", image], capture_output=True)

    @staticmethod
    def request(port: int, method: str, path: str, body=None, headers=None, *, chunked=False):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(method, path, body, headers or {}, encode_chunked=chunked)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def posts(self, port: int) -> int:
        status, body = self.request(port, "GET", "/api/received")
        self.assertEqual(status, 200)
        return json.loads(body)["posts"]

    def test_spa_routes_health_and_missing_assets(self) -> None:
        for port in self.ports:
            with self.subTest(port=port):
                status, index = self.request(port, "GET", "/")
                self.assertEqual(status, 200)
                self.assertIn(b'id="root"', index)
                self.assertEqual(self.request(port, "GET", "/events/example"), (200, index))
                self.assertEqual(self.request(port, "GET", "/health")[0], 200)
                self.assertEqual(self.request(port, "GET", "/assets/missing.js")[0], 404)

    def test_exact_limit_and_actor_query_reach_backend(self) -> None:
        for port in self.ports:
            with self.subTest(port=port):
                path = "/api/media?user_id=owner&filename=image.png"
                status, body = self.request(port, "POST", path, b"x" * (1024 * 1024))
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {"bytes": 1024 * 1024, "path": path})
                path = "/api/events/event?actor_id=owner&viewer_id=owner"
                self.assertEqual(json.loads(self.request(port, "GET", path)[1])["path"], path)

    def test_declared_overflow_never_reaches_backend(self) -> None:
        for port in self.ports:
            with self.subTest(port=port):
                before = self.posts(port)
                status, _body = self.request(port, "POST", "/api/media", b"x" * (1024 * 1024 + 1))
                self.assertEqual(status, 413)
                self.assertEqual(self.posts(port), before)

    def test_chunked_overflow_never_reaches_backend(self) -> None:
        for port in self.ports:
            with self.subTest(port=port):
                before = self.posts(port)
                status, _body = self.request(
                    port, "POST", "/api/media", [b"x" * 524288, b"x" * 524289], chunked=True
                )
                self.assertEqual(status, 413)
                self.assertEqual(self.posts(port), before)

    def test_invalid_content_length_never_reaches_backend(self) -> None:
        for port in self.ports:
            for length in ("-1", "bad"):
                with self.subTest(port=port, length=length):
                    before = self.posts(port)
                    status, _body = self.request(
                        port, "POST", "/api/media", b"x", {"Content-Length": length}
                    )
                    self.assertEqual(status, 400)
                    self.assertEqual(self.posts(port), before)


if __name__ == "__main__":
    if "--backend" in sys.argv:
        HTTPServer(("0.0.0.0", 8000), Backend).serve_forever()
    else:
        unittest.main(verbosity=2)
