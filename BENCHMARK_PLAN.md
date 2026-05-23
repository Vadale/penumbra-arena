# Penumbra-Bench — Benchmark Specification

A formal benchmark suite + leaderboard built on top of the Penumbra
runtime, positioned as the standard evaluation environment for
**privacy-aware, adversarially-robust, multi-agent reinforcement
learning**.

**Status**: planning, deferred to post-OSS-launch (target release
as v1.1 in month 2-3 of [`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md)).

Sister documents:
- [`OSS_PAPER_DRAFT.md`](OSS_PAPER_DRAFT.md) — the academic paper
  will introduce Penumbra-Bench formally
- [`FEDERATED_LEARNING_PLAN.md`](FEDERATED_LEARNING_PLAN.md) — FL
  tasks become benchmark tasks
- [`SYNTHETIC_DATA_PLAN.md`](SYNTHETIC_DATA_PLAN.md) — Penumbra-Data
  is the dataset companion

---

## 1. Why a benchmark, and why now

### 1.1 The gap

No existing RL benchmark integrates the four axes Penumbra runs on:

| Benchmark | Multi-agent | Privacy | Adversarial | Crypto |
|---|---|---|---|---|
| MuJoCo / DM Control | ✗ | ✗ | ✗ | ✗ |
| Atari 2600 / ALE | ✗ | ✗ | ✗ | ✗ |
| ProcGen / MiniGrid | ✗ | ✗ | ✗ | ✗ |
| MineRL | ✗ | ✗ | ✗ | ✗ |
| MeltingPot (DeepMind) | ✓ | ✗ | ✗ | ✗ |
| StarCraft II (PySC2) | ✓ | ✗ | ✗ | ✗ |
| OpenAI Five / Dota | ✓ | ✗ | partial | ✗ |
| **Penumbra-Bench** | **✓** | **✓** | **✓** | **✓** |

Industry / regulatory drivers that make THIS axis-combo timely:
- **EU AI Act** (in force August 2026) requires adversarial-
  robustness evaluation for high-risk ML systems
- **NIST AI Risk Management Framework** (AI RMF 1.0) cites
  privacy-respecting evaluation as a control
- **Apple-style on-device ML** is now mainstream; the privacy-
  aware angle aligns with Apple's "Private Cloud Compute" vision
  (2024)
- **Multi-agent systems** are exploding in production (AutoGen,
  CrewAI, multi-agent LLM pipelines) but with no standard
  robustness benchmark

### 1.2 The strategic upside

A benchmark cited by 10 research papers = a permanent academic
footprint. A successful benchmark is also a long-tail traffic
generator (every paper using it brings citations and stars).
And benchmarks generate B2B opportunity (compliance teams pay to
"pass Penumbra-Bench evaluation" as part of vendor due diligence).

## 2. Benchmark structure

### 2.1 Task taxonomy

Five canonical tasks, each isolating ONE axis but combinable into
"all-axes" composite scores.

#### Task PA1 — Privacy-Aware Coordination
**Goal**: agents coordinate to reach goals using ONLY DP-noised
position observations of teammates.

**Inputs**: per-agent local observation (cost-to-neighbour features)
+ a DP-noised aggregate of teammate density (Laplace mechanism,
configurable ε).

**Metrics**:
- Goal reach rate (R)
- Privacy budget used per episode (E)
- Pareto frontier on (R, ε)

#### Task AR1 — Adversarial Resilience
**Goal**: maintain performance when F% of validators are
Byzantine (equivocation; submit malicious match-outcome blocks).

**Inputs**: standard arena + F% Byzantine ratio (0%, 10%, 20%, 33%)
+ slashing budget.

**Metrics**:
- Match conclusion rate
- Chain growth rate (blocks per minute)
- Fraction of Byzantine validators caught
- Performance retention vs F=0 baseline

#### Task MC1 — Multi-agent Cooperation under Encryption
**Goal**: agents trade goods to maximise GROUP welfare while seeing
only encrypted aggregates of partners' inventory.

**Inputs**: each agent has CKKS-encrypted view of other agents'
inventory totals (per-product) — never plaintext.

**Metrics**:
- Total welfare (sum of agent utilities)
- Gini coefficient (lower = more equitable)
- Number of trades per match
- Information-theoretic bound: did any agent learn another's
  plaintext inventory? (Should be NO.)

#### Task PB1 — Privacy-Budget Management
**Goal**: agents must allocate a fixed DP budget across N
information queries, choosing when to "spend" ε for high-fidelity
data and when to operate on stale/noised data.

**Inputs**: starting ε per match + N queries to make + each
query's ε cost is determined dynamically.

**Metrics**:
- Final goal-reach rate
- Budget exhaustion rate (matches where ε ran out)
- Strategic efficiency: reach goal / ε spent

#### Task LR1 — Linkability Resistance
**Goal**: train a policy whose trajectories do NOT reveal agent
identity to a downstream linkability attacker.

**Inputs**: standard arena + the linkability attack module trained
on the SAME agents' historical trajectories.

**Metrics**:
- Goal reach rate (utility)
- Linkability accuracy (privacy) — must drop below random guessing
  (1/n_agents) within ε of theoretical optimum
- Pareto frontier on (utility, linkability)

### 2.2 Combined "Penumbra-Bench Composite"
A single composite score: weighted combination of all five tasks
with documented weights. Designed so that gaming one task by ignoring
another lowers your composite score.

Composite = 0.25 × PA1 + 0.20 × AR1 + 0.20 × MC1 + 0.15 × PB1 + 0.20 × LR1

(Weights chosen by survey of the FL + privacy + ML safety community;
documented in the paper's supplementary material.)

### 2.3 Difficulty tiers

| Tier | Agents | Nodes | Episode length | Use case |
|---|---|---|---|---|
| **Tiny** | 5 | 10 | 100 ticks | Smoke test, CI |
| **Small** | 20 | 25 | 500 ticks | Hyperparameter sweeps |
| **Medium** | 50 | 50 | 2000 ticks | Standard benchmark |
| **Large** | 100 | 100 | 10000 ticks | Research extension |

## 3. Submission protocol

### 3.1 Artefact requirements

To submit a result to Penumbra-Bench, you provide:

1. **Trained policy artefact** — PyTorch `.pt` checkpoint with a
   defined input/output interface (NEIGHBOURS_K=6 features in,
   NEIGHBOURS_K+1 logits out).
2. **Config YAML** — hyperparameters used for training (not
   evaluation; eval is standardised).
3. **Method description** — Markdown file (1-3 pages) describing
   the approach.
4. **Reproducibility statement** — seeds used, total wall-clock
   time, hardware used.

### 3.2 Evaluation procedure

Submissions are evaluated by:

1. **Hash-pinning** the Penumbra commit + configuration that the
   submission targeted (so results are exactly reproducible).
2. **Running the standardised eval suite** — 5 tasks × 100 episodes
   per task × 5 different random seeds = 2500 episodes total.
3. **Generating a result JSON** with per-task metrics, composite
   score, and 95% confidence intervals.

Estimated time per submission: ~30 min on a Mac mini M4.

### 3.3 Submission channel

Phase 1 (months 0-6 post-launch): GitHub PR to
`Vadale/penumbra-bench-submissions` repo. Each PR adds a folder
under `submissions/<author>-<method>-<date>/`. Manual review by
maintainer; merge = added to leaderboard.

Phase 2 (month 6+): automate via GitHub Actions runner. PRs
trigger evaluation pipeline; result JSON auto-committed to a
public leaderboard.

Phase 3 (year 1+, contingent on traction): hosted submission
service (small free tier + paid lane for organisations that need
SLAs).

### 3.4 Leaderboard

Static site on GitHub Pages (free):
- `penumbra-arena.github.io/bench/`
- Top 20 submissions per task
- Composite score leaderboard
- Per-method "method cards" with description
- Filter by tier (Tiny / Small / Medium / Large)
- Filter by submission date (so new work is visible)
- Star history per submission (engagement)

## 4. Implementation tiers

### Tier 1 — Local benchmark runner (~5-6h)

**New file**: `packages/learning/penumbra_learning/benchmark.py`

```python
"""Run a policy through the Penumbra-Bench suite, output result JSON."""

from dataclasses import dataclass

@dataclass(slots=True)
class TaskResult:
    task_id: str
    score: float
    metric_values: dict[str, float]
    metric_ci_95: dict[str, tuple[float, float]]
    n_episodes: int
    wall_seconds: float

@dataclass(slots=True)
class BenchSubmission:
    submitter: str
    method: str
    tier: str  # "tiny" | "small" | "medium" | "large"
    tasks: tuple[TaskResult, ...]
    composite_score: float
    submission_timestamp_ns: int
    penumbra_commit: str
    pytorch_version: str
    hardware: str

def run_benchmark(
    policy_path: Path,
    tier: str = "medium",
    seed: int = 42,
) -> BenchSubmission:
    """Run a policy through all 5 tasks at the given tier."""
    ...
```

**New CLI**: `uv run python -m penumbra_learning.benchmark <policy.pt>`

**Tests**:
- `test_benchmark_runs_smoke` — runs a random policy through Tiny tier
- `test_benchmark_reproducibility` — same seed = same result
- `test_benchmark_metrics_in_bounds` — all metrics in [0, 1] or
  documented ranges
- `test_baseline_random_walk_below_1_pct_composite` — sanity check

### Tier 2 — Web leaderboard (~3-4h)

**New file**: `apps/web/src/pages/Bench.tsx` (new route `/bench`)

Renders the leaderboard from a `leaderboard.json` served from
GitHub Pages or `/api/leaderboard` on the backend.

**Backend endpoint**: `GET /benchmark/leaderboard` reads the JSON
file from the file system; bench results live in `state/bench/`.

### Tier 3 — Submission repo + CI automation (~6-8h)

**New repo**: `Vadale/penumbra-bench-submissions`

- README with submission format + instructions
- `.github/workflows/evaluate.yml` — runs `run_benchmark` on each PR
- `.github/workflows/update_leaderboard.yml` — on merge, regenerate
  `leaderboard.json`

### Tier 4 — Baseline methods catalogue (~6-8h)

Implement and submit a set of baseline policies so the leaderboard
isn't empty at launch:

| Baseline | Expected composite | Purpose |
|---|---|---|
| Random walk | ~0.10 | Floor reference |
| Greedy nearest-goal | ~0.25 | Naïve heuristic |
| MAPPO (shipped checkpoint) | ~0.45 | Pre-trained learned policy |
| MAPPO + DP-SGD finetune | ~0.40 | Privacy-aware variant |
| MAPPO + Byzantine robustness | ~0.43 | Adversarial-robust variant |
| MAPPO + linkability defence | ~0.41 | Privacy-utility tradeoff |
| Multi-agent SAC | ~0.30 | Classical actor-critic baseline |

Each baseline as a sub-folder in `submissions/baseline-*`.

## 5. Pedagogical and research positioning

### 5.1 For undergrads
A reference RL environment with extra dimensions beyond MuJoCo:
they learn that "good policy" isn't one number — it's a Pareto
frontier across utility, privacy, robustness, and equity.

### 5.2 For grad students + researchers
A citable benchmark with five well-defined tasks + composite +
metric CIs + baselines. Methodologically defensible: standardised
seeds, standardised hardware target, public submission protocol.
Citation count grows organically.

### 5.3 For industry (compliance / risk teams)
A standardised vendor-evaluation tool. "Has your model been
Penumbra-Bench evaluated? What was the composite?" becomes a
quick filter for procurement.

### 5.4 For OSS contributors
A clear way to contribute: submit a method. Each accepted submission
appears on the public leaderboard with the contributor's name +
GitHub link. Strong incentive structure.

## 6. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Benchmark gaming (overfit to eval seeds) | 5 seeds + held-out test seed pool drawn after each release |
| Hardware variance affects results | Standardised tier definitions + 95% CIs reported |
| Composite weights criticized | Publish individual task scores too; transparency about weights |
| Submission spam | Manual review in Phase 1; automated quality checks in Phase 2 |
| Insufficient baselines = empty leaderboard | Tier 4 ships 7 baselines at launch |
| Existing benchmarks dismiss us | Cite them explicitly + show the axis-gap they don't fill |

## 7. Out of scope

- Continuous control tasks (the arena is discrete-graph; expanding
  to continuous would be a separate Penumbra variant)
- Real-world dataset replacement (no medical / financial data;
  Penumbra is synthetic by design — that's a feature)
- LLM evaluation (Penumbra is multi-agent RL; LLM-eval is a
  different problem and well-served by other benchmarks)
- Single-agent baselines (we're explicitly multi-agent)

## 8. KPIs for the benchmark's success

| Metric | Target Month 3 | Target Month 12 |
|---|---|---|
| Total submissions | 7 (baselines) | 30+ |
| External submitters | 0 | 10+ |
| Academic citations | 0 | 5+ |
| GitHub stars on bench-submissions repo | 50 | 300 |
| Leaderboard page views / month | 50 | 1000 |
| Methods adopted on leaderboard from major labs | 0 | 1+ |

## 9. Implementation order (recommended)

1. Read this document end-to-end.
2. Implement Tier 1 (benchmark runner) — local, no infrastructure.
3. Submit 7 baselines (Tier 4) — populates the leaderboard.
4. Implement Tier 2 (web leaderboard) — static, lives on GitHub Pages.
5. Implement Tier 3 (CI automation) — only when submission volume
   warrants it (10+ external submissions or wait 3 months
   post-launch).

## 10. References

- Bellemare et al. "The Arcade Learning Environment: An Evaluation
  Platform for General Agents." JAIR 2013 (the ALE / Atari paper
  pattern).
- Brockman et al. "OpenAI Gym." 2016.
- Suarez et al. "Neural MMO 2.0: A Massively Multi-task Addition to
  Massively Multi-agent Learning." NeurIPS 2023 (a recent
  multi-agent benchmark with a similar ambition scope).
- Leibo et al. "Scalable Evaluation of Multi-Agent Reinforcement
  Learning with Melting Pot." ICML 2021.
- Henderson et al. "Deep Reinforcement Learning that Matters."
  AAAI 2018 (the methodological reference for honest RL benchmarks).
- Cobbe et al. "Leveraging Procedural Generation to Benchmark
  Reinforcement Learning." ICML 2020 (ProcGen).

---

**End of plan.** Penumbra-Bench is the artefact that turns a
"working educational tool" into "academic infrastructure". Every
paper that cites it makes the next paper more likely. The flywheel
takes ~12 months to spin up but compounds permanently.
