# Security audit — Penumbra crypto + chain + attacker + FL

Date: 2026-05-23
Auditor: crypto-auditor agent (post-Phase-2.5)
Verdict: **SAFE-FOR-RESEARCH + SAFE-FOR-DEMO**. Not yet
SAFE-FOR-PRODUCTION.

All 159 in-scope tests pass. Attacker demos (replay, byzantine,
Dinur-Nissim DP recon, linkability, timing side-channel, SNARK
forgery) all correctly accept honest cases and reject malicious
ones.

## Findings by severity

### MED-HIGH (must fix for any privacy claim)

- **DP-SGD per-batch clipping instead of per-example** [x] FIXED —
  `packages/learning/penumbra_learning/federated.py`. The RDP
  accountant in `federated_dp.py` is mathematically correct; the
  trainer used to clip the AGGREGATED gradient
  (`torch.nn.utils.clip_grad_norm_(actor.parameters(), clip)`)
  after `loss.backward()`. Abadi et al. (2016) requires PER-EXAMPLE
  clipping: each sample's gradient L2 ≤ C *individually*, then sum,
  then add noise.
  - Fix shipped: `_dp_step_per_example` computes per-sample
    gradients via `torch.func.vmap(grad(...))` over
    `torch.func.functional_call`, clips each ``||g_i||_2 ≤ clip``
    individually, sums the clipped grads, adds Gaussian noise of
    std ``sigma * clip`` to the sum, divides by the batch size,
    and only then runs ``optimizer.step()``. Poisson subsampling
    (Bernoulli inclusion per example, empty batches skipped)
    replaces the previous with-replacement `torch.randint` so the
    SGM sample-rate assumption is now realised — see
    `_poisson_subsample_indices`. New tests
    `test_dp_clipping_is_per_example` and
    `test_poisson_subsampling_skips_empty_batches` lock the
    invariant.
  - Status: **FIXED** [x].

### MED (must fix for production use)

- **Bitcoin-style Merkle leaf-duplication malleability**
  (CVE-2012-2459) — `packages/chain/penumbra_chain/merkle.py:57-58`.
  Verified empirically: `build_root([a,b,c]) == build_root([a,b,c,c])`.
  In Penumbra's current use the payload list is server-generated,
  not user-submitted, so the practical exploit surface is small,
  but a malicious proposer could exploit it.
  - Fix: enforce no duplicate adjacent leaves OR pad odd-final
    leaves with a fixed zero leaf + tag the level + include the
    tree height in each internal-node hash.
  - Status: **FIXED 2026-05-23** [x] — internal-node hashes are
    now level-tagged (`hash_internal(left, right, level)`), and
    odd-length levels pad with a fixed `_PADDING_NODE` sentinel
    instead of duplicating the last leaf. Breaking change:
    invalidates any previously persisted chain Merkle roots
    (in-memory chain by default, so no migration needed).
    Regression-pinned by `tests/test_merkle.py`.

- **DP noise PRNG is non-cryptographic** — `packages/crypto/dp.py:77`.
  `np.random.default_rng()` is PCG64, predictable to an adversary.
  Adversarial DP requires unpredictable noise (else the adversary
  subtracts the noise).
  - Fix: seed `np.random.default_rng` from `secrets.token_bytes`, or
    accept an explicit `np.random.Generator` argument that the
    caller must seed from a CSPRNG.
  - Status: **FIXED 2026-05-23** [x] — `DPMechanism`'s default
    `rng` is now `secure_rng()`, seeding PCG64 from
    `secrets.token_bytes(8)`. Callers may still pass an explicit
    Generator for reproducibility. Regression-pinned by
    `test_dpmechanism_default_rng_is_secrets_seeded` and
    `test_dpmechanism_explicit_rng_reproducible` in
    `tests/test_dp.py`.

