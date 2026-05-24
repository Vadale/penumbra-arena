"""Pedagogical re-implementations of SMPC and ZK building blocks.

Concept taught: how the *primitives* that ship in audited libraries
(secret sharing, Beaver triples, Pedersen commitments, Schnorr Σ
protocols, LWE-based TFHE, Yao garbled circuits) actually work
internally — written from scratch with every step traceable, so the
abstractions in the production library stop being magic.

These modules are **offline-only**: they are exercised by tests and by
learner-driven exploration, never on the hot path. Production code uses
the audited libraries in the parent package.

The point of these files is to make every line inspectable, the maths
visible in the source, and the security properties traceable to a
concrete reference.

Modules
- shamir.py     — Shamir secret sharing over a prime field
- beaver.py     — Beaver multiplication triples for SMPC
- pedersen.py   — Pedersen commitments over a Schnorr group
- schnorr.py    — Schnorr Σ-protocol + Fiat-Shamir non-interactive ZK
- yao.py        — Yao garbled circuits + millionaires comparator
"""
