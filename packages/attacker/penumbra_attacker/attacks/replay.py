"""Replay attack against nonce-less Dilithium signatures.

How the attack works
--------------------
ML-DSA-65 (Dilithium-3) signs raw bytes. If an agent's protocol just
sends `(payload, sign(sk, payload))`, an eavesdropper can capture the
pair on the wire and re-send it later — the signature stays valid
because the message hasn't changed. The replayed action is then
indistinguishable from a fresh one as far as the verifier knows.

Why Penumbra resists it
-----------------------
Penumbra wraps every action payload with `(action, tick_counter,
agent_id)` *before* signing. The signature is over the concatenated
bytes, so a replayed sig binds to its original tick — replaying it at
tick+k means tick_counter mismatches the current state and the
verifier rejects.

Mitigation if you don't have a tick
-----------------------------------
Use a per-session monotonic counter or a random nonce + replay-cache.

Try it
------
>>> from penumbra_attacker.attacks import replay
>>> result = replay.demo()
>>> result.naive_succeeded
True
>>> result.with_tick_counter_succeeded
False
"""

from __future__ import annotations

from dataclasses import dataclass

from penumbra_crypto import pq


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Outcome of one replay demo: did the attack succeed?"""

    naive_succeeded: bool
    with_tick_counter_succeeded: bool


def demo() -> ReplayResult:
    """End-to-end demonstration of the attack and the defence."""
    keypair = pq.sig_keygen()

    # ── Naïve protocol: sign just the action bytes ─────────────────
    action = b"MOVE NORTH"
    captured_sig = pq.sign(keypair.secret_key, action)
    # Eavesdropper replays the exact same (action, sig) pair later.
    replayed_ok = pq.verify(keypair.public_key, action, captured_sig)
    naive_succeeded = replayed_ok  # True — that's the bug

    # ── Hardened protocol: bind to the tick ────────────────────────
    original_tick = 100
    original_message = _bind(action, tick=original_tick, agent_id=12)
    captured_sig_v2 = pq.sign(keypair.secret_key, original_message)
    # Replay at a later tick: the signature is over the OLD message,
    # but the verifier reconstructs the message from the CURRENT tick.
    later_tick = 150
    expected_message_at_replay = _bind(action, tick=later_tick, agent_id=12)
    replayed_v2_ok = pq.verify(keypair.public_key, expected_message_at_replay, captured_sig_v2)
    with_tick_counter_succeeded = replayed_v2_ok  # False — defence holds

    return ReplayResult(
        naive_succeeded=naive_succeeded,
        with_tick_counter_succeeded=with_tick_counter_succeeded,
    )


def _bind(action: bytes, *, tick: int, agent_id: int) -> bytes:
    """Domain-tagged bind: action || tick (big-endian) || agent_id."""
    return action + b"|" + tick.to_bytes(16, "big") + b"|" + agent_id.to_bytes(8, "big")
