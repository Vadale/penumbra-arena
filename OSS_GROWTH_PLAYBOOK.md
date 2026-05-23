# Penumbra — OSS Growth Playbook (Free & Organic)

A field manual for getting GitHub stars + community + visibility
**without spending money**. Time is the only currency.

Sister to [`OSS_LAUNCH_ROADMAP.md`](OSS_LAUNCH_ROADMAP.md) (the
12-week timeline). This doc is the deep tactics — what to do at
each step and WHY each tactic works.

**Core thesis**: visibility is a multiplicative function of
(content quality) × (distribution channels) × (consistency over
time) × (network effects from cross-pollination). Skip any factor
and the others can't compensate.

---

## Part 1 — Pre-launch: build credibility BEFORE the repo is public

The single highest-leverage period in any OSS launch. The day you
flip the repo public, you want the audience already PRE-WARMED.
Eight to twelve weeks of patient pre-work makes a 5-10× difference
in launch-day star count.

### 1.1 Build in public (weeks -12 to -4)
- [ ] Tweet a screenshot of Penumbra weekly. Always include one
  insight ("here's what I learned about CKKS modulus chains
  today"). No promotion. Just transparent progress.
- [ ] Write one dev.to / Hashnode / Medium article every 2 weeks
  on a sub-topic (CKKS, MAPPO, persistent homology). Cross-post
  to your own blog if you have one.
- [ ] Pin progress threads on X/Twitter. Build a habit of #buildinpublic
  hashtag use.
- [ ] Maintain a public TODO board (GitHub Projects, even on a
  private repo — link previews are visible).

Why it works: people who see you posting consistently for 8 weeks
develop pseudo-relationship. They feel they KNOW the project
already by launch day. They're far more likely to star + share
than cold visitors.

### 1.2 Contribute to adjacent projects (weeks -12 to -4)
- [ ] Submit a documentation PR to OpenFHE (you'll find a typo
  or unclear section in 20 minutes of reading).
- [ ] Submit a small bug fix or test improvement to TenSEAL.
- [ ] Open a GitHub Discussion in CleanRL with a thoughtful
  question or insight about MAPPO scaling.
- [ ] Engage with `py_ecc` and `circom` issue queues.

Why it works: when you launch and DM these projects' maintainers
("hey, I built X using your library, would you take a look?"),
your name is already familiar. Strangers ignore launch DMs;
contributors get attention.

### 1.3 Answer questions in target communities (weeks -12 to -4)
- [ ] r/MachineLearning, r/cryptography, r/Python — build comment
  karma. Aim for ≥1000 per subreddit before any "Show HN"-style
  posts (most subreddits filter sub-1000-karma submissions).
- [ ] Stack Overflow: 5-10 high-quality answers in the
  `homomorphic-encryption` and `reinforcement-learning` tags.
- [ ] Cryptography Stack Exchange: same.

Why it works: subreddit algorithms weight contributor history.
A r/ML post from a 50-karma account dies; from a 5000-karma
account it reaches the front page.

### 1.4 Build the mailing list (weeks -8 to launch)
- [ ] Set up a free landing page (Carrd, Tally, Substack — all
  free) with one line: "Penumbra is launching in X weeks; drop
  your email for the launch announcement".
- [ ] Promote it on every Twitter post + dev.to article.
- [ ] Target: 200-500 emails by launch day. Each email is a
  ~70% guaranteed star.

Why it works: launch-day stars compound. The first 100 stars in
the first 6 hours triggers the GitHub trending algorithm; the
mailing list guarantees this momentum.

### 1.5 Influencer pre-seeding (weeks -4 to -1)
Identify 5-10 micro-influencers in your space:
- **Crypto**: @matthew_d_green, @hashimotor (TLS), @hardyrandall.
- **ML**: @karpathy (too big; skip), but @soumithchintala (mid-tier),
  @karpat in micro-tier.
- **Italian dev**: search "Italian OSS contributor" / GDG / PyCon Italia.

Send a personal email or DM 4 weeks before launch:
"Hi [name], I've been following your work on X. I built Penumbra,
an integrated runtime for [whatever they care about] inspired
partly by [their thing]. Here's the private repo link; would you
take 10 minutes to look? No need to share publicly until launch
day, I just want to know if I missed anything obvious."

Why it works: people LOVE being asked for technical opinion.
Half will reply with useful feedback. A quarter will offer to
share on launch day. That's 1-2 amplifiers you didn't have before.

**Anti-tactic**: do NOT ask them to tweet at launch. Ask for
feedback. The tweet comes naturally if they like it.

---

## Part 2 — GitHub repo SEO (most undervalued lever)

A repo with weak SEO is invisible to organic discovery. Six small
optimizations push organic traffic up 3-5×.

### 2.1 Repository surface
- [ ] **Name**: short + memorable. `penumbra-arena` is fine.
  `penumbra` alone would be better (squat is okay until conflict).
- [ ] **Description** (<120 chars): keywords first. Suggested:
  "Privacy-preserving multi-agent arena for hands-on crypto, ML,
  and adversarial pedagogy. Mac mini M4, no GPU."
- [ ] **Topics** (max 20, choose 15-18):
  ```
  cryptography, post-quantum, homomorphic-encryption,
  differential-privacy, zero-knowledge-proofs,
  multi-agent-rl, reinforcement-learning, mappo,
  graph-attention, simulation, dashboard,
  apple-silicon, python, typescript, pedagogy,
  open-source, multi-agent, mlops, security-education,
  benchmark
  ```
- [ ] **Open Graph image** (`.github/og-image.png`, 1200×630).
  Custom design. Use Figma free tier or Canva. Hero text +
  one screenshot.
- [ ] **README first paragraph**: visible in social previews +
  search results. Treat like an ad copy. Lead with the novel
  position claim.

### 2.2 README structure
The hierarchy that converts:
1. Title + tagline (one sentence)
2. Hero screenshot or GIF (10-15s loop showing the dashboard)
3. **Status badges** (tests passing, license, latest tag, stars)
4. One-sentence "what is this" — non-technical reader friendly
5. "Quick start" code block — runs in <60 seconds
6. **Demo video** (90 seconds, embedded YouTube)
7. Concept overview (technical reader)
8. Architecture diagram
9. Run / Develop
10. Documents table
11. License + contributing

### 2.3 Pinned README assets
- [ ] Hero screenshot in `.github/screenshots/hero.png`. 1920×1080.
  Show: WorldView populated + AnalyticsPanel with 3-4 active tiles
  + at least one open modal.
- [ ] Animated GIF in `.github/screenshots/demo.gif`. 10-15s loop.
  Record with QuickTime; convert with
  `ffmpeg -i in.mov -vf "fps=15,scale=720:-1" -loop 0 demo.gif`.
- [ ] 90-second YouTube demo, embedded in README via the standard
  `https://www.youtube.com/watch?v=...` link (GitHub auto-renders
  as a play button on hover).

### 2.4 Discoverable file structure
- [ ] `LICENSE` at root (MIT). GitHub auto-detects.
- [ ] `CONTRIBUTING.md` at root. GitHub shows in "Contribute" tab.
- [ ] `SECURITY.md` — adds "Security" tab + credibility.
- [ ] `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1, standard.
- [ ] `.github/FUNDING.yml` — even at zero income, adds the
  "Sponsor" button visible on the repo. Pure signal.
- [ ] `.github/ISSUE_TEMPLATE/` — three templates: `bug.yml`,
  `feature.yml`, `question.yml`. Reduces noise + makes the repo
  look maintained.
- [ ] `.github/PULL_REQUEST_TEMPLATE.md`.
- [ ] `CHANGELOG.md` at root. Even if it just says "v1.0.0:
  initial public release."

### 2.5 Profile-level optimization
- [ ] Pin Penumbra to the user's GitHub profile (one of the 6
  pinned repos).
- [ ] Update profile README with one paragraph about Penumbra.
- [ ] Profile bio: one line mentioning Penumbra + arXiv link.

Why it works: every visitor to your profile becomes a potential
star. The pin is the cheapest distribution channel that exists.

---

## Part 3 — Launch day mechanics (deep tactics)

### 3.1 Pre-launch (day -1)
- [ ] Tag `v1.0.0`. Push tag. Verify GitHub Release page renders
  cleanly with release notes.
- [ ] DRY RUN: have one friend visit the GitHub link, attempt
  `docker compose up`, report friction. Fix before launch.
- [ ] **One trusted friend stars + forks the repo overnight**, so
  it isn't 0/0 at launch (a 1-starred repo gets 5× more stars
  than a 0-starred repo from the same traffic).

### 3.2 Time of launch
- **Day**: Tuesday or Wednesday. Monday is competing with HN
  backlog. Friday is low engagement. Saturday-Sunday spike but
  the audience is different (more general, less depth).
- **Hour**: 9:00 AM EST = 6:00 AM PT = 15:00 CET = 22:00 JST.
  Hits the morning rush in US, late morning in Europe, evening
  in Asia. The "global wave" is maximized.

### 3.2a What Hacker News actually is (for newcomers)

If you've never used Hacker News before, here's the model.

**Hacker News** (`news.ycombinator.com`) is a community-driven
link-aggregation forum operated by Y Combinator (the startup
accelerator behind Stripe, Airbnb, Dropbox, OpenAI). Founded by
Paul Graham in 2007. ~5 million monthly visitors — but the audience
is heavily weighted toward developers, founders, VCs, researchers,
and the "people who decide what gets popular" in tech.

It is NOT a portal where journalists write articles about you.
It is a forum where:
1. YOU submit a link with a title.
2. OTHER users upvote (or downvote) the submission.
3. If enough upvotes accumulate in the first 60-90 minutes after
   submission, the story reaches the **front page** (top 30
   visible stories).
4. Front page stories get 50,000-200,000 views in 24 hours.

**Submission categories**:

| Category | When to use | Title format |
|---|---|---|
| **Show HN** | When you've built something yourself and want feedback | `Show HN: <name> – <what it does in 5-8 words>` |
| **Ask HN** | Asking the community a substantive question | `Ask HN: <your question>` |
| Regular link | Sharing an article, paper, or other content | The article title, no prefix |

For an OSS project launch, use **Show HN**. The community expects:
- A working demo (link to GitHub repo)
- An author who responds to comments in real time
- A clear, technical description (no marketing language)

**Realistic outcomes** for a Show HN submission:

| Result | Upvotes | Visits | GitHub stars typically gained |
|---|---|---|---|
| Flop (90% of submissions) | 0-5 | < 500 | 5-10 |
| Decent (small lift) | 30-100 | 5,000 | 50-100 |
| Front page (1-2% of submissions) | 200-500 | 50,000-100,000 | 300-800 |
| Top of front page | 1000+ | 200,000+ | 1500-3000 |

A well-prepared Show HN with a novel project (which Penumbra is)
has roughly a 30-40% chance of reaching the front page.

**The submission process**:

1. Create an account at `news.ycombinator.com/login` (free,
   instant; just username + password).
2. Wait at least 1-2 weeks after creating the account before
   posting; meanwhile, leave 5-10 helpful comments on other
   stories. This builds a thin reputation; brand-new accounts
   are downweighted by the algorithm.
3. On launch day, go to `news.ycombinator.com/submit`.
4. Enter the URL of your repo + the Show HN title.
5. Click "Submit".
6. Open the submission's page and immediately leave a comment
   that opens the discussion: 3-5 sentences describing what
   you built, why, and the key technical decisions.
7. Stay at the keyboard for the next 6 hours. Reply to every
   comment within 10-15 minutes. The algorithm penalizes
   silent authors.

**The first 60 minutes determine the trajectory.** Submissions
that don't accumulate at least 10-15 upvotes in the first hour
rarely recover. Submissions that gain 30+ upvotes in the first
hour are likely to hit the front page.

**Anti-patterns** (do not do these):

- Do NOT ask friends to upvote (vote-ring detection bans the
  submitter permanently).
- Do NOT submit the same link more than once per year.
- Do NOT reply with just "thanks!" — wastes a comment slot. Use
  the upvote arrow on praise.
- Do NOT argue defensively with critics. Acknowledge ("you're
  right, that's a good point") and move on. You lose every
  public argument.

**Why Hacker News matters more than other channels**:
- A Reddit post tracks for 6 hours; an HN front-page hit tracks
  for 24-48 hours.
- HN comments often get cited in newsletters, blog posts, and
  academic papers — the discussion has long-tail value beyond
  the launch day.
- TechCrunch, The Verge, and other tech publications routinely
  cover stories that hit HN front page; you might get
  unsolicited press coverage from a single successful Show HN.
- The HN audience is the demographic that adopts OSS tools at
  work. A star from an HN reader is worth ~5× a star from a
  random Twitter follower in terms of downstream usage.

**You only get one Show HN per project.** If it fails, you cannot
resubmit with the same title or substantially similar content.
This is why the launch prep matters: the title, the timing, the
hero screenshot, the demo video, the response readiness all need
to be polished BEFORE the submission.

You CAN later submit follow-up stories on HN that are NOT Show HN:
- "Penumbra 6 months later: what we learned"
- "How we shipped Penumbra-Bench"
- "Federated learning with CKKS aggregation in 200 lines"

Each of these is a fresh submission with a fresh chance to reach
the front page.

### 3.3 The hour-by-hour playbook

**T+0 — submission**
- Submit to Hacker News.
- Wait 2-3 minutes for it to be indexed.
- Verify the submission shows on `news.ycombinator.com/newest`.

**T+10 minutes**
- Cross-post to Reddit (3-5 subreddits, one post each, native
  title format per subreddit).
- LinkedIn long-form post.
- Twitter/X launch thread.

**T+30 minutes**
- Submit to Lobste.rs (need invite, ask 1 month in advance).
- Submit to dev.to as an article (link in last paragraph).
- DM the influencers you pre-seeded.

**T+1 to T+6 hours**
- **Stay at the keyboard.** Reply to every comment within 10-15
  minutes.
- HN: thoughtful responses, even to harsh critiques. NEVER
  argue defensively. Acknowledge ("you're right, I should add
  that to the roadmap"), then move on.
- Reddit: same, with subreddit-specific tone.
- LinkedIn: respond with depth, tag the relevant people if
  natural.

**T+6 to T+24 hours**
- First sleep. Check on wake.
- If HN front page: 30-90% probability of 200-500 stars in next
  24 hours.
- If Reddit hit: smaller bump but more sustained over a week.
- If LinkedIn hit: usually leads to DMs / inbound, less stars.

**T+48 hours**
- Aggregate: stars count, top channels, sentiment of comments.
- Public progress tweet: "Penumbra Day 2: X stars, Y issues,
  Z PRs. Loving this. Here's what's next."

### 3.4 Title formulas that work

For Hacker News specifically:
- `Show HN: <project> – <what it does in 5-8 words>`
  Example: `Show HN: Penumbra – privacy-preserving multi-agent
  arena, runs on a Mac mini`
- Avoid: superlatives ("incredible", "revolutionary"), generic
  ("an open source project for X"), needy ("please check out").

For Reddit r/MachineLearning specifically:
- `[P] <project> — <novel claim in 8-12 words>`
  Example: `[P] Penumbra — integrated multi-agent arena with
  live PPO training + encrypted state, runs on M4`

For LinkedIn:
- Don't use HN-style title. Use personal narrative:
  "I built X for myself to learn Y. Here's what I shipped."

For X/Twitter:
- First tweet is the hook + screenshot. Don't waste it on a
  title.

### 3.5 Submission-specific channel etiquette

**Hacker News**:
- Submit ONCE. Don't resubmit if it doesn't take off in 4 hours.
- Don't ask friends to upvote (vote ring detection bans the
  submitter).
- Don't reply with "thanks!" to praise — wastes a comment slot.
  Use upvotes for those.

**Reddit r/MachineLearning**:
- Read the pinned posting guide; r/ML is the strictest.
- Lead with technical contribution, not "I'm proud of this".
- DO NOT crosspost the same content to r/programming and r/ML
  within an hour — mods flag this as spam.

**Reddit r/cryptography**:
- Smaller community, kinder. Lead with the novel position
  ("a Groth16 verifier from scratch in Python").

**LinkedIn**:
- 1500-2500 character sweet spot.
- 3-5 hashtags max (`#opensource #cryptography #machinelearning`).
- Tag 1-2 RELEVANT people, not random influencers.

**X/Twitter**:
- Threads outperform single tweets.
- Reply to your own thread 4-6 hours later with a "follow-up"
  tweet. Algorithm rewards this.
- Use the X "longer post" feature if you have the option, but
  threads still beat long posts.

---

## Part 4 — Sustained promotion (weeks 2-24)

### 4.1 The two-week rule
**Single biggest determinant of OSS survival**: ship something
visible every 2 weeks for the first 6 months. Tactics:

| Cadence | Ship type |
|---|---|
| Week 2 | First follow-up blog post (one deep concept) |
| Week 4 | First new feature release (e.g. Logistics Tier 1) |
| Week 6 | YouTube tutorial video |
| Week 8 | "Penumbra week 8 update" thread + LinkedIn |
| Week 10 | Conference workshop submission |
| Week 12 | Logistics Tier 2 + dev.to article |
| Week 14 | Talk at first online meetup |
| Week 16 | Hackathon prizes announced |
| Week 18 | First academic citation tracked |
| Week 20 | Tier 3 logistics |
| Week 22 | "Penumbra month 6" reflection post |
| Week 24 | Decision point (per OSS_LAUNCH_ROADMAP.md L5) |

### 4.2 Newsletter outreach playbook

**When**: 1-2 weeks AFTER launch, not the day of. Editors hate
"please feature my brand-new thing" — they want post-launch proof
of momentum.

**Targets (in order of leverage)**:
- TLDR (free signup, then propose feature once you have ≥200 stars)
- Hacker Newsletter (kale@hackernewsletter.com)
- Pointer (digest of programming writing)
- Last Week in AI (for the ML angle)
- The Pragmatic Engineer (broad reach, Substack)
- Programming Digest
- Daily Engineer
- DataElixir (for the analytics + ML angle)
- The Sample (curated newsletter directory; submit yourself)
- Faun.dev (DevOps adjacent)

**Email format** (3-5 sentences max):
```
Subject: Penumbra (OSS) — [novel claim in 10 words]

Hi [name],

I launched Penumbra last week — a [one-line description].
It's been on the HN front page / Reddit r/X / etc. Here's
the [github link] and the [arXiv link].

I think your readers might enjoy [specific angle for their
audience]. Would you consider a brief feature?

Happy to send screenshots, a short video, or write the
copy for you.

Best,
[name]
```

### 4.2a Hugging Face Hub as a second distribution channel

If [`SYNTHETIC_DATA_PLAN.md`](SYNTHETIC_DATA_PLAN.md) ships
alongside or shortly after the OSS launch, the dataset becomes
a SECOND distribution channel that runs on HF's own algorithm:

- HF datasets ranked by likes + downloads in the past 7 days
  appear on `huggingface.co/datasets?sort=trending`
- HF Spaces (free) can host a live demo using the dataset
- Researchers searching for "synthetic multi-agent" or "privacy
  preserving dataset" find the HF page; the HF page links back
  to the GitHub repo
- Each HF download is a referrer to the GitHub README

Tactics:
- [ ] Submit the dataset to HF "Trending datasets" by getting 10+
  likes in the first 24 hours
- [ ] Cross-list the dataset on Papers With Code
- [ ] Set up a small HF Space (free tier) with an interactive
  notebook that loads a sample of the dataset

### 4.2b Benchmark leaderboard as a sustained promotion engine

If [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) ships as v1.1, the
leaderboard becomes a slow-burn promotion engine. Tactics:

- [ ] Track who lands a top-10 submission; @-mention them on X
  with congratulations
- [ ] Quarterly "Penumbra-Bench Q1 review" post: top methods,
  new techniques, total submissions
- [ ] Reach out to research groups working on related problems
  with "would your method be a good fit for our benchmark?"
- [ ] Submit the benchmark to NeurIPS Datasets & Benchmarks Track
- [ ] Submit a "demo paper" describing the leaderboard to the
  next ML conference's demo track

### 4.3 "Awesome" list submissions

Submit a PR to each, with the entry text drafted. List ordered by
star count of the destination repo (proxies for traffic):

- `awesome-cryptography` (3-tier list, very curated)
- `awesome-zero-knowledge-proofs`
- `awesome-fhe`
- `awesome-pq-crypto` / `awesome-quantum-resistant`
- `awesome-rl`
- `awesome-mlops`
- `awesome-multi-agent`
- `awesome-pedagogy` / `awesome-courses`
- `awesome-privacy`
- `awesome-self-hosted` (if Penumbra qualifies as such)
- `awesome-blockchain` (peripheral but accepts)
- `awesome-python` (low-quality bar; high traffic)

**Entry format** (most "awesome" lists use this):
```
- [Penumbra](https://github.com/Vadale/penumbra-arena) - Privacy-preserving multi-agent arena for hands-on crypto + ML + adversarial pedagogy. Runs on Mac mini M4, no GPU required.
```

### 4.4 Conference + meetup submissions

**Conferences with rolling acceptance** (anytime):
- PyCon US / EuroPython — lightning talks open weeks-ahead
- SciPy — same
- Open Source Summit (Linux Foundation; Europe + NA)
- FOSDEM (volunteer-organized; submit early Dec for Feb)

**Conferences with annual deadlines**:
- NeurIPS Datasets & Benchmarks Track — May submission
- ICML AutoRL workshop — June submission
- USENIX CSET workshop — late submission for August/September
- Real World Crypto — November submission for January
- ZK Summit — varies
- AAAI / IJCAI — annual

**Meetups** (low bar, high practice value):
- Python Italia (mailing list)
- ItaliaPython
- GDG Milano / Roma
- OWASP Italy chapter
- Local university research groups
- Online: Meet the Maintainer, Open Source Friday

### 4.5 Become a podcast guest (free amplifiers)

Target podcasts that talk to your audience. Pitch with a hook +
3 specific talking points:

- ChangeLog (general OSS)
- Software Engineering Daily
- Hanselminutes
- ZK Podcast (specific to zk)
- The Pragmatic Engineer Podcast
- Practical AI

Pitch email (3 sentences max):
```
Subject: Podcast guest? Penumbra — integrated runtime for
crypto + ML pedagogy

Hi [host], I built Penumbra (HN front page, X stars).
I think your audience would enjoy a discussion on:
(1) why integrated runtimes matter,
(2) what we learned from 6 attack vectors against our own crypto,
(3) running PPO on Apple Silicon without CUDA.

[GitHub link] [arXiv link]
```

### 4.6 Wikipedia (long game)

When Penumbra accumulates:
- 1500+ stars,
- 2+ academic citations in independent papers,
- 3+ conference talks delivered,
- Coverage in at least one notable newsletter/blog,

… then a Wikipedia article becomes possible. **Do not write it
yourself** — Wikipedia rejects autobiographical articles.

Instead: ensure independent coverage exists. Notable bloggers /
academics write about you → Wikipedia editor notices →
article is created naturally.

### 4.7 Star compounding tactics

**GitHub Trending eligibility**:
- ≥30 new stars in a day → language-specific trending (Python,
  TypeScript).
- ≥100 → global trending.
- One day on global trending = 200-500 stars cascade.

**How to trigger**: a single big amplifier (HN front page,
viral tweet, podcast feature) usually does it. Hard to trigger
deterministically.

**Star history charts**:
- After 100 stars, post a `star-history.com/#Vadale/penumbra-arena`
  graph on Twitter monthly. Visual progress is engaging.
- After 1000 stars, do a "1000 stars, here's what I learned"
  blog post.

---

## Part 5 — Community-building tactics

### 5.1 GitHub Discussions setup
- [ ] Enable Discussions on the repo.
- [ ] Create categories: Q&A, Show & Tell, Ideas, Research.
- [ ] Pin one welcome discussion: "Hi! How are you using
  Penumbra? Tell us in the replies."
- [ ] Respond to every Discussion within 24h for first 3 months.

### 5.2 Discord / Slack
**Recommendation**: Discord (free, more active for OSS).

Setup:
- Channels: `#announcements` (read-only), `#general`,
  `#help`, `#contributors`, `#showcase`, `#italian-speakers`
  (your home community).
- Pin the README + arXiv link.
- Don't promote Discord until you have 200+ stars (creates
  empty-server perception).

