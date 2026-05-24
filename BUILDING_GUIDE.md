# Building Your Own Penumbra — From Empty Folder to Live Lab

A pedagogical re-build guide. Each phase walks through what to build,
why it exists, the smallest viable version, the gotchas, and pointers
to the real file in this repo when you want to see the full version.

Estimated time to walk through (reading + tinkering): **15-20 hours**
spread across a week. Estimated time to actually re-implement from
scratch: **80-120 hours** depending on background.

**Target reader**: knows Python decently, has touched FastAPI / React
once, is comfortable on a Mac terminal. We do NOT assume crypto, RL,
econometrics, or topology background — each concept is introduced where
you first need it with a 2-paragraph primer + a reference.

> If you only want to USE Penumbra, read [`USAGE.md`](USAGE.md) instead.
> This document is for people who want to UNDERSTAND it by re-building.

---

## Table of contents

- [Phase 0 — Prerequisites + scaffold](#phase-0--prerequisites--scaffold)
- [Phase 1 — Core domain (the simulation tick)](#phase-1--core-domain-the-simulation-tick)
- [Phase 2 — Cryptography layer](#phase-2--cryptography-layer)
- [Phase 3 — Local blockchain](#phase-3--local-blockchain)
- [Phase 4 — Reinforcement learning (MAPPO)](#phase-4--reinforcement-learning-mappo)
- [Phase 5 — Analytics pipeline](#phase-5--analytics-pipeline)
- [Phase 6 — Transport layer (FastAPI + WebSocket)](#phase-6--transport-layer-fastapi--websocket)
- [Phase 7 — Frontend (React + Vite + r3f)](#phase-7--frontend-react--vite--r3f)
- [Phase 8 — Chart engineering](#phase-8--chart-engineering)
- [Phase 9 — Three CLIs (pna / psh / pno)](#phase-9--three-clis-pna--psh--pno)
- [Phase 10 — Tests + reproducibility](#phase-10--tests--reproducibility)
- [Appendix A — Concepts cheat sheet](#appendix-a--concepts-cheat-sheet)
- [Appendix B — How to read the existing code](#appendix-b--how-to-read-the-existing-code)

---

## Phase 0 — Prerequisites + scaffold

### What you need installed

```sh
# Homebrew (skip if you have it)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install uv pnpm node@22 jq pkg-config cmake
# uv  = Python project/dep manager (fast pip+venv+poetry replacement)
# pnpm = Node package manager (efficient disk usage via content-addressable store)
# cmake + pkg-config = needed when OpenFHE builds from source

# Optional: real Jupyter for the notebook export tile
pip install jupyter
```

You also need:
- Python 3.12+ (uv will install it for you)
- macOS Apple Silicon (M1/M2/M3/M4) for MPS-accelerated PyTorch
- 16 GB RAM minimum (the design budget)

### Workspace layout

Hexagonal architecture. Pure domain in the centre, ports + adapters
in the rings. The shape we'll build toward:

```
penumbra-arena/
├── pyproject.toml              # uv workspace root
├── pnpm-workspace.yaml
├── packages/                   # Python packages
│   ├── core/                   # arena + agent + simulation
│   ├── crypto/                 # CKKS, TFHE, DP, BLS, VRF, ...
│   ├── chain/                  # blocks, PoS-VRF, slashing
│   ├── learning/               # MAPPO + GATv2
│   ├── analytics/              # 30+ streaming consumers
│   ├── attacker/               # 12 attacks + pna CLI
│   ├── shell_coach/            # 19 lessons + psh CLI
│   ├── operator/               # cyber range + pno CLI
│   ├── ctf/                    # capture-the-flag mode
│   ├── notebook/               # IPython magics
│   └── transport/              # FastAPI + WS + orchestrator
└── apps/
    └── web/                    # React 19 + Vite + r3f
```

### Phase 0 commands (do these in order)

```sh
mkdir penumbra-arena && cd penumbra-arena
git init
echo ".venv/\nnode_modules/\nstate/\n__pycache__/\n.DS_Store" > .gitignore

# Top-level workspace
cat > pyproject.toml <<'EOF'
[tool.uv.workspace]
members = ["packages/*"]
[tool.pyright]
include = ["packages"]
strict = ["packages"]
[tool.ruff]
target-version = "py312"
line-length = 100
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "PT", "RUF", "N", "S"]
EOF

mkdir -p packages apps/web infra
echo 'packages:\n  - apps/web' > pnpm-workspace.yaml

# Pre-commit
cat > .pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
EOF
uvx pre-commit install
```

### Key design rules (write these in `CLAUDE.md`)

1. **Strict typing**: every public function annotated; `pyright --strict`
   must pass.
2. **Single RNG**: every random call goes through one seeded `Generator`
   (we'll build it in Phase 1). No `random.random()` or `np.random.rand()`
   anywhere else.
3. **Hexagonal**: pure domain in `core/`; everything else is an adapter.
4. **No comments unless explaining non-obvious why**.
5. **Module docstrings include `Concept taught: ...`** — turns the
   codebase into a self-documenting tutorial.

📖 Reference: this repo's `pyproject.toml`, `CLAUDE.md`,
`.pre-commit-config.yaml`.

---

## Phase 1 — Core domain (the simulation tick)

### Concept primer

A **simulation** = a tick loop driving N agents on a graph. Each tick:
- Every agent observes a local view of the graph.
- Every agent chooses an action (move to neighbour, stay).
- The simulation updates positions, increments a tick counter, optionally
  ends the match if a goal is reached.

We want this to be:
- **Pure synchronous Python** (easy to property-test).
- **Reproducible** (same seed → bit-identical run).
- **Perpetual** (when one match ends, the next starts immediately with
  refreshed topology + persistent agent identities).

### Step 1.1 — The single RNG (`core/rng.py`)

The most important file in the project. Build it first.

```python
# packages/core/penumbra_core/rng.py
from __future__ import annotations
import os, secrets
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True, slots=True)
class Seeded:
    """One blessed source of randomness — fanned out by named purpose."""
    master_seed: int
    def numpy_for(self, purpose: str) -> np.random.Generator:
        # Deterministic per-purpose substream: same purpose -> same RNG.
        seed = abs(hash((self.master_seed, purpose))) % (2**32)
        return np.random.default_rng(seed)

def bootstrap() -> Seeded:
    raw = os.environ.get("PENUMBRA_SEED")
    seed = int(raw) if raw else int.from_bytes(secrets.token_bytes(4), "big")
    return Seeded(master_seed=seed)
```

**Why this matters**: every later module asks `seeded.numpy_for("agent_X")`
instead of calling `np.random` directly. Two runs with the same
`PENUMBRA_SEED=42` produce bit-identical chains, replays, attacks.
This is what makes the whole system *testable* and *reproducible*.

📖 Reference: `packages/core/penumbra_core/rng.py`.

### Step 1.2 — Arena (`core/arena.py`)

A **procedurally dynamic graph** = a graph where edge costs drift over
time (Ornstein-Uhlenbeck noise: mean-reverting random walk), goals
migrate every K ticks, and "weather" events occasionally delete or
re-add edges.

```python
# Simplified — see arena.py for the full version
import networkx as nx
@dataclass
class Arena:
    config: ArenaConfig
    graph: nx.Graph
    edge_cost: dict[Edge, float]
    goals: list[NodeId]
    rng: np.random.Generator

    @classmethod
    def build(cls, config, seeded):
        # Watts-Strogatz small-world graph (high clustering + short paths)
        rng = seeded.numpy_for("arena")
        graph = nx.watts_strogatz_graph(config.n_nodes, config.ring_neighbours, config.rewire_prob, seed=int(rng.integers(0, 2**31)))
        # ... (initialise edge_cost with OU long-run mean + jitter)
        return cls(...)

    def step(self) -> None:
        # OU drift on every edge cost
        # Occasional weather event (delete/re-add edge)
        # Occasional goal migration
```

**Concept taught**: a graph where *no static shortest path exists*
forces agents to keep replanning — this is what makes RL meaningful here.
A static maze would be solved by Dijkstra in 0.1 ms and the RL would
overfit.

📖 Reference: `packages/core/penumbra_core/arena.py`.

### Step 1.3 — Agent (`core/agent.py`)

```python
@dataclass
class Agent:
    id: int
    name: str         # human-readable, e.g. "amber fox"
    position: NodeId
    money: float = 1000.0
    policy: Callable[[Arena, Agent], Action] = random_walk_policy

def random_walk_policy(arena: Arena, agent: Agent) -> Action:
    rng = arena.rng  # NEVER `np.random` directly!
    neighbours = list(arena.graph.neighbors(agent.position))
    return Action(move_to=int(rng.choice(neighbours)))
```

The policy is a **function** — later we'll plug in MAPPO instead.
Keeping it functional means swapping policies is trivial (no class
hierarchy refactor).

📖 Reference: `packages/core/penumbra_core/agent.py`.

### Step 1.4 — Simulation tick loop (`core/simulation.py`)

```python
@dataclass
class Simulation:
    config: SimulationConfig
    arena: Arena
    agents: list[Agent]
    current_match: Match
    tick_counter: int = 0

    def tick(self) -> TickFrame | None:
        if self.paused:
            return None
        self.arena.step()
        actions = [agent.policy(self.arena, agent) for agent in self.agents]
        for agent, act in zip(self.agents, actions):
            self._apply(agent, act)
        match = self.current_match
        if match.ticks_elapsed(self.tick_counter) >= match.max_ticks:
            self._restart_match()
        self.tick_counter += 1
        return TickFrame(tick=self.tick_counter, positions=[a.position for a in self.agents])
```

**Property tests** (write these immediately):
- `sim.tick()` is idempotent given the same `Seeded` state.
- After N ticks, positions are deterministic from `PENUMBRA_SEED`.
- Match restart preserves agent identities + total money.

📖 Reference: `packages/core/penumbra_core/simulation.py` +
`packages/core/tests/test_simulation.py`.

### Phase 1 acceptance test

```sh
PENUMBRA_SEED=42 uv run python -c "
from penumbra_core.simulation import Simulation, SimulationConfig
from penumbra_core.rng import bootstrap
sim = Simulation.build(SimulationConfig(), bootstrap())
for _ in range(100): sim.tick()
print('tick=', sim.tick_counter, 'first_3=', [a.position for a in sim.agents[:3]])
"
```
Run it twice → identical output. If not, you violated the RNG rule
somewhere.

---

## Phase 2 — Cryptography layer

### Concept primer

We want **encrypted aggregates** of agent state — the spectator (dashboard,
attacker) can see "the average position is roughly here" without ever
seeing any individual agent's true position. Tools:

1. **CKKS** (Cheon-Kim-Kim-Song, 2017) — *Homomorphic Encryption* for
   approximate arithmetic. You add encrypted vectors and decrypt the
   sum.
2. **Differential Privacy** — add calibrated noise to query answers so
   no individual contribution can be reconstructed. The "privacy budget"
   ε caps cumulative leakage.
3. **Post-Quantum signatures** (Dilithium, SPHINCS+) — sign agent actions
   with keys that resist Shor's algorithm.
4. **BLS aggregate signatures** — many validators sign the same message,
   produce ONE compact signature, verify with O(1) pairing.
5. **VRF** (Verifiable Random Function) — pseudo-random output that's
   provably unbiased. Used for blockchain leader election.
6. **VDF** (Verifiable Delay Function) — a computation that takes
   provably-long wall-clock time. Used as a source of unbiasable
   randomness for the next match's seed.

### Step 2.1 — CKKS adapter (`crypto/ckks.py`)

```python
# Use OpenFHE-Python (or TenSEAL as fallback)
import openfhe

class CKKSContext:
    def __init__(self, *, ring_dim: int = 8192, mult_depth: int = 3):
        params = openfhe.CCParamsCKKSRNS()
        params.SetRingDim(ring_dim)
        params.SetMultiplicativeDepth(mult_depth)
        self.cc = openfhe.GenCryptoContext(params)
        self.cc.Enable(openfhe.PKESchemeFeature.PKE)
        # ... key generation
```

**Gotchas you WILL hit**:
- OpenFHE-Python builds from source on Apple Silicon — takes ~15 min
  and you need cmake + a C++17 toolchain. If it fails, the env var
  `PENUMBRA_HE_BACKEND=tenseal` falls back to a wheel-shipped library.
- **Rescale after every multiplication** unless you've explicitly
  budgeted the multiplicative depth. Forget this and the noise blows
  up the ciphertext.
- **SIMD-pack many agents into one ciphertext** — CKKS slots are
  cheap. Packing 32-64 agents per ciphertext brings memory from
  ~5 GB to ~250 MB on M4.

📖 Reference: `packages/crypto/penumbra_crypto/ckks.py`.

### Step 2.2 — DP accountant (`crypto/dp.py`)

```python
class DpAccountant:
    """Rényi DP composition tracker (Mironov 2017)."""
    def __init__(self, budget: float):
        self.budget = budget
        self.spent = 0.0
    def charge(self, epsilon: float) -> None:
        if self.spent + epsilon > self.budget:
            raise BudgetExhaustedError(...)
        self.spent += epsilon

def add_laplace_noise(value: float, sensitivity: float, epsilon: float, rng) -> float:
    scale = sensitivity / epsilon
    return value + rng.laplace(0.0, scale)
```

**Critical gotcha**: noise MUST come from a CSPRNG, not `numpy.random`.
We added this to the audit-fix because it's the difference between
"actual privacy guarantee" and "security theatre". Use Python's
`secrets` module to seed.

📖 Reference: `packages/crypto/penumbra_crypto/dp.py`.

### Step 2.3 — Post-quantum (`crypto/pq.py`)

```python
from pqcrypto.sign.dilithium3 import generate_keypair, sign, verify
# or from pqcrypto.kem.kyber768 import generate_keypair, encrypt, decrypt
```

The `pqcrypto` package wraps NIST-standardized PQ primitives (Kyber for
KEM, Dilithium + SPHINCS+ for signatures). Use these directly — don't
roll your own.

**Audit-blocked patterns**:
- Never `==` to compare secret material — use `hmac.compare_digest`.
- Never `numpy.random` for key generation — use `secrets.token_bytes`.
- Wipe secret-key buffers after use (we have a `wipe()` helper).

📖 Reference: `packages/crypto/penumbra_crypto/pq.py`,
`packages/crypto/penumbra_crypto/bls.py`,
`packages/crypto/penumbra_crypto/vrf.py`,
`packages/crypto/penumbra_crypto/vdf.py`.

### Step 2.4 — Educational SMPC primitives (`crypto/educational/`)

This is the *teaching* sub-package: Shamir secret sharing, Beaver
triples, Pedersen commitments, Schnorr signatures, Yao garbled circuits
— all **from scratch in pure Python**, no library wrapping.

The rule: this code is offline-only. It's never on the hot tick path.
You re-implement it to learn the math, then use a real library in
production.

📖 Reference: `packages/crypto/penumbra_crypto/educational/`.

### Phase 2 acceptance test

```python
ctx = CKKSContext()
a = ctx.encrypt_vector([1.0, 2.0, 3.0])
b = ctx.encrypt_vector([4.0, 5.0, 6.0])
c = ctx.add(a, b)
assert ctx.decrypt(c) == pytest.approx([5.0, 7.0, 9.0], abs=1e-3)
```

---

## Phase 3 — Local blockchain

### Concept primer

A **PoS-VRF blockchain**: validators stake coins, are randomly selected
to propose each block (selection probability ∝ stake), use a VRF to
prove they were honestly elected. Other validators sign the block with
BLS — many signatures aggregate to one. Equivocation (signing two
conflicting blocks at the same height) gets the validator's stake
slashed.

Why include this? Penumbra anchors **match outcomes** to the chain with
a zk-SNARK proof of "the winning agent reached the goal via legal
moves". Gives an unforgeable history.

### Step 3.1 — Block + Merkle (`chain/block.py`)

```python
@dataclass(frozen=True, slots=True)
class Block:
    height: int
    parent_hash: bytes
    timestamp: int
    txs: tuple[Tx, ...]
    proposer_pk: bytes
    bls_sig_aggregate: bytes
    @property
    def merkle_root(self) -> bytes:
        return build_root([tx.hash() for tx in self.txs])

def build_root(leaves: list[bytes]) -> bytes:
    # Level-tagged hashing + zero-leaf sentinel pad → closes CVE-2012-2459
    # See packages/chain/penumbra_chain/merkle.py for the audit-safe version
    ...
```

**Audit gotcha**: a naive Merkle implementation is vulnerable to
**CVE-2012-2459** (duplicate-leaf attack where `[a, b, c]` and
`[a, b, c, c]` produce the same root). The fix is level-tagged hashing
+ a sentinel zero-leaf pad. We fixed this in our audit closure.

📖 Reference: `packages/chain/penumbra_chain/block.py`,
`packages/chain/penumbra_chain/merkle.py`.

### Step 3.2 — Consensus (`chain/consensus.py`)

VRF leader election + BLS-aggregated finality + stake-weighted threshold.

```python
def select_leader(validators: list[Validator], slot: int, vrf_sk: bytes) -> Validator:
    """VRF output gives an unbiasable random index weighted by stake."""
    ...

def finalise(block: Block, signatures: dict[bytes, BLSig], validator_stakes: dict[bytes, int] | None = None, total_stake: int | None = None) -> bool:
    # Verify each sig via BLS pairing
    # Quorum: ceil(2/3 * ORIGINAL total stake) when stake-weighted
    # Otherwise legacy count-mode for backwards compat
    ...
```

📖 Reference: `packages/chain/penumbra_chain/consensus.py`.

### Step 3.3 — zk-SNARK verifier (`crypto/snark.py`)

Educational Groth16 verifier (~200 LOC), using `py_ecc` for BN254
pairings. The circuit (`circuits/match_outcome.circom`) is compiled
externally via `circom + snarkjs` (Node-based, runs locally).

The verifier checks:
- The proof points are on the BN254 curve.
- **G2 points are in the correct subgroup** (Wu et al. 2022 cofactor
  check — our audit added this).
- The pairing equation `e(A, B) = e(α, β) · e(L, γ) · e(C, δ)` holds.

📖 Reference: `packages/crypto/penumbra_crypto/snark.py`.

---

## Phase 4 — Reinforcement learning (MAPPO)

### Concept primer

**MAPPO** = Multi-Agent Proximal Policy Optimization (Yu et al. 2022).
Decentralized actors, centralized critic. Each agent has its own actor
network producing action probabilities; one shared critic estimates the
value of the joint state.

Why MAPPO not Q-learning or DQN? Continuous-action friendly,
sample-efficient, stable on small networks (2-layer MLP fits in the
M4 memory budget).

### Step 4.1 — Environment wrapper (`learning/env.py`)

Wrap the Penumbra simulation as a PettingZoo `ParallelEnv`:

```python
from pettingzoo import ParallelEnv

class PenumbraEnv(ParallelEnv):
    def reset(self, seed=None):
        # bootstrap a fresh sim from the seed
        ...
    def step(self, actions):
        # apply each agent's action, tick the sim, return (obs, rew, term, trunc, info)
        ...
```

### Step 4.2 — Actor + Critic networks (`learning/mappo.py`)

```python
import torch.nn as nn
class Actor(nn.Module):
    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 128):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, n_actions),
        )
    def forward(self, obs):
        return torch.softmax(self.mlp(obs), dim=-1)

class Critic(nn.Module):
    # Same structure but outputs a scalar value
    ...
```

**MPS-specific gotchas**:
- `torch.device("mps")` works but some ops fall back to CPU silently
  — check with `torch.set_default_device("mps")` and a sanity forward
  pass on import.
- Prefer `float32` everywhere — `float64` on MPS is slow.
- The C++ caching allocator holds memory between ticks. Add
  `gc.collect()` every ~100 ticks or RSS climbs ~400 MB/h.

### Step 4.3 — PPO training loop (`learning/training.py`)

Standard PPO: collect rollouts, compute GAE advantages, clip-ratio
policy loss + value loss + entropy bonus. CleanRL has a great reference
implementation we adapted (~400 LOC).

📖 Reference: `packages/learning/penumbra_learning/mappo.py`.

### Step 4.4 — GATv2 pathfinder (`learning/gat_pathfinder.py`)

`torch_geometric.nn.GATv2Conv` over the supply graph. Each node is a
city; edges are roads with weight = current OU cost. The GAT learns
"attention weights" over neighbours so the agent can plan multi-hop.

```python
from torch_geometric.nn import GATv2Conv
class SupplyGraphEncoder(nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim, heads=4):
        super().__init__()
        self.gat1 = GATv2Conv(in_dim, hidden_dim, heads=heads)
        self.gat2 = GATv2Conv(hidden_dim * heads, out_dim, heads=1)
```

📖 Reference: `packages/learning/penumbra_learning/supply_gnn.py`.

### Step 4.5 — Federated learning (Tier 1-5)

This is the **encrypted distributed training** layer. Each agent does
local SGD on its (observation, label) buffer, the updates are encrypted
with CKKS + noised with DP-SGD (per-example clipping + Poisson
subsampling) + Byzantine-robust aggregated (Krum / TrimmedMean), then
decrypted by the server. The server applies the average update.

📖 Reference: `packages/learning/penumbra_learning/federated.py`,
`packages/learning/penumbra_learning/federated_dp.py`.

---

## Phase 5 — Analytics pipeline

### Concept primer

We need to compute, in real time, ~30 statistics over the streaming
agent state. The constraint: don't materialise full history in memory
(Penumbra runs perpetually). Use rolling windows + lazy streams.

Stack:
- **Polars** lazy frames — pandas-style API, but Arrow-backed and
  streaming-friendly.
- **statsmodels** + **scipy.stats** — descriptive + inferential tests,
  OLS, ARIMA, VAR.
- **linearmodels** + **arch** — panel regressions, GARCH.
- **ripser** — persistent homology (lighter than `giotto-tda` on M4).
- **POT** — optimal transport / Sinkhorn divergence.
- **NumPyro** SVI (not MCMC) — Bayesian posteriors fast enough for
  the live path.
- **BERTopic** + `bge-small-en-v1.5` — topic drift on the synthetic
  utterance corpus.

### Step 5.1 — The dashboard pipeline (`analytics/dashboard_pipeline.py`)

The orchestrator of the analytics layer. Each consumer has a
**cadence**: descriptive every 1s, GARCH every 5s, NumPyro Bayesian
every 30s, etc.

```python
class DashboardPipeline:
    def __init__(self, cadences: dict[str, float]):
        self.cadences = cadences
        self._last_run: dict[str, float] = {}
        self._snapshot = DashboardSnapshot()
        self.on_signal: Callable | None = None  # event-bus emit hook

    def observe(self, *, tick, positions, heatmap, utterances): ...
    def record_trades(self, ...): ...
    def recompute(self):
        now = time.monotonic()
        if self._due(now, "garch"): self._snapshot.garch = self._compute_garch()
        if self._due(now, "inflation"):
            self._snapshot.inflation = self._compute_inflation()
            # Emit cpi.shock if outside threshold band
            if abs(ratio_vs_ema(...)) > 1.30:
                self.on_signal("cpi.shock", {...})
        # ... ~30 more consumers
```

📖 Reference: `packages/analytics/penumbra_analytics/dashboard_pipeline.py`
(the biggest file in the repo — ~1700 LOC; read the docstring + the
`recompute()` method first, then drill into individual consumers).

### Step 5.2 — Adding a new consumer

The 5-step recipe (also in `CLAUDE.md`):

1. Create `packages/analytics/<name>.py` with module docstring including
   `Concept taught: ...`.
2. Expose a single public function `compute(state: SimulationState) ->
   <name>Result`.
3. Register it in `dashboard_pipeline.py` with its cadence.
4. Add a property-based test under `tests/analytics/test_<name>.py`.
5. Update the corresponding `packages/analytics/README.md` section.

---

## Phase 6 — Transport layer (FastAPI + WebSocket)

### Concept primer

The transport layer is the **only** place asyncio touches the domain.
The simulation is pure synchronous Python; the orchestrator wraps it in
an asyncio task that ticks at a fixed cadence and broadcasts each
frame to all WebSocket subscribers.

### Step 6.1 — FastAPI app factory (`transport/api.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    sim, mappo_runtime = _build_simulation_with_optional_mappo()
    hub = Hub()
    orchestrator = Orchestrator.build(sim)
    async def push(frame): await hub.broadcast(encode_frame(frame))
    loop = TickLoop(sim, push, tick_hz=tick_hz)
    await loop.start()
    yield
    await loop.stop()

def build_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    # @app.get("/health"), @app.get("/dashboard"), @app.websocket("/ws")
    # ... ~150 routes total
    return app
```

📖 Reference: `packages/transport/penumbra_transport/api.py` (the second
biggest file — ~4000 LOC; the route handlers are all bite-sized but
there are a LOT of them).

### Step 6.2 — TickLoop (`transport/loop.py`)

```python
class TickLoop:
    def __init__(self, sim, consumer, *, tick_hz: float = 2.0):
        self._period = 1.0 / tick_hz
    async def _run(self):
        while True:
            frame = self._simulation.tick()
            if frame is not None:
                await self._consumer(frame)
            await asyncio.sleep(self._period)
```

### Step 6.3 — Orchestrator + EventBus (`transport/orchestrator.py` + `events.py`)

The **EventBus** is an in-process pub/sub. Components emit events
(`cpi.shock`, `garch.spike`, `agent.blocked`, `validator.slashed`,
`chain.block.finalised`, `ml.policy.updated`); handlers in the same
process react. This is what makes the dashboard feel "alive" — a
GARCH spike triggers a market regime change which triggers a logistics
retune which triggers a reorder, all visible as cascading events.

```python
class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[Handler]] = {}
    def subscribe(self, kind: str, handler: Handler):
        self._subscribers.setdefault(kind, []).append(handler)
    def emit(self, event: Event):
        for h in self._subscribers.get(event.kind, []):
            try: h(event)
            except Exception: logger.exception("handler raised")
```

5 handler tiers wired in `orchestrator.py:setup`:
1. Stats ↔ Logistics/Market (GARCH spike → reorder retune)
2. Security ↔ Market/FL (agent.blocked → skip in market + FL)
3. DP-budget-aware analytics cadence (ε exhausted → degrade)
4. ML/RL ↔ Logistics reward loop
5. Chain-as-event-source (block.finalised → market.credit_winners)

📖 Reference: `packages/transport/penumbra_transport/orchestrator.py`,
`events.py`.

### Step 6.4 — World snapshot (`transport/world.py`)

Save/load the entire simulation state (positions, chain, market, RNG,
ciphertext buffers) to disk. Needed for: branching, replay, the
videogame-style Save & Resume.

```python
def save_simulation(sim: Simulation, path: Path) -> None:
    payload = {
        "tick_counter": sim.tick_counter,
        "agents": [serialize_agent(a) for a in sim.agents],
        "arena": serialize_arena(sim.arena),
        "chain": sim.chain.to_dict(),
        # ...
    }
    atomic_write(path, pickle.dumps(payload))  # tmp + fsync + os.replace
```

📖 Reference: `packages/transport/penumbra_transport/world.py`,
`packages/operator/penumbra_operator/save_resume.py`.

---

## Phase 7 — Frontend (React + Vite + r3f)

### Concept primer

Vite + React 19 + TS strict + Tailwind v4 + react-three-fiber for the
3D arena + xterm.js for the embedded terminal.

### Step 7.1 — Scaffold

```sh
cd apps/web
pnpm create vite@latest . --template react-ts
pnpm add tailwindcss@4 @tailwindcss/vite three @react-three/fiber @react-three/drei xterm zustand
pnpm add -D @biomejs/biome vitest @testing-library/react jsdom
```

### Step 7.2 — Vite config + Tailwind tokens

Vite proxy lets `/api/...` calls reach the FastAPI backend without CORS.

```ts
// vite.config.ts
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/dashboard": "http://localhost:8100",
      "/operator": {
        target: "http://localhost:8100",
        bypass: (req) => req.url === "/operator" ? req.url : undefined,  // SPA serves the bare path
      },
      "/ws": { target: "ws://localhost:8100", ws: true },
      // ... etc
    },
  },
});
```

`index.css` defines the design tokens via Tailwind v4 `@theme`:

```css
@import "tailwindcss";
@theme {
  --color-penumbra-bg: oklch(20% 0.02 200);
  --color-penumbra-panel: oklch(25% 0.02 200);
  --color-penumbra-cyan: oklch(75% 0.15 200);
  --color-penumbra-ember: oklch(65% 0.18 50);
  --font-mono: "JetBrains Mono", monospace;
  --text-xs: 10px;
  --text-sm: 12px;
  --text-base: 14px;
}
```

### Step 7.3 — Stream → state (`streams/dashboard.ts`)

A zustand store ingests WebSocket frames:

```ts
export const usePenumbraStore = create<State>((set) => ({
  lastFrame: null,
  history: [],
  ingest: (frame) => set((s) => ({
    lastFrame: frame,
    history: [...s.history.slice(-499), frame],  // ring buffer
  })),
}));

// Connect WS once on app mount
export function connectWebSocket() {
  const ws = new WebSocket("/ws");
  ws.onmessage = (e) => usePenumbraStore.getState().ingest(decode(e.data));
}
```

### Step 7.4 — The dashboard layout (`routes/Dashboard.tsx`)

3-column grid: arena left (1fr), analytics middle (340px sidebar), chain
right (300px sidebar). Bottom panel takes 42% of height with 3 tabs
(coach / shell / repl).

```tsx
<main className="grid flex-1 grid-cols-[1fr_340px_300px] overflow-hidden">
  <section className="flex min-h-0 flex-col">
    <ArenaCaption tickHz={tickHz} />
    <div className="relative min-h-0 flex-1">{arenaModeView}</div>
    <div className="flex h-[42%] min-h-0 flex-col">
      {/* coach / shell / repl tabs */}
    </div>
  </section>
  <aside><AnalyticsPanel /></aside>
  <aside><ChainExplorer /></aside>
</main>
```

The `min-h-0` on flex children is **critical** — without it, xterm.js
and SVG charts overflow their container.

📖 Reference: `apps/web/src/routes/Dashboard.tsx`.

---

## Phase 8 — Chart engineering

The most under-appreciated part of the project. **95 tiles** in
`AnalyticsPanel.tsx`, each one a clickable concept. The pattern is the
same for every tile:

### The 5-step tile recipe

1. **Backend endpoint**: add a `@app.get` under
   `packages/transport/penumbra_transport/api.py` returning a flat JSON
   dict with `available: bool` so the frontend can render an empty
   state cleanly.

2. **Chart component**: `apps/web/src/charts/FooChart.tsx`. Fetch the
   endpoint on mount (one-shot or via `useFetchJsonPoll` for live).
   Render as SVG / D3 / Plot. Look at `VDFChart.tsx` (~100 LOC) for a
   minimal one-shot panel; `TrainingCurves.tsx` for a polling one.

3. **Modal route**: extend `MetricKind` in `DetailModal.tsx` with the
   new id; add the `META` entry (label + description + optional `cli`
   hint); add one branch `if (metric === "foo") return <FooChart />`.

4. **Tile**: add `<Cell label="..." onClick={() => open("foo")} />` in
   the right section of `AnalyticsPanel.tsx`; add the new id to the
   `Exclude<MetricKind, ...>` literal so the per-tile history mini-
   trend skips it.

5. **Proxy** (if NEW URL prefix): add `"/foo": API_HTTP` to
   `apps/web/vite.config.ts`.

### Example: build the simplest chart

```tsx
// apps/web/src/charts/HelloChart.tsx
import { useFetchJsonOnce } from "../hooks/useFetchJson";
import { FetchError } from "./_shared/FetchError";

export function HelloChart() {
  const state = useFetchJsonOnce<{value: number}>("/hello");
  if (state.kind === "loading") return <span>warming…</span>;
  if (state.kind === "error") return <FetchError message={state.message} />;
  return <div className="text-2xl">{state.value.value}</div>;
}
```

### D3 + brush-select pattern

For time-series charts that need user interaction (drag-select a window
to see stats only in that range), use the `useBrushSelection` hook:

```tsx
const svgRef = useRef<SVGSVGElement>(null);
const { range, clear, overlay } = useBrushSelection(svgRef, xScale, invertX, bounds);
const filtered = range ? data.filter(d => d.x >= range.start && d.x <= range.end) : data;
return (
  <>
    <svg ref={svgRef}>...{overlay}</svg>
    <BrushStats range={range} stats={windowStats(filtered)} onClear={clear} />
  </>
);
```

### Export buttons

Every chart can be exported via `<ExportButtons metric="garch" />`:

```tsx
function useExport(metric: string) {
  const download = async (format: "csv"|"json"|"png"|"notebook") => {
    const url = format === "notebook" ? `/export/notebook?metric=${metric}` : `/export/chart/${metric}?format=${format}`;
    const blob = await (await fetch(url)).blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${metric}.${format}`;
    a.click();
  };
  return { download };
}
```

Server-side: `/export/chart/{metric}?format=png` renders via matplotlib
at 800×400 with proper title + axes + legend. See
`packages/transport/penumbra_transport/interactivity.py` for the
~30-metric dispatch table.

---

## Phase 9 — Three CLIs (pna / psh / pno)

### Concept primer

`pna` (attacker), `psh` (shell coach), `pno` (operator). All built with
typer (FastAPI's CLI sibling).

### Skeleton (`<package>/cli.py`)

```python
# packages/operator/penumbra_operator/cli.py
import os, typer
app = typer.Typer(help="Penumbra Operator console")
_DEFAULT_API = os.environ.get("PENUMBRA_API_URL", "http://localhost:8000")

@app.command()
def enable(api: str = typer.Option(_DEFAULT_API, "--api")) -> None:
    result = _http_post(_api_url(api, "/operator/enable"), {})
    typer.echo(json.dumps(result, indent=2))
```

Install with `uv tool install ./packages/operator` → `pno enable` works
from anywhere on `$PATH`.

📖 Reference: `packages/operator/penumbra_operator/cli.py`,
`packages/attacker/penumbra_attacker/cli.py`,
`packages/shell_coach/penumbra_shell_coach/cli.py`.

---

## Phase 10 — Tests + reproducibility

### Test discipline

- **Property-based tests** with `hypothesis` for crypto + arena
  invariants. ~60% of tests are property-based.
- **Integration tests** with `TestClient(app)` for endpoints.
- **Reproducibility tests**: run sim twice with same seed → assert
  bit-identical state.
- **Vitest** for the React frontend (jsdom + happy-dom).

### Test counts (current state)

- ~860 backend pytest functions
- 105 vitest functions
- ~965+ tests total, all green

### Pre-commit hygiene

Ruff (lint + format) + Pyright (strict) + Biome (web) all run on every
commit. **After every commit, run `git log --oneline -1` and confirm
HEAD matches the new message** — if it doesn't, the commit was silently
rolled back (pre-commit had unstaged changes); fix and re-commit.

---

## Appendix A — Concepts cheat sheet

Quick refresher on what each technology *does* and *why*:

| Concept | Library | Purpose in Penumbra |
|---|---|---|
| CKKS | OpenFHE-Python / TenSEAL | Encrypt agent state for additive aggregation |
| TFHE | Concrete-ML | Encrypted comparison ("is agent in region?") |
| DP | diffprivlib / opendp | Noisy aggregates, ε budget tracking |
| Kyber | pqcrypto | Post-quantum KEM for session keys |
| Dilithium | pqcrypto | Post-quantum signatures on actions |
| BLS | py_ecc | Aggregate validator signatures |
| VRF | custom | Block proposer selection (unbiasable) |
| VDF | custom (Wesolowski) | Match-seed randomness |
| Groth16 | py_ecc | zk-SNARK verifier for match outcomes |
| MAPPO | from-scratch | Multi-agent RL on MPS |
| GATv2 | torch_geometric | Graph attention for pathfinding |
| Ripser | ripser | Persistent homology of coalition graphs |
| Sinkhorn | POT | Optimal transport between heatmaps |
| GARCH | arch | Volatility modelling on agent metrics |
| NumPyro | NumPyro | Bayesian posterior over hidden state |
| BERTopic | bertopic + bge-small | Topic drift on utterance corpus |
| HDBSCAN | hdbscan | Faction clustering |
| networkx | networkx | The arena's underlying graph |
| Polars | polars | Streaming-friendly dataframes |
| DuckDB | duckdb | Local OLAP for the history table |

---

## Appendix B — How to read the existing code

You don't have to read 85k LOC. The strategic reading order:

1. `CLAUDE.md` + this guide — orient yourself.
2. `packages/core/penumbra_core/rng.py` — the seed of everything (40 LOC).
3. `packages/core/penumbra_core/simulation.py` — the tick loop (~250 LOC).
4. `packages/transport/penumbra_transport/api.py` — start with the
   `build_app()` factory and the `/dashboard` endpoint; the rest is
   variations on the same shape (~4000 LOC, skim).
5. `packages/transport/penumbra_transport/orchestrator.py` — see how
   the EventBus + 5 handler tiers wire everything together (~1000 LOC).
6. `packages/analytics/penumbra_analytics/dashboard_pipeline.py` —
   the big consumer (~1700 LOC). Read the docstring + `recompute()`,
   then pick 3 consumers at random.
7. `apps/web/src/routes/Dashboard.tsx` + `apps/web/src/charts/
   AnalyticsPanel.tsx` + `apps/web/src/charts/DetailModal.tsx` — the
   frontend triangle. Each ~500 LOC.
8. Pick **one** package directory you find interesting and read it
   end-to-end. Suggested first picks for different interests:
   - Crypto curious → `packages/crypto/penumbra_crypto/educational/`
     (from-scratch Shamir, Beaver, Pedersen, Schnorr, Yao)
   - ML curious → `packages/learning/penumbra_learning/mappo.py`
     + `federated.py` + `federated_dp.py`
   - Systems curious → `packages/transport/penumbra_transport/world.py`
     + `packages/operator/penumbra_operator/save_resume.py`
   - Crypto + chain → `packages/chain/penumbra_chain/consensus.py`
     + `packages/crypto/penumbra_crypto/snark.py`

### When to clone vs reference

You don't need to re-implement every line. Suggested phasing:
- **Re-implement from scratch**: Phase 1 (core RNG + arena + sim).
  This is your foundation; understanding it makes everything else
  comprehensible.
- **Re-implement minimum viable**: Phase 2 (CKKS adapter), Phase 4
  (single-agent PPO), Phase 6 (FastAPI + WS), Phase 7 (one chart end-to-
  end).
- **Read + tinker**: Phase 3 (chain), Phase 5 (analytics consumers),
  Phase 8 (more charts), Phase 9 (CLIs).
- **Use the existing code**: educational SMPC primitives, the federated
  learning Tier 2-5, the 19 shell-coach lessons, the 12 operator
  scenarios.

After 80-120 hours of this you'll know Penumbra inside out **and** have
internalized 20+ load-bearing concepts (homomorphic encryption,
differential privacy, BLS pairings, MAPPO, GAT, persistent homology,
Sinkhorn, GARCH, Bayesian SVI, hexagonal architecture, async transport,
event-driven design, ...).

That's the goal. Penumbra is a *codebase to learn from*, not just a
program to run.

---

## Final encouragement

Don't try to build it linearly Phase 1 → 10. Build:

1. Phase 0 (scaffold)
2. Phase 1 (tick loop)
3. Phase 6 minimal (FastAPI returning the tick counter)
4. Phase 7 minimal (one React component fetching the tick counter)

— and you already have a working "Penumbra-zero". From there, ADD ONE
THING AT A TIME. Encrypted positions? Now you need CKKS (Phase 2).
A second agent with a learned policy? Now you need MAPPO (Phase 4).
A real-time topic model? Now you need Phase 5.

**The order to add features should follow your curiosity, not this
guide's numbering.** The guide is a map; you choose the path.

Good luck.

— Vadale, 2026
