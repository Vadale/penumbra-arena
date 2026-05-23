# Penumbra: A 50-Agent Privacy-Preserving Arena for Hands-On Cryptography, Multi-Agent RL, and Adversarial Pedagogy

**Authors**: Vadale¹

¹ Independent

**Status**: working draft for OSS launch announcement / paper. Refine
before submission. Target venues:
- *NeurIPS Datasets & Benchmarks Track* (large benchmark angle)
- *USENIX Security CSET workshop* (security-education angle)
- *ICML AutoRL workshop* (live-training-mutation angle)
- arXiv preprint as the lowest-friction release

---

## Abstract

We introduce **Penumbra**, an open-source perpetual multi-agent arena
that integrates privacy-preserving primitives, multi-agent reinforcement
learning, and adversarial probes into a single live runtime. 50 agents
compete on a procedurally-dynamic 50-node graph; their per-tick state
is encrypted under CKKS, their movements signed under Dilithium, and
match outcomes anchored on a local PoS-VRF blockchain with BLS-
aggregated finality. The dashboard exposes ~57 clickable concept tiles
spanning statistics, econometrics, ML interpretability, six classes of
post-quantum cryptography, and an attacker console with six executable
attack/forgery demos. The novel contribution is **co-location**: every
pillar fires on every tick within a single hexagonal architecture, so
a learner can probe e.g. how Differential Privacy budget exhaustion
interacts with downstream causal inference — a question that requires
six separate research codebases in the current state of the art.

We open-source the full ~33 600 LOC codebase (Python 3.12 + TypeScript
React 19, strict typing across the stack, 326 tests passing) and
present three reference use cases: (1) a hands-on undergraduate
syllabus for post-quantum cryptography integrating live forgery
attempts; (2) an adversarial-ML benchmark suite comparing learned MAPPO
policies against OR-Tools VRP centralized optimal under the same world;
and (3) a privacy-budget audit dashboard suitable for compliance teams
preparing for the August 2026 EU AI Act enforcement deadlines.

## 1. Introduction

Modern cryptography, machine learning, and operations research are
taught and researched in disjoint codebases. A student learning CKKS
homomorphic encryption from one Jupyter notebook, multi-agent RL from
another, and zk-SNARK verifiers from a third does not see them
INTERACTING — which is precisely where the production engineering
challenge lies. We argue (Section 2) that **integrated runtimes** are
essential for the next decade of crypto + ML pedagogy, and present
Penumbra as a working artefact.

Contributions:
1. A complete, type-strict open-source implementation of an N=50
   privacy-preserving multi-agent system on Apple Silicon (MPS),
   running ~10 Hz tick rate with all pillars active in <8 GB RAM.
2. A novel "concept tile" dashboard idiom (~57 tiles, each with a
   live data view + an educational description + an interactive
   modal) that makes integrated systems probe-able by non-specialists.
3. Six executable adversarial demos (replay, byzantine equivocation,
   Dinur-Nissim DP reconstruction, linkability, timing side-channel,
   SNARK forgery) demonstrating that the underlying primitives'
   soundness arguments are not just theoretical.
4. A live PPO training facility that mutates the inference policy of
   the same arena the user is observing, with reward-shaping sliders
   exposed to the human — to our knowledge the first published
   instance of "click-to-modify reward function" in an integrated
   RL pedagogy environment.

## 2. Why integrate?

(Sections 2.1–2.5 to expand. Argument outline:)

- **2.1** Crypto-ML interactions are real and load-bearing in
  production but invisible in isolated tutorials. Example: CKKS
  approximate decryption error compounds across MAPPO observation
  windows; a learner with TWO disjoint notebooks won't see this.
- **2.2** Differential privacy budget exhaustion is the most common
  privacy failure in deployed systems (CITE Apple iCloud post-mortem,
  TODO link). Co-locating the DP mechanism with downstream
  statistical inference (which uses the noised aggregate) makes the
  failure mode VISIBLE on the dashboard.
- **2.3** Adversarial intuition develops by attempting attacks, not
  reading them. Penumbra's attacker console runs six attacks in
  process; the verifier rejects each, and the user sees the
  soundness argument operate.
- **2.4** Multi-agent RL convergence in non-stationary environments
  is poorly served by gym-style benchmarks. Penumbra's perpetual
  loop (no episodes; agent identities persist; arena topology
  drifts via OU on edge costs) is a more realistic substrate.
- **2.5** Local-first / no-cloud / no-GPU constraints align with
  both the EU's data sovereignty agenda and the realities of
  university computing budgets. Penumbra targets a Mac mini M4 by
  design.

## 3. Architecture

(Reference Figure 1 — package diagram. 9 packages, hexagonal.)

(Subsection 3.1: pillars, what lives where.)
(Subsection 3.2: the tick loop — what each subsystem does per 100ms.)
(Subsection 3.3: orchestration — how the FastAPI lifespan owns every
  background task and shuts them down cleanly.)

## 4. The Dashboard as Pedagogical Surface

(57 tiles. Group by pillar. Table 1: every tile + concept it teaches +
endpoint it polls.)

