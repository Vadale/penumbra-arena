"""BERTopic on the agent-utterance stream.

Concept taught: BERTopic (Grootendorst 2022) is a topic modeller that
combines transformer embeddings + UMAP dimensionality reduction +
HDBSCAN clustering + class-based TF-IDF for human-readable labels.
It outperforms LDA on short documents and doesn't require a fixed
topic count up front — the dendrogram falls out of HDBSCAN.

Penumbra's twist
----------------
The agents don't speak via an LLM (out of scope). Instead each agent
emits one of a fixed set of templated utterances tied to its current
action — "moving to north node", "scanning goal region", "joining
coalition with agent 7". Over thousands of ticks the cumulative
utterance corpus has the topic structure of "what agents are doing
right now"; BERTopic over that corpus surfaces 3-6 emergent themes
that track simulation dynamics — explore/exploit, defensive/
aggressive, alliance/solo.

Embedding model
---------------
`bge-small-en-v1.5` (BAAI). ~133 MB on first download, MPS-friendly
(<200 MB RAM after warm-up). Cached under
`~/.cache/huggingface/hub/` so subsequent runs are instant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np

# Static corpus of agent utterances, tagged by action category.
# 8-12 phrases per category × 4 categories = 40 phrases total. The
# simulation's per-tick utterance generator samples from these.
_CORPUS_BY_ACTION: Final[dict[str, tuple[str, ...]]] = {
    "explore": (
        "moving to a previously unseen node",
        "scanning the topology for shorter paths",
        "drifting toward an unknown corner of the graph",
        "exploring an edge I have not used before",
        "investigating the periphery of the arena",
        "probing whether this edge cost is volatile",
        "sweeping the upstream region for hidden goals",
        "wandering off the well-trodden path",
        "checking nodes that have low recent traffic",
        "expanding my reach to the far side of the map",
    ),
    "exploit": (
        "heading straight for the closest goal",
        "taking the locally cheapest hop",
        "racing the leader to the upcoming goal",
        "committing to the shortest path I currently know",
        "cashing in on a known-good edge cost",
        "exploiting the gap the others left open",
        "pursuing the high-value node directly",
        "minimising my time to the goal frontier",
        "exploiting the cheap weather window on this edge",
        "sprinting along the geodesic I memorised last match",
    ),
    "defend": (
        "blocking the corridor my coalition controls",
        "guarding the goal we own from the leader",
        "patrolling the entrance to our region",
        "staying within range of the friendly cluster",
        "holding position to deny the contested edge",
        "covering an ally who is exposed",
        "fortifying the choke point on the central path",
        "shadowing a rival agent who is closing in",
        "intercepting a probable approach line",
        "maintaining a buffer between the rival and our goal",
    ),
    "ally": (
        "joining the coalition forming around the south goal",
        "signalling intent to cooperate with agent 7",
        "matching pace with an adjacent friendly",
        "merging into the central cluster",
        "aligning trajectory with my faction",
        "exchanging position information with the coalition",
        "voting to ratify the new alliance topology",
        "regrouping with the agents I shared the last goal with",
        "splitting from the central cluster toward a sub-coalition",
        "signing on as a follower in the new alliance",
    ),
}

ALL_ACTIONS: tuple[str, ...] = tuple(_CORPUS_BY_ACTION.keys())


def utterance_for(action: str, rng: np.random.Generator) -> str:
    """One templated utterance, sampled uniformly from the action's bucket."""
    if action not in _CORPUS_BY_ACTION:
        raise ValueError(f"unknown action {action!r}; choices: {sorted(ALL_ACTIONS)}")
    options = _CORPUS_BY_ACTION[action]
    return str(rng.choice(options))


@dataclass(frozen=True, slots=True)
class TopicResult:
    """Output of one BERTopic compute() pass over a corpus."""

    n_topics: int  # excluding the -1 noise label
    n_documents: int
    n_noise: int  # documents BERTopic couldn't assign
    topic_sizes: dict[int, int]  # topic_id → count (excludes -1)
    representative_words: dict[int, tuple[str, ...]]  # top-k per topic
    embedding_model: str


