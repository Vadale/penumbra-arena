# Penumbra — Usage guide

Hands-on quickstart for running Penumbra, driving the dashboard, and
using the three CLIs (`pna`, `psh`, `pno`). Everything below runs
locally on macOS; no external services.

For the architecture map see [`CLAUDE.md`](CLAUDE.md), for the build
history see [`ROADMAP.md`](ROADMAP.md), for step-by-step recipes when
extending the code see [`PROMPTING_GUIDE.md`](PROMPTING_GUIDE.md).

---

## 1. Boot in 60 seconds

```sh
# Backend (FastAPI + tick loop on port 8100)
PENUMBRA_SEED=42 \
PENUMBRA_MAPPO_CHECKPOINT="$(pwd)/checkpoints/mappo_v0.pt" \
uv run uvicorn penumbra_transport.api:app --port 8100

# Frontend (separate terminal — Vite dev server on 5173)
PENUMBRA_API_PORT=8100 pnpm --filter web dev
```

Open <http://localhost:5173>. The first visit shows a **Welcome modal**
+ **Tour overlay**; dismiss them once and the choice persists in
localStorage.

The default tick rate is **2 Hz** so you can follow what's happening.
Adjust live with the **speed widget** in the header
(`pause / .5x / 1x / 2x / 5x / 10x`).

### Tunable environment variables

| Var | Default | What it does |
|---|---|---|
| `PENUMBRA_SEED` | 42 | Seed fan-out for `random` / `numpy` / `torch` / `jax` |
| `PENUMBRA_TICK_HZ` | 2.0 | Initial simulation tick rate (Hz) |
| `PENUMBRA_API_PORT` | 8000 | Backend port (we use 8100 above) |
| `PENUMBRA_HE_BACKEND` | `openfhe` | `openfhe` or `tenseal` (fallback) |
| `PENUMBRA_MAPPO_CHECKPOINT` | unset | Path to a `.pt` checkpoint; falls back to random walk if absent |
| `PENUMBRA_ENABLE_PTY` | unset | `1` to enable the real `zsh` PTY in the bottom shell tab |

### Install the CLIs once

```sh
uv tool install ./packages/attacker      # pna
uv tool install ./packages/shell_coach   # psh
uv tool install ./packages/operator      # pno
```

After install they're on `$PATH` system-wide. All three default to
`--api http://localhost:8000`; **pass `--api http://localhost:8100`**
when running against the boot above, OR re-launch the backend with the
default port. The examples below assume port 8100.

---

## 2. The three CLIs at a glance

| CLI | Role | Stateful? |
|---|---|---|
| `pno` | **Operator** — drive the player-controlled agent, query DP, sign messages, list / replay sessions | Yes — needs the running backend |
| `pna` | **Attacker** — try replay / linkability / Dinur-Nissim / Byzantine / timing / SNARK forgery; world snapshot save/load | Mostly local; chain commands hit the backend |
| `psh` | **Shell coach** — 19 lessons (filesystem / pipes / processes / networking / crypto / scripting + 8 cross-pillar stories) + explain / suggest / interpret helpers | Standalone — no backend needed |

---

## 3. `pno` — the Operator console

### 3.1 Bootstrap the operator slot

```sh
pno enable --api http://localhost:8100
# {"enabled": true, "agent_id": 50, "starting_coins": 1000, "starting_epsilon": 5.0, ...}

pno status --api http://localhost:8100
# {"position": 0, "coins": 1000, "epsilon_remaining": 5.0, "queue": [], "score": {...}}
```

`pno enable` reserves agent slot `N+1` (where N is the simulated
population, default 50) and gives you a starting wallet + privacy budget.
You can `pno disable` to release the slot, or just leave it active.

### 3.2 The 11 action verbs

| Command | Args | Cost | Effect |
|---|---|---|---|
| `pno move N` | target_node | edge_cost coins | Move to a neighbour node |
| `pno buy P Q` | product, qty | market price × qty | Buy from the local city market |
| `pno sell P Q` | product, qty | (earns coins) | Sell to the local city market |
| `pno dispatch CITY P Q REWARD` | city, product, qty, reward | 5 coins | Place a logistics order pre-assigned to you |
| `pno cancel ORDER_ID` | order id | refund 5 coins | Release a pending order back to the pool |
| `pno query-dp STAT EPS` | statistic, epsilon | EPS from budget | DP-noised query (`money_supply` / `price_index` / ...) |
| `pno sign MSG` | hex message | 0 | Return a Dilithium signature |
| `pno verify MSG SIG PK` | msg, sig, pk | 0 | Verify a Dilithium triple |

