# Penumbra — Post-Stress Review & Optimization Plan

This document is the **operating script** for the review pass that
runs after the 24h stress test ends. It exists so we don't waste an
hour re-deciding what to prioritize when the stress test report lands.

Order: triage stress findings → frontend audit → backend perf hotspots
→ UI/UX polish → release.

**Pre-requisite**: `state/stress/run-<ts>.csv` + the auto-generated
`-report.md` from `scripts/analyze_stress.py`.

---

## Step 0 — Triage from the stress report (~30 min)

Open the report. For each finding:

| Severity | Action |
|---|---|
| 🔴 CRIT | Add to "fix-before-anything" list. Block release on this. |
| 🟡 WARN | Add to "investigate-during-perf-pass" list. |
| 🟢 OK | Note in `ROADMAP.md` as "verified". |

Track in a simple checklist below. Update as we go.

```
- [ ] CRIT-1 (placeholder, to fill in)
- [ ] WARN-1 (placeholder)
```

## Step 1 — Frontend audit cleanup (~2-3h)

Goals (independent of stress findings). **Frontend audit measured
2026-05-23**:

1. **Extract shared chart primitives.** Measurements:
   - `Stat({label, value, accent, ember, caption})` re-declared in
     **45 chart files**
   - `Verdict({label, ok, caption, inverted})` re-declared in **7
     files**
   - `Block({label, value, accent})` re-declared in **5 files**
   - Estimated savings on extraction: **500-800 LOC**
   - **Plan**:
     - Create `apps/web/src/charts/_shared/Stat.tsx`
     - Create `apps/web/src/charts/_shared/Verdict.tsx`
     - Create `apps/web/src/charts/_shared/Block.tsx`
     - Replace local declarations file-by-file (~15 min/file × 45 = ~12h
       if done strictly mechanically, OR do it via a single sed pass
       in 30 min — recommended approach: write a one-shot codemod
       script and run with `pnpm test` after each batch).
     - Net: ~600 LOC removed + canonical visual style guaranteed by
       single source of truth.

   **⚠️ Found during audit**: `streams/dashboard.ts` polls `/dashboard`
   every **500ms**. That's 2× per second and the endpoint returns a
   ~40-field JSON snapshot. Likely contributes to CPU% under stress.
   Recommend: 1500ms (3× slower, still feels real-time).

2. **Audit imports.** Run `pnpm exec biome check src` and address any
   `unused import` warnings (currently filtered to warnings; promote
   the critical ones to errors).

3. **Audit poll cadences.** Cross-check `src/charts/*.tsx`
   `setInterval` ms values against the M4 budget. Targets:
   - PyTorch forward passes (saliency, value-map, GAT, policy): ≥ 4s
   - py_ecc Groth16 (ZK, snark-forge, multiplier): cache + 8s poll
   - Stateful HTTP polls: 1.5-2s OK
   - Pure read endpoints (chain/mempool/vrf): 1.5s OK

4. **Identify orphaned components.** **Found during audit**: 0 dead
   components. All `src/charts/*.tsx` files are imported either by
   `DetailModal.tsx` or by a test. Skip this step.

5. **Consolidate the wired-up sets.** The `Cell` tile in
   `AnalyticsPanel.tsx`, the `MetricKind` union, the
   `mapMetricToHistoryKey` exclude list, and the `DetailModal` route
   `if (metric === ...)` chain all carry the same N-tile invariant.
   This is correct-by-paranoia but brittle. Consider:
   - A central `chartRoutes.ts` that lists `(MetricKind, Component,
     META)` triples once, imported by both `DetailModal` and
     `AnalyticsPanel`.
   - Reduces 5-place edits per new tile to 1-place.

## Step 2 — Backend perf hotspots (~3-4h, conditional on stress findings)

Candidates already KNOWN from the codebase to be worth measuring:

### 2.1 CKKS allocation (every 1s in encrypted_heatmap.compute)
The orchestrator runs CKKS encrypt → sum → decrypt every second. The
TenSEAL `CKKSVector` wraps a C++ object; we `del` aggressively but
the allocator may still drift. Stress test will reveal.

If RSS grows monotonically and the leak traces to CKKS:
- Reduce poly degree from 16384 → 8192
- Bump heatmap cadence from 1s → 2s
- Add explicit `gc.collect()` after each release