Goal: 50 members by month 6. Quality > quantity. A 50-person
Discord with 5 active contributors beats a 500-person Discord
with no engagement.

### 5.3 Office hours
- [ ] Once a month, host a 60-minute live coding / Q&A on
  Twitch or YouTube Live. Free, builds parasocial bond.
- Record + repost on YouTube for asynchronous reach.

### 5.4 Hackathon

Self-sponsored, online, 48 hours. Budget: $500-1000 in prizes
(Amazon gift cards / Penumbra t-shirts if you spin up Printful).

Tracks:
- "Best new dashboard tile" ($300)
- "Best attacker variant" ($300)
- "Most creative use of the Penumbra API" ($200)
- Best paper citation / write-up ($200)

Why it works: 50-100 hackathon participants × they each tell ≥5
friends = audience expansion.

---

## Part 6 — Multiplier strategies

### 6.1 Localization
- [ ] Italian README (`README.it.md`). Your home market is high-
  engagement.
- [ ] Spanish README (~580M speakers).
- [ ] Chinese README (`README.zh-CN.md`) — submit to Chinese
  developer communities (Juejin, V2EX). High-leverage if you
  can identify a friend to help with idioms.

Why it works: most OSS projects are English-only. Translations
unlock entirely fresh audiences.

### 6.2 Cross-language YouTube
- Italian channel: tutorials for the Italian dev community.
- English channel: international reach.
- Same content, different language → 2× audience for ~30% extra
  effort.

