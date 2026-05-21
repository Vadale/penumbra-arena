# penumbra-attacker

Adversarial-crypto laboratory. Every Penumbra primitive has a
matching *working attack* here, so the user learns what each defence
is *for* by trying the attack it was designed to stop.

## Concept taught

Defence-by-defence:

- **`attacks/replay.py`** — Dilithium signatures over raw payloads
  are replayable; the defence is binding the signature to a monotonic
  context (tick + agent_id).
- **`attacks/linkability.py`** — naïve trajectory aggregation
  de-anonymises agents at near-100% accuracy across matches; the
  defence is adding Laplace-scale noise to the released features.
- **`attacks/dp_reconstruction.py`** — Dinur-Nissim row reconstruction
  against an unaccounted DP release: 250 noisy queries on a 32-bit
  vector → 100% recovery. The defence is the privacy *accountant* in
  `penumbra_crypto.dp`, not the noise mechanism itself.
- **`attacks/byzantine.py`** — a single BLS keyholder signing two
  conflicting blocks at the same height produces a publicly-verifiable
  equivocation proof. Real PoS slashes on this; Penumbra detects but
  doesn't yet slash.
- **`attacks/timing_sidechannel.py`** — Welch's t-test on CKKS `add`
  latencies across sparse vs dense ciphertexts. TenSEAL/OpenFHE are
  constant-time on this path; the t-statistic stays small.

## Micro-experiments

1. Convince yourself replay works against the naïve protocol:
   ```sh
   pna replay-cmd
   # naive replay succeeded: True
   # with tick-counter binding, replay succeeded: False
   ```
2. Find the threshold where DP reconstruction breaks down:
   ```sh
   pna dp-reconstruct --bits 32 --queries 200 --noise 0.1   # ~100% recovery
   pna dp-reconstruct --bits 32 --queries 200 --noise 5     # ~50% (coin flip)
   ```
   The defence the accountant provides is bounding the total number of
   queries with the given noise level so the adversary can't accumulate
   enough signal.

## CLI

```sh
uv tool install ./packages/attacker
pna --help
pna {replay-cmd,linkability-cmd,dp-reconstruct,byzantine-cmd,timing}
```

## Deferred

- `snark_forgery.py` — would demonstrate that without per-input
  binding (the Bernhard-Pereira-Warinschi 2012 family of bugs), a
  Fiat-Shamir transcript can be replayed under a different statement.
  The Schnorr ZK code in `crypto/educational/schnorr.py` already
  closes this; the standalone attack module is documentation work
  that's still TODO.
