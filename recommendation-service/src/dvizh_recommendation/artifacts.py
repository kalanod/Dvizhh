import os
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory


def write_artifact(
    output: Path, payload: bytes, *, mode: int = 0o600,
    validate_existing: Callable[[Path], None] | None = None,
) -> None:
    with TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory) / output.name
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staging, output)
        except FileExistsError:
            if validate_existing is None:
                raise
            validate_existing(output)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
