import asyncio
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import asyncpg
import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc
from redis.exceptions import ConnectionError

from dvizh_recommendation.config import Settings
from dvizh_recommendation.database import Databases
from dvizh_recommendation.main import running_server
from dvizh_recommendation.service import SERVICE_NAME


@pytest.mark.parametrize("failure", ["connection", "timeout"])
@pytest.mark.parametrize("dependency", ["redis", "source", "vector"])
def test_health_tracks_failure_and_recovery_of_each_required_dependency(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    dependency: str,
    failure: str,
) -> None:
    monkeypatch.setattr("dvizh_recommendation.main.HEALTH_CHECK_INTERVAL_SECONDS", 0.01)
    caplog.set_level(logging.INFO, logger="dvizh_recommendation.main")

    class Dependency:
        def __init__(self, error):
            self.error = error
            self.mode = "healthy"
            self.entered = asyncio.Event()
            self.rechecked = asyncio.Event()
            self.failed_checks = 0
            self.active = 0

        async def check(self, *args, **kwargs):
            self.active += 1
            try:
                if self.mode != "healthy":
                    self.failed_checks += 1
                    if self.failed_checks == 2:
                        self.rechecked.set()
                if self.mode == "connection":
                    raise self.error("Dependency unavailable")
                if self.mode == "timeout":
                    self.entered.set()
                    await asyncio.Event().wait()
                return 1
            finally:
                self.active -= 1

    async def run():
        dependencies = {
            "redis": Dependency(ConnectionError),
            "source": Dependency(asyncpg.PostgresConnectionError),
            "vector": Dependency(asyncpg.PostgresConnectionError),
        }

        @asynccontextmanager
        async def connect_databases(settings):
            yield Databases(
                source=SimpleNamespace(fetchval=dependencies["source"].check),
                vector=SimpleNamespace(fetchval=dependencies["vector"].check),
            )

        @asynccontextmanager
        async def connect_redis(settings):
            yield SimpleNamespace(ping=dependencies["redis"].check, register_script=Mock())

        monkeypatch.setattr("dvizh_recommendation.main.connect_databases", connect_databases)
        monkeypatch.setattr("dvizh_recommendation.main.connect_redis", connect_redis)
        settings = Settings(
            grpc_bind_address="127.0.0.1:0",
            source_database_url="postgresql://source.invalid/source",
            vector_database_url="postgresql://vector.invalid/vector",
            redis_url="redis://redis.invalid/0",
            redis_timeout_seconds=0.1,
            database_timeout_seconds=0.1,
            shutdown_grace_seconds=0.1,
            _env_file=None,
        )
        async with (
            running_server(settings) as (_, port),
            grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel,
        ):
            client = health_pb2_grpc.HealthStub(channel)
            requests = [
                health_pb2.HealthCheckRequest(service=service) for service in ("", SERVICE_NAME)
            ]
            watches = [client.Watch(request) for request in requests]

            async def expect_status(status):
                responses = await asyncio.wait_for(
                    asyncio.gather(*(watch.read() for watch in watches)), timeout=2
                )
                assert all(response.status == status for response in responses)
                responses = await asyncio.gather(
                    *(client.Check(request, timeout=2) for request in requests)
                )
                assert all(response.status == status for response in responses)

            try:
                await expect_status(health_pb2.HealthCheckResponse.SERVING)
                dependencies[dependency].mode = failure
                await expect_status(health_pb2.HealthCheckResponse.NOT_SERVING)
                await asyncio.wait_for(dependencies[dependency].rechecked.wait(), timeout=2)
                dependencies[dependency].mode = "healthy"
                await expect_status(health_pb2.HealthCheckResponse.SERVING)
                name = {"redis": "redis", "source": "postgres", "vector": "pgvector"}[dependency]
                transitions = [
                    (record.getMessage(), record.dependency)
                    for record in caplog.records
                    if record.name == "dvizh_recommendation.main"
                ]
                assert transitions == [
                    ("Dependency unavailable", name),
                    ("Dependency recovered", name),
                ]
                dependencies[dependency].entered.clear()
                dependencies[dependency].mode = "timeout"
                await asyncio.wait_for(dependencies[dependency].entered.wait(), timeout=2)
            finally:
                for watch in watches:
                    watch.cancel()

        assert all(dependency.active == 0 for dependency in dependencies.values())

    asyncio.run(run())