> Add `--api http://localhost:8100` to every command (or alias it).

### 3.3 A full operator session (logistics scenario)

```sh
alias pno8100='pno --api http://localhost:8100'   # one-time

pno8100 enable
pno8100 status                                  # see starting state
pno8100 move 3                                  # walk to node 3
pno8100 dispatch 7 0 50 12.5                    # ship 50 units of product 0 to city 7 for 12.5 coins
pno8100 query-dp money_supply 0.1               # take a DP measurement, spends ε=0.1
pno8100 status                                  # see updated coins / epsilon / score

pno8100 sessions                                # list past sessions
pno8100 replay <session_id>                     # re-run + scorecard diff
```

The dashboard's `/operator` route **mirrors all of this in the
browser** — Action Builder dropdown, action log, scorecard. Use whichever
surface you prefer; both hit the same `/operator/*` REST endpoints.

### 3.4 Scenarios (12 starter drills)

Scenarios are managed via REST (no dedicated `pno scenarios` subcommand
yet — use the `/operator` browser page or `curl`):

```sh
# List all 12 scenarios
curl -s http://localhost:8100/operator/scenarios | jq

# Start one
curl -s -X POST http://localhost:8100/operator/scenarios/defense_dp_drain/start | jq

# Live progress (1 Hz polling from the browser; or curl it)
curl -s http://localhost:8100/operator/scenarios/defense_dp_drain/status | jq

# Abandon
curl -s -X POST http://localhost:8100/operator/scenarios/defense_dp_drain/abandon
```

The 4 difficulty tiers go from `tutorial_*` (5 actions to win) to
`expert_*` (multi-step compositions). Each scenario declares its
preconditions, victory + failure clauses (tick-based, never wall-clock),
and per-axis scorecard weights so the composite is comparable across
runs. Save & Resume auto-snapshots after every action — close the tab,
reopen, the banner offers `[Resume]`.

---

## 4. `pna` — Adversarial attacker console

Each subcommand is an attack with a doctring that documents **how it
works**, **why Penumbra defends against it**, and **what would break it**.

```sh
pna replay-cmd
# Demonstrates: forging a replayed Dilithium signature without a
# tick-counter binding succeeds; with the binding, the verifier rejects.

pna linkability-cmd --agents 8 --matches 50
# De-anonymise an agent from movement traces. Shows attacker accuracy
# WITH vs WITHOUT k-anonymity + padding defenses.

pna dp-reconstruct --bits 64 --queries 400 --noise 0.1
# Dinur-Nissim row reconstruction. Demonstrates that without the DP
# accountant capping ε, the attacker recovers the private vector.

pna byzantine-cmd
pna byzantine-cmd --submit-self-slash    # hits the real chain /chain/_demo/self-slash

pna timing --samples 50
# Time CKKS .add on sparse vs dense ciphertexts; Welch t-test.
# Modern CKKS pads to the full polynomial degree -> t-stat stays small.

pna snark-forge
# Attempt a Groth16 forgery; verifier rejects (G2 subgroup membership
# is checked since the 2026-05-24 audit closure).

pna world save my-snapshot               # snapshot current chain to state/snapshots/my-snapshot/
pna world list
pna world load my-snapshot               # rewind the live chain
```

All 6 attacks are also reachable from the dashboard via the relevant
tile in the "defenses + attacks" section of AnalyticsPanel.

---

## 5. `psh` — Shell coach

Standalone tutor for macOS / Unix terminal fluency. No backend needed.

```sh
psh lessons                                # list all 19 lessons
psh lesson filesystem                      # walk through "ls / find / mdfind / du / eza"
psh lesson story_bullwhip_leak             # cross-pillar story: logistics bullwhip + DP leak

psh explain "find . -name '*.py' -exec grep -l foo {} +"
# Breaks down each flag with semantics + alternatives.

psh suggest "ls"
# Suggests next commands: "ls | wc -l", "du -sh *", "eza --tree -L 2".

psh interpret "zsh: command not found: rg"
# Fix hint: "brew install ripgrep"
```

