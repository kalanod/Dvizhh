import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from .features import encode_features, feature_type
from .model_registry import MODEL_FILE, LinearModel


class Example(BaseModel):
    split: Literal["train", "validation", "test"]
    features: dict[str, JsonValue]
    label: Literal[0, 1]


class TrainingConfig(BaseModel, extra="forbid", frozen=True):
    inverse_regularization: float = Field(default=1.0, gt=0, allow_inf_nan=False)


def fit_ranker(
    dataset: Path, config: TrainingConfig | None = None
) -> tuple[LinearModel, str, dict[str, float]]:
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss

    config = config or TrainingConfig()
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    dataset_version = manifest.pop("dataset_version")
    if hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest() != dataset_version:
        raise ValueError("Dataset manifest checksum mismatch")
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported dataset schema")

    data = {"train": [], "validation": [], "test": []}
    checksum = hashlib.sha256()
    with (dataset / "examples.jsonl").open("rb") as stream:
        for line in stream:
            checksum.update(line)
            example = Example.model_validate_json(line)
            data[example.split].append(example)
    if checksum.hexdigest() != manifest["examples_sha256"]:
        raise ValueError("Dataset examples checksum mismatch")
    if any(not examples for examples in data.values()):
        raise ValueError("Train, validation and test splits must all contain examples")
    if {row.label for row in data["train"]} != {0, 1}:
        raise ValueError("The training split must contain both booking outcomes")

    schema = {name: feature_type(value) for name, value in data["train"][0].features.items()}
    vectorizer = DictVectorizer()
    inputs = {
        split: [encode_features(row.features, schema) for row in rows]
        for split, rows in data.items()
    }
    matrix = vectorizer.fit_transform(inputs["train"])
    estimator = LogisticRegression(C=config.inverse_regularization, max_iter=1000).fit(
        matrix, [row.label for row in data["train"]]
    )
    metrics = {
        f"{split}_log_loss": float(
            log_loss(
                [row.label for row in data[split]],
                estimator.predict_proba(vectorizer.transform(inputs[split])),
                labels=[0, 1],
            )
        )
        for split in ("validation", "test")
    }
    model = LinearModel(
        feature_version=manifest["feature_version"],
        feature_schema=schema,
        weights=dict(zip(vectorizer.get_feature_names_out(), estimator.coef_[0], strict=True)),
        intercept=estimator.intercept_[0],
    )
    return model, dataset_version, metrics


def train_and_register(
    dataset: Path,
    experiment: str,
    name: str,
    git_sha: str,
    config: TrainingConfig | None = None,
) -> str:
    import mlflow
    from mlflow.exceptions import MlflowException

    config = config or TrainingConfig()
    model, dataset_version, metrics = fit_ranker(dataset, config)
    mlflow.set_experiment(experiment)
    client = mlflow.MlflowClient()
    try:
        client.create_registered_model(name)
    except MlflowException as error:
        if error.error_code != "RESOURCE_ALREADY_EXISTS":
            raise
    tags = {
        "dataset_version": dataset_version,
        "feature_version": model.feature_version,
        "git_sha": git_sha,
    }
    with mlflow.start_run(tags=tags) as run:
        mlflow.log_param("algorithm", model.kind)
        mlflow.log_params(config.model_dump())
        mlflow.log_metrics(metrics)
        mlflow.log_dict(model.model_dump(mode="json"), f"ranker/{MODEL_FILE}")
        version = client.create_model_version(
            name,
            mlflow.get_artifact_uri("ranker"),
            run_id=run.info.run_id,
            tags=tags,
        )
    return f"models:/{version.name}/{version.version}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        parser.error("MLFLOW_TRACKING_URI is required")
    config = TrainingConfig.model_validate_json(args.config.read_bytes()) if args.config else None
    print(train_and_register(args.dataset, args.experiment, args.model, args.git_sha, config))


if __name__ == "__main__":
    main()
