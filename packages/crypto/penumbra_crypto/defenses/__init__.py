"""Defense primitives — privacy-utility tradeoff modules.

Concept taught: every defense in this package answers the same shape
of question — "by how much can we drop an adversary's accuracy if we
release a noisier / smaller / synthetic version of our data?". Each
module exposes a pure-functional API + a ``demo()`` returning a
measurable tradeoff curve the dashboard renders directly.

Phase 5 Tier 3 ships six defenses; none of them touch the existing
cryptographic invariants of Penumbra (CKKS rescale rules, BLS
aggregation, signature verification) — they are additive primitives
that the orchestrator can compose around the existing release path in
Phase 6b Tier 4.
"""

from __future__ import annotations

from penumbra_crypto.defenses.data_poisoning import (
    DECOY_FLAG,
    PoisoningError,
    PoisoningReport,
    inject_decoy_traces,
)
from penumbra_crypto.defenses.data_poisoning import (
    evaluate_tradeoff as evaluate_poisoning_tradeoff,
)
from penumbra_crypto.defenses.gan_defenses import (
    GANDefenseError,
    SyntheticReport,
    fit_gaussian_model,
    synthesise_trajectories,
)
from penumbra_crypto.defenses.gan_defenses import (
    evaluate_tradeoff as evaluate_synthetic_tradeoff,
)
from penumbra_crypto.defenses.k_anonymity import (
    KAnonymityError,
    KAnonymityReport,
    k_anonymise,
)
from penumbra_crypto.defenses.k_anonymity import (
    evaluate_tradeoff as evaluate_k_anonymity_tradeoff,
)
from penumbra_crypto.defenses.l_diversity import (
    LDiversityError,
    LDiversityReport,
    l_diversify,
)
from penumbra_crypto.defenses.l_diversity import (
    evaluate_tradeoff as evaluate_l_diversity_tradeoff,
)
from penumbra_crypto.defenses.padding import (
    PaddingError,
    PaddingReport,
    cover_traffic_schedule,
    pad_request,
    pad_response,
    unpad,
)
from penumbra_crypto.defenses.padding import (
    evaluate_tradeoff as evaluate_padding_tradeoff,
)
from penumbra_crypto.defenses.request_obfuscation import (
    DUMMY_FLAG,
    ObfuscationError,
    ObfuscationReport,
    add_dummy_queries,
    bonferroni_correct_queries,
)
from penumbra_crypto.defenses.request_obfuscation import (
    evaluate_tradeoff as evaluate_obfuscation_tradeoff,
)

__all__ = [
    "DECOY_FLAG",
    "DUMMY_FLAG",
    "GANDefenseError",
    "KAnonymityError",
    "KAnonymityReport",
    "LDiversityError",
    "LDiversityReport",
    "ObfuscationError",
    "ObfuscationReport",
    "PaddingError",
    "PaddingReport",
    "PoisoningError",
    "PoisoningReport",
    "SyntheticReport",
    "add_dummy_queries",
    "bonferroni_correct_queries",
    "cover_traffic_schedule",
    "evaluate_k_anonymity_tradeoff",
    "evaluate_l_diversity_tradeoff",
    "evaluate_obfuscation_tradeoff",
    "evaluate_padding_tradeoff",
    "evaluate_poisoning_tradeoff",
    "evaluate_synthetic_tradeoff",
    "fit_gaussian_model",
    "inject_decoy_traces",
    "k_anonymise",
    "l_diversify",
    "pad_request",
    "pad_response",
    "synthesise_trajectories",
    "unpad",
]
