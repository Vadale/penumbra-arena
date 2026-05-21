"""Per-agent Dilithium signing of moves.

Concept taught: post-quantum signatures are not just a primitive in
`crypto/pq.py` — every agent action in the running system is signed
and verified. This module hosts the per-agent keystore and a
verify-then-apply gate the orchestrator uses each tick.

Why this matters
----------------
If the simulation accepted unsigned moves, a malicious client (or a
network adversary) could inject "move agent 7 to node 3" packets the
server has no way to authenticate. With per-agent Dilithium keys at
boot, every move comes with a 3309-byte signature over the canonical
(tick, agent_id, target_node) tuple — replay and impersonation are
out of bounds.

Pedagogical caveats
- In our single-process setup the keys live in the same Python
  process as the moves they authenticate, so the threat model is
  purely demonstrative. The *protocol* is what's load-bearing: an
  out-of-process agent (Phase 8+) would keep its secret key on its
  own host and sign there.
- We track verify counters so the dashboard can surface aggregate
  stats — `/agents/signing-stats` is the inspection seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from penumbra_crypto import pq


@dataclass(slots=True)
class SigningStats:
    """Counters for the dashboard."""

    verified: int = 0
    rejected: int = 0


@dataclass(slots=True)
class AgentKeystore:
    """Per-agent Dilithium keypairs + verification counters.

    `keypairs[i]` corresponds to agent id i. Use `sign_move()` /
    `verify_move()` as a pair on the orchestrator's hot path.
    """

    keypairs: list[pq.SigKeypair] = field(default_factory=list)
    stats: SigningStats = field(default_factory=SigningStats)

    @classmethod
    def for_n_agents(cls, n: int) -> AgentKeystore:
        return cls(keypairs=[pq.sig_keygen() for _ in range(n)])

    def sign_move(self, *, agent_id: int, tick: int, target_node: int) -> bytes:
        """Produce a Dilithium signature over the canonical move tuple."""
        keypair = self.keypairs[agent_id]
        message = canonical_move_bytes(tick=tick, agent_id=agent_id, target_node=target_node)
        return pq.sign(keypair.secret_key, message)

    def verify_move(
        self,
        *,
        agent_id: int,
        tick: int,
        target_node: int,
        signature: bytes,
    ) -> bool:
        """Check that `signature` is a valid Dilithium sig on the canonical bytes."""
        if not 0 <= agent_id < len(self.keypairs):
            self.stats.rejected += 1
            return False
        message = canonical_move_bytes(tick=tick, agent_id=agent_id, target_node=target_node)
        ok = pq.verify(self.keypairs[agent_id].public_key, message, signature)
        if ok:
            self.stats.verified += 1
        else:
            self.stats.rejected += 1
        return ok


def canonical_move_bytes(*, tick: int, agent_id: int, target_node: int) -> bytes:
    """Stable byte representation the prover and verifier both agree on.

    Layout: domain-tag || tick(16 BE) || agent_id(8 BE) || target_node(8 BE).
    """
    return (
        b"penumbra-move-v1|"
        + tick.to_bytes(16, "big")
        + agent_id.to_bytes(8, "big")
        + target_node.to_bytes(8, "big")
    )
