"""Verify automatic database preparation on disposable containers."""

import json
import subprocess
import time
import unittest
from uuid import uuid4


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


class StartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = "dvizh-init-test-" + uuid4().hex
        self.containers = []
        docker("network", "create", self.network)
        self.addCleanup(self.cleanup)
        for alias, image in (("postgres", "dvizh-postgres"), ("pgvector", "dvizh-pgvector")):
            name = self.network + "-" + alias
            docker(
                "run", "--detach", "--rm", "--pull", "never", "--name", name,
                "--network", self.network, "--network-alias", alias,
                "--env", "POSTGRES_USER=startup", "--env", "POSTGRES_PASSWORD=startup",
                "--env", "POSTGRES_DB=startup_test", "--env", "RECSYS_READER_PASSWORD=reader",
                image,
            )
            self.containers.append(name)
            for _attempt in range(100):
                ready = subprocess.run(
                    ["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "startup"],
                    capture_output=True,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError(docker("logs", name))
        self.source, self.vector = self.containers

    def cleanup(self) -> None:
        for name in reversed(self.containers):
            subprocess.run(["docker", "stop", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", self.network], capture_output=True)

    def sql(self, container: str, sql: str) -> str:
        return docker(
            "exec", container, "psql", "-X", "-U", "startup", "-d", "startup_test",
            "-At", "-v", "ON_ERROR_STOP=1", "-c", sql,
        )

    def prepare(self) -> None:
        output = docker(
            "run", "--rm", "--pull", "never", "--network", self.network,
            "--env", "POSTGRES_USER=startup", "--env", "POSTGRES_PASSWORD=startup",
            "--env", "POSTGRES_DB=startup_test", "--env", "RECSYS_READER_PASSWORD=reader",
            "--env", "VECTOR_USER=startup", "--env", "VECTOR_PASSWORD=startup",
            "--env", "VECTOR_DB=startup_test", "dvizh-database-init",
        )
        self.assertIn("Database preparation complete.", output)

    def assert_ready(self) -> None:
        role = json.loads(self.sql(
            self.source,
            "SELECT json_build_object('login', rolcanlogin, 'superuser', rolsuper) "
            "FROM pg_roles WHERE rolname = 'recsys_reader'",
        ))
        self.assertEqual(role, {"login": True, "superuser": False})
        self.assertEqual(self.sql(
            self.source,
            "SELECT has_table_privilege('recsys_reader', 'startup_probe', 'SELECT') "
            "AND NOT has_table_privilege('recsys_reader', 'startup_probe', 'INSERT')",
        ), "t")
        self.assertEqual(self.sql(self.source, "SELECT value FROM startup_probe"), "preserved")
        self.assertEqual(self.sql(self.vector, "SELECT value FROM startup_probe"), "preserved")
        self.assertEqual(self.sql(
            self.vector,
            "SELECT to_regclass('public.event_embeddings') IS NOT NULL "
            "AND to_regclass('public.indexer_state') IS NOT NULL",
        ), "t")
        connection = docker(
            "exec", "--env", "PGPASSWORD=reader", self.source, "psql", "-X",
            "-h", "127.0.0.1", "-U", "recsys_reader", "-d", "startup_test", "-Atc",
            "SELECT value FROM startup_probe",
        )
        self.assertEqual(connection, "preserved")

    def test_fresh_upgrade_and_repeated_preparation_preserve_data(self) -> None:
        for container in self.containers:
            self.sql(
                container,
                "CREATE TABLE startup_probe (value text); "
                "INSERT INTO startup_probe VALUES ('preserved')",
            )
        with self.subTest("fresh databases"):
            self.prepare()
            self.assert_ready()
        self.sql(self.source, "DROP OWNED BY recsys_reader; DROP ROLE recsys_reader")
        self.sql(self.vector, "DROP TABLE event_embeddings; DROP TABLE indexer_state")
        with self.subTest("existing databases without reader role or vector schema"):
            self.prepare()
            self.assert_ready()
        with self.subTest("repeated startup"):
            self.prepare()
            self.assert_ready()


if __name__ == "__main__":
    unittest.main(verbosity=2)
