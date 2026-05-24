# Phase 5 + Phase 6b — Build Order

Wave-based dispatch strategy to avoid the Anthropic rate-limit crashes
that killed 2 of the 4 parallel agents during Phase 6a.

**Rule of thumb**: max 3 parallel agents at any moment.

---

## Dependency graph

```
Phase 5 Tier 1 (foundation primitives) ─┐
Phase 5 Tier 2 (attacks)                 │
Phase 5 Tier 3 (defenses)                ├──> Phase 6b Tier 3 (attack actions wired)
Phase 5 Tier 4 (interactive surfaces)    │    Phase 6b Tier 4 (defense actions wired)
Phase 5 Tier 5 (narrative content)       │
                                          │
Phase 6b Tier 1 (operator agent + CLI) ──┤
Phase 6b Tier 2 (Operator Console UI)    │
Phase 6b Tier 5 (scenarios + engine)     │
Phase 6b Tier 6 (replay + leaderboard) ──┘
```

## Waves

### Wave 1 — independent foundations (3 agents)
- Agent A: **Phase 5 Tier 1** (foundation primitives: FROST, SPHINCS+,
  Verkle, BBS+, Yao, PSI, Loopix, STARK verifier)
- Agent B: **Phase 6b Tier 1** (operator agent slot + 8 core actions +
  `pno` CLI)
- Agent C: **Phase 5 Tier 3** (defenses: k-anonymity, l-diversity,
  data poisoning, padding, GAN poison, request obfuscation)

### Wave 2 — attack vertical + scenario engine + Operator UI (3 agents)
- Agent D: **Phase 5 Tier 2** (6 attack modules: agent_fingerprint,
  trajectory_fingerprint, membership_inference, model_inversion,
  reward_poisoning, cache_sidechannel)
- Agent E: **Phase 6b Tier 2** (Operator Console UI — `/operator`
  React route + Action Builder + live log + mini-dashboard +
  score card)
- Agent F: **Phase 6b Tier 5** (scenario engine + 12 starter YAML
  scenarios, independent of Tier 2-4 attack/defense modules)

### Wave 3 — attack/defense wiring + interactive surfaces (3 agents)
- Agent G: **Phase 6b Tier 3 + 4** (attack actions wired + defense
  actions wired — depends on Phase 5 Tier 2 + Tier 3)
- Agent H: **Phase 5 Tier 4** (CTF mode + custom policy injection +
  Jupyter bridge + replay+branching)
- Agent I: **Phase 6b Tier 6** (replay log + cross-session leaderboard)

### Wave 4 — narrative content (1 agent + integration test myself)
- Agent J: **Phase 5 Tier 5** (8-10 cross-pillar story tutorials)
- Me: final integration sweep + 10-min stress test + commit batch.

## Crash-recovery protocol

If an agent fails with "API Error: Server is temporarily limiting
requests · Rate limited":
1. Check the repo with `git status` and `pyright` — most of the
   code likely landed.
2. Re-dispatch the same agent with a shorter follow-up prompt:
   "Tier X agent was rate-limited. Pick up where you left off
   — see git status for what's already written. Run the
   validation gates + report. Do NOT redo work."
3. Reduce parallelism for the next wave (drop from 3 → 2).
