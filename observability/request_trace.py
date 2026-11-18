"""Return correlated request logs and a Tempo trace as JSON."""

import argparse
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_LIMIT = 500
_ERROR_FIELDS = (
    "service",
    "operation",
    "status",
    "dependency",
    "error_type",
    "error_reason",
    "error_location",
    "error_file",
    "error_line",
    "error_function",
    "message",
    "upstream",
    "upstream_status",
    "trace_id",
    "span_id",
)


def _json_get(url: str, token: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=10) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def _request_data(url: str, token: str, request_id: str, hours: int) -> dict:
    selector = '{service_name=~".+"} | json | request_id=' + json.dumps(request_id)
    params = urlencode(
        {
            "query": selector,
            "start": time.time_ns() - hours * 3_600_000_000_000,
            "limit": _LIMIT,
            "direction": "forward",
        }
    )
    loki = f"{url}/api/datasources/proxy/uid/dvizh-loki"
    streams = _json_get(f"{loki}/loki/api/v1/query_range?{params}", token)["data"]["result"]
    entries = (entry for stream in streams for entry in stream["values"])
    logs = [json.loads(line) for _, line in sorted(entries, key=lambda entry: int(entry[0]))]
    failures = [
        record
        for record in logs
        if record.get("error_type")
        or record.get("error_reason")
        or record.get("level") in {"ERROR", "CRITICAL"}
    ]
    trace_ids = list(
        dict.fromkeys(
            record["trace_id"]
            for record in logs
            if re.fullmatch("[0-9a-f]{32}", record.get("trace_id", ""))
        )
    )
    trace_id = next(
        (
            record["trace_id"]
            for record in reversed(failures)
            if record.get("trace_id") in trace_ids
        ),
        trace_ids[-1] if trace_ids else None,
    )
    trace = None
    trace_error = None
    if trace_id:
        try:
            tempo = f"{url}/api/datasources/proxy/uid/dvizh-tempo"
            trace = _json_get(f"{tempo}/api/traces/{trace_id}", token)
        except HTTPError as exc:
            trace_error = {"status": exc.code}
        except (URLError, TimeoutError):
            trace_error = {"error": "tempo_unavailable"}
        except ValueError:
            trace_error = {"error": "tempo_invalid_response"}

    return {
        "request_id": request_id,
        "errors": [
            {key: record[key] for key in _ERROR_FIELDS if key in record} for record in failures
        ],
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "trace": trace,
        "trace_error": trace_error,
        "logs": logs,
        "limit_reached": len(logs) == _LIMIT,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_id")
    parser.add_argument("--hours", type=int, default=1)
    args = parser.parse_args()
    token = os.getenv("GRAFANA_TOKEN")
    if not token:
        parser.error("GRAFANA_TOKEN is required")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", args.request_id):
        parser.error("invalid request_id")
    if not 1 <= args.hours <= 336:
        parser.error("--hours must be between 1 and 336")
    url = os.getenv("GRAFANA_URL", "http://127.0.0.1:3000").rstrip("/")
    try:
        result = _request_data(url, token, args.request_id, args.hours)
    except HTTPError as exc:
        print(json.dumps({"error": "grafana_http_error", "status": exc.code}))
        raise SystemExit(1) from None
    except (URLError, TimeoutError):
        print(json.dumps({"error": "grafana_unavailable"}))
        raise SystemExit(1) from None
    except (ValueError, KeyError, TypeError):
        print(json.dumps({"error": "grafana_invalid_response"}))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
