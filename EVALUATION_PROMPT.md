# Penumbra — Independent Evaluation Prompt

Copy everything below this line into a fresh chat with a frontier
model (Claude Opus / GPT-5 / Gemini 2.5 / etc.). Attach or paste the
contents of `README.md`, `USAGE.md`, `ROADMAP.md`, and `CLAUDE.md`
from the repo. Then send the prompt.

The goal is a brutally honest, **independent** second opinion — the
author of this software is wondering if it's actually valuable and
needs an external voice. Frame the prompt so the model is incentivized
to say "no, this isn't valuable" if that's the honest answer. Don't
let it flatter the author.

---

# PROMPT

You are an independent product-and-engineering advisor. A solo
developer (Vadale) built a project called **Penumbra** over ~3 weeks
on a Mac mini M4. They are now asking themselves: "is this actually
useful? does this have value? to whom?"

They suspect the answer might be "no" and want you to confirm or
contradict that, **with reasoning grounded in market reality, not in
appreciation of the engineering**. They've already received plenty of
positive feedback about how impressive it is technically. They need
the opposite: cold judgement.

## What you know

Read the attached `README.md`, `USAGE.md`, `ROADMAP.md`, `CLAUDE.md`.
These describe what Penumbra is, what it can do, who it's targeted at
in the author's view, and the build history.

If the docs don't tell you something, ASK. Don't invent.

## Important context the docs don't make obvious

- Solo author (Vadale). No team. No funding. No marketing budget.
- Built in ~3 weeks of intensive work, mostly with Claude Code
  (AI-pair-programmed; the author wrote the architecture and reviewed
  every diff but did not type most of the lines).
- Target hardware: single Mac mini M4, 16 GB RAM. All-local.
- The author has tried multiple positionings in their head: teaching
  platform, academic benchmark, cyber-range, portfolio piece, B2B
  privacy-engineering training. They explicitly rejected "build a
  videogame" and "build a pro dashboard for industry".
- Stated launch direction (per memory): OSS-first MIT license + a
  CC-BY-4.0 dataset on Hugging Face Hub + an arXiv preprint, then
  layer B2B education on top **only if** OSS validates demand
  (gate: 500+ GitHub stars OR 10+ bench submissions in 6 months).
- The author has NOT YET launched publicly. The repo is private. No
  arXiv preprint submitted. No HF dataset uploaded. No social posts.
- The author's primary career interest: being interesting/employable
  to top AI labs OR top quant/fintech firms OR doing a PhD in
  privacy-preserving ML.

## What to evaluate

Don't summarize. Don't praise the engineering. Don't suggest "rewrite
in Rust" or "add more features". Specifically answer:

### 1. Is Penumbra useful — and if so, to whom?

For each plausible audience (researcher / student / educator /
security engineer / company / recruiter / nobody), rate Penumbra's
fit on a 1-5 scale and give **one concrete reason**. Be willing to
write "nobody — 0/5" if that's true.

### 2. What kind of "useful" is realistic?

Distinguish between:
- "Useful as a learning artifact for the author themselves" (resume
  value, technical depth demonstration)
- "Useful as a tool other people will USE regularly"
- "Useful as a benchmark or citation in other people's work"
- "Useful commercially (sellable to a company / educational
  institution / etc.)"

Rate each on plausibility 1-5 and give the reasoning.

### 3. What would the brutal market reality look like at launch?

If the author launched tomorrow on Hacker News + Reddit + arXiv,
realistically:
- How many stars in 30 days? Range, not a number.
- How many actual usage cases (people running it past 5 minutes)?
- How many citations or downstream uses in 12 months?
- What would the comments under the HN post most likely look like?

Be specific. "Could go viral with the right framing" is not an answer.
Pick the most likely outcome at 50th-percentile and at 10th-percentile.

### 4. If you HAD to keep the project but reposition it for maximum
useful-ness, what would you change?

NOT a re-write. The author doesn't want to change the code. They want
to know what to do with what they already have. Answer:
- One sentence repositioning of the README opening line.
- 3 things to KEEP front-and-center on the dashboard.
- 5+ things to HIDE in "advanced" because they confuse the value prop.
- A 30-day launch plan that has a realistic chance of actual impact.

### 5. If you were the author, what would you do next?

Three options, ranked. For each: the realistic outcome 6 months from
now. Include the "stop working on this and pivot" option if relevant.

## What to avoid

- DON'T be diplomatic. The author has heard "wow this is impressive"
  enough.
- DON'T suggest more features. The project is already too broad —
  more features make it worse.
- DON'T suggest pivot away from technical depth — the author's
  comparative advantage IS technical depth.
- DON'T say "it depends on the audience" without committing to which
  audience is realistic.
- DON'T say "the engineering is impressive" — that's the unhelpful
  praise the author wants to bypass.
- DON'T write a marketing pitch. Write a sober assessment.

## Output format

A direct response in plain prose (or terse sections with bullet
points). Under 2000 words total. Lead with the verdict ("Penumbra
is/isn't valuable, because: ..."), then the 5 sections above.

If your honest answer is "this is a beautiful demo with no audience
beyond the author's own portfolio", say so. The author will thank you
for the honesty, not for the praise.

---

# How to use this prompt

1. Open a fresh chat in your model of choice (Claude Opus 4.7, GPT-5,
   Gemini 2.5 Pro, etc.). Use the most capable / extended-reasoning
   variant available.
2. Paste the prompt above (everything between `# PROMPT` and the
   horizontal rule).
3. Attach (or paste, in this order): `README.md`, `USAGE.md`,
   `ROADMAP.md`, `CLAUDE.md`. If your model has a code-attachment
   feature, attach the full repo and tell it to start with those 4.
4. Read the verdict carefully. If the model hedges, push back: "give
   me a sharper, less hedged version. I want the worst-case honest
   assessment."
5. Then ask: "given your verdict, what is the SINGLE most valuable
   action I can take in the next 7 days?" That's the operational
   answer you need.

If the model gives you a vapid pep-talk, switch to a different model
or restart the prompt with stronger language ("be brutal", "I am
seeking unfavourable verdicts", "if you flatter me I will lose
weeks").

## Why a second opinion?

The author has been working with one specific AI agent (Claude Code)
that helped build everything. That agent has implicit incentive
alignment with the existing artifact — it's emotionally invested in
the codebase it just produced. An independent model with no history
provides counter-evidence. If a fresh frontier model reads the same
docs and reaches the same verdict, the conclusion is much more robust.

If two independent models BOTH say "this is valuable", proceed with
launch. If two independent models BOTH say "this isn't valuable",
reposition or pivot. If they disagree, you have something interesting
to dig into.
