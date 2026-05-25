# CONCEPTS.md — concept → code index

Alphabetical index of every named concept Penumbra implements, with a
pointer to the source file (and line where useful). This is the
"grep-friendly entry" for someone who already knows what they're
looking for.

The complementary docs are:
- `USAGE.md` — what you DO with Penumbra
- `BUILDING_GUIDE.md` — what you'd LEARN by rebuilding it
- `examples/README.md` — runnable snippets of single primitives

---

## A

- **ACF / PACF (autocorrelation diagnostics)** — `packages/analytics/penumbra_analytics/time_series.py` · ARIMA-order chooser, plotted in `apps/web/src/charts/ACFChart.tsx`
- **Agent fingerprinting attack** — `packages/attacker/penumbra_attacker/attacks/agent_fingerprint.py` · 1-NN classifier on per-agent feature vectors
- **ANOVA F-test** — `packages/analytics/penumbra_analytics/inferential.py` · across HDBSCAN cluster labels
- **ARIMA forecast** — `packages/analytics/penumbra_analytics/time_series.py:arima_one_step` · AR(1) one-step-ahead with PI
- **`asyncio.to_thread` (CPU-bound batching)** — `packages/transport/penumbra_transport/orchestrator.py:_cpu_bound_analytics` · single hop per analytics tick

## B

- **Bayesian posterior — Beta(α, β)** — `packages/analytics/penumbra_analytics/bayes.py` · Beta(1,1) prior + binomial likelihood
- **BBS+ — selective-disclosure credentials** — `packages/crypto/penumbra_crypto/bbs_plus.py` · pairing-based signature on attribute vector
- **Beaver triples** — `packages/crypto/penumbra_crypto/educational/beaver.py` · secret multiplication via one broadcast round
- **BLS aggregate signatures** — `packages/crypto/penumbra_crypto/bls.py:aggregate_signatures` · BLS12-381, 96-byte aggregate. See `examples/06_bls_aggregate_finality.py`
- **BLS validator-set finality** — `packages/chain/penumbra_chain/node.py` · >2/3 quorum signs block hash
- **Block production loop** — `packages/transport/penumbra_transport/orchestrator.py` · ANALYTICS_INTERVAL + BLOCK_INTERVAL cadences
- **Bullwhip effect (multi-echelon)** — `packages/core/penumbra_core/logistics_echelon.py` · variance amplification upstream
- **Byzantine equivocation slashing** — `packages/chain/penumbra_chain/slashing.py` · evidence = (sig_a, hash_a, sig_b, hash_b). See `examples/04_merkle_cve_2012_2459.py` for the related Merkle invariant.

## C

- **Cache side-channel on CKKS** — `packages/attacker/penumbra_attacker/attacks/cache_sidechannel.py` · Flush+Reload-style timing; modern CKKS pads → leak_detected=False
- **Cargo capacity constraints** — `packages/core/penumbra_core/logistics.py:CargoConstraints` · caps BUY by remaining capacity
- **Causal inference — IPW / AIPW** — `packages/analytics/penumbra_analytics/causal.py` · propensity-score reweighting + doubly-robust
- **Changepoint detection** — `packages/analytics/penumbra_analytics/time_series.py:detect_mean_changepoints`
- **CKKS — approximate homomorphic encryption** — `packages/crypto/penumbra_crypto/ckks.py` · TenSEAL/OpenFHE backend toggle. See `examples/02_ckks_encrypt_aggregate.py`
- **Concept-tile dashboard pattern** — `apps/web/src/charts/AnalyticsPanel.tsx` + `apps/web/src/charts/DetailModalMeta.ts` · 99 tiles, 12 sections, each opens a modal with educational description
- **Cox proportional hazards** — `packages/analytics/penumbra_analytics/survival.py:cox_proportional_hazards`
- **CPI — Laspeyres price index** — `packages/core/penumbra_core/economy.py:Market.price_index`
- **CSPRNG-seeded DP noise** — `packages/crypto/penumbra_crypto/dp.py:secure_rng` · seeds PCG64 from `secrets.token_bytes(8)`
- **CTF challenges (5 starter)** — `packages/ctf/penumbra_ctf/` + `packages/ctf/challenges/*.yaml`

