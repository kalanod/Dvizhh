"""Verify automatic database preparation on disposable containers."""

import json
import subprocess
import time
import unittest
from uuid import uuid4


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


class StartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = "dvizh-init-test-" + uuid4().hex
        self.containers = []
        docker("network", "create", self.network)
        self.addCleanup(self.cleanup)
        self.source = self.start_database("postgres")

    def start_database(self, alias: str) -> str:
        name = self.network + "-" + alias
        docker(
            "run", "--detach", "--rm", "--pull", "never", "--name", name,
            "--network", self.network, "--network-alias", alias,
            "--tmpfs", "/var/lib/postgresql/data",
            "--env", "POSTGRES_USER=startup", "--env", "POSTGRES_PASSWORD=startup",
            "--env", "POSTGRES_DB=startup_test", "--env", "RECSYS_READER_PASSWORD=reader",
            "dvizh-" + alias,
        )
        self.containers.append(name)
        for _attempt in range(100):
            ready = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "startup"],
                capture_output=True, check=False,
            )
            if ready.returncode == 0:
                return name
            time.sleep(0.2)
        raise RuntimeError(docker("logs", name))

    def cleanup(self) -> None:
        for name in reversed(self.containers):
            subprocess.run(["docker", "stop", name], capture_output=True, check=False)
        subprocess.run(["docker", "network", "rm", self.network], capture_output=True, check=False)

    def sql(self, container: str, sql: str) -> str:
        return docker(
            "exec", container, "psql", "-X", "-U", "startup", "-d", "startup_test",
            "-At", "-v", "ON_ERROR_STOP=1", "-c", sql,
        )

    def prepare_source(self) -> None:
        docker(
            "run", "--rm", "--pull", "never", "--network", self.network,
            "--env", "POSTGRES_USER=startup", "--env", "POSTGRES_PASSWORD=startup",
            "--env", "POSTGRES_DB=startup_test", "--env", "RECSYS_READER_PASSWORD=reader",
            "dvizh-database-init",
        )

    def prepare_vector(self) -> None:
        docker(
            "run", "--rm", "--pull", "never", "--network", self.network,
            "--env", "PGHOST=pgvector", "--env", "PGUSER=startup",
            "--env", "PGPASSWORD=startup", "--env", "PGDATABASE=startup_test",
            "--entrypoint", "psql", "dvizh-pgvector-init", "-X", "--single-transaction",
            "--set=ON_ERROR_STOP=1", "--file=/docker-entrypoint-initdb.d/01-vector.sql",
        )

    def assert_source_ready(self) -> None:
        self.assertEqual(self.sql(
            self.source, "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'dvizh_auth')",
        ), "t")
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
        connection = docker(
            "exec", "--env", "PGPASSWORD=reader", self.source, "psql", "-X",
            "-h", "127.0.0.1", "-U", "recsys_reader", "-d", "startup_test", "-Atc",
            "SELECT value FROM startup_probe",
        )
        self.assertEqual(connection, "preserved")

    def assert_vector_ready(self) -> None:
        self.assertEqual(self.sql(self.vector, "SELECT value FROM startup_probe"), "preserved")
        self.assertEqual(self.sql(
            self.vector,
            "SELECT to_regclass('public.event_embeddings') IS NOT NULL "
            "AND to_regclass('public.embedding_index_versions') IS NOT NULL "
            "AND to_regclass('public.user_embeddings') IS NOT NULL "
            "AND to_regclass('public.recommendation_pages') IS NOT NULL",
        ), "t")

    def test_fresh_upgrade_and_repeated_preparation_preserve_data(self) -> None:
        create_probe = (
            "CREATE TABLE startup_probe (value text); "
            "INSERT INTO startup_probe VALUES ('preserved')"
        )
        self.sql(self.source, create_probe)
        with self.subTest("source preparation without pgvector"):
            self.prepare_source()
            self.assert_source_ready()
        self.vector = self.start_database("pgvector")
        self.sql(self.vector, create_probe)
        self.sql(self.source, "DROP OWNED BY recsys_reader; DROP ROLE recsys_reader")
        self.sql(
            self.vector,
            "DROP TABLE event_embeddings, user_embeddings, embedding_index_versions, "
            "recommendation_pages",
        )
        with self.subTest("existing databases without reader role or vector schema"):
            self.prepare_source()
            self.prepare_vector()
            self.assert_source_ready()
            self.assert_vector_ready()
        with self.subTest("repeated startup"):
            self.prepare_source()
            self.prepare_vector()
            self.assert_source_ready()
            self.assert_vector_ready()


if __name__ == "__main__":
    unittest.main(verbosity=2)
