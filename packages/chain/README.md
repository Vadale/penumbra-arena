# penumbra-chain

A minimal local blockchain that anchors match outcomes.

## Concept taught

- **Block + Merkle tree** — content-addressed, tamper-evident history.
- **PoS-VRF leader election** — every validator computes a VRF beta on
  the previous block hash; the lowest beta becomes the proposer. No
  one can grind a seed, no one can predict the leader.
- **BLS aggregate finality** — >2/3 of validators sign the proposed
  block; their N individual signatures aggregate into one 96-byte sig
  verified by one pairing equation.

In Penumbra the chain is a single in-process node — there's only one
machine, but the validator set is N keypairs each held by the same
process. The point is *pedagogical*: every step of consensus is
inspectable, every cryptographic check is real.

## Public API

```python
from penumbra_chain.node import Node, Validator
```
