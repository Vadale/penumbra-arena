# Penumbra — OSS Launch Roadmap

The operating plan for taking Penumbra from "post-Phase-8 private
repo" to "public OSS project with traction". Twelve weeks from start
to launch, with month-by-month sustainment plan after launch.

Sister documents:
- `OSS_PAPER_DRAFT.md` — academic / technical preprint for arXiv
- `EDU_B2B_PITCH.md` — commercial follow-on if OSS validates demand
- `REVIEW_PLAN.md` — code-cleanup pass that precedes launch
- `LOGISTICS_PLAN.md` — Tier-1-to-4 logistics extension (post-launch)

**Decision context**: OSS-first chosen 2026-05-23. B2B Edu is a
follow-on conditional on OSS demand signals. See
`memory/project_penumbra_oss_decision.md` for the reasoning.

---

## Phase L0 — Pre-launch readiness (weeks 1-4)

Goal: the repo public-ready. Anything a curious developer might check
within the first 60 seconds of clicking the GitHub link must be
present and good.

### Week 1: stress test triage + code-cleanup pass
- [ ] Run the stress test (already in flight at time of writing).
- [ ] Generate the report with `scripts/analyze_stress.py`.
- [ ] Triage CRIT findings (see `REVIEW_PLAN.md` Step 0).
- [ ] Fix CRIT findings.
- [ ] Re-run a 4-hour stress to verify the fixes.

### Week 2: code consolidation
- [ ] Extract `Stat`, `Verdict`, `Block` shared components
  (frontend audit found 45 / 7 / 5 duplications respectively).
- [ ] Address WARN findings from the stress report.
- [ ] Bump `/dashboard` poll cadence to 1500ms.
- [ ] Add `LICENSE` (MIT).
- [ ] Add `CONTRIBUTING.md`.
- [ ] Add `SECURITY.md` (responsible disclosure for the attacker
  module).
