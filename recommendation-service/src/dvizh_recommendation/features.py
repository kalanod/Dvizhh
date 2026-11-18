from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING, Literal

from pydantic import JsonValue

from .recommendations import FeatureSnapshot

if TYPE_CHECKING:
    from asyncpg import Record


type FeatureType = Literal["number", "category"]

FEATURE_VERSION = "catalog-v1"
FEATURE_SCHEMA: dict[str, FeatureType] = {
    "hours_until_start": "number",
    "hours_since_publication": "number",
    "participants_count": "number",
    "price_type": "category",
    "format": "category",
    "join_policy": "category",
}


def catalog_feature_snapshot(
    row: Record, as_of: datetime, algorithm_version: str
) -> FeatureSnapshot:
    publication = row["published_at"] or row["created_at"]
    return FeatureSnapshot(
        occurrence_id=row["occurrence_id"],
        feature_version=FEATURE_VERSION,
        features={
            "hours_until_start": (row["starts_at"] - as_of).total_seconds() / 3600,
            "hours_since_publication": (as_of - publication).total_seconds() / 3600,
            "participants_count": row["participants_count"],
            "price_type": row["price_type"],
            "format": row["format"],
            "join_policy": row["join_policy"],
        },
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