### 6.3 Long-tail SEO via decision posts
Every technical decision in Penumbra is a potential blog post that
will rank for niche searches FOREVER. Each post = a small but
permanent traffic stream. Suggested first 10:

1. "Why we chose MIT over Apache-2 for Penumbra"
2. "Why MAPPO and not SAC for multi-agent RL"
3. "Why TenSEAL and not OpenFHE as primary HE backend"
4. "What we learned shipping a Groth16 verifier in pure Python"
5. "How we run 50 agents at 10 Hz on a Mac mini M4"
6. "Live training in an inference loop — what could possibly go
   wrong"
7. "The bullwhip effect, visualized in a 50-agent supply chain"
8. "Differential privacy budget exhaustion: a failure-mode tour"
9. "How we measure optimality gap between learned and centralized
   policies"
10. "Why we ship a `pna` CLI for attacks AND a dashboard"

Each post: 1500-3000 words, 1-2 diagrams, code excerpts, links
back to the repo + arXiv. Cross-publish to dev.to + your own
blog. Each post will accumulate traffic for 12-24 months.

### 6.4 Twitter list strategy

Once you launch:
- [ ] Maintain a Twitter list of "Penumbra contributors" (anyone
  who has interacted with the repo). Public list → ego boost for
  list members → they share more.
