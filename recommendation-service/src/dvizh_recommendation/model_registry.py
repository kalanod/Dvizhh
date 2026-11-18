import asyncio
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, FiniteFloat, JsonValue

from .candidates import FEATURE_SCHEMA, FEATURE_VERSION

MODEL_FILE = "ranker.json"
type FeatureType = Literal["number", "category"]


def feature_type(value: JsonValue) -> FeatureType:
    if isinstance(value, str):
        return "category"
    if type(value) in {int, float}:
        return "number"
    raise ValueError("Ranking features must be numbers or strings")


def encode_features(
    features: Mapping[str, JsonValue], schema: Mapping[str, FeatureType]
) -> dict[str, float]:
    if features.keys() != schema.keys():
        raise ValueError("Ranking features do not match the model schema")
    encoded = {}
    for name, value in features.items():
        if feature_type(value) != schema[name]:
            raise ValueError(f"Wrong type for ranking feature {name}")
        if isinstance(value, str):
            encoded[f"{name}={value}"] = 1.0
        else:
            number = float(value)
            if not isfinite(number):
                raise ValueError(f"Non-finite ranking feature {name}")
            encoded[name] = number
    return encoded


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
    if model.feature_version != FEATURE_VERSION or model.feature_schema != FEATURE_SCHEMA:
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