- **Stake-weighted finality threshold uses post-slash active count**
  — `packages/chain/penumbra_chain/consensus.py:148-160`. An
  attacker who slashes enough honest validators can dominate the
  post-slash quorum. Acceptable for single-process pedagogy;
  blocks production-grade use.
  - Fix: thresh against stake-weighted original validator set OR
    slow-moving committee.
  - Status: **FIXED 2026-05-24** [x] — `finalise()` now accepts an
    optional `validator_stakes: dict[bytes, int]` (+ `total_stake`)
    parameter. When supplied, the quorum is `ceil(2/3 · ORIGINAL
    total_stake)` measured against the sum of stakes of validators
    whose sigs verified, so slashing honest nodes can't lower the
    bar. Legacy count-mode is preserved when `validator_stakes is
    None`. Regression-pinned by
    `test_finality_stake_weighted_unchanged_by_slashing_an_honest_validator`.

### LOW-MED

- **Groth16 G2 subgroup membership check missing** — `packages/
  crypto/snark.py:136`. `_is_valid_g2` only checks the twist curve
  equation; the BN128 G2 cofactor is ~10^76 so a small-subgroup
  attacker could in principle craft a non-subgroup G2 point.
  Practically the pairing equation still constrains the forger,
  but the security reduction is weakened.
  - Fix: add Wu et al. 2022 cofactor multiplication subgroup check.
  - Status: **FIXED 2026-05-24** [x] — `_is_valid_g2` now verifies
    `multiply(P, CURVE_ORDER) is None` after the twist-equation
    check, rejecting any point outside the prime-order subgroup.
    Regression-pinned by `test_verify_rejects_non_subgroup_g2_point`
    (uses a deterministic non-subgroup point at x=FQ2([1,0])).

### LOW

- **VRF verify uses `==`** instead of `hmac.compare_digest`
  (`packages/crypto/vrf.py:125`). β is public in Penumbra so the
  side-channel matters only if the VRF is repurposed.
  - Status: **FIXED 2026-05-24** [x] — `vrf.verify` now compares β
    via `hmac.compare_digest`, eliminating the first-mismatching-
    byte timing oracle for any downstream repurposing of the VRF
    where β is treated as secret.
- **Wesolowski VDF Miller-Rabin uses deterministic small-prime
  witnesses** — adversarial inputs could construct strong-
  pseudoprimes against the fixed witnesses. The prime is public
  anyway. Documented.
- **Timing side-channel attack threshold too loose** — `packages/
  attacker/attacks/timing_sidechannel.py` accepts up to |t| < 50;
  standard α=0.05 wants |t| < ~2. Penumbra's TenSEAL backend is
  constant-time and observed t ≈ 0.12, but the loose threshold
  would silently pass a real leak.
  - Fix: tighten to |t| < 5.
  - Status: **FIXED 2026-05-24** [x] — module doctest tightened to
    `|t| < 5`; `tests/test_attacker.py::test_timing_sidechannel_constant_time`
    threshold tightened from `< 100` to `< 5` so a real leak
    presenting as |t| ≫ 2 will no longer slip past CI.
- **CKKS context recreated per round in FL trainer** — minor perf
  cost, no security implication. Cache on the trainer instance.
- **No key zeroization anywhere.** Python `bytes` are immutable;
  partial mitigation only via `bytearray`. Acceptable for
  educational scope.
  - Status: **FIXED 2026-05-24** [x] — `bls.wipe(key)` helper added
    (zeroes a `bytearray` in place, no-ops + logs on immutable
    `bytes`). `bls.keygen`/`bls.sign`/`bls.prove_possession` and
    `pq.kem_decapsulate`/`pq.sign` now route secret-key material
    through transient bytearrays wiped in `finally:` clauses, so
    the secret does not linger in Python's heap beyond the
    underlying primitive's call. Regression-pinned by
    `test_wipe_zeroes_bytearray` + `test_wipe_on_bytes_is_noop_and_does_not_raise`.