## D

- **Defense — GAN (synthetic trace)** — `packages/crypto/penumbra_crypto/defenses/gan_defenses.py`
- **Defense — k-anonymity** — `packages/crypto/penumbra_crypto/defenses/k_anonymity.py`
- **Defense — ℓ-diversity** — `packages/crypto/penumbra_crypto/defenses/l_diversity.py`
- **Defense — padding + Poisson cover traffic** — `packages/crypto/penumbra_crypto/defenses/padding.py`
- **Dilithium (ML-DSA-65) signatures** — `packages/crypto/penumbra_crypto/pq.py` · `pqcrypto`-backed
- **Dinur-Nissim DP reconstruction** — `packages/attacker/penumbra_attacker/attacks/dp_reconstruction.py` · O(n) random queries → reconstructs the row
- **DP-SGD per-example clipping** — `packages/learning/penumbra_learning/federated.py` · `torch.func.vmap(grad(functional_call))`
- **DP — Laplace mechanism + budget** — `packages/crypto/penumbra_crypto/dp.py:DPMechanism`. See `examples/01_dp_budget_walkthrough.py`

## E

- **EncryptedHeatmap** — `packages/transport/penumbra_transport/encrypted_heatmap.py` · CKKS encrypt → server sums → DP-noise on decrypt
- **EventBus (in-process pub-sub)** — `packages/transport/penumbra_transport/events.py:EventBus` · subscribe / emit / recent / stats
- **Event handler tiers (cross-pillar)** — `packages/transport/penumbra_transport/orchestrator.py:_wire_event_bus` · 5 tiers (Stats↔Logistics, Security↔Market, DP-budget↔analytics, ML/RL↔Logistics, Chain↔Market)

## F

- **FastAPI lifespan owns background tasks** — `packages/transport/penumbra_transport/api.py:lifespan` · block + heatmap + analytics tasks live here
- **FedAvg / Krum / TrimmedMean** — `packages/learning/penumbra_learning/federated.py` · functional aggregators, switchable at runtime via `method=` arg
- **FedProx proximal term** — `packages/learning/penumbra_learning/federated.py` · `fedprox_mu` knob
- **Fiedler vector + algebraic connectivity** — `packages/analytics/penumbra_analytics/linalg.py`
- **FROST — threshold Schnorr** — `packages/crypto/penumbra_crypto/frost.py` · per-signature binding factors

## G

- **GAT v2 pathfinder (in-tree)** — `packages/learning/penumbra_learning/gat_pathfinder.py:GATv2Layer`
- **GAT v2 supply-graph encoder (PyG)** — `packages/learning/penumbra_learning/supply_gnn.py`
- **GARCH(1,1) — conditional volatility** — `packages/analytics/penumbra_analytics/time_series.py:fit_garch`
- **Granger causality** — `packages/analytics/penumbra_analytics/econometrics.py:granger_matrix`
- **Groth16 verifier (pure Python)** — `packages/crypto/penumbra_crypto/snark.py` · py_ecc-backed; G2 subgroup check on input

## H

- **HDBSCAN clustering** — `packages/analytics/penumbra_analytics/clustering.py:hdbscan_cluster`
- **Heatmap density (DP-noised)** — `packages/transport/penumbra_transport/encrypted_heatmap.py`
- **`hmac.compare_digest` (constant-time)** — used in VRF + timing-sidechannel + key compare

## K

- **KZG opening (Verkle leaf proof)** — `packages/crypto/penumbra_crypto/verkle.py`
- **k-of-n threshold ECDSA (GG18)** — `packages/crypto/penumbra_crypto/threshold_ecdsa.py`
- **Kyber (ML-KEM-768) KEM** — `packages/crypto/penumbra_crypto/pq.py` · `pqcrypto`-backed

