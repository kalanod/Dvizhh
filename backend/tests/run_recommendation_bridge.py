"""Check recommendation attribution and failover on a disposable Compose project."""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http.cookiejar import CookieJar
from pathlib import Path
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
RECSYS = "recommendation-service"

def check_trace(grafana_url: str, request_id: str, trace_id: str, origin: dict) -> None:
    # The synthetic parent is not exported, so the collector can use its full 75-second wait.
    deadline = time.monotonic() + 95
    while True:
        response = subprocess.run(
            [sys.executable, str(ROOT / "observability/request_trace.py"), request_id],
            env={**os.environ, "GRAFANA_URL": grafana_url},
            capture_output=True,
            timeout=22,
            text=True,
        )
        data = json.loads(response.stdout)
        if response.returncode and data.get("status") in {401, 403}:
            raise AssertionError(data)
        logs = [row for row in data.get("logs", []) if row.get("trace_id") == trace_id]
        trace = data.get("trace") or {}
        spans_by_name = {
            span["name"]: span
            for batch in trace.get("batches", trace.get("resourceSpans", []))
            for scope in batch.get("scopeSpans", [])
            for span in scope["spans"]
        }
        http = spans_by_name.get("POST /api/events/discovery")
        client = spans_by_name.get("grpc GetRecommendations")
        server = spans_by_name.get("GetRecommendations")
        backend_log = any(row.get("service") == "backend" for row in logs)
        recsys_log = any(
            row.get("service") == RECSYS
            and row.get("session_id") == origin["session_id"]
            and row.get("recommendation_request_id") == origin["request_id"]
            for row in logs
        )
        if http and client and server and backend_log and recsys_log:
            assert client["parentSpanId"] == http["spanId"], (http, client)
            assert server["parentSpanId"] == client["spanId"], (client, server)
            break
        if time.monotonic() >= deadline:
            raise AssertionError({"spans": list(spans_by_name), "logs": logs,
                                  "trace_error": data.get("trace_error")})
        time.sleep(2)
    print("Grafana found Backend and RecSys by HTTP request ID and returned one linked trace.")