- [ ] Maintain a list of "OSS projects we ❤️" — shows you care
  about the ecosystem, not just yourself.

### 6.5 Cross-repo strategic mentions

Find existing tutorials / blog posts that touch your domain.
Submit small docs PRs that add a "see also: Penumbra" link
where genuinely useful. **Only where useful** — abuse damages
both repos.

Targets:
- Awesome lists (Section 4.3 above)
- TenSEAL tutorials / docs
- CleanRL examples folder
- Any course material referencing CKKS / Kyber / Dilithium

---

## Part 7 — Anti-patterns (do NOT)

| Anti-pattern | What goes wrong |
|---|---|
| Buy stars / sock-puppet accounts | GitHub detects → shadow-ban → game over |
| Spam Discord / Slack communities | Reputation damage spreads fast |
| Mass-DM influencers asking for stars | They've seen it 100 times; auto-delete |
| Submit to same subreddit twice in a week | Moderator filter / ban |
| Argue with critics on HN / Reddit | You lose every public argument |
| Disappear after launch | Single biggest project-killing pattern |
| Promise features at launch you haven't shipped | Burns credibility forever |
| Ignore non-English-speaking users | You leave 60% of OSS audience on the table |
| Refuse PRs for not-invented-here reasons | Contributors leave; the project stagnates |
| Treat the launch as the goal | Launch is week 5 of a 52-week marathon |