## L

- **Linkability attack (1-NN over trajectories)** — `packages/attacker/penumbra_attacker/attacks/linkability.py`
- **Logistic regression — propensity** — `packages/analytics/penumbra_analytics/inferential.py:fit_logit`
- **Logistics — (s, S) reorder policy** — `packages/core/penumbra_core/logistics.py:ReorderPolicy`
- **Logistics — carrier dispatch (Dijkstra)** — `packages/core/penumbra_core/logistics.py:assign_carriers`
- **Logistics — multi-echelon supply chain** — `packages/core/penumbra_core/logistics_echelon.py:EchelonNetwork`
- **Logistics — VRP solver (greedy / 2-opt / OR-Tools)** — `packages/core/penumbra_core/logistics_or.py`
- **Loopix mix-net** — `packages/crypto/penumbra_crypto/mix_net.py` · onion routing

## M

- **MAPPO (multi-agent PPO, CleanRL-style)** — `packages/learning/penumbra_learning/mappo.py`
- **MAPPO live training (background asyncio)** — `packages/learning/penumbra_learning/live_trainer.py`
- **Match (per-round goal walk)** — `packages/core/penumbra_core/match.py`
- **Membership inference (Shokri shadow models)** — `packages/attacker/penumbra_attacker/attacks/membership_inference.py`
- **Mempool (chain transactions)** — `packages/chain/penumbra_chain/node.py`
- **Mempool (logistics orders)** — `packages/core/penumbra_core/logistics.py:LogisticsMempool`
- **Merkle (level-tagged, zero-leaf pad)** — `packages/chain/penumbra_chain/merkle.py` · CVE-2012-2459 closed. See `examples/04_merkle_cve_2012_2459.py`
- **Mix-net (Loopix-style)** — `packages/crypto/penumbra_crypto/mix_net.py`
- **Model inversion (Deep Leakage from Gradients)** — `packages/attacker/penumbra_attacker/attacks/model_inversion.py`
- **Monte Carlo bootstrap fan + VaR/CVaR** — `packages/analytics/penumbra_analytics/monte_carlo.py`

## N

- **NumPyro SVI Bayesian posterior** — `packages/analytics/penumbra_analytics/bayes.py`

## O

- **Operator agent (cyber range)** — `packages/operator/penumbra_operator/` · 20 actions, 12 scenarios, session replay
- **OU edge cost drift** — `packages/core/penumbra_core/arena.py` · Ornstein-Uhlenbeck process

## P

- **Padding defense + Poisson cover traffic** — `packages/crypto/penumbra_crypto/defenses/padding.py`
- **PCA scree + Kaiser criterion** — `packages/analytics/penumbra_analytics/linalg.py:pca`
- **Pedersen commitments** — `packages/crypto/penumbra_crypto/educational/pedersen.py`
- **Permutation test (exact)** — `packages/analytics/penumbra_analytics/inferential.py:permutation_test`
- **Persistent homology (Vietoris-Rips)** — `packages/analytics/penumbra_analytics/topology.py` · ripser-backed
- **PoS-VRF leader election** — `packages/chain/penumbra_chain/consensus.py`
- **PRNG via `secrets.token_bytes`** — used throughout `crypto/` and `chain/`; never `random` for key material
- **PSI — Private Set Intersection (OPRF/DH)** — `packages/crypto/penumbra_crypto/psi.py`

## R

- **RDP accountant (Rényi DP)** — `packages/learning/penumbra_learning/federated_dp.py:RDPAccountant` · 118-order grid. See `examples/05_rdp_dp_sgd_accountant.py`
- **Replay attack on Dilithium** — `packages/attacker/penumbra_attacker/attacks/replay.py` · tick-counter binding defends
- **Reward poisoning (5% backdoor)** — `packages/attacker/penumbra_attacker/attacks/reward_poisoning.py`
- **`rng.py` — central RNG** — `packages/core/penumbra_core/rng.py:bootstrap` · seeds random / numpy / torch / jax from PENUMBRA_SEED
- **ROC + AUC** — `packages/analytics/penumbra_analytics/inferential.py:fit_roc`