- [ ] Add `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).

### Week 3: public-facing polish
- [ ] Hero screenshot in README. A single image showing the dashboard
  with the WorldView, a populated AnalyticsPanel, and at least one
  modal open (Policy Inspector or ZK verify).
- [ ] Animated GIF (10-15s) demonstrating: dashboard loads → click
  a tile → see the modal populate live. Record with QuickTime,
  convert with `ffmpeg`.
- [ ] 90-second YouTube demo video. Script: "Penumbra is N agents on
  a graph. Their state is encrypted. We can attack the system from
  inside. We can train ML live. All on one Mac mini. Watch."
- [ ] GitHub topics: `cryptography`, `post-quantum`, `multi-agent-rl`,
  `simulation`, `homomorphic-encryption`, `differential-privacy`,
  `zero-knowledge-proofs`, `pedagogy`, `apple-silicon`, `python`,
  `typescript`.
- [ ] GitHub Discussions enabled.
- [ ] Issue templates (`bug`, `feature`, `question`).
- [ ] PR template.
- [ ] README badges: tests passing, license, latest tag,
  contributors, GitHub stars.
- [ ] Quick-start that works from a fresh clone in < 60 seconds
  (verify on a clean machine or VM).

### Week 4: paper preprint + launch artefacts
- [ ] Finalize `OSS_PAPER_DRAFT.md`: fill in TODO sections, complete
  the references, run a writing pass for clarity.
- [ ] Submit to arXiv (cs.CR or cs.LG primary; cross-list).
- [ ] Make the arXiv link the FIRST link in the README.
- [ ] Write the "Show HN" submission title + opening comment.
- [ ] Write the LinkedIn long-form post.
- [ ] Write the X/Twitter launch thread (8-12 tweets, each tweet a
  visual hook).
- [ ] Write the dev.to / Hashnode launch article.
- [ ] Build a landing page at `penumbra-arena.dev` (or a section of
  the user's personal site). Mandatory elements: title, one-sentence
  description, hero screenshot, "Run it" code block, link to GitHub
  + arXiv, three demo gifs.

**End of Phase L0 acceptance gate** (all must be true to launch):
- README hero screenshot present + works on dark mode
- `LICENSE`, `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT` all present
- arXiv preprint live with a stable URL
- 326 / 326 backend tests + 24 / 24 vitest still passing
- All findings from stress test addressed (CRIT closed, WARN logged)
- `docker compose up` from a fresh clone works end-to-end on a M-series
  Mac
- Tour overlay reflects current 57-tile reality

If any gate fails, the launch slips one week — never compress on
readiness.

---

## Phase L1 — Launch day (week 5)

Goal: maximize first-48-hour visibility. GitHub's algorithm strongly
favors recent activity, so concentrated traffic in the launch window
compounds.

Choose: **Tuesday or Wednesday, 9:00 AM EST**. Avoid Mondays
(competition with Show HN backlog), avoid Fridays (low engagement).
Avoid US holidays.

### T-1 day (the day before)
- [ ] Quiet final review: `git log` since last public push, ensure
  no embarrassing commit messages, no leftover TODOs in commit
  bodies, no secrets in history.
- [ ] Tag `v1.0.0` and `git push --tags`.
- [ ] Verify GitHub releases page renders cleanly with release notes.
- [ ] One trusted friend stars and forks the repo (so it isn't 0/0
  at launch).
- [ ] Pre-write 5 short responses to anticipated questions: "Why
  not use X?", "What's the difference vs OpenFHE?", "Does it work
  on Linux?", "What's the license?", "How is this different from
  AnyLogic?".

### Launch day, 9:00 AM EST
- [ ] Submit to Hacker News: `Show HN: Penumbra — privacy-preserving
  multi-agent arena to learn crypto + ML by attacking it`.
  Opening comment: 4-5 sentences max, mention M4 hardware target,
  mention adversarial console, link to arXiv.
- [ ] Submit to Lobste.rs (need an invite, ask for one in advance).
- [ ] Submit to Reddit:
  - `r/MachineLearning` (use "[P] Project" tag; avoid promotional
    tone; lead with technical novelty)
  - `r/cryptography` (lead with PQ + adversarial angle)
  - `r/Python` (general programming community)
  - `r/learnmachinelearning` (educational angle)
  - `r/opensource` (general)
- [ ] LinkedIn long-form post with personal narrative ("I built this
  to teach myself X; here's what I learned").
- [ ] X/Twitter launch thread.
- [ ] Dev.to article cross-posted.

### Launch day, 9:00 AM - 6:00 PM EST
- [ ] **Be at the keyboard.** First-day comment responses define
  whether the project gets traction.
- [ ] Reply to every HN comment within 30 minutes (even if just to
  acknowledge). The HN algorithm penalizes silent authors.
- [ ] Reply to every Reddit comment with substance.
- [ ] Reply to LinkedIn DMs.
- [ ] Engage with X/Twitter replies, especially from accounts with
  >5k followers.

### Launch day, evening
- [ ] Status check: GitHub stars count, HN ranking, Reddit upvotes.
- [ ] Capture the day-1 numbers as a baseline (we'll measure
  trajectory by them).
- [ ] Sleep. Tomorrow has its own work.

---

## Phase L2 — Launch week sustainment (week 5 days 2-7)

Goal: convert day-1 traffic into week-1 contributors and stars.

- [ ] Respond to every GitHub issue within 24 hours.
- [ ] Welcome the first PR loudly and merge it FAST (a contributor's
  first PR is their evaluation of your project).
- [ ] Day 3: write a follow-up blog post diving deep into one
  concept (e.g. "Why we ship a Groth16 verifier in pure Python").
- [ ] Day 5: post a "first 5 days in OSS" reflection on
  LinkedIn / X. People love progress updates.
- [ ] Day 7: weekly digest tweet — "Penumbra week 1: X stars, Y
  contributors, Z issues closed".

**Week 5 acceptance**: at least 100 GitHub stars, at least 3
issues opened by external users (low bar but signals real attention).

---

## Phase L3 — Month 2-3 sustained promotion

Goal: move from "launched" to "growing". The compound-growth phase
of an OSS project starts in month 2 — most projects die in this
window because the founder loses momentum.

### Newsletter outreach (one a week)
- TLDR Newsletter (`tldr.tech`)
- Pointer (`pointer.io`)
- Hacker Newsletter (`hackernewsletter.com`)
- Last Week in AI (`lastweekin.ai`)
- The Pragmatic Engineer (Substack)
- O'Reilly Radar (longer cycle)

### Submit to "Awesome" lists
- `awesome-cryptography`
- `awesome-rl` (or related multi-agent lists)
- `awesome-privacy`
- `awesome-zero-knowledge-proofs`
- `awesome-fhe`
- `awesome-pedagogy` or `awesome-courses` if relevant

### Conference / workshop submissions
- [ ] NeurIPS Datasets & Benchmarks Track (May submission for
  December conference)
- [ ] ICML AutoRL workshop
- [ ] USENIX Security CSET workshop (security education)
- [ ] PyCon (US + EuroPython)
- [ ] Real World Crypto (RWC)
- [ ] CrytpoConference workshops
- [ ] Open Source Summit (Europe + North America)

### Talks / podcasts
- Reach out to: ChangeLog podcast, Software Engineering Daily,
  Hanselminutes, Local meetups (Python Italia, OWASP local
  chapters, MIT Crypto reading group equivalents).
- One talk per month minimum, alternating online / in-person.

### Tutorials / YouTube
- Series of 6-8 short videos (5-10 min each), one per pillar:
  "Penumbra explained — 1. The arena", "2. Encrypted heatmaps",
  "3. The attacker console", etc.

### Partnership / cross-promotion
- Reach out to authors of OpenFHE, TenSEAL, CleanRL with an "I built
  X on top of your work, would you like to mention it?" email.
- Same with the developers of `pna`-adjacent tools (Counterfit, IBM
  ART) — even competitive, polite outreach generates backlinks.

### KPIs to track weekly
| Metric | Week 5 target | Week 12 target |
|---|---|---|
| GitHub stars | ≥ 100 | ≥ 500 |
| Forks | ≥ 5 | ≥ 30 |
| External PRs merged | ≥ 1 | ≥ 10 |
| External issues opened | ≥ 3 | ≥ 25 |
| Twitter followers added | ≥ 50 | ≥ 300 |
| arXiv views (per Semantic Scholar / Connected Papers) | ≥ 100 | ≥ 500 |
| Newsletter mentions | ≥ 1 | ≥ 5 |
| Speaking invitations | 0 | ≥ 2 |

---

## Phase L4 — Month 4-6 — accumulation

Goal: convert the audience into a real community, prepare the
"second wave" to keep momentum.

- [ ] Launch GitHub Discussions categories: Q&A, Show & Tell,
  Ideas, Research-grade.
- [ ] Run a Penumbra hackathon (online, free, 48 hours, sponsored
  by yourself for $500-1000 in prizes — Amazon gift cards or t-shirts).
  Track: best new dashboard tile, best attacker variant, best paper
  citation.
- [ ] Apply to be the maintainer in residence at one of:
  - GitHub's Open Source Maintainer program
  - The Linux Foundation Mentorship program
  - Google Summer of Code (as a hosting org)
- [ ] University outreach: email CS departments offering Penumbra as
  a teaching tool. Target: Polimi, Bocconi, ETH Zürich, EPFL, MIT,
  Stanford, CMU.
- [ ] Public release of Tier 1 of the logistics layer
  (`LOGISTICS_PLAN.md`). This is a fresh news angle ~3 months after
  launch: "Penumbra v1.1 — supply chain edition".

---

## Phase L5 — Month 6 decision point

Re-evaluate based on the KPI data. Three possible paths:

### Path A: Strong traction (≥ 500 stars, ≥ 2 talk invites)
→ Layer B2B services. Open `EDU_B2B_PITCH.md`, hire/partner with one
sales rep, target 5 enterprise pilots over the next 6 months.

### Path B: Moderate traction (100-500 stars, no invites)
→ Continue OSS investment for another 3 months. Add Tier 2 of the
logistics layer + Tier 3 (multi-echelon supply chain).

### Path C: No traction (< 100 stars at month 6)
→ Genuinely re-evaluate. Possible pivots:
- Narrow scope to one pillar (e.g. "Penumbra for crypto education
  only") and re-launch as a smaller, more focused project.
- Sell to an existing OSS organization (Apache Foundation, Linux
  Foundation, Mozilla) as a donated project.
- Park the project; it stays as the user's portfolio piece.

---

## The promotion playbook (tactics that matter)

Below is the **specific** how-to for getting an OSS project noticed.
General "build great software" advice is omitted because it's
obvious.

### The 48-hour rule (most important)
GitHub's algorithm strongly favors stars accumulated in the FIRST
48 HOURS after launch. A project that gets 100 stars in 48 hours
will outrank a project that gets 500 stars spread over 5 weeks.
This means: pre-stage ALL launch artefacts, and post them in a
tight 6-hour window.

### Tweet/post structure that works
The "show, don't tell" formula:
1. Lead with the one-line claim ("X agents on a graph, fully
   encrypted, all on one Mac mini").
2. Visual: screenshot or GIF in tweet 2.
3. Demo: what does it look like to RUN this? Code block in tweet 3.
4. Why it matters: one paragraph on the novel-position claim.
5. Link to GitHub.

What does NOT work: jargon-loaded openings, listing 20 features,
asking for stars explicitly.

### Hacker News specifically
- The title is the difference between 5 upvotes and 500. Examples:
  - BAD: "I built a multi-agent simulation framework"
  - GOOD: "Show HN: Penumbra — 50 agents, encrypted, attackable from
    inside, runs on a Mac mini"
- Submit on Tuesday or Wednesday at 9:00 AM EST.
- The first 90 minutes determine the ranking trajectory. Stay at the
  keyboard.
- Engage critics seriously, not defensively. HN respects "good point,
  I'll add that to the roadmap" responses.

### Reddit specifically
- Every subreddit has its own etiquette. r/MachineLearning hates
  promotional posts; lead with technical content. r/programming is
  more permissive but moderators are strict.
- Crosspost SPARINGLY — 5+ subreddits in 1 hour reads as spam.
- ALWAYS read the subreddit's pinned rules. Most disqualifying
  failures are rule violations, not content problems.

### LinkedIn specifically
- Long-form (1500-2500 chars) outperforms short posts by 3-5×.
- Lead with PERSONAL narrative: "I built this because I wanted to
  learn X. Here's what I found."
- Tag relevant accounts sparingly (1-2 max).
- Hashtags: 3-5 is the sweet spot. `#opensource #cryptography
  #machinelearning` are obvious starters.