def run(command: list[str], *, observability: bool = False) -> None:
    def compose(*arguments: str, stdin: str | None = None) -> str:
        result = subprocess.run(
            [*command, *arguments], input=stdin, capture_output=True, text=True, timeout=90,
        )
        if result.returncode:
            raise RuntimeError(f"Compose {' '.join(arguments[:3])}: {result.stderr.strip()}")
        return result.stdout.strip()

    def address(service: str, port: str) -> str:
        mapping = compose("port", service, port)
        return f"http://127.0.0.1:{mapping.rsplit(':', 1)[1]}"

    def source_sql(statement: str) -> str:
        return compose(
            "exec", "-T", "postgres", "sh", "-ec",
            'psql -X -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -v ON_ERROR_STOP=1',
            stdin=statement,
        )

    url = address("nginx", "80")
    marker = f"bridge{uuid4().hex[:12]}"
    start = datetime.now(UTC)
    selected = (start + timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)

    def post(
        client, path: str, payload: dict, status: int = 200, actor: str | None = None,
        *, traced: tuple[str, str] | None = None,
    ):
        destination = address("backend", "8000") if traced else url
        request = Request(destination + path, json.dumps(payload).encode(), method="POST")
        request.add_header("Content-Type", "application/json")
        if traced:
            request_id, trace_id = traced
            request.add_header("X-Request-ID", request_id)
            request.add_header("traceparent", f"00-{trace_id}-{uuid4().hex[:16]}-01")
        if actor is not None:
            request.add_header("X-Dvizh-Account", "1")
            request.add_header("X-Dvizh-Account-Id", actor)
        try:
            response = client.open(request, timeout=8)
        except HTTPError as error:
            response = error
        with response:
            body = response.read()
            assert response.status == status, (path, response.status, body)
            if traced:
                assert response.headers["X-Request-ID"] == traced[0]
            return json.loads(body) if body else None

    def account(role: str):
        client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        username = f"{marker}_{role}"
        password = uuid4().hex
        user = post(client, "/api/auth/register", {"username": username, "password": password}, 201)
        post(client, "/api/auth/login", {"login": username, "password": password}, 204)
        post(client, "/api/users", {
            "id": user["id"], "username": username, "display_name": role,
        }, 201, user["id"])
        return client, user["id"]

    host, organizer = account("host")
    viewer, actor = account("viewer")

    def event(label: str, starts_at: datetime = selected) -> dict:
        return post(host, "/api/events", {
            "organizer_id": organizer, "title": f"{marker} {label}",
            "starts_at": starts_at.isoformat(), "timezone": "UTC", "format": "ONLINE",
            "online_url": "https://example.invalid/recommendation-bridge",
        }, 201, organizer)

    oldest, older, recent = event("oldest"), event("older"), event("recent")
    recommended = event("recurring", selected - timedelta(days=1))
    occurrence = source_sql(
        "INSERT INTO event_occurrences (event_id, starts_at, timezone) "
        f"VALUES ('{UUID(recommended['id'])}', '{selected.isoformat()}', 'UTC') RETURNING id;"
    )
    request = {
        "sort": "relevance", "include_map": False, "limit": 1,
        "filters": {"q": marker, "date_from": selected.date().isoformat(),
                    "date_to": selected.date().isoformat()},
    }
    discovery = "/api/events/discovery"
    # A sampled parent makes the healthy HTTP→gRPC trace deterministic.
    traced = (uuid4().hex, "0001" + uuid4().hex[4:]) if observability else None
    first = post(viewer, discovery, request, traced=traced)["feed"]
    assert "total_events" not in first and first["next_cursor"], first
    assert first["refresh_after_seconds"] > 0, first
    assert [(item["id"], item["occurrence_id"]) for item in first["items"]] == [
        (recommended["id"], occurrence),
    ], first
    origin = {key: str(UUID(first[key])) for key in ("session_id", "request_id")}

    def feedback(event_type: str) -> dict:
        return {"interaction_id": str(uuid4()), "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(), "item_id": recommended["id"], **origin}

    impression = feedback("IMPRESSION")
    accepted = post(viewer, "/api/interactions", {"interactions": [impression]}, actor=actor)
    assert accepted["accepted_interaction_ids"] == [impression["interaction_id"]], accepted
    signup = f"/api/events/{recommended['id']}/participants?occurrence_id={occurrence}"
    booking = post(viewer, signup, {"user_id": actor, "interaction": feedback("JOIN_CLICK")},
                   actor=actor)
    assert booking["status"] == "GOING", booking

    output = f"/tmp/{marker}"
    compose(
        "exec", "-T", RECSYS, "python", "-m", "dvizh_recommendation.dataset", output,
        "--start", (start - timedelta(minutes=1)).isoformat(),
        "--validation-start", (start + timedelta(days=2)).isoformat(),
        "--test-start", (start + timedelta(days=3)).isoformat(),
        "--as-of", (start + timedelta(days=4)).isoformat(),
        "--observation-hours", "24", "--feature-version", "catalog-v1",
    )
    exported = compose("exec", "-T", RECSYS, "cat", output + "/examples.jsonl")
    examples = map(json.loads, exported.splitlines())
    attributed = [row for row in examples if row["request_id"] == origin["request_id"]]
    assert len(attributed) == 1, attributed
    sample = attributed[0]
    assert sample["item_id"] == recommended["id"] and sample["label"] == 1, sample
    assert sample["features"]["format"] == "ONLINE", sample
    print("HTTP recommendation, selected occurrence and confirmed signup reached the dataset.")

    refresh = f"{discovery}/refresh"
    original_cursor = first["next_cursor"]
    post(host, refresh, {"cursor": original_cursor}, 409, organizer)
    post(viewer, refresh, {"cursor": "malformed"}, 409, actor)
    post(build_opener(ProxyHandler({})), refresh, {"cursor": original_cursor}, 401, actor)

    redis_key = "recsys:session:" + sha256(origin["session_id"].encode()).hexdigest()
    session_predicate = f"WHERE id = '{UUID(origin['session_id'])}'"

    shortened = 30
    time.sleep(1)
    source_sql(
        f"UPDATE discovery_sessions SET expires_at = now() + interval '{shortened} seconds' "
        f"{session_predicate};"
    )
    redis_cli = ("exec", "-T", "redis", "redis-cli")
    assert compose(*redis_cli, "EXPIRE", redis_key, str(shortened)) == "1"
    renewed_cursor = post(viewer, refresh, {"cursor": original_cursor}, actor=actor)["next_cursor"]
    assert renewed_cursor != original_cursor
    assert float(source_sql(
        "SELECT extract(epoch FROM (expires_at - now())) FROM discovery_sessions "
        f"{session_predicate};"
    )) > shortened
    assert int(compose(*redis_cli, "TTL", redis_key)) > shortened

    continuation = {**request, "cursor": renewed_cursor}
    post(host, discovery, continuation, 409)
    post(viewer, discovery, {**request, "cursor": "malformed"}, 409)
    barrier = Barrier(2, timeout=5)

    def next_page(cursor):
        barrier.wait()
        return post(viewer, discovery, {**continuation, "cursor": cursor})["feed"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(next_page, cursor) for cursor in (original_cursor, renewed_cursor)]
        page, repeated = (fetch.result() for fetch in requests)
    for response in (page, repeated):
        assert [item["id"] for item in response["items"]] == [recent["id"]], response
        assert response["session_id"] == origin["session_id"] and response["next_cursor"], response
        assert "total_events" not in response, response
    assert page["request_id"] == repeated["request_id"] != origin["request_id"], (page, repeated)
    print("Renewal extended both lifetimes, and both cursors read the same page and request ID.")

    continuation = {**request, "cursor": page["next_cursor"]}
    try:
        compose("stop", RECSYS)
        newest = event("new during outage")
        fallback_cursor = post(
            viewer, refresh, {"cursor": continuation["cursor"]}, actor=actor,
        )["next_cursor"]
        fallback = post(viewer, discovery, {**continuation, "cursor": fallback_cursor})["feed"]
        assert [item["id"] for item in fallback["items"]] == [newest["id"]], fallback
        assert "total_events" not in fallback and fallback["next_cursor"], fallback
        assert not fallback.get("session_id") and not fallback.get("request_id"), fallback
    finally:
        compose("start", RECSYS)

    for _ in range(30):
        try:
            compose("exec", "-T", RECSYS, "python", "-m", "dvizh_recommendation.healthcheck")
        except RuntimeError:
            time.sleep(1)
        else:
            break
    else:
        raise RuntimeError("RecSys did not recover after restart")

    replayed = post(viewer, discovery, continuation)["feed"]
    assert [item["id"] for item in replayed["items"]] == [newest["id"]], replayed
    assert "total_events" not in replayed and not replayed.get("request_id"), replayed
    for expected in (older, oldest):
        fallback = post(viewer, discovery, {**request, "cursor": fallback["next_cursor"]})["feed"]
        assert [item["id"] for item in fallback["items"]] == [expected["id"]], fallback
        assert not fallback.get("session_id") and not fallback.get("request_id"), fallback
    assert not fallback["next_cursor"], fallback
    assert "refresh_after_seconds" not in fallback, fallback
    print("The same HTTP feed continued without duplicates during outage and after recovery.")
    if traced:
        check_trace(address("grafana", "3000"), *traced, origin)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("-f", "--file", type=Path, action="append", default=[])
    parser.add_argument(
        "--observability", action="store_true",
        help="Check Grafana using GRAFANA_TOKEN and published Backend/Grafana ports",
    )
    args = parser.parse_args()
    if not args.project_name.startswith("dvizh-test-"):
        parser.error("Use an isolated Compose project named dvizh-test-*")
    if args.observability and not os.environ.get("GRAFANA_TOKEN"):
        parser.error("--observability requires a read-only GRAFANA_TOKEN")
    command = [
        "docker", "compose", "--project-name", args.project_name, "-f", str(ROOT / "compose.yaml"),
    ]
    if args.env_file:
        command.extend(["--env-file", str(args.env_file)])
    for file in args.file:
        command.extend(["-f", str(file)])
    run(command, observability=args.observability)


if __name__ == "__main__":
    main()