@dataclass(slots=True)
class _CachedModel:
    """Tiny memoisation cell for the embedding model (heavy to load)."""

    name: str | None = None
    model: object | None = None


_EMBEDDING_CACHE: _CachedModel = _CachedModel()
_DEFAULT_MODEL: Final[str] = "BAAI/bge-small-en-v1.5"


def _load_embedding_model(name: str) -> object:
    if _EMBEDDING_CACHE.name == name and _EMBEDDING_CACHE.model is not None:
        return _EMBEDDING_CACHE.model
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(name)
    _EMBEDDING_CACHE.name = name
    _EMBEDDING_CACHE.model = model
    return model


def compute(
    corpus: list[str],
    *,
    embedding_model_name: str = _DEFAULT_MODEL,
    min_topic_size: int = 5,
    top_n_words: int = 5,
) -> TopicResult:
    """Fit BERTopic on the corpus and return a structured summary.

    Edge cases:
    - Corpus shorter than 2*min_topic_size returns a zero-topic
      result rather than a BERTopic error; the dashboard pipeline
      uses this to silently warm up.
    """
    if len(corpus) < 2 * min_topic_size:
        return TopicResult(
            n_topics=0,
            n_documents=len(corpus),
            n_noise=len(corpus),
            topic_sizes={},
            representative_words={},
            embedding_model=embedding_model_name,
        )

    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from umap import UMAP

    embedder = _load_embedding_model(embedding_model_name)
    # Force seed + small components so the result is reproducible at the
    # small dataset sizes we feed in. Production BERTopic uses these
    # defaults plus a richer vectoriser; we keep it minimal.
    umap = UMAP(n_neighbors=5, n_components=3, min_dist=0.0, random_state=42)
    hdbscan = HDBSCAN(min_cluster_size=min_topic_size, prediction_data=True)
    model = BERTopic(
        embedding_model=embedder,
        umap_model=umap,
        hdbscan_model=hdbscan,
        top_n_words=top_n_words,
        calculate_probabilities=False,
        verbose=False,
    )
    try:
        topics, _probs = model.fit_transform(corpus)
        topics_array = np.asarray(topics)
        info = model.get_topic_info()

        topic_sizes: dict[int, int] = {}
        rep_words: dict[int, tuple[str, ...]] = {}
        topic_ids = [int(t) for t in info["Topic"].tolist()]
        counts = [int(c) for c in info["Count"].tolist()]
        for tid, count in zip(topic_ids, counts, strict=True):
            if tid == -1:
                continue
            topic_sizes[tid] = count
            topic_info = model.get_topic(tid)
            if isinstance(topic_info, list):
                rep_words[tid] = tuple(w for w, _ in topic_info)
    finally:
        # Stress-test fix A: explicitly release the per-call BERTopic +
        # UMAP + HDBSCAN models. Without this they accumulate in
        # backreference cycles and the embedder's torch tensors stay
        # pinned in MPS memory across calls.
        del model
        del umap
        del hdbscan
        del info

    return TopicResult(
        n_topics=len(topic_sizes),
        n_documents=len(corpus),
        n_noise=int(np.sum(topics_array == -1)),
        topic_sizes=topic_sizes,
        representative_words=rep_words,
        embedding_model=embedding_model_name,
    )


@dataclass(slots=True)
class UtteranceStream:
    """Rolling buffer of per-agent utterances for the dashboard pipeline."""

    capacity: int = 400
    utterances: list[str] = field(default_factory=list)

    def emit(self, action: str, rng: np.random.Generator) -> None:
        """Append one utterance sampled for `action`."""
        self.utterances.append(utterance_for(action, rng))
        # Bounded ring: drop the oldest when over capacity.
        if len(self.utterances) > self.capacity:
            self.utterances = self.utterances[-self.capacity :]

    def snapshot(self) -> list[str]:
        return list(self.utterances)
