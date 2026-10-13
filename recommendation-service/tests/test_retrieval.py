from uuid import UUID

import pytest
from pydantic import ValidationError

from dvizh_recommendation.retrieval import Embedding, EmbeddingSpace, ScoredItem

SPACE = EmbeddingSpace(model_id="test-model", dimension=2, metric="cosine")


@pytest.mark.parametrize("values", [(1.0,), (float("nan"), 1.0), (float("inf"), 1.0), (0.0, 0.0)])
def test_invalid_embeddings_are_rejected(values: tuple[float, ...]) -> None:
    with pytest.raises(ValidationError):
        Embedding(space=SPACE, values=values)


@pytest.mark.parametrize("score", [float("nan"), float("inf")])
def test_non_finite_retrieval_scores_are_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        ScoredItem(item_id=UUID(int=1), retrieval_score=score)