- Time of post: Tuesday-Thursday 7-9 AM in the target timezone.

### Twitter/X specifically
- Threads outperform single tweets.
- Each tweet should stand alone (someone who only reads tweet 4
  should still get the point).
- Use 2-4 images per thread, never just text.
- Quote-tweet your own original tweet after 4-6 hours to boost
  engagement (algorithm friendly).

### Anti-tactics (definitely don't do)
- Don't buy stars. GitHub detects this and shadow-bans the repo.
- Don't @-mention strangers asking them to star.
- Don't fake activity (no sock-puppet accounts).
- Don't spam Discord/Slack communities.
- Don't sneak the project into unrelated comment threads.
- Don't argue with criticism — acknowledge, take notes, move on.
- Don't promise features in launch posts that aren't already shipped.

### The "second wave" rule
The single biggest failure mode of OSS launches: founder publishes,
gets day-1 buzz, then disappears for two weeks. Project dies.

Counter: every 2 weeks after launch, ship something visible:
- A new tile / feature
- A blog post on a concept
- A YouTube demo
- A conference submission update
- A KPI update post ("Penumbra month 1: stars 47 → 134")

This trains the audience that the project is ALIVE.

---

## Risks specific to OSS launch

| Risk | Likelihood | Mitigation |
|---|---|---|
| Day-1 attention fails (silent launch) | 30% | Pre-stage all artefacts; do launch on a Tuesday; recruit one HN-experienced friend to upvote and engage |
| Attention but no contributors | 50% | Make first PRs trivial (typo fixes, doc improvements); always merge external PRs within 48 hours |
| Niche too narrow (only crypto people care) | 20% | Logistics layer post-launch broadens the appeal; talk at non-crypto venues |
| Maintainer burnout | medium-long term | Cap to 5-10 hours/week sustained; use templates for issue responses |
| Negative criticism from established players | 15% | Engage respectfully, learn from valid critiques, ignore trolls |
| Fork by a larger company | 10% | MIT license accepts this; counter with continuous shipping that the fork can't keep up with |

---

## What success looks like at month 12

Concretely:
- 1500+ GitHub stars
- 30+ external contributors
- 3+ conference talks delivered
- Penumbra cited in at least one academic paper
- 1 partnership with an established OSS project (TenSEAL, CleanRL, etc.)
- Tier 1 + Tier 2 of the logistics layer shipped
- B2B Edu pilot conversations started (if Path A signals appeared)

If we reach this in 12 months, the project has proven itself. Then
the Edu B2B layer is genuinely de-risked.

---

## Open-source promotion: the meta-rule

**The single best advertisement for an OSS project is continuous,
visible improvement.** Stars accrue to projects that look ALIVE.
Whatever you do, ship something visible every two weeks for the
first six months. After that the audience self-sustains.

The roadmap above is detailed because the launch window is precious
and one-shot. After week 6 the project's growth becomes much more
emergent — the audience does the promotion.

---

**This document is a planning artefact. Update milestone checkboxes
as you go. Commit changes with `docs(oss-launch): mark <step>
complete` to keep a public audit trail.**