---

## Part 8 — The compounding flywheel (12-24 month view)

| Month | Cumulative effect |
|---|---|
| 0 | Launch: 100-500 stars from concentrated traffic |
| 1 | First newsletter mention: +200 stars over a week |
| 3 | First conference talk delivered: +300 stars + speakers list mention |
| 6 | Academic citation: +100 stars + Google Scholar visibility |
| 9 | Speaker invites snowball; talks at 2-3 conferences |
| 12 | "Penumbra at 1 year" retrospective post viral: +1000 stars |
| 18 | Logistics Tier 3 ships: news angle for fresh coverage |
| 24 | Community of 50+ regular contributors; project self-sustains |

Each milestone makes the next milestone easier. The flywheel
doesn't start until you're past month 3-6 — which is exactly when
most projects die from founder burnout. The single difference
between projects that win and projects that don't is **showing up
every 2 weeks for the first year**.

---

## Part 9 — KPI dashboard

Track weekly. Snapshot in a `growth.md` file that you update
publicly. Transparency itself is a marketing tactic.

| Metric | How to track | Cadence |
|---|---|---|
| GitHub stars | API or repo page | Weekly |
| Forks | API | Weekly |
| External PRs merged | API + manual filter | Bi-weekly |
| External issues opened | API | Weekly |
| Twitter followers added | Twitter analytics | Weekly |
| arXiv views | Semantic Scholar / Connected Papers | Monthly |
| Newsletter mentions | Google Alerts on "Penumbra" | Weekly |
| Speaking invitations | Email count | Monthly |
| Wikipedia notability score | Independent coverage count | Quarterly |
| Hackernews submissions referencing Penumbra | search.hn.algolia.com | Monthly |
| Reddit mentions | searx + manual | Monthly |
| Google Scholar citations | Author dashboard | Quarterly |