- **Persistence writes have no atomic `tmp+rename`** — crash
  mid-write leaves half-written secrets file. `crypto_persistence.py:48`,
  `persistence.py:131`.
  - Status: **FIXED 2026-05-24** [x] — both
    `crypto_persistence._atomic_owner_only_write` and
    `chain.persistence._atomic_owner_only_write` now write to
    `path.tmp` with mode 0o600, `fsync`, then `os.replace` onto the
    destination — POSIX guarantees the rename is atomic, so a crash
    leaves the OLD blob intact rather than a truncated one.
    `save_dp_budget` switched to the same primitive via
    `_atomic_write_text`. Regression-pinned by
    `test_atomic_write_preserves_original_on_mid_write_crash`.
- **DP-SGD uses with-replacement sampling** [x] FIXED — was
  `torch.randint(0, n, ...)`. RDP-SGM analysis assumes Poisson
  subsampling (Bernoulli inclusion per example). Replaced with
  `torch.rand(n) < (batch_size / n)` in `_poisson_subsample_indices`;
  empty batches are skipped by `_train_local_actor`.
- **RDP order grid sparse** — uses 12 orders; Opacus uses ~60.
  Result is slightly looser (conservative) ε bound.
  - Status: **FIXED 2026-05-24** [x] — `_DEFAULT_ORDERS` now
    spans 58 dense orders (α = 1.2, 1.3, …, 6.9) plus three large-α
    anchors (64, 128, 256), matching Opacus's reference grid. The
    canonical scenario (σ=1.1, q=0.01, T=1000, δ=1e-5) now yields a
    strictly smaller ε than the legacy 12-order grid; pinned by
    `test_default_grid_is_denser_than_sparse_baseline`.

## Cross-cutting OK

- All key material derives from `secrets.token_bytes` /
  `secrets.randbelow`.
- No `pickle` / `eval` / `exec` on untrusted data.
- No hardcoded test seeds in production paths.
- BLS rogue-key defence via G2 ProofOfPossession (IETF ciphersuite).
- Chain block-signing payload binds height + domain tag (A1, A4
  audit closures real).
- Slashing evidence rebuilds canonical payload before BLS verify
  (A2, A3 closures real).

## References consulted

CKKS (Cheon-Kim-Kim-Song 2017), TFHE (Chillotti et al. 2020),
Rényi DP (Mironov 2017), SGM RDP (Mironov-Talwar-Zhang 2019),
RDP→DP (Canonne-Kamath-Steinke 2020), DP-SGD (Abadi et al. 2016),
Subsampled RDP (Wang et al. 2019), composition (Dwork-Roth 2014),
Dinur-Nissim 2003, Groth16 (Groth 2016), BLS (Boneh-Lynn-Shacham
2001), rogue-key PoP (Boneh-Drijvers-Neven 2018), VRF (RFC 9381),
Wesolowski VDF 2019, Shamir 1979, Beaver 1991, Schnorr 1991,
Fiat-Shamir pitfalls (Bernhard et al. 2012), Krum (Blanchard et al.
2017), FedProx (Li et al. 2020), NIST FIPS 203/204 (2024),
CVE-2012-2459.

## Production blockers (must fix before claiming "SAFE-FOR-PRODUCTION")

1. Per-example DP-SGD clipping (MED-HIGH) [x] FIXED
2. Merkle leaf-duplication malleability (MED) [x] FIXED
3. CSPRNG for DP noise (MED) [x] FIXED
4. G2 subgroup membership check (LOW-MED) [x] FIXED 2026-05-24
5. Stake-weighted finality threshold (MED) [x] FIXED 2026-05-24
6. Atomic `tmp+rename` writes (LOW) [x] FIXED 2026-05-24
7. Poisson subsampling for DP-SGD (LOW) [x] FIXED
8. Denser RDP order grid (LOW) [x] FIXED 2026-05-24
9. Key zeroization where feasible (LOW) [x] FIXED 2026-05-24
10. VRF constant-time `compare_digest` (LOW) [x] FIXED 2026-05-24
11. Timing side-channel attack threshold (LOW) [x] FIXED 2026-05-24
