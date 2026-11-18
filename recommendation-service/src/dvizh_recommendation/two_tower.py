import hashlib
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Literal

import torch
from pydantic import BaseModel, Field
from safetensors.torch import load_file, save_file
from torch import Tensor, nn
from torch.nn.functional import normalize

from .embedding_encoder import ENCODER_FILE, ItemEncoderInput, UserEncoderInput
from .retrieval import EmbeddingSpace

WEIGHTS_FILE = "weights.safetensors"
MODEL_KIND = "two-tower-v1"
_FEATURE_COUNT = 2048
_HIDDEN_SIZE = 128
_DIMENSION = 384
_ENCODING_BATCH_SIZE = 128
_TOKENS = re.compile(r"[^\W_]+")


class TwoTowerManifest(BaseModel, extra="forbid", frozen=True):
    kind: Literal["two-tower-v1"] = MODEL_KIND
    weights_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@lru_cache(maxsize=4096)
def _feature_buckets(item: ItemEncoderInput) -> tuple[int, ...]:
    features = {f"word:{text}" for text in _TOKENS.findall(
        f"{item.title} {item.description}".casefold(),
    )}
    features.update(f"topic:{topic_id}" for topic_id in item.topic_ids)
    return tuple(sorted({
        int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little")
        % _FEATURE_COUNT
        for feature in features
    }))


def encode_features(groups: Sequence[Sequence[ItemEncoderInput]]) -> Tensor:
    result = torch.zeros((len(groups), _FEATURE_COUNT), dtype=torch.float32)
    for row, items in enumerate(groups):
        for item in items:
            buckets = _feature_buckets(item)
            if buckets:
                result[row, list(buckets)] += 1.0 / len(buckets)
    return normalize(result)


def _tower() -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(_FEATURE_COUNT, _HIDDEN_SIZE),
        nn.ReLU(),
        nn.Linear(_HIDDEN_SIZE, _DIMENSION),
    )


class TwoTower(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.user_tower = _tower()
        self.item_tower = _tower()

    def users(self, features: Tensor) -> Tensor:
        return normalize(self.user_tower(features))

    def items(self, features: Tensor) -> Tensor:
        return normalize(self.item_tower(features))


class TwoTowerEncoder:
    def __init__(self, model: TwoTower, model_id: str) -> None:
        self.space = EmbeddingSpace(model_id=model_id, dimension=_DIMENSION, metric="cosine")
        self.model = model.eval()

    @torch.inference_mode()
    def encode_items(self, items: Sequence[ItemEncoderInput]) -> list[list[float]]:
        return [
            row
            for offset in range(0, len(items), _ENCODING_BATCH_SIZE)
            for row in self.model.items(encode_features([
                (item,) for item in items[offset:offset + _ENCODING_BATCH_SIZE]
            ])).tolist()
        ]

    @torch.inference_mode()
    def encode_users(self, users: Sequence[UserEncoderInput]) -> list[list[float]]:
        return [
            row
            for offset in range(0, len(users), _ENCODING_BATCH_SIZE)
            for row in self.model.users(encode_features([
                user.history for user in users[offset:offset + _ENCODING_BATCH_SIZE]
            ])).tolist()
        ]


def save_two_tower(model: TwoTower, directory: Path) -> None:
    weights = directory / WEIGHTS_FILE
    save_file(model.state_dict(), weights)
    manifest = TwoTowerManifest(weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest())
    (directory / ENCODER_FILE).write_text(manifest.model_dump_json() + "\n", encoding="utf-8")


def load_two_tower(directory: Path, model_id: str) -> TwoTowerEncoder:
    manifest = TwoTowerManifest.model_validate_json((directory / ENCODER_FILE).read_bytes())
    weights = directory / WEIGHTS_FILE
    if hashlib.sha256(weights.read_bytes()).hexdigest() != manifest.weights_sha256:
        raise ValueError("Two-Tower weights checksum mismatch")
    tensors = load_file(weights, device="cpu")
    if any(
        tensor.dtype != torch.float32 or not torch.isfinite(tensor).all()
        for tensor in tensors.values()
    ):
        raise ValueError("Two-Tower weights must be finite float32 tensors")
    with torch.random.fork_rng(devices=[]):
        model = TwoTower()
    model.load_state_dict(tensors)
    return TwoTowerEncoder(model, model_id)
