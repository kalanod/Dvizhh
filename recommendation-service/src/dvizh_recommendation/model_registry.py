import asyncio
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, FiniteFloat, JsonValue

from .features import FEATURE_SCHEMAS, FeatureType, encode_features

MODEL_FILE = "ranker.json"


class LinearModel(BaseModel, extra="forbid", frozen=True, hide_input_in_errors=True):
    kind: Literal["logistic-regression"] = "logistic-regression"
    feature_version: str
    feature_schema: dict[str, FeatureType]
    weights: dict[str, FiniteFloat]
    intercept: FiniteFloat


class PreparedRanker(BaseModel, extra="forbid", frozen=True, hide_input_in_errors=True):
    uri: str
    model: LinearModel


def ranker_artifact_path(uri: str, directory: Path) -> Path:
    if re.fullmatch(r"models:/[^/@\s]+/[1-9][0-9]*", uri) is None:
        raise ValueError("Use an exact MLflow model URI: models:/<name>/<version>")
    return directory / f"{sha256(uri.encode()).hexdigest()}.json"


def validate_ranker_features(model: LinearModel) -> None:
    if model.feature_schema != FEATURE_SCHEMAS.get(model.feature_version):
        raise ValueError("Ranker inputs are incompatible with catalog features")


class LinearRanker:
    def __init__(self, version: str, model: LinearModel) -> None:
        self.version = version
        self.feature_version = model.feature_version
        self.feature_schema = model.feature_schema
        self.model = model

    async def score(self, items: Sequence[Mapping[str, JsonValue]]) -> list[float]:
        return [
            self.model.intercept
            + sum(
                value * self.model.weights.get(key, 0.0)
                for key, value in encode_features(features, self.feature_schema).items()
            )
            for features in items
        ]


def _load_ranker(uri: str, directory: Path) -> LinearRanker:
    artifact = ranker_artifact_path(uri, directory)
    try:
        prepared = PreparedRanker.model_validate_json(artifact.read_bytes())
    except FileNotFoundError as exc:
        raise ValueError(f"Ranker {uri} has not been prepared") from exc
    if prepared.uri != uri:
        raise ValueError("Prepared ranker URI does not match the requested version")
    validate_ranker_features(prepared.model)
    return LinearRanker(prepared.uri, prepared.model)


async def load_ranker(uri: str, directory: Path) -> LinearRanker:
    return await asyncio.to_thread(_load_ranker, uri, directory)
