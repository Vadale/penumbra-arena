# penumbra-attacker — the 12 attacks (and what defends each)

Adversarial-crypto laboratory. Every Penumbra primitive has at least
one *working attack* here, so the learner discovers what each defence
is *for* by trying the attack it stops. The `pna` CLI is the
shell-level entry; the dashboard's "defenses + attacks" section is
the GUI version of the same surface.

## The 12 attacks

Each attack lives in `penumbra_attacker/attacks/<name>.py` with a
top-of-file docstring covering:
1. How the attack works (the threat model).
2. Why Penumbra resists it (the defence).
3. What would break the defence (the threat model's edge).

### Tier 1 — the "you'd see these in a textbook" set

| Attack | Defence | File |
|---|---|---|
| **Dilithium replay** — capture a signed payload, replay it later | sign over `(action, tick_counter, agent_id)`, not just `action` | `attacks/replay.py` |
| **Byzantine equivocation** — sign two conflicting blocks at the same height | slashing — anyone can submit `(sig_a, sig_b)` as evidence and the chain burns the validator's stake | `attacks/byzantine.py` |
| **Dinur-Nissim DP reconstruction** — `n^Ω(1)` random queries reconstruct the bit-vector | hard ε budget — once spent, the DP mechanism refuses further releases | `attacks/dp_reconstruction.py` |
| **Linkability** — re-identify an agent from movement trace across matches | k-anonymity + DP noise + per-match identity shuffling on aggregates | `attacks/linkability.py` |
| **CKKS timing side-channel** — time `add` on sparse vs dense ciphertexts; Welch t-test the latencies | TenSEAL / OpenFHE pad to full polynomial degree on every op (constant-time) | `attacks/timing_sidechannel.py` |
| **Groth16 forgery** — flip A's low bit; replay with tampered public inputs | G2 subgroup membership check + IC binds proofs to public inputs (pairing equation fails) | `attacks/snark_forgery.py` (note: integrated into the SNARK module's own tests rather than a separate file — see `crypto/snark.py`) |

### Tier 2 — the "ML-side, more surprising" set

| Attack | Defence | File |
|---|---|---|
| **1-NN agent fingerprint** — per-agent feature vector (action histogram, latency, curvature, trade pattern) → re-identify across matches | DP noise on aggregates + identity shuffling | `attacks/agent_fingerprint.py` |
| **HMM trajectory fingerprint** — fit a Baum-Welch HMM per agent over action sequences; forward log-likelihood matches | RAPPOR-style action randomisation | `attacks/trajectory_fingerprint.py` |
| **Shokri shadow-model membership inference** — train N shadows; meta-classify "in train set" vs "not" | DP-SGD + confidence clipping → adversary drops below 1 % advantage | `attacks/membership_inference.py` |
| **Deep Leakage from Gradients (Zhu et al. 2019)** — given a leaked per-sample gradient, recover the input by gradient matching | DP-SGD per-sample clipping + Gaussian noise + CKKS secure aggregation | `attacks/model_inversion.py` |
| **Reward poisoning** — inflate rewards on 5 % of training episodes tied to attacker's target action | reward clipping + median-of-means + Krum / TrimmedMean | `attacks/reward_poisoning.py` |
| **CKKS cache side-channel** — Flush+Reload-style timing on sparse vs dense ciphertexts | modern CKKS pads to full polynomial degree; `leak_detected` returns False on the lab build | `attacks/cache_sidechannel.py` |

## How to run them

### From the dashboard

The dashboard's `defenses + attacks` section in `AnalyticsPanel.tsx`
exposes each attack as a clickable tile. Click → open detail modal →
the underlying endpoint runs the attack and returns the metric curve
(accuracy with vs without defence).

### From the CLI

```sh
uv tool install ./packages/attacker
export PENUMBRA_API_URL=http://localhost:8100   # if backend is running

pna replay-cmd                                   # textbook replay
pna linkability-cmd --agents 8 --matches 50      # linkability
pna dp-reconstruct --bits 64 --queries 400       # Dinur-Nissim
pna byzantine-cmd                                # equivocation
pna byzantine-cmd --submit-self-slash            # also files evidence
pna timing --samples 50                          # cache side-channel
```

### From Python (no backend)

The Tier 2 attacks have minimal-dependency demos:

```python
from penumbra_attacker.attacks import membership_inference
result = membership_inference.run_demo()
print(result["adv_naive_train_acc"], result["adv_defended_train_acc"])
```

Look at the file header of each attack — many have a `demo()` or
`run_demo()` function that exercises the attack against an in-process
toy target, no FastAPI needed.

## What this teaches that other "adversarial ML" repos don't

Most adversarial-ML repos focus on ONE attack class (e.g., FGSM on
ImageNet, or PATE membership inference on CIFAR). Penumbra's
attacker package crosses categories:

- **Crypto** (replay, SNARK forgery, equivocation, timing)
- **Privacy** (DP reconstruction, linkability, k-anon homogeneity)
- **ML-privacy** (membership inference, model inversion, reward poisoning)
- **System-level** (cache side-channel)

Each is tiny (~150-300 LOC) — the point is the *vocabulary*, not the
state-of-the-art accuracy.

## Extracting attacks as a spin-off

The Tier 2 attacks (`agent_fingerprint`, `trajectory_fingerprint`,
`membership_inference`, `model_inversion`, `reward_poisoning`,
`cache_sidechannel`) could ship as a standalone "adversarial-ML
teaching kit" without the rest of Penumbra. They depend on
`numpy` / `torch` / `scikit-learn`, not on the simulation.

If you wanted to do this:

1. Copy `packages/attacker/penumbra_attacker/attacks/` to a new repo.
2. Lift `_demo_target_dataset()` helpers (or inline them).
3. Drop the `attacks/__init__.py` Penumbra-CLI hooks.
4. Each attack stays self-contained; bundle the docstrings as a
   `WHAT_THIS_TEACHES.md` summary.

Expected work: ~1 week. Tier 1 attacks are more coupled to the
runtime (they file evidence on the local chain) so they don't extract
as cleanly.

## Layout

```
penumbra_attacker/
  attacks/
    replay.py                  # Tier 1
    byzantine.py               # Tier 1
    dp_reconstruction.py       # Tier 1
    linkability.py             # Tier 1
    timing_sidechannel.py      # Tier 1
    agent_fingerprint.py       # Tier 2
    trajectory_fingerprint.py  # Tier 2
    membership_inference.py    # Tier 2
    model_inversion.py         # Tier 2
    reward_poisoning.py        # Tier 2
    cache_sidechannel.py       # Tier 2
  policy_sandbox.py            # AST-validated user policy runner (CTF support)
  cli.py                       # `pna` Typer CLI
```
