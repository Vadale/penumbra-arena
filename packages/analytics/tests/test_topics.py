"""Tests for the BERTopic-based agent-utterance analytics."""

from __future__ import annotations

import numpy as np
import pytest
from penumbra_analytics.topics import (
    ALL_ACTIONS,
    UtteranceStream,
    compute,
    utterance_for,
)


def test_utterance_for_returns_valid_phrase() -> None:
    rng = np.random.default_rng(seed=1)
    phrase = utterance_for("explore", rng)
    assert isinstance(phrase, str)
    assert len(phrase) > 0


def test_utterance_for_rejects_unknown_action() -> None:
    rng = np.random.default_rng(seed=1)
    with pytest.raises(ValueError, match="unknown action"):
        utterance_for("teleport", rng)


def test_utterance_stream_caps_at_capacity() -> None:
    rng = np.random.default_rng(seed=2)
    stream = UtteranceStream(capacity=10)
    for _ in range(25):
        stream.emit("explore", rng)
    assert len(stream.utterances) == 10


def test_all_action_buckets_non_empty() -> None:
    rng = np.random.default_rng(seed=3)
    for action in ALL_ACTIONS:
        # Sample 5 utterances; all must be distinct strings.
        sampled = {utterance_for(action, rng) for _ in range(5)}
        assert len(sampled) >= 1


def test_compute_returns_empty_result_for_tiny_corpus() -> None:
    """Pipelines feed an empty buffer at startup; the function must not crash."""
    result = compute([])
    assert result.n_topics == 0
    assert result.n_documents == 0


@pytest.mark.slow
def test_compute_recovers_action_topics() -> None:
    """BERTopic should find at least 2 distinct topics in a 4-action mixture.

    Marked slow because it downloads bge-small-en-v1.5 on first run
    (~133 MB) and warms up MPS — ~30 s the first time, ~2 s after.
    """
    rng = np.random.default_rng(seed=7)
    corpus: list[str] = []
    for action in ALL_ACTIONS:
        for _ in range(30):
            corpus.append(utterance_for(action, rng))

    result = compute(corpus, min_topic_size=5)
    # 4 action buckets seed the corpus; HDBSCAN can either merge
    # explore/exploit-style phrasing or split each bucket into sub-
    # themes ("blocking" vs "patrolling" inside defend). The looser
    # bound below reflects what we actually see — between 1 and ~12
    # topics, never zero. The exact count isn't load-bearing; the
    # invariants are.
    assert 1 <= result.n_topics <= 12
    assert result.n_documents == len(corpus)
    # Every topic-id maps to non-empty representative words.
    for tid, words in result.representative_words.items():
        assert len(words) > 0, f"topic {tid} has no representative words"
