import json
from collections.abc import Sequence

from .candidates import RecommendationPipeline, RetrievalScoreRanker
from .config import Settings
from .database import Databases
from .hnsw import HnswCandidates
from .model_registry import load_ranker
from .recommendations import BASELINE_VERSION, CandidateGenerator, Ranker


class PipelineFactory:
    def __init__(
        self, databases: Databases, settings: Settings, *,
        additional_generators: Sequence[tuple[CandidateGenerator, str]] = (),
    ) -> None:
        self.databases = databases
        self.settings = settings
        self._generators = tuple(generator for generator, _ in additional_generators)
        self._sources = [[generator.name, version] for generator, version in additional_generators]
        if any(not name or not version for name, version in self._sources):
            raise ValueError("Candidate generators require a name and a version")
        self._rankers: dict[tuple[str, str | None], Ranker | None] = {}

    def catalog(self) -> RecommendationPipeline:
        return RecommendationPipeline(self.databases.source, self.settings.database_timeout_seconds)

    def _version(self, base: str | list[str]) -> str:
        if self._sources:
            return json.dumps({"base": base, "sources": self._sources})
        return base if isinstance(base, str) else json.dumps(base)

    async def load(
        self, ranker_uri: str | None, model_id: str | None, revision: str | None,
    ) -> RecommendationPipeline:
        model_id = model_id or None
        ranker: Ranker | None = (
            await load_ranker(ranker_uri, self.settings.ranker_model_dir) if ranker_uri else None
        )
        version = ranker.version if ranker else BASELINE_VERSION
        if model_id and ranker is None:
            ranker = RetrievalScoreRanker(HnswCandidates.name)
        if self._sources:
            version = ranker.version if ranker else "source-order-v1"
        pipeline = await self._build(ranker, version, model_id, revision or None)
        if pipeline is None:
            raise ValueError("No compatible published HNSW index for the configured model")
        self._rankers[version, model_id] = ranker
        return pipeline

    async def restore(self, version: str) -> RecommendationPipeline | None:
        try:
            base = json.loads(version)
        except ValueError:
            base = version
        if self._sources:
            if not isinstance(base, dict) or base.get("sources") != self._sources:
                return None
            base = base.get("base")
        if isinstance(base, str):
            ranker_version, model_id, revision = base, None, None
        elif (
            isinstance(base, list) and len(base) in (2, 3)
            and all(isinstance(part, str) for part in base)
        ):
            ranker_version, model_id, *revisions = base
            revision = revisions[0] if revisions else model_id
        else:
            return None
        key = (ranker_version, model_id)
        if key not in self._rankers:
            return None
        return await self._build(self._rankers[key], ranker_version, model_id, revision, version)

    async def _build(
        self, ranker: Ranker | None, ranker_version: str, model_id: str | None,
        revision: str | None, session_version: str | None = None,
    ) -> RecommendationPipeline | None:
        generators = self._generators
        session_base: str | list[str] = ranker_version
        algorithm_base: str | list[str] = ranker.version if ranker else ranker_version
        if model_id:
            generator = HnswCandidates(self.databases.vector, model_id, revision)
            if not await generator.check_ready() or generator.revision is None:
                return None
            generators = (generator, *generators)
            session_base = [ranker_version, model_id, generator.revision]
            algorithm_base = [algorithm_base, model_id, generator.revision]
        return RecommendationPipeline(
            self.databases.source, self.settings.database_timeout_seconds,
            ranker=ranker,
            generators=generators,
            version=session_version or self._version(session_base),
            algorithm_version=self._version(algorithm_base),
        )
