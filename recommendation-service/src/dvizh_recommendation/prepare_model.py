import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .config import DEFAULT_RANKER_MODEL_DIR
from .model_registry import (
    MODEL_FILE,
    LinearModel,
    PreparedRanker,
    ranker_artifact_path,
    validate_ranker_features,
)


def prepare_ranker(uri: str, directory: Path) -> Path:
    from mlflow.artifacts import download_artifacts

    destination = ranker_artifact_path(uri, directory)
    with TemporaryDirectory() as download_dir:
        artifact = Path(
            download_artifacts(artifact_uri=f"{uri}/{MODEL_FILE}", dst_path=download_dir)
        )
        model = LinearModel.model_validate_json(artifact.read_bytes())
    validate_ranker_features(model)
    prepared = PreparedRanker(uri=uri, model=model)

    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=directory) as staging_dir:
        staging = Path(staging_dir) / MODEL_FILE
        with staging.open("wb") as file:
            file.write(prepared.model_dump_json().encode())
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(staging, destination)
        except FileExistsError:
            existing = PreparedRanker.model_validate_json(destination.read_bytes())
            if existing != prepared:
                raise ValueError(f"Prepared ranker {uri} has different contents") from None
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("uri", help="Exact MLflow model URI: models:/<name>/<version>")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.environ.get("RANKER_MODEL_DIR", DEFAULT_RANKER_MODEL_DIR)),
    )
    args = parser.parse_args()
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        parser.error("MLFLOW_TRACKING_URI is required")
    print(prepare_ranker(args.uri, args.output_dir))


if __name__ == "__main__":
    main()
