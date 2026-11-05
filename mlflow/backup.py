"""Back up or restore the MLflow database and artifacts together."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
DATABASE_ENVIRONMENT = 'export PGPASSWORD="$POSTGRES_PASSWORD" PGCONNECT_TIMEOUT=10; '
STORAGE_ACCESS = """
set -eu
umask 077
printf '%s\n%s\n' mlflow "$MLFLOW_STORAGE_SECRET_KEY" |
    mc --config-dir /tmp/mlflow-backup alias set storage http://minio:9000 >/dev/null 2>&1
"""


class Compose:
    def __init__(self, environment_file: Path) -> None:
        self.command = [
            "docker", "compose", "--project-directory", str(ROOT),
            "--env-file", str(environment_file), "--profile", "ml",
        ]

    def run(
        self, *arguments: str, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None,
    ) -> str:
        try:
            result = subprocess.run(
                [*self.command, *arguments], stdin=stdin,
                stdout=stdout if stdout is not None else subprocess.PIPE,
                stderr=subprocess.PIPE, check=True,
            )
        except FileNotFoundError:
            raise RuntimeError("Docker is not installed or is unavailable.") from None
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"Docker Compose {arguments[0]} failed (exit {error.returncode})."
            ) from None
        return result.stdout.decode().strip() if result.stdout is not None else ""

    def running(self) -> bool:
        return bool(self.run("ps", "--status", "running", "--quiet", "mlflow"))

    def database(
        self, command: str, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None,
    ) -> None:
        self.run(
            "exec", "-T", "postgres", "sh", "-ec", DATABASE_ENVIRONMENT + command,
            stdin=stdin, stdout=stdout,
        )

    def artifacts(self, directory: Path, restore: bool = False) -> None:
        mount = str(directory) + ":/backup" + (":ro" if restore else ":rw")
        command = (
            "mirror --quiet --overwrite --remove /backup/artifacts storage/mlflow-artifacts"
            if restore else "mirror --quiet storage/mlflow-artifacts /backup/artifacts"
        )
        self.run(
            "run", "--rm", "-T", "--no-deps", "--volume", mount,
            "--user", f"{os.getuid()}:{os.getgid()}", "--entrypoint", "/bin/sh", "mlflow-init",
            "-ec", STORAGE_ACCESS + "mc --config-dir /tmp/mlflow-backup " + command,
        )


def checksums(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"Unsupported backup entry: {relative}")
        if path.is_file() and relative != "manifest.json":
            with path.open("rb") as source:
                result[relative] = hashlib.file_digest(source, "sha256").hexdigest()
    return result


def validate(directory: Path) -> None:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Backup must be a directory.")
    manifest = directory / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("Backup is incomplete: manifest.json is missing.")
    try:
        recorded = json.loads(manifest.read_text())
    except (ValueError, UnicodeError):
        raise ValueError("Backup manifest is invalid.") from None
    if (
        not isinstance(recorded, dict) or recorded.get("format") != 1
        or not isinstance(recorded.get("files"), dict)
        or not (directory / "metadata.dump").is_file()
        or (directory / "metadata.dump").stat().st_size == 0
        or not (directory / "artifacts").is_dir()
    ):
        raise ValueError("Backup is incomplete or has an unsupported format.")
    if recorded["files"] != checksums(directory):
        raise ValueError("Backup files are missing, changed, or unexpected.")


def backup(compose: Compose, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("Backup destination already exists; choose a new directory.")
    was_running = compose.running()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(mkdtemp(prefix=".mlflow-backup-", dir=destination.parent))
    try:
        if was_running:
            compose.run("stop", "mlflow")
        (temporary / "artifacts").mkdir()
        with (temporary / "metadata.dump").open("wb") as target:
            compose.database(
                'pg_dump --host=127.0.0.1 --username "$POSTGRES_USER" --no-password '
                "--dbname=mlflow --format=custom --no-owner --no-acl",
                stdout=target,
            )
        compose.artifacts(temporary)
        (temporary / "manifest.json").write_text(
            json.dumps({"format": 1, "files": checksums(temporary)}, indent=2) + "\n"
        )
        temporary.rename(destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        if was_running:
            compose.run("start", "mlflow")


def restore(compose: Compose, source: Path) -> None:
    validate(source)
    was_running = compose.running()
    compose.run("stop", "mlflow")
    compose.database(
        'dropdb --host=127.0.0.1 --username "$POSTGRES_USER" --no-password '
        "--if-exists --force mlflow; "
        'createdb --host=127.0.0.1 --username "$POSTGRES_USER" --no-password '
        "--owner=mlflow --template=template0 mlflow"
    )
    with (source / "metadata.dump").open("rb") as archive:
        compose.database(
            'pg_restore --host=127.0.0.1 --username "$POSTGRES_USER" --no-password '
            "--dbname=mlflow --role=mlflow --no-owner --no-acl --single-transaction",
            stdin=archive,
        )
    compose.artifacts(source, restore=True)
    if was_running:
        compose.run("start", "mlflow")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.production")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="Save the MLflow database and artifacts.").add_argument(
        "directory", type=Path,
    )
    commands.add_parser(
        "restore", help="Replace MLflow data with a trusted backup.",
    ).add_argument("directory", type=Path)
    arguments = parser.parse_args()
    os.umask(0o077)
    environment_file = arguments.env_file.expanduser().absolute()
    directory = arguments.directory.expanduser().absolute()
    try:
        if not environment_file.is_file():
            raise ValueError("Environment file does not exist.")
        with environment_file.open("rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another MLflow backup/restore is running.") from None
            compose = Compose(environment_file)
            if arguments.command == "backup":
                backup(compose, directory)
                print(f"MLflow backup saved to {directory}")
            else:
                restore(compose, directory)
                print("MLflow database and artifacts restored.")
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