### 2.2 LiveTrainer GPU pressure
The trainer runs PPO updates on the SAME MAPPO actor the inference
loop uses. If inference latency jumps when training enabled:
- Confirm via stress test (CPU% should rise; tick Hz should NOT drop)
- Mitigation: throttle trainer to N iter/min via `sleep_between_seconds`

### 2.3 Analytics consumers under load
13 consumers run on rotating cadences (1s / 5s / 30s / 60s). Some
(BERTopic, persistence homology) are heavy.
- If any consumer takes > cadence to complete, the pipeline backs up.
- Solution: log per-consumer wall-time; alert on slow ones.

### 2.4 Encrypted heatmap CKKS warm-up
First sample at boot encodes the keygen + first sum. Latency on T+0
may differ from steady state. Confirm via stress profile.

## Step 3 — UI/UX polish (~2-3h)

Visual / interaction nits the user has not asked for but improve
quality of life:

1. **Loading states** — every "warming up" string is currently bespoke.
   Standardize to `<LoadingHint reason="..." />`.

2. **Empty states** — when an endpoint returns `available: false`,
   the chart shows a tiny "X unavailable" message. Could be richer:
   why unavailable, what to do, link to docs.

3. **Modal layout consistency** — some modals (Pedersen, Beaver) have
   3 grid cells in the top bar; others (CKKS, Kyber) have 4. Make
   uniform.

4. **Color hierarchy** — cyan = OK / data, ember = warning / danger,
   muted = secondary. Audit every chart for inconsistencies.

5. **Tile ordering on AnalyticsPanel** — currently chronological by
   when added. Group by pillar (stats / econometrics / ML / crypto /
   chain / economy / world). Update Tour overlay accordingly.

6. **Tour overlay length** — 6 steps may now be 7-8 with logistics.
   Don't bloat; pick the most representative 6.

## Step 4 — Final gates (~1h)

Before tagging `pre-launch-cleanup-done`:

- [ ] All Step-0 CRIT findings closed (verified)
- [ ] `uv run pytest packages -q` green
- [ ] `pnpm --filter web test` green
- [ ] `uv run pyright packages` clean
- [ ] `uv run ruff check packages` clean
- [ ] `pnpm --filter web typecheck` clean
- [ ] `pnpm --filter web exec biome check src` clean (no errors,
      warnings OK)
- [ ] `docker compose up` from a clean clone boots all services
- [ ] `uv tool install ./packages/attacker && pna --help` works
- [ ] `uv tool install ./packages/shell_coach && psh lessons` shows 11
- [ ] README, ROADMAP, PROMPTING_GUIDE, CLAUDE.md cross-references valid
- [ ] At least one fresh screenshot in README

## Step 5 — Release decision (~30 min meeting with self)

After the cleanup pass + the data from the stress test + the
documents you wrote (OSS_PAPER_DRAFT.md, EDU_B2B_PITCH.md), make
the call.

Default if undecided (per
[`memory/project_penumbra_post_stress_plan.md`](~/.claude/projects/.../memory/project_penumbra_post_stress_plan.md)):
**ship OSS first.** Paper preprint + GitHub public + a "Show HN"
post. The Edu B2B pitch can run in parallel (or in 6 months from
OSS-validated momentum).

If shipping OSS:
- [ ] Choose license (MIT / Apache-2 / BSD-3). Recommendation: MIT.
- [ ] Add `LICENSE` file.
- [ ] Add `CONTRIBUTING.md` (light: code style, commit conventions,
      test-first, crypto-auditor review for crypto changes).
- [ ] Add `SECURITY.md` (responsible disclosure for the attacker code).
- [ ] Add `CODE_OF_CONDUCT.md` (Contributor Covenant, standard).
- [ ] Public release tag: `v1.0.0`.
- [ ] arXiv preprint uploaded.
- [ ] HN / Reddit / Twitter announcement.

## Step 6 — What we explicitly skip

(Reaffirm; don't drift.)

- Mobile responsive — out of scope per original plan.
- Multi-machine distribution — out of scope.
- EVM / Substrate chain integration — out of scope.
- KMS / hardware key isolation — out of scope.
- GPU FHE — needs CUDA, not Metal — out of scope.
- LLM-generated agent utterances — out of scope.
- Real ERP / production logistics integration — see `LOGISTICS_PLAN.md`
  out-of-scope section.

---

## Workflow

Open this file at the start of the post-stress review pass. Update
checkboxes as you go. Commit the updated version when each step
completes so the repo history mirrors the review.

Tag at the end: `post-stress-review-done`.
