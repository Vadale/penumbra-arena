# Penumbra — Enterprise Training Platform (Edu B2B)

A working draft for the commercial-direction pitch. Audience:
corporate training buyers at banks, insurance, fintech, gov sec
teams, large logistics + healthcare orgs.

**Use this document to**: structure a sales call, draft a one-pager,
write a landing page, or pitch a paid pilot.

**Current status (2026-05-23)**: this commercial direction is
deferred until the OSS launch (see `OSS_LAUNCH_ROADMAP.md`) generates
demand signals (≥ 500 stars, ≥ 2 talk invites, or inbound consulting
requests at ≥ $5k/day rate). Without those signals, B2B-Edu pursuit
risks 9-15 months of solo-founder sales work before the first dollar
of revenue — wasteful versus the OSS path's near-zero marginal cost.

---

## The pitch in one paragraph

Your engineering teams need to migrate to post-quantum cryptography
by the NIST 2030 deadline. They also need to internalize differential
privacy under the EU AI Act (in force August 2026), fluency in
adversarial-ML defence under the new SOC2 controls, and the supply-
chain modelling that's the daily bread of your operations team.
Today they get this from disjoint Coursera modules, OWASP slides,
and external trainers — none of which let them ACTUALLY TOUCH the
crypto, watch the attacks fail, and re-train an ML policy live.
**Penumbra is one screen, one Mac, one afternoon. Every concept is
a clickable tile that runs real code and rejects real attacks.**

## The 5 problems we solve for enterprise

| Problem | What teams do today | Penumbra solves it by … |
|---|---|---|
| PQ migration urgency | Read NIST FIPS 203/204 PDFs in isolation | Live Kyber + Dilithium tiles with key sizes, encaps/decaps, tamper rejection on screen |
| AI Act compliance prep | Generic "what is DP" slides | DP-noised vs clean heatmap side-by-side + the budget exhaustion failure mode visible live |
| Adversarial ML defence | Theoretical OWASP top-10 talks | 6 attacker chips run against the live system, defences observable |
| Multi-agent RL operational risk | "We have an ML team, they handle it" | Policy inspector, value map, saliency, live training, A/B checkpoint compare — Ops can SEE what the policy is doing |
| Supply chain optimization training | $10k/seat AnyLogic licenses | Penumbra logistics layer + OR-Tools VRP benchmark (see LOGISTICS_PLAN.md), 1 install per laptop |

## Target buyer personas

### P1 — Chief Information Security Officer (CISO)
- **Pain**: 2026-2030 NIST PQ migration, AI Act / SOC2 / ISO 27001
  audit prep
- **Penumbra value**: a single training artefact that covers the 8
  primitives the audit will ask about
- **Decision criteria**: "can my team SEE the controls work?"
  Penumbra's answer: yes, on screen, in a Mac mini.
- **Price tolerance**: $20-80k for a comprehensive curriculum +
  ongoing access

### P2 — Head of ML Operations
- **Pain**: regulatory scrutiny on model robustness; need internal
  red-teaming capability
- **Penumbra value**: a sandbox where engineers PRACTISE adversarial
  thinking before touching production
- **Decision criteria**: "does it scale to 50+ engineers in
  parallel?" → SaaS deployment of Penumbra instances
- **Price tolerance**: $5-20k/seat/year for SaaS

### P3 — VP of Engineering Learning & Development
- **Pain**: training budget under pressure; need measurable outcomes
- **Penumbra value**: 11 shell lessons + 5 attack chips + ~57 concept
  tiles = a 4-week internal bootcamp curriculum
- **Decision criteria**: completion rates + skill assessment
  reproducibility
- **Price tolerance**: $50-500/seat/year volume

### P4 — Head of Supply Chain (LOGISTICS_PLAN.md needed)
- **Pain**: bullwhip / forecasting / inventory optimization workshops
  cost $5-15k/day to bring in consultants
- **Penumbra value**: Tier 1-3 of the logistics layer turns the same
  installation into a SCM training environment
- **Decision criteria**: "can it model my ACTUAL supply chain?" →
  Penumbra is illustrative, not literal; pitch as foundation training
- **Price tolerance**: $10-50k/workshop module

## Curriculum modules (each ~4 hours)

### Module 1 — Post-quantum cryptography (PQC) fundamentals
- Kyber ML-KEM-768: keygen, encaps, decaps, tampered ciphertext rejection
- Dilithium ML-DSA-65: per-agent signatures, message-binding
- BLS aggregate signatures: N signers, 1 verification, rogue-key defence
- VDF, VRF: leader election that can't be biased
- **Hands-on**: tamper a ciphertext, watch the decapsulation diverge

### Module 2 — Homomorphic encryption + differential privacy
- CKKS: encrypt → sum → decrypt round-trip + approximation error
- Laplace mechanism with budget accountant
- Privacy budget exhaustion as a failure mode
- **Hands-on**: tune ε per release; watch the budget deplete; observe
  the un-noised fallback log

### Module 3 — Zero-knowledge proofs
- Groth16 verifier: pairing equation + public input binding
- Multiplier circuit (a·b ≡ c) → legal_path circuit (graph adjacency)
- SNARK forgery attempts + soundness defence
- Schnorr Σ-protocol with Fiat-Shamir
- Pedersen commitment + homomorphic add
- **Hands-on**: flip a public input bit → verifier REJECTs

### Module 4 — Multi-agent ML + interpretability
- MAPPO actor-critic on a 50-agent graph
- Policy inspector: action probabilities, saliency, value estimate
- Live PPO training: start/stop, reward shaping sliders
- A/B compare two checkpoints + KL divergence + agreement rate
- **Hands-on**: turn crowding-penalty to -0.05, retrain 5 minutes,
  observe swarm dispersion

