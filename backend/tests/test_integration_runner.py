"""The integration runner must never reuse or remove application resources."""

import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location(
    "backend_integration_runner",
    Path(__file__).resolve().parents[1] / "tests/run_integration.py",
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_runner_isolates_environment_and_cleans_up(monkeypatch):
    original = dict(os.environ)
    docker = Mock(side_effect=["database-id", "127.0.0.1:51001", "storage-id", "127.0.0.1:51002"])
    commands = Mock()
    cleanup = Mock()
    monkeypatch.setattr(runner, "docker", docker)
    monkeypatch.setattr(runner, "wait_ready", Mock())
    monkeypatch.setattr(runner, "python", commands)
    monkeypatch.setattr(runner.subprocess, "run", cleanup)
    runner.run("postgres-test", "minio-test")
    environment = commands.call_args_list[0].kwargs["environment"]
    assert environment["DATABASE_URL"] == environment["TEST_DATABASE_URL"]
    assert environment["DATABASE_URL"].endswith("@127.0.0.1:51001/dvizh_media_test")
    assert environment["TEST_MINIO_ENDPOINT"] == "127.0.0.1:51002"
    assert dict(os.environ) == original
    assert [call.args for call in commands.call_args_list[1:]] == [
        ("-m", "alembic", "upgrade", "head"), ("-m", "alembic", "check"),
        ("-m", "pytest", "-q"), ("-m", "ruff", "check", "src", "tests", "alembic"),
    ]
    names = [call.args[4] for call in [docker.call_args_list[0], docker.call_args_list[2]]]
    assert names[0].startswith("dvizh-backend-test-db-")
    assert names[1].startswith("dvizh-backend-test-store-")
    assert [call.args[0][-1] for call in cleanup.call_args_list] == list(reversed(names))


@pytest.mark.parametrize("stage", ["start", "port", "python"])
def test_failure_always_cleans_owned_containers(monkeypatch, stage):
    failure = subprocess.CalledProcessError(1, ["test-command"])
    effects = ["database-id", "127.0.0.1:51001", "storage-id", "127.0.0.1:51002"]
    if stage == "start":
        effects[2] = failure
    elif stage == "port":
        effects[3] = "0.0.0.0:51002"
    monkeypatch.setattr(runner, "docker", Mock(side_effect=effects))
    monkeypatch.setattr(runner, "wait_ready", Mock())
    monkeypatch.setattr(runner, "python", Mock(side_effect=failure))
    cleanup = Mock()
    monkeypatch.setattr(runner.subprocess, "run", cleanup)
    with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
        runner.run("postgres-test", "minio-test")
    assert cleanup.call_count == 2
    for call in cleanup.call_args_list:
        assert call.args[0][:3] == ["docker", "rm", "--force"]
        assert call.args[0][-1].startswith("dvizh-backend-test-")
