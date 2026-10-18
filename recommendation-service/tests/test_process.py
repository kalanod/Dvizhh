from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import grpc
import pytest

if TYPE_CHECKING:
    from conftest import IntegrationDatabases


pytestmark = pytest.mark.integration


def test_server_process_passes_healthcheck_and_exits_cleanly_on_sigterm(
    integration_databases: IntegrationDatabases,
) -> None:
    service_dir = Path(__file__).resolve().parents[1]
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    address = f"127.0.0.1:{port}"
    environment = {
        **os.environ,
        "GRPC_BIND_ADDRESS": address,
        "SOURCE_DATABASE_URL": integration_databases.source_url,
        "VECTOR_DATABASE_URL": integration_databases.vector_url,
        "DATABASE_TIMEOUT_SECONDS": "2",
        "SHUTDOWN_GRACE_SECONDS": "1",
    }
    healthcheck_command = [sys.executable, "-m", "dvizh_recommendation.healthcheck"]

    process = subprocess.Popen(
        [sys.executable, "-m", "dvizh_recommendation.main"],
        cwd=service_dir,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=10)

        healthcheck = subprocess.run(
            healthcheck_command,
            cwd=service_dir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert healthcheck.returncode == 0, healthcheck.stdout + healthcheck.stderr

        process.terminate()
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 0, output
        assert (
            subprocess.run(
                healthcheck_command, cwd=service_dir, env=environment, timeout=5
            ).returncode
            == 1
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
