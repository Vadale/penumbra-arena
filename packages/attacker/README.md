# penumbra-attacker

Adversarial-crypto lab. Each attack is a working Python module the
user can pipe into the dashboard's REPL panel or run via the `pna` CLI.

## Concept taught

Every cryptographic primitive in Penumbra has a corresponding attack
demo here. The point is **adversarial intuition**: you learn what a
defence is *for* by trying the attack it was designed to stop.

- `attacks/replay.py` — replay a captured Dilithium signature on a
  fresh nonce-less action. Shows why every action must include a
  monotonic counter.
- `attacks/linkability.py` — de-anonymise an agent from its movement
  trace when the simulation forgets to add noise to released
  trajectories.
- `attacks/dp_reconstruction.py` — Dinur-Nissim row reconstruction
  against a sequence of DP query releases with depleted budget.
- `attacks/byzantine.py` — spin up a malicious validator that signs
  two conflicting blocks at the same height. Shows the slashing case
  that real PoS chains punish.
- `attacks/timing_sidechannel.py` — measure CKKS operation latency
  to infer the *shape* of an encrypted vector (even when its values
  stay hidden).

## CLI

```sh
uv tool install ./packages/attacker
pna --help
```