### Module 5 — Adversarial defence
- Replay attack + nonce binding
- Byzantine validator equivocation + BLS-aggregated slashing
- Linkability attack on movement patterns + DP defence
- Timing side-channel on CKKS operations
- Dinur-Nissim DP reconstruction
- **Hands-on**: each `pna` attack run from the dashboard; the
  defence observable

### Module 6 — Operations research + supply chain (requires LOGISTICS_PLAN tiers)
- Cargo capacity + demand curves + (s, S) reorder policy
- VRP as centralized planner; optimality gap vs learned policy
- Multi-echelon supply chain + bullwhip effect
- **Hands-on**: tune (s, S) sliders, watch fill rate and holding cost trade

### Module 7 — Macos/Unix shell fluency (psh lessons 1-11)
- Filesystem, text processing, pipes, processes, networking, archives,
  permissions, macOS-specific (brew/defaults/mdfind/pbcopy), modern CLI
  (rg/jq/fzf/eza), crypto tools (openssl/gpg/ssh-keygen), scripting hygiene
- **Hands-on**: every lesson has step-validated commands; the dashboard
  PTY is the workspace

## Pricing model (recommended)

### Tier 1 — Single seat / individual learner
- $99/mo or $999/yr
- Penumbra cloud-hosted instance, persistent for 90 days
- All 7 modules + reference materials
- Discord access + monthly Q&A

### Tier 2 — Team (5-25 seats)
- $79/seat/mo (vol discount)
- All Tier 1 + shared workspace + cohort progress tracking
- 1 cohort kickoff call + 1 mid-cohort sync (live)

### Tier 3 — Enterprise (25+ seats)
- $59/seat/mo or $499/seat/yr (enterprise commit)
- Tier 2 + on-prem deployment option + SLA + dedicated account team
- Custom module 7 (your-org-shell-lesson) included
- Compliance documentation pack (SOC2, ISO 27001, AI Act mapping)

### Workshop bookings (any tier)
- $7,500 for a 4-hour live workshop facilitated by the Penumbra
  team, module of choice (1 of 7), up to 30 attendees
- $40k for a 5-day cohort bootcamp covering modules 1-5

## Differentiation matrix

| Dimension | Penumbra | Coursera Crypto | AnyLogic | Counterfit | OWASP |
|---|---|---|---|---|---|
| Live integrated runtime | ✓ | ✗ | partial | ✗ | ✗ |
| Cryptography coverage | comprehensive PQ | classical only | ✗ | ✗ | partial |
| Adversarial console | 6 attacks live | reading only | ✗ | yes but ML-only | reading only |
| Multi-agent RL | live training | ✗ | partial | ✗ | ✗ |
| Supply chain (with Logistics tier) | ✓ | ✗ | ✓ (€10k/seat) | ✗ | ✗ |
| Shell coach included | ✓ | ✗ | ✗ | ✗ | ✗ |
| Open source backbone | ✓ | ✗ | ✗ | ✓ (M$) | ✓ |
| Mac mini deployment | ✓ | n/a | ✓ ($$) | ✓ | n/a |
| Price/seat/year | $999-1500 | $80-400 | $7-15k | free | free |

## Go-to-market sequence (12 months)

### Month 1-2 — soft launch
- OSS repo public on GitHub with paper preprint on arXiv
- "Show HN" + 3-4 conference workshops submitted (BlackHat, RSA,
  USENIX Security, NeurIPS Demos)
- 5 free Tier-1 betas to friends-of-friends in target buyer personas

### Month 3-4 — validate Tier 2
- Convert 2 of the betas to paid team accounts
- Iterate on module ordering + difficulty curve
- Hire (or 50% partner) a sales person for enterprise outreach

### Month 5-8 — enterprise sales motion
- Target: 5 enterprise pilots ($20-50k each)
- Focus verticals: banks, healthcare insurance, gov sec contractors
- Compliance pack drafted (AI Act mapping, NIST PQ migration brief)

### Month 9-12 — scale or pivot
- If 5+ pilots converted: hire SDR + customer success, raise pre-
  seed
- If <3 pilots: pivot to OSS-with-services model (paper-driven
  consulting + customs)

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Long sales cycle (6-12 mo for enterprise) | Lead with workshop bookings ($7.5k each, 30-day cycle) |
| OSS undercuts paid offering | Paid = compliance pack + SLA + hosted + custom curriculum + cohort facilitation; OSS = just the runtime |
| Penumbra demands deep technical readiness | Offer a "managed cohort" tier where we deliver the workshop |
| Single-author bus factor | Year 1: hire one engineer + one curriculum lead from revenue |
| Competition from Coursera-grade content | Compete on integration + hands-on, NOT on lesson volume |

## Open questions for the founder

These should be resolved before going to market:

1. **Solo or co-founder?** Hiring a sales/business-development partner
   doubles the chance of crossing the chasm to enterprise but halves
   the equity.
2. **Hosted SaaS or on-prem?** Enterprise security teams often refuse
   cloud-hosted training; on-prem requires K8s / Docker compose
   shipping discipline.
3. **AI Act compliance certification?** SOC2 is ~$30-50k + 6 months
   to obtain — go for it now or wait for 5 enterprise paying
   customers as a forcing function?
4. **Do we go bilingual (Italian + English) for the curriculum?**
   The European market is large; the founder is Italian-speaking
   natively. Cost: ~2x curriculum writing.

---

**This document is a planning artefact, not a published commitment.**
Revise as the market gives signal.
