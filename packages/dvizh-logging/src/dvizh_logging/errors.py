import errno
import socket
from pathlib import PurePath
from traceback import walk_tb
from urllib.error import HTTPError, URLError

_SOURCE_ROOTS = {
    "dvizh_auth": "auth-api/src",
    "dvizh_backend": "backend/src",
    "dvizh_recommendation": "recommendation-service/src",
}

_NETWORK_ERRORS = {
    errno.ECONNREFUSED: "Connection refused by the dependency",
    errno.ECONNRESET: "Connection reset by the dependency",
    errno.EHOSTUNREACH: "Dependency host is unreachable",
    errno.ENETUNREACH: "Dependency network is unreachable",
    errno.ETIMEDOUT: "Connection timed out",
}


def _error_reason(error: BaseException) -> str | None:
    visited: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in visited and len(visited) < 8:
        visited.add(id(current))
        if isinstance(current, HTTPError):
            return f"Dependency returned HTTP {current.code}"
        if isinstance(current, socket.gaierror):
            return "Could not resolve the dependency address"
        if isinstance(current, TimeoutError):
            return "The operation exceeded its timeout"
        if isinstance(current, OSError) and current.errno in _NETWORK_ERRORS:
            return _NETWORK_ERRORS[current.errno]
        if isinstance(current, ConnectionRefusedError):
            return _NETWORK_ERRORS[errno.ECONNREFUSED]
        if isinstance(current, URLError) and isinstance(current.reason, BaseException):
            current = current.reason
        else:
            current = current.__cause__ or (
                current.__context__ if not current.__suppress_context__ else None
            )
    if type(error).__module__ == "redis.exceptions":
        if type(error).__name__ == "ConnectionError":
            return "Redis connection failed"
        if type(error).__name__ == "TimeoutError":
            return "Redis did not respond before the timeout"
    if isinstance(error, KeyError):
        return "The operation accessed a missing key"
    if isinstance(error, IndexError):
        return "The operation accessed an index outside the sequence"
    return None


def error_fields(error: BaseException) -> dict[str, object]:
    stack = []
    location = None
    for frame, line in walk_tb(error.__traceback__):
        filename = PurePath(frame.f_code.co_filename)
        function = frame.f_code.co_name
        file = str(filename)
        module = frame.f_globals.get("__package__") or frame.f_globals.get("__name__", "")
        package = module.split(".", 1)[0]
        if package in _SOURCE_ROOTS and package in filename.parts:
            source_path = filename.parts[filename.parts.index(package) :]
            file = f"{_SOURCE_ROOTS[package]}/{'/'.join(source_path)}"
            location = (file, line, function)
        stack.append({"file": file, "line": line, "function": function})

    fields: dict[str, object] = {
        "error_type": type(error).__name__,
        "error_stack": stack[-32:],
    }
    reason = _error_reason(error)
    if reason is not None:
        fields["error_reason"] = reason
    if location is not None:
        file, line, function = location
        fields.update(
            error_location=f"{file}:{line} ({function})",
            error_file=file,
            error_line=line,
            error_function=function,
        )
    return fields