---

## Part 10 — When NOT to follow this playbook

This playbook assumes the project is positioned for broad audience.
A few scenarios where you should deviate:

- **Highly specialized academic niche** (e.g. "a new VRF
  construction for blockchain finality") — skip HN / Reddit; go
  directly to academic outreach (mailing lists, workshop
  submissions, paper preprints). Audience is 500 people max
  globally; popular promotion is wasted.
- **Enterprise tool with no individual users** — same; the
  "stars" metric is mostly vanity. Go via Gartner mention, RFP
  responses, partner channels.
- **Already established maintainer** — your existing audience IS
  the launch channel. Don't perform launch theater.

For Penumbra, none of these apply — it's exactly the right
audience for the playbook above.

---

## Quick-reference checklist

**Pre-launch (8-12 weeks)**:
- [ ] Build in public on Twitter / dev.to
- [ ] Contribute to OpenFHE / TenSEAL / CleanRL
- [ ] Reddit karma ≥1000 in target subs
- [ ] Mailing list 200+
- [ ] Influencer pre-seed (5-10 personal DMs)

**GitHub SEO**:
- [ ] Topics (15-18)
- [ ] OG image (1200×630)
- [ ] Hero screenshot + GIF in README
- [ ] LICENSE / CONTRIBUTING / SECURITY / CODE_OF_CONDUCT / FUNDING.yml
- [ ] Issue templates + PR template
- [ ] Pin to user profile

**Launch day**:
- [ ] Tuesday or Wednesday, 9 AM EST
- [ ] HN + 5 subreddits + LinkedIn + X thread + dev.to
- [ ] One friend pre-stars at T-1
- [ ] Stay at keyboard 6 hours

**Sustainment (every 2 weeks)**:
- [ ] Blog post or feature release
- [ ] Conference / talk submission
- [ ] Newsletter outreach
- [ ] Update KPI dashboard

**Community**:
- [ ] GitHub Discussions enabled
- [ ] Discord set up (post-200-stars)
- [ ] Office hours monthly
- [ ] Hackathon at month 4

**Don't**:
- [ ] Buy stars / use bots
- [ ] Spam communities
- [ ] Argue with critics publicly
- [ ] Disappear after launch
- [ ] Promise undelivered features

---

**This playbook is a planning artefact. Update sections with
learnings as the launch unfolds. The single rule that beats all
others: SHOW UP. Every 2 weeks. For a year. The compounding does
the work.**
