import argparse
import hashlib
import os
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import torch
from torch import Tensor
from torch.nn.functional import cross_entropy

from .embedding_encoder import ItemEncoderInput, register_encoder
from .encoder_data import HISTORY_LIMIT, EncoderDataset
from .two_tower import MODEL_KIND, TwoTower, encode_features, save_two_tower

_BATCH_SIZE = 128
_TEMPERATURE = 0.1
_LEARNING_RATE = 0.003
_RECALL_K = 10
_SEED = 42


@dataclass(frozen=True)
class TrainingExample:
    history: tuple[ItemEncoderInput, ...]
    target: ItemEncoderInput


def _split_examples(
    dataset: EncoderDataset, validation_start: datetime,
) -> tuple[list[TrainingExample], list[TrainingExample]]:
    train: list[TrainingExample] = []
    validation: list[TrainingExample] = []
    items = {item.item_id: item for item in dataset.items}
    histories: dict[UUID, deque[ItemEncoderInput]] = defaultdict(
        lambda: deque(maxlen=HISTORY_LIMIT),
    )
    registrations = sorted(dataset.registrations, key=lambda row: row.confirmed_at)
    for confirmed_at, records in groupby(registrations, key=lambda row: row.confirmed_at):
        batch = tuple(records)
        examples = train if confirmed_at < validation_start else validation
        for record in batch:
            history = histories[record.user_id]
            if history:
                examples.append(TrainingExample(tuple(history), items[record.item_id]))
        for record in batch:
            histories[record.user_id].append(items[record.item_id])
    return train, validation


def _exclude_history(
    scores: Tensor, batch: Sequence[TrainingExample], columns: dict[UUID, int],
) -> Tensor:
    mask = torch.zeros_like(scores, dtype=torch.bool)
    for row, example in enumerate(batch):
        previous = [
            columns[item.item_id]
            for item in example.history
            if item.item_id != example.target.item_id and item.item_id in columns
        ]
        if previous:
            mask[row, previous] = True
    return scores.masked_fill(mask, -torch.inf)


def _train_epoch(
    model: TwoTower, optimizer: torch.optim.Optimizer, examples: Sequence[TrainingExample],
    generator: torch.Generator,
) -> float:
    total_loss = 0.0
    seen = 0
    order = torch.randperm(len(examples), generator=generator).tolist()
    for offset in range(0, len(examples), _BATCH_SIZE):
        batch = [examples[i] for i in order[offset:offset + _BATCH_SIZE]]
        candidates = list({example.target.item_id: example.target for example in batch}.values())
        if len(candidates) < 2:
            continue
        columns = {item.item_id: index for index, item in enumerate(candidates)}
        users = model.users(encode_features([example.history for example in batch]))
        items = model.items(encode_features([(item,) for item in candidates]))
        scores = users @ items.T / _TEMPERATURE
        if not torch.isfinite(scores).all():
            raise ValueError("Two-Tower training diverged")
        scores = _exclude_history(scores, batch, columns)
        usable = torch.isfinite(scores).sum(dim=1) > 1
        if not usable.any():
            continue
        target = torch.tensor([columns[example.target.item_id] for example in batch])[usable]
        loss = cross_entropy(scores[usable], target)
        if not torch.isfinite(loss):
            raise ValueError("Two-Tower training diverged")
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(target)
        seen += len(target)
    if not seen:
        raise ValueError("No training example had an unobserved item in its batch")
    return total_loss / seen


@torch.inference_mode()
def _validation_recall(
    model: TwoTower, examples: Sequence[TrainingExample], catalogue: Sequence[ItemEncoderInput],
) -> float:
    hits = 0
    columns = {item.item_id: index for index, item in enumerate(catalogue)}
    items = torch.cat([
        model.items(encode_features([(item,) for item in catalogue[offset:offset + _BATCH_SIZE]]))
        for offset in range(0, len(catalogue), _BATCH_SIZE)
    ])
    for offset in range(0, len(examples), _BATCH_SIZE):
        batch = examples[offset:offset + _BATCH_SIZE]
        users = model.users(encode_features([example.history for example in batch]))
        scores = _exclude_history(users @ items.T, batch, columns)
        nearest = scores.topk(min(_RECALL_K, len(catalogue)), dim=1).indices
        targets = torch.tensor([columns[example.target.item_id] for example in batch])
        hits += (nearest == targets[:, None]).any(dim=1).sum().item()
    return hits / len(examples)


def train_and_register_encoder(
    dataset: Path, *, validation_start: datetime, experiment: str, name: str,
    git_sha: str, epochs: int = 8,
) -> str:
    if epochs < 1:
        raise ValueError("At least one epoch is required")
    payload = dataset.read_bytes()
    data = EncoderDataset.model_validate_json(payload)
    if validation_start.utcoffset() is None or not data.start < validation_start < data.as_of:
        raise ValueError("Require start < validation-start < as-of with a time zone")
    training, validation = _split_examples(data, validation_start)
    if len({example.target.item_id for example in training}) < 2 or not validation:
        raise ValueError("Require two distinct training targets and a validation example")

    generator = torch.Generator().manual_seed(_SEED)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(_SEED)
        model = TwoTower()
    optimizer = torch.optim.Adam(model.parameters(), lr=_LEARNING_RATE)
    for _ in range(epochs):
        loss = _train_epoch(model, optimizer, training, generator)
    metrics = {
        "train_loss": loss,
        "validation_recall_at_10": _validation_recall(model.eval(), validation, data.items),
    }
    with TemporaryDirectory() as path:
        directory = Path(path)
        save_two_tower(model, directory)
        return register_encoder(
            directory,
            experiment=experiment,
            name=name,
            tags={
                "dataset_version": hashlib.sha256(payload).hexdigest(),
                "git_sha": git_sha,
            },
            metrics=metrics,
            params={
                "algorithm": MODEL_KIND,
                "epochs": epochs,
                "seed": _SEED,
                "validation_start": validation_start.isoformat(),
                "train_examples": len(training),
                "validation_examples": len(validation),
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--validation-start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--epochs", type=int, default=8)
    args = parser.parse_args()
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        parser.error("MLFLOW_TRACKING_URI is required")
    print(train_and_register_encoder(
        args.dataset, validation_start=args.validation_start, experiment=args.experiment,
        name=args.model, git_sha=args.git_sha, epochs=args.epochs,
    ))


if __name__ == "__main__":
    main()
