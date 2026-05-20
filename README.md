# Penumbra

> A privacy-preserving perpetual multi-agent arena built to teach statistics,
> linear algebra, modern neural networks, and cutting-edge cryptography in one
> integrated runtime.

**Status:** scaffolding (Phase 0 of the build).

**Concept.** N=20–50 autonomous agents compete on a procedurally dynamic graph
("arena"). Each agent's true state is encrypted (CKKS + TFHE); the spectator
sees only encrypted aggregates and differentially-private releases. Every
pillar fires on every simulation tick:

- **Neural networks** — MAPPO multi-agent RL on Apple MPS, GATv2 pathfinder
- **Cryptography** — homomorphic encryption, SMPC, post-quantum (Kyber/Dilithium),
  BLS, VRF, VDF, zk-SNARK, a local PoS blockchain anchoring match outcomes
- **Statistics** — descriptive, inferential, econometrics (OLS/IV/GMM/VAR/GARCH),
  Monte Carlo, causal, survival, Bayesian
- **Linear algebra & topology** — graph Laplacians, spectral clustering,
  persistent homology, optimal transport

A built-in **Attacker Console** and a **Shell Coach** turn the dashboard into a
hands-on lab for adversarial intuition and macOS/Unix terminal fluency.

## Documents

- [`ROADMAP.md`](./ROADMAP.md) — phased build plan and learning checkpoints
- [`PROMPTING_GUIDE.md`](./PROMPTING_GUIDE.md) — step-by-step per-module recipes
- [`CLAUDE.md`](./CLAUDE.md) — instructions for Claude Code agents

## Quickstart (after Phase 1)

```sh
docker compose up                # backend + frontend on localhost
open http://localhost:5173       # dashboard
uv tool install ./packages/attacker      # then: pna --help
uv tool install ./packages/shell_coach   # then: psh lessons
```

## Hardware target

Mac mini M4, 16 GB RAM. Total runtime memory target: < 8 GB.

## License

Private project. Not for distribution.