## S

- **Saliency — ∂p(action)/∂x** — `apps/web/src/charts/SaliencyChart.tsx`
- **Schnorr Σ-protocol + Fiat-Shamir** — `packages/crypto/penumbra_crypto/educational/schnorr.py`
- **Shamir secret sharing** — `packages/crypto/penumbra_crypto/educational/shamir.py`. See `examples/03_shamir_secret_sharing.py`
- **Shell coach lessons (19 YAML)** — `packages/shell_coach/penumbra_shell_coach/lessons/*.yaml`
- **Sinkhorn / W₁ optimal transport** — `packages/analytics/penumbra_analytics/transport.py`
- **Slashing (chain)** — `packages/chain/penumbra_chain/slashing.py`
- **Snapshot/restore (world state)** — `packages/transport/penumbra_transport/world.py`
- **SPHINCS+ (hash-based PQ sigs)** — `packages/crypto/penumbra_crypto/sphincs.py`
- **STARK — FRI verifier** — `packages/crypto/penumbra_crypto/stark.py` · transparent setup
- **Stat consumer (dashboard pipeline)** — `packages/analytics/penumbra_analytics/dashboard_pipeline.py:DashboardPipeline` · 13 consumers
- **Survival — Kaplan-Meier** — `packages/analytics/penumbra_analytics/survival.py:kaplan_meier`

## T

- **TFHE (LWE, educational)** — `packages/crypto/penumbra_crypto/educational/tfhe_boolean.py` · NAND from scratch
- **Tick loop (perpetual simulation)** — `packages/core/penumbra_core/simulation.py`
- **Time scrubber (replay 500 ticks)** — `apps/web/src/charts/TimeScrubber.tsx`
- **Timing side-channel on CKKS** — `packages/attacker/penumbra_attacker/attacks/timing_sidechannel.py` · Welch t-test
- **Topological features (h₀, h₁)** — `packages/analytics/penumbra_analytics/topology.py`
- **Trajectory fingerprint (HMM)** — `packages/attacker/penumbra_attacker/attacks/trajectory_fingerprint.py`

## V

- **VAR — Vector AutoRegression** — `packages/analytics/penumbra_analytics/econometrics.py:fit_var`
- **VDF — Wesolowski** — `packages/crypto/penumbra_crypto/vdf.py` · T squarings, fast verify
- **Verkle tree (KZG)** — `packages/crypto/penumbra_crypto/verkle.py`
- **VRF — Schnorr-based** — `packages/crypto/penumbra_crypto/vrf.py`

## W

- **Welch t-test (constant-time check)** — `packages/attacker/penumbra_attacker/attacks/timing_sidechannel.py`
- **World branching** — `packages/transport/penumbra_transport/world.py:WorldBranchRegistry`

## Y

- **Yao garbled circuits (millionaires)** — `packages/crypto/penumbra_crypto/educational/yao.py`

## Z

- **Zero-knowledge multiplier circuit (circom)** — `circuits/multiplier.circom` + `packages/crypto/penumbra_crypto/snark.py`
- **Zeroization of secret keys** — `packages/crypto/penumbra_crypto/bls.py:wipe`

---

## How to use this index

- **Looking for a paper-named concept** (e.g. "Dinur-Nissim", "Shokri 2017",
  "Wesolowski VDF")? grep this file, jump to the implementation.
- **Looking for "how do they do X"?** This is the wider net; the per-package
  README (`packages/<name>/README.md`) goes deeper on the *why*.
- **Building a spin-off?** Cross-reference with `examples/README.md` —
  each runnable script there exercises one of the concepts here without
  the full runtime.
