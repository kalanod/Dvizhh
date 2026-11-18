import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from .retrieval import EmbeddingSpace

ENCODER_FILE = "encoder.json"


@dataclass(frozen=True)
class ItemEncoderInput:
    item_id: UUID
    title: str
    description: str
    topic_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class UserEncoderInput:
    user_id: UUID
    history: tuple[ItemEncoderInput, ...]


class EmbeddingEncoder(Protocol):
    @property
    def space(self) -> EmbeddingSpace: ...

    def encode_items(self, items: Sequence[ItemEncoderInput]) -> Sequence[Sequence[float]]: ...

    def encode_users(self, users: Sequence[UserEncoderInput]) -> Sequence[Sequence[float]]: ...


def write_artifact(output: Path, payload: bytes) -> None:
    with TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory) / output.name
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, output)
        directory_fd = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


class _EncoderKind(BaseModel, hide_input_in_errors=True):
    kind: str


def _adapter(kind: str) -> tuple[Callable[[Path, str], EmbeddingEncoder], tuple[str, ...]]:
    if kind == "two-tower-v1":
        from .two_tower import WEIGHTS_FILE, load_two_tower

        return load_two_tower, (WEIGHTS_FILE,)
    raise ValueError("Unsupported embedding encoder kind")


def _validate_model_uri(uri: str) -> None:
    if re.fullmatch(r"models:/[^/@\s]+/[1-9][0-9]*", uri) is None:
        raise ValueError("Use an exact MLflow model URI: models:/<name>/<version>")


def load_encoder(uri: str) -> EmbeddingEncoder:
    from mlflow.artifacts import download_artifacts

    _validate_model_uri(uri)
    with TemporaryDirectory() as directory:
        manifest = Path(
            download_artifacts(artifact_uri=f"{uri}/{ENCODER_FILE}", dst_path=directory)
        )
        kind = _EncoderKind.model_validate_json(manifest.read_bytes()).kind
        loader, files = _adapter(kind)
        for filename in files:
            download_artifacts(artifact_uri=f"{uri}/{filename}", dst_path=directory)
        return loader(Path(directory), uri)


def register_encoder(
    directory: Path,
    *,
    experiment: str,
    name: str,
    tags: Mapping[str, str],
    metrics: Mapping[str, float],
    params: Mapping[str, object],
) -> str:
    import mlflow
    from mlflow.exceptions import MlflowException

    _validate_model_uri(f"models:/{name}/1")
    kind = _EncoderKind.model_validate_json((directory / ENCODER_FILE).read_bytes()).kind
    _, files = _adapter(kind)
    artifacts = [directory / filename for filename in (ENCODER_FILE, *files)]
    if not all(artifact.is_file() for artifact in artifacts):
        raise ValueError("Embedding encoder artifact is incomplete")

    mlflow.set_experiment(experiment)
    client = mlflow.MlflowClient()
    try:
        client.create_registered_model(name)
    except MlflowException as error:
        if error.error_code != "RESOURCE_ALREADY_EXISTS":
            raise

    model_tags = {**tags, "encoder_kind": kind}
    with mlflow.start_run(tags=model_tags) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for artifact in artifacts:
            mlflow.log_artifact(str(artifact), artifact_path="encoder")
        version = client.create_model_version(
            name, mlflow.get_artifact_uri("encoder"), run_id=run.info.run_id, tags=model_tags,
        )
    return f"models:/{version.name}/{version.version}"