The 19 lessons cover: filesystem, text processing, pipes & redirection,
processes, networking, archives, permissions, macOS-specific tools,
modern CLI replacements (rg/bat/eza/fzf/zoxide/delta/jq), crypto-adjacent
tools (openssl/gpg/age/ssh-keygen), scripting hygiene + 8 cross-pillar
stories (bullwhip-leak, honest-validator, replay-chain, dp-starvation,
fl-backdoor, carrier-extortion, mix-net-defense, ctf-speedrun).

The embedded shell coach side-panel in the dashboard runs the same
allow-listed commands without the user needing a terminal.

---

## 6. Dashboard interactions (no terminal required)

### 6.1 Navigation

| URL | What |
|---|---|
| `/` | Main dashboard (arena + analytics + chain + bottom panel) |
| `/operator` | Cyber-range Console (Status / Action Builder / Log / Score) |
| `/bench` | Penumbra-Bench leaderboard (5 tasks × 4 tiers) |
| `/config` | Live configuration editor (5 runtime mutable + 3 restart-required + 2 read-only badges) |

### 6.2 Header controls

- **Speed widget**: `pause / .5x / 1x / 2x / 5x / 10x`. Live POST to
  `/control/tick_hz`; the simulation rate updates immediately.
- **Notification badge**: ✓ active / ○ off / × denied / — unsupported.
  Click the `notifications` tile to opt in per event kind.

### 6.3 Arena (left column)

- **4 view modes**: `map / world / graph / 3d` — toggle via overlay
  tabs at the top-right of the arena.
- **Click on an agent** → slide-in **AgentDetailPanel** showing id,
  position, money, current policy (mappo / random_walk), MAPPO action
  distribution (bar chart), recent_actions list, encrypted_state bytes,
  Kyber + Dilithium key fingerprints, last observation stats. Use
  Prev/Next to cycle through.
- **Hover** a tile or edge → tooltip with weight / weather / agent count.
- **TimeScrubber** below the arena: drag back through the last 500
  ticks; banner overlays "REPLAY MODE" in ember; `[Resume Live]` snaps
  back. `[Play back]` auto-advances at 1 Hz.

### 6.4 Analytics panel (right column)

95 clickable tiles in 12 named sections (statistics / econometrics /
linalg & topology / economy / logistics / RL & FL / chain / privacy & DP
/ crypto HE+PQ / crypto SMPC+ZK / defenses + attacks / interactive sandboxes).

**Click any tile** → DetailModal with:
- Educational description (the "why", not just the "what").
- Live chart fetched from the backend.
- For 19 tiles: a cyan-bordered "Try it in your shell" block with the
  exact `pna` / `psh` / `pno` / `curl` command.
- For 4 tiles (`inflation`, `garch`, `signing_verified`, `bls_aggregate`):
  an inline `Trigger this event` button that POSTs `/control/inject`.
- For 7 tiles (`inflation`, `garch`, `training_curves`, `wealth`,
  `candles`, `mempool`, `signing_verified`): **ExportButtons**
  `[csv] [json] [png] [ipynb]` to download the underlying data.
- For ANY tile: `Download as PNG` to capture the chart as an image
  (client-side, no server roundtrip).

### 6.5 Brush-select on 5 time-series charts

`TrainingCurves`, `InflationChart`, `GarchChart`, `CandlestickChart`,
`LineChart` — drag horizontally inside the chart to select a window.
A `BrushStats` card appears below: `Window: tick A..B · mean=X · std=Y ·
n=Z · [× clear selection]`.

### 6.6 Lab Experiments tile

Centralized panel for one-click triggers:
- `[Trigger CPI shock]` ratio input — emits `cpi.shock`
- `[Force GARCH spike]` magnitude input — emits `garch.spike`
- `[Block agent #]` id + reason — emits `agent.blocked`
- `[Slash validator #]` id — emits `validator.slashed`
- `[Step 1] [Step 10] [Step 100]` — manual tick advance (works even
  when paused via the speed widget)
- Recent injections log (last 20, this session)

Each trigger fires through the in-process EventBus so the 5 cross-pillar
handler tiers react in real time (logistics retune, market regime change,
DP cadence degrade, FL trainer skip, etc.).

### 6.7 Bottom panel — 3 tabs

