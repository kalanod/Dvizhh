"""Run backend checks against disposable PostgreSQL and MinIO containers."""

import argparse
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


@contextmanager
def container(image: str, name: str, port: int, environment: dict[str, str], *command: str):
    arguments = ["run", "--detach", "--rm", "--name", name]
    for key, value in environment.items():
        arguments.extend(["--env", f"{key}={value}"])
    arguments.extend(["--publish", f"127.0.0.1::{port}", image, *command])
    try:
        docker(*arguments)
        mapping = docker("port", name, f"{port}/tcp")
        match = re.fullmatch(r"127\.0\.0\.1:(\d+)", mapping)
        if match is None:
            raise RuntimeError("Unexpected test container port mapping")
        yield int(match[1])
    finally:
        # The generated name belongs only to this invocation, including failed starts.
        subprocess.run(["docker", "rm", "--force", name], check=False, capture_output=True)


def wait_ready(database: str, storage_port: int) -> None:
    opener = build_opener(ProxyHandler({}))
    for _ in range(60):
        ready = subprocess.run(
            ["docker", "exec", database, "pg_isready", "-h", "127.0.0.1",
             "-U", "media_test", "-d", "dvizh_media_test"],
            capture_output=True,
        ).returncode == 0
        try:
            with opener.open(f"http://127.0.0.1:{storage_port}/minio/health/ready", timeout=1):
                if ready:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Test PostgreSQL and MinIO did not become ready")


def python(*args: str, environment: dict[str, str]) -> None:
    subprocess.run([sys.executable, *args], cwd=BACKEND, env=environment, check=True)


def run(postgres_image: str, minio_image: str) -> None:
    suffix = uuid4().hex
    database = f"dvizh-backend-test-db-{suffix}"
    storage = f"dvizh-backend-test-store-{suffix}"
    with (
        container(postgres_image, database, 5432, {
            "POSTGRES_DB": "dvizh_media_test", "POSTGRES_USER": "media_test",
            "POSTGRES_PASSWORD": "media-test-password",
            "RECSYS_READER_PASSWORD": "media-test-reader",
        }) as database_port,
        container(minio_image, storage, 9000, {
            "MINIO_ROOT_USER": "media_test", "MINIO_ROOT_PASSWORD": "media-test-password",
        }, "server", "/data", "--console-address", ":9873") as storage_port,
    ):
        wait_ready(database, storage_port)
        environment = dict(os.environ)
        environment["DATABASE_URL"] = (
            "postgresql+asyncpg://media_test:media-test-password"
            f"@127.0.0.1:{database_port}/dvizh_media_test"
        )
        environment["TEST_DATABASE_URL"] = environment["DATABASE_URL"]
        environment["TEST_MINIO_ENDPOINT"] = f"127.0.0.1:{storage_port}"
        environment["NO_PROXY"] = ",".join(filter(None, [
            environment.get("NO_PROXY"), "localhost", "127.0.0.1",
        ]))
        environment["no_proxy"] = environment["NO_PROXY"]
        python("-c", (
            "import os; from minio import Minio; "
            "client = Minio(os.environ['TEST_MINIO_ENDPOINT'], "
            "access_key='media_test', secret_key='media-test-password', secure=False); "
            "client.make_bucket('media-test')"
        ), environment=environment)
        for arguments in [
            ("-m", "alembic", "upgrade", "head"),
            ("-m", "alembic", "check"),
            ("-m", "pytest", "-q"),
            ("-m", "ruff", "check", "src", "tests", "alembic"),
        ]:
            python(*arguments, environment=environment)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-image", default="dvizh-postgres:latest")
    parser.add_argument("--minio-image", default="dvizh-minio:latest")
    arguments = parser.parse_args()
    run(arguments.postgres_image, arguments.minio_image)


if __name__ == "__main__":
    main()
