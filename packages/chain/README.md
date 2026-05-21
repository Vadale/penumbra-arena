# penumbra-chain

A minimal **PoS-VRF blockchain** that anchors Penumbra match outcomes
on a tamper-evident, BLS-finalised history.

## Concept taught

Three cryptographic ideas, all live in one tick of the chain:

1. **Content addressing** (`block.py`, `merkle.py`) — every block hash is
   the SHA-256 of its canonical header encoding. Mutate any byte and the
   hash changes; the Merkle root commits to the payload separately so a
   light client can verify a single transaction without downloading
   the whole block.
2. **VRF leader election** (`consensus.py`) — every validator computes
   β_i = VRF(sk_i, prev_hash). The lowest β wins the right to propose.
   No proposer can grind the seed, no observer can predict the winner
   until proofs are published.
3. **BLS aggregate finality** (`consensus.py`) — N validators sign the
   proposed block hash; their N individual sigs collapse into one
   96-byte aggregate verified by one pairing equation.

In Penumbra the validator set is N keypairs hosted in the same
process; the cryptography is real but the network layer is trivial.
Same primitives extend unchanged to a real distributed deployment.

## Micro-experiments

1. Boot a Node and watch leader rotation:
   ```python
   from penumbra_chain.node import Node
   from penumbra_chain.block import MatchOutcome
   import hashlib

   node = Node.boot(n_validators=4)
   for i in range(5):
       node.submit_outcome(MatchOutcome(
           match_id=i, winner_agent_id=0, winning_goal=1,
           started_tick=i*100, end_tick=i*100+50, end_reason="won",
           arena_signature=hashlib.sha256(f"arena-{i}".encode()).digest(),
       ))
       block = node.produce_block()
       print(f"block {block.header.height} proposed by",
             block.header.proposer_pubkey[:8].hex())
   ```
2. Try the byzantine attack from the Attacker Console:
   `pna byzantine-cmd` — see two valid sigs on conflicting blocks at
   the same height. That's the equivocation proof real chains slash on.

## Public API

```python
from penumbra_chain.node import Node                            # boot, submit_outcome, produce_block
from penumbra_chain.block import Block, BlockHeader, MatchOutcome
from penumbra_chain.consensus import keygen, elect_leader, finalise
from penumbra_chain.merkle import build_root, build_proof, verify_proof
```

## Deferred

- **Slashing transactions** — equivocation detection works; on-chain
  punishment doesn't yet. See `attacker/byzantine.py` for the proof
  the slashing tx would consume.
- **Disk persistence** — the chain is in-memory; restart loses
  everything. DuckDB snapshot pending.
