# Penumbra-Data — Synthetic Dataset Specification

A pre-computed, reproducible dataset published on Hugging Face Hub
that captures Penumbra's multi-modal output — agent trajectories,
trade events, encrypted heatmaps, match outcomes, chain blocks, and
labelled adversarial probes — as a public research resource.

**Status**: planning, deferred to post-OSS-launch (target as v1.0
launch-day asset OR as v1.1 release at month 1-2 of
[`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md)).

Sister documents:
- [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) — uses Penumbra-Data as
  the evaluation corpus
- [`FEDERATED_LEARNING_PLAN.md`](FEDERATED_LEARNING_PLAN.md) — uses
  Penumbra-Data as local-client data sources

---

## 1. The case for a synthetic dataset

### 1.1 What's broken in current synthetic data
The synthetic-data ecosystem has three structural problems:

1. **Hidden generative process** — most synthetic datasets (Faker,
   most LLM-generated CSVs) come from black-box generators. You
   can't tell what's signal vs noise.
2. **No ground truth on adversarial events** — anomaly-detection
   benchmarks often have ad-hoc labels.
3. **No privacy provenance** — datasets that claim "privacy
   preserving" usually mean "anonymised post-hoc", which is fragile.

Penumbra produces data with NONE of these problems:

- **Open generative process** — every trajectory is reproducible
  from `(seed, config_hash, commit_sha)`. Source code is public.
- **Built-in ground truth on adversarial events** — when the
  attacker module fires, the event is labelled in the data.
- **Genuine privacy provenance** — the DP budget, the CKKS
  ciphertexts, the noise scales are all logged at generation time.

### 1.2 Why this matters strategically

A widely-cited dataset is one of the most durable forms of
academic impact: papers cite the dataset for as long as it's used,
which can be decades (consider MNIST, Penn Treebank, ImageNet).

Each citation grows GitHub visibility, search rank, and the
"awesome-datasets" list inclusions. Penumbra-Data is the kind of
asset that **continues earning attention years after release**.

## 2. Dataset structure

### 2.1 Modalities

Each Penumbra run generates seven correlated streams that we
publish as separate parquet files:

| Modality | Records per tick | Use case |
|---|---|---|
| `positions` | 50 (agent_id, x, y, tick) | Multi-agent trajectory analysis |
| `trades` | 0-N (tick, agent_id, node_id, product, side, qty, price) | Economic / market behaviour |
| `inventory` | 50 × 30 (agent_id, product, count, tick) | Inventory dynamics |
| `prices` | 50 nodes × 30 products (city, product, price, tick) | Time-series forecasting |
| `heatmaps` | 1 (tick, density_vector[n_nodes], dp_noise_scale, epsilon_spent) | Privacy-preserving aggregate |
| `matches` | 0-1 (match_id, winner, start_tick, end_tick, end_reason) | Sequence prediction |
| `attacks` | 0-N (tick, attack_type, target_agent, success) | Anomaly detection labels |
| `chain_blocks` | 0-1 (height, hash, validator, n_outcomes, n_slashings) | Transactional data |

### 2.2 Dataset tiers

| Tier | Wall time | Trajectories | Files | Compressed size | Use case |
|---|---|---|---|---|---|
| **Mini** | 5 min | ~100 | 7 × parquet | ~5 MB | Smoke test, tutorial |
| **Standard** | 1 hour | ~1,200 | 7 × parquet | ~100 MB | Most research use |
| **Large** | 24 hours | ~30,000 | 7 × parquet, sharded | ~3 GB | Robust statistical analysis |
| **Mega** | 1 week | ~200,000 | 7 × parquet, sharded | ~20 GB | Large-scale ML pretraining |

All tiers reproducible from `(seed, tier, penumbra_commit_sha)`.

### 2.3 Schema

Published in `schemas/` as JSON Schema files + a Python validator
in `penumbra_data.schema`.

Example `positions.parquet` schema:
```yaml
- name: tick
  type: int64
  description: "Tick counter from simulation start (0-indexed)"
- name: agent_id
  type: int16
  description: "Agent identifier, persistent across matches"
- name: node_id
  type: int16
  description: "Graph node the agent is currently on"
- name: match_id
  type: int32
  description: "Match identifier"
- name: dp_eps_used_so_far
  type: float64
  description: "Cumulative DP epsilon spent up to this tick"
```

Schema includes versioning: any change bumps a `schema_version`
field. Old schemas remain published; new ones get a new HF revision.

### 2.4 Provenance manifest

Every dataset release includes a `provenance.json` with:
```json
{
  "penumbra_commit": "abc123...",
  "penumbra_version": "v1.2.0",
  "tier": "standard",
  "seed": 42,
  "wall_seconds_to_generate": 3612.5,
  "hardware": "Mac mini M4, 16 GB RAM",
  "config_hash": "sha256(SimulationConfig serialised)",
  "schema_version": "1.0",
  "modalities_included": ["positions", "trades", "..."],
  "n_trajectories": 1234,
  "n_total_ticks": 4321099,
  "n_matches": 567,
  "n_chain_blocks": 89,
  "n_attack_events": 12,
  "dp_total_epsilon": 1000.0,
  "dp_epsilon_spent": 982.3,
  "license": "CC-BY-4.0"
}
```

## 3. Distribution

### 3.1 Hugging Face Hub
Primary distribution channel — free, indexed by Google Scholar,
trusted by researchers.

Repo: `huggingface.co/datasets/Vadale/penumbra-data`

Structure:
```
penumbra-data/
├── README.md                       # Dataset card (HF format)
├── provenance.json
├── schemas/
│   ├── positions.schema.json
│   └── ...
├── mini/
│   ├── positions.parquet
│   ├── trades.parquet
│   └── ...
├── standard/
│   └── ...
├── large/
│   ├── positions/                  # sharded
│   │   ├── 00000.parquet
│   │   └── 00001.parquet
│   └── ...
└── mega/
    └── ...
```

### 3.2 Direct download (mirror)
GitHub Releases + R2 / Hetzner mirror for users who prefer not to
use HuggingFace. Direct download URLs in the dataset card.

### 3.3 Datasets library compatibility
```python
from datasets import load_dataset
ds = load_dataset("Vadale/penumbra-data", "standard")
# ds["positions"], ds["trades"], etc.
```

Implement the HF `datasets` library loader so the dataset shows up
in the `datasets` search UI (huge traffic source).

## 4. Implementation tiers

### Tier 1 — Generator + Mini dataset (~4-5h)

**New file**: `scripts/generate_dataset.py`

```python
"""Run Penumbra for N hours, capture all 7 modalities to parquet.

Usage:
    uv run python scripts/generate_dataset.py \\
        --tier standard \\
        --output state/datasets/penumbra-standard-v1.0 \\
        --seed 42
"""

import polars as pl
from penumbra_core.simulation import Simulation

# Hook into orchestrator.pipeline observers to capture each
# modality.  Write to parquet shards every N minutes.
```

**New file**: `packages/data/penumbra_data/schema.py` — JSON schema
+ validator.

**Tests**:
- `test_mini_dataset_generation_smoke` — 5 min run produces all 7
  files
- `test_dataset_schema_validates` — read a parquet file, assert
  every column matches schema
- `test_dataset_reproducibility` — same seed = same files (hash
  equality of parquet bytes)

**Acceptance**: ship the Mini tier (~5 MB) as `state/datasets/mini/`
in the public repo.

### Tier 2 — Standard tier + Hugging Face publication (~3-4h)

- [ ] Run Standard tier generation (1 hour wall time).
- [ ] Validate.
- [ ] Write a HuggingFace dataset card (`README.md` in HF format).
- [ ] Upload to `huggingface.co/datasets/Vadale/penumbra-data`.
- [ ] Test loading via `datasets.load_dataset`.
- [ ] Cross-link from Penumbra README.

### Tier 3 — Large tier + Datasets library loader (~4-5h)

- [ ] Run Large tier (24-hour wall time on M4; align with the
  stress-test cycle so we get both for free).
- [ ] Implement `datasets/penumbra-data/penumbra-data.py` loader.
- [ ] Submit dataset to:
  - HF "Trending datasets" by getting initial likes from early users
  - `awesome-public-datasets`
  - `awesome-synthetic-data`

### Tier 4 — Mega tier + research-grade documentation (~8-10h)

- [ ] Run Mega tier (1 week wall time; possibly multiple seeds in
  parallel if a 2nd M4 available).
- [ ] Write a "How researchers use Penumbra-Data" tutorial notebook
  (Jupyter; uploads to HF).
- [ ] Reference baselines:
  - LSTM forecaster on prices
  - Anomaly detector trained on attack labels
  - FL benchmark using positions as local data
- [ ] Submit a paper or short note to a Datasets-and-Benchmarks
  venue.

## 5. Use cases (publish these as tutorial notebooks)

Each notebook becomes content for promotion (blog posts, conference
demos).

1. **Multi-agent trajectory forecasting** — given the first 100
   ticks, predict positions for the next 50.
2. **Anomaly detection on attack labels** — train a classifier on
   the labelled attack events; evaluate on held-out time windows.
3. **Federated learning benchmark** — split agents into N FL
   clients, each with their own positions; evaluate FedAvg vs Krum
   vs centralised.
4. **Privacy-preserving inference** — given only the DP-noised
   heatmap stream, infer the true position distribution. Measure
   the error vs ε.
5. **Synthetic stock-like time series** — use prices as a
   training corpus for a price-forecasting LSTM.
6. **Inventory management** — predict stockout events.
7. **Causal effect estimation** — agents that join a coalition vs
   don't; measure ATE of coalition-joining on success rate.

## 6. Licensing

**CC-BY-4.0** for the data (researchers can use, must cite).

**MIT** for the generator code (consistent with the rest of
Penumbra).

Provenance: clearly state the data is synthetic, derived from a
public open-source generator, no personal information, no medical
or financial data, no real-world subject data.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Users assume the data is real-world | Mandatory "SYNTHETIC" label in every modality file + dataset card |
| Schema drift across versions | Schema versioning + old releases preserved on HF |
| Large file sizes blow up download | Sharded parquet (Tier 3+) + Hugging Face streaming-compatible |
| Cannot be cited if not archived | Hugging Face mirrors to Zenodo on request for DOI |
| Researchers find the data "too synthetic" | Document the OU process + heterogeneity choices explicitly; provide tiers from toy to research-grade |

## 8. KPIs

| Metric | Target Month 3 | Target Month 12 |
|---|---|---|
| Total downloads on HF | 200 | 5,000+ |
| Citations in academic papers | 0 | 3+ |
| Tutorial notebooks published | 3 | 7 |
| Mega tier downloads | 0 | 50+ |
| Forks of the dataset repo | 0 | 10+ |

## 9. Out of scope

- Real-world data integration (Penumbra is synthetic by design)
- Multi-language dataset cards (English only at launch; translations
  later)
- Streaming / live updates (snapshots only)
- Personal identifying information (NEVER — it's all synthetic)

## 10. Implementation order

1. Read this document end-to-end.
2. Implement Tier 1 (generator) — runs against existing Penumbra
   instance, no architectural changes needed.
3. Generate Mini tier + commit to repo (tracked in git, < 10 MB).
4. Implement Tier 2 (Hugging Face publication of Standard tier).
   Coordinate timing with the OSS launch — Standard tier publication
   is itself a launch artefact.
5. Tier 3 (Large) follows after Logistics Tier 1 (so the dataset
   has logistics + economy modalities).
6. Tier 4 (Mega + research notebooks + paper note) is a 6-9 month
   horizon item.

## 11. References

- ImageNet, MNIST, CIFAR — the citation-flywheel exemplars.
- The Pile (EleutherAI) — for the "open generative process" angle.
- BIG-bench (Google Research) — for the modular task-suite pattern.
- AnyLogic synthetic datasets — for what NOT to do (proprietary,
  hard to reproduce).
- Common Crawl — for the value of pure scale + provenance.
- Hugging Face Datasets documentation:
  `huggingface.co/docs/datasets/share`.

---

**End of plan.** Penumbra-Data is the lowest-effort, highest-leverage
asset Penumbra can ship. It makes the project citable, downloadable,
and indexable in a way that pure-code OSS isn't. The first 100
downloads compound into the next 1000.