| Tab | What |
|---|---|
| **coach** | Allow-listed `pna` / `psh` chips. Click → runs in-process. Safe. |
| **shell** | Real macOS `zsh` PTY. Requires `PENUMBRA_ENABLE_PTY=1` at backend boot. Welcome banner: `==> penumbra-shell — type psh lessons to start tutorials, pna --help for attacks, pno --help for the operator console` |
| **repl** | Sandboxed Python REPL with `pna.api` pre-imported. |

### 6.8 Other interactive tiles

- **CTF**: pick 1 of 5 challenges, the hint from `acceptance.hint` is
  surfaced, submit a flag in the text box.
- **Custom Policy**: write a Python `policy(state, obs) -> action`,
  the backend AST-validates and runs it sandboxed. Errors are surfaced
  as `policy rejected — <first line> · [show full traceback]`.
- **World Branches**: save current world to a named branch, list, load.
- **Branch Compare**: pick two branches → 3 metrics side-by-side with
  shared y-axis.
- **Story Mode**: 8 guided cross-pillar walkthroughs.
- **Achievements**: 9 unlockable badges (Curious / Explorer / Operator /
  Drillmaster / Capture / Flagrunner / Lab Rat / Speed Demon /
  Completionist).
- **Operator Scenarios**: pick 1 of 12 cyber-range drills, the
  ScenarioRunner snapshots your start state and evaluates victory +
  failure clauses while the panel is open and after every action.

---

## 7. The most-useful REST endpoints

```sh
# Health + control
curl http://localhost:8100/health
curl http://localhost:8100/control/tick_hz
curl -X POST -d '{"tick_hz": 5}' -H 'Content-Type: application/json' http://localhost:8100/control/tick_hz
curl -X POST -d '{"n": 10}' -H 'Content-Type: application/json' http://localhost:8100/control/step

# Agents
curl http://localhost:8100/agents | jq
curl http://localhost:8100/agents/12 | jq

# Events
curl 'http://localhost:8100/events/recent?limit=20' | jq

# Inject events live
curl -X POST -d '{"kind":"cpi.shock","payload":{"ratio":1.5}}' -H 'Content-Type: application/json' \
  http://localhost:8100/control/inject

# Configuration
curl http://localhost:8100/config | jq
curl -X POST -d '{"reward_weights":{"dispatch_bonus":12.0}}' -H 'Content-Type: application/json' \
  http://localhost:8100/config

# Operator scenarios
curl http://localhost:8100/operator/scenarios | jq
curl -X POST http://localhost:8100/operator/scenarios/<id>/start

# Save & Resume
curl http://localhost:8100/operator/sessions/resumable | jq

# Export
curl -o inflation.csv 'http://localhost:8100/export/chart/inflation?format=csv'
curl -o inflation.ipynb 'http://localhost:8100/export/notebook?metric=inflation'
```

Full endpoint list lives in `packages/transport/penumbra_transport/api.py`
(~150 routes). The dashboard's `network` tab in DevTools is the easiest
way to discover what's available.

---

## 8. Common workflows (cookbook)

### Run the smallest "end-to-end" demo

```sh
# Terminal 1
PENUMBRA_SEED=42 \
PENUMBRA_MAPPO_CHECKPOINT="$(pwd)/checkpoints/mappo_v0.pt" \
PENUMBRA_ENABLE_PTY=1 \
uv run uvicorn penumbra_transport.api:app --port 8100

# Terminal 2
PENUMBRA_API_PORT=8100 pnpm --filter web dev

# Browser
open http://localhost:5173
```

Then in the dashboard: `/` → click an agent → see the inspector. Click
the `Lab` tile → trigger a CPI shock. Open `/operator` → enable → run
3 actions → watch the scorecard. Open `/config` → change `tick_hz` to 5.

### Play a scenario from terminal-only

```sh
alias api='http://localhost:8100'
pno --api $api enable

# Pick a scenario via REST
curl $api/operator/scenarios | jq '.scenarios[].id'
curl -X POST $api/operator/scenarios/tutorial_first_dispatch/start

# Take actions
pno --api $api move 2
pno --api $api dispatch 5 0 30 8.0
pno --api $api status

# Check scenario progress
curl $api/operator/scenarios/tutorial_first_dispatch/status | jq
```

### Run an attack and see the defense

