from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING, Literal

from pydantic import JsonValue

from .recommendations import FeatureSnapshot

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping


type FeatureType = Literal["number", "category", "optional-number"]

FEATURE_VERSION = "catalog-v1"
HNSW_FEATURE_VERSION = "catalog-hnsw-v1"
FEATURE_SCHEMA: dict[str, FeatureType] = {
    "hours_until_start": "number",
    "hours_since_publication": "number",
    "participants_count": "number",
    "price_type": "category",
    "format": "category",
    "join_policy": "category",
}
_SCORE_SOURCES = {
    FEATURE_VERSION: (),
    HNSW_FEATURE_VERSION: ("hnsw",),
}
FEATURE_SCHEMAS: dict[str, dict[str, FeatureType]] = {
    version: {**FEATURE_SCHEMA, **{f"{source}_score": "optional-number" for source in sources}}
    for version, sources in _SCORE_SOURCES.items()
}


def catalog_feature_snapshot(
    row: RowMapping,
    as_of: datetime,
    algorithm_version: str,
    *,
    feature_version: str = FEATURE_VERSION,
    source_scores: Mapping[str, float] | None = None,
) -> FeatureSnapshot:
    publication = row["published_at"] or row["created_at"]
    features: dict[str, JsonValue] = {
        "hours_until_start": (row["starts_at"] - as_of).total_seconds() / 3600,
        "hours_since_publication": (as_of - publication).total_seconds() / 3600,
        "participants_count": row["participants_count"],
        "price_type": row["price_type"],
        "format": row["format"],
        "join_policy": row["join_policy"],
    }
    scores = source_scores or {}
    for source in _SCORE_SOURCES[feature_version]:
        features[f"{source}_score"] = scores.get(source)
    return FeatureSnapshot(
        occurrence_id=row["occurrence_id"],
        feature_version=feature_version,
        features=features,
        calculated_at=as_of,
        algorithm_version=algorithm_version,
    )


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
        expected = schema[name]
        if expected == "optional-number":
            if value is None:
                encoded[f"{name}=missing"] = 1.0
                continue
            expected = "number"
        if feature_type(value) != expected:
            raise ValueError(f"Wrong type for ranking feature {name}")
        if isinstance(value, str):
            encoded[f"{name}={value}"] = 1.0
        else:
            number = float(value)
            if not isfinite(number):
                raise ValueError(f"Non-finite ranking feature {name}")
            encoded[name] = number
    return encoded