(Subsection 4.1: the click-to-modal idiom. Each modal renders an
SVG / D3 chart + an educational paragraph in English. Cite the
"concept tile" pattern as a contribution.)

(Subsection 4.2: live ML interaction — Policy Inspector, training
curves, value map, reward shaping. Show how the user mutates
inference temperature and watches the action distribution.)

## 5. Adversarial Console

(Six attacks. For each:
- threat model
- one-line attack mechanism
- defence the verifier provides
- code citation: file:line)

| Attack | Defence | File |
|---|---|---|
| Replay | Tick-counter binding | `attacker/attacks/replay.py:48` |
| Byzantine equivocation | BLS aggregate slashing | `attacker/attacks/byzantine.py:49` |
| Dinur-Nissim DP reconstruction | Privacy budget accountant | `attacker/attacks/dp_reconstruction.py:48` |
| Linkability | DP-noised aggregates | `attacker/attacks/linkability.py:48` |
| Timing side-channel | Constant-time operations | `attacker/attacks/timing_sidechannel.py:55` |
| SNARK forgery | Groth16 pairing equation | `attacker/attacks/snark_forgery.py:51` |

## 6. Evaluation

### 6.1 Reproducibility
`PENUMBRA_SEED=42` produces bit-identical trajectories across runs.
Property-based tests (`hypothesis`) enforce invariants: money
conservation, RNG fan-out determinism, BLS aggregate verifies for
honestly-produced blocks.

### 6.2 Performance on M4
(Stress test results — to fill in from the 24h run currently active.)

### 6.3 Pedagogical reach
Six reference learning paths, each ~4 hours, demonstrated end-to-end:
1. CKKS internals → encrypted aggregates → DP-noised release → inferential stats on noised data
2. MAPPO training from scratch → live policy inspection → adversarial reward shaping
3. Groth16 verification → multiplier circuit → legal-path circuit → forgery attempt
4. PoS-VRF consensus → BLS aggregate → slashing → mempool inspection
5. Persistent homology of agent coalitions → optimal transport between heatmaps
6. Shell fluency for the integrated system: 11 lessons, ~25 commands each

## 7. Related Work

(One paragraph each:)
- TenSEAL, OpenFHE, Concrete-ML — homomorphic encryption libraries
  but no integrated runtime.
- PettingZoo, RLLib, CleanRL — multi-agent RL libraries but no
  privacy or crypto integration.
- circom, snarkjs — ZK toolchains but no live integration with a
  multi-agent system.
- SimPy, AnyLogic, SUMO — simulation frameworks but no crypto pillar
  and (with the exception of SUMO) limited OSS reach.
- Counterfit, IBM ART, Robust Intelligence — adversarial ML but
  attack-focused, not pedagogy-focused.

## 8. Limitations

- Single-host, single-process (intentional; multi-machine is out of
  scope).
- Educational TFHE is bootstrap-free (documented caveat).
- CKKS is approximate by design; cryptographic security analysis is
  out of scope but the standard NIST recommendations are honoured.
- Apple Silicon MPS is the primary target; CUDA/CPU fall-backs work
  but are not optimized.

## 9. Conclusion

Penumbra demonstrates that an integrated runtime spanning crypto,
ML, statistics, and OR is buildable as a single open-source codebase
within budget on commodity Apple Silicon hardware. We hope it serves
as both a benchmark substrate and a teaching tool, and we welcome
contributors at <https://github.com/Vadale/penumbra-arena>.

## Acknowledgements

(TBA)

## References

[BIB] Brody, Alon, Yahav. "How attentive are graph attention networks?"
ICLR 2022. (GATv2)

[BIB] Cheon, Kim, Kim, Song. "Homomorphic encryption for arithmetic of
approximate numbers." ASIACRYPT 2017. (CKKS)

[BIB] Cuturi. "Sinkhorn distances: lightspeed computation of optimal
transport." NeurIPS 2013.

[BIB] Dinur, Nissim. "Revealing information while preserving privacy."
PODS 2003.

[BIB] Dwork, McSherry, Nissim, Smith. "Calibrating noise to sensitivity
in private data analysis." TCC 2006.

[BIB] Forrester. *Industrial Dynamics*. MIT Press, 1961. (Bullwhip)

[BIB] Groth. "On the size of pairing-based non-interactive arguments."
EUROCRYPT 2016. (Groth16)

[BIB] Lyubashevsky, Peikert, Regev. "On ideal lattices and learning
with errors over rings." EUROCRYPT 2010. (Ring-LWE foundation for
Kyber and Dilithium)

[BIB] NIST FIPS 203. Module-Lattice-Based Key-Encapsulation Mechanism
Standard. 2024.

[BIB] NIST FIPS 204. Module-Lattice-Based Digital Signature Standard.
2024.

[BIB] Schulman et al. "Proximal Policy Optimization." 2017.

[BIB] Wesolowski. "Efficient verifiable delay functions." EUROCRYPT
2019.

[BIB] Yu et al. "The Surprising Effectiveness of PPO in Cooperative,
Multi-Agent Games." NeurIPS 2022. (MAPPO)

(Add ~10 more once the rest of the manuscript is fleshed out.)