```sh
pna replay-cmd                                   # naive vs tick-bound Dilithium
pna dp-reconstruct --queries 400                 # Dinur-Nissim w/o DP accountant
pna byzantine-cmd --submit-self-slash --api http://localhost:8100
```

The dashboard mirrors the same in the `defenses + attacks` section
tiles (e.g. `attack_replay`, `attack_dp_reconstruct`).

### Export a chart for an experiment writeup

```sh
# Browser: open DetailModal of any of the 7 exportable charts -> [csv][json][png][ipynb]
# OR via terminal:
curl -o garch.json 'http://localhost:8100/export/chart/garch?format=json'
curl -o garch.png 'http://localhost:8100/export/chart/garch?format=png'
curl -o garch.ipynb 'http://localhost:8100/export/notebook?metric=garch'
jupyter notebook garch.ipynb
```

### Walk through a shell-coach lesson while running the sim

```sh
# Backend running in another terminal; lesson 5 hits localhost:8100
psh lesson networking_curl
```

The lesson includes steps like `curl http://localhost:8100/health` so
your terminal practice is rooted in the running stack.

### Save a world, perturb, compare, rollback

```sh
pna world save baseline
# Trigger a few experiments via dashboard Lab panel...
pna world save after-experiments
pna world list
# In the browser: open Branch Compare tile -> pick baseline + after-experiments
pna world load baseline    # rewind the live chain
```

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/operator` returns `{"detail":"Not Found"}` | Stale vite proxy intercepts the bare path | Restart `pnpm --filter web dev` (the bypass is in `vite.config.ts`) |
| Agents move too fast | Default tick rate too high | Use the speed widget or `PENUMBRA_TICK_HZ=1` at boot |
| Shell terminal shows "PTY shell disabled" | `PENUMBRA_ENABLE_PTY` unset | Re-launch backend with `PENUMBRA_ENABLE_PTY=1` |
| `pno` defaults to port 8000 but server is on 8100 | CLI default | Always pass `--api http://localhost:8100` or alias |
| Welcome modal won't go away | localStorage in private-browsing mode | Persistent storage disabled; close + reopen normal window |
| Charts show "warming…" forever | Backend endpoint 500ed | DevTools network tab → look at the failing fetch (now visible via `useFetchJsonOnce` errors) |
| Memory > 8 GB | CKKS pkg too aggressive OR too many agents | Lower `n_agents` in `/config` (restart required) OR set `PENUMBRA_HE_BACKEND=tenseal` |
| Tests fail to find chromium | Playwright browser not installed | `/opt/anaconda3/bin/playwright install chromium` |

---

## 10. Where to look next

- **Concept "why" per tile**: open DetailModal — every entry has a
  description.
- **Extend the dashboard with a new tile**: follow the 5-step recipe in
  [`CLAUDE.md`](CLAUDE.md) ("Dashboard tile pattern").
- **Add a new analytics module**: 5-step recipe in
  [`CLAUDE.md`](CLAUDE.md) ("Adding a new analytics module").
- **Crypto / chain changes**: route through the `crypto-auditor`
  Claude Code agent before commit (see [`CLAUDE.md`](CLAUDE.md)).
- **Live-edit a scenario YAML**: `packages/operator/scenarios/*.yaml`.
- **Add a CTF challenge**: `packages/ctf/challenges/*.yaml`.
- **Add a shell-coach lesson**: `packages/shell_coach/lessons/*.yaml`.

---

## TL;DR (one screen)

```sh
# Boot
PENUMBRA_SEED=42 \
PENUMBRA_MAPPO_CHECKPOINT="$(pwd)/checkpoints/mappo_v0.pt" \
PENUMBRA_ENABLE_PTY=1 \
uv run uvicorn penumbra_transport.api:app --port 8100 &
PENUMBRA_API_PORT=8100 pnpm --filter web dev &
open http://localhost:5173

# Operator
alias pno='pno --api http://localhost:8100'
pno enable && pno move 3 && pno dispatch 5 0 30 8 && pno status

# Attacker
pna replay-cmd
pna dp-reconstruct --queries 400

# Shell coach
psh lessons
psh lesson story_dp_starvation

# Trigger live
curl -X POST -d '{"kind":"cpi.shock","payload":{"ratio":1.5}}' \
  -H 'Content-Type: application/json' http://localhost:8100/control/inject

# Export
curl -o garch.csv 'http://localhost:8100/export/chart/garch?format=csv'
```
