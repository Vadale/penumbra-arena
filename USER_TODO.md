# USER_TODO — cose che richiedono MANI UMANE prima del lancio OSS

> Documento separato per ricordarti tutte le azioni che non posso
> eseguire io (Claude). In ordine di priorità per il lancio.
> Tutte le altre cose tecniche/codice sono già completate al
> 100% nel repository.

Data: 2026-05-24
Stato repo: post-Phase-6b (cyber range), v3.0-ready in code.
832 backend test + ~30 vitest tutti green; 11 packages; 91 tile / 96 chart; 3 React routes
(`/`, `/bench`, `/operator`); 3 CLI (`pna`, `psh`, `pno`).
Tutte le fasi di codice (Phase 5 + 6a + 6b) shipped 2026-05-24.

---

## 🚫 REPO VISIBILITY GATE — NON flippare a public finché P0 non chiusi

**Stato repo GitHub**: `Vadale/penumbra-arena` — **PRIVATE**.

**Topics**: già aggiunti (15: reinforcement-learning, multi-agent,
federated-learning, homomorphic-encryption, differential-privacy,
benchmark, dataset, blockchain, cyber-range, privacy-preserving,
mappo, ckks, post-quantum, zk-snark, research).

**Bloccanti hard per il flip a public** (vedi anche P0 §1-3 sotto):

1. **Email `lemostream@proton.me` esposta in 3 file** (`SECURITY.md`,
   `CODE_OF_CONDUCT.md`, `USER_TODO.md` stesso). Una volta pubblico:
   - Google indicizza in 24-48h
   - Scanner spam la trovano in giorni
   - Disclosure crypto-security arrivano sulla personale, non su un
     alias dedicato
   - **Azione**: cambia con `security@penumbra-arena.org` (richiede
     dominio) o `Penumbra-Arena+security@protonmail.com` (gratis)

2. **`docs/hero.png` non esiste** — README lo referenzia → image broken
   sulla landing page GitHub. **Azione**: vedi P0 §2 sotto per i comandi.

3. **`docs/og.png` non esiste** — quando il link gira su Twitter /
   LinkedIn / HN, sharing preview = testo nudo → -3x click-through.
   **Azione**: vedi P0 §3 sotto.

**Soft (raccomandati ma non bloccanti)**:

4. **Leggere il verdetto di un second-opinion model** prima di lanciare
   (vedi `EVALUATION_PROMPT.md`). Magari l'altro modello suggerisce un
   repositioning della README che vorrai applicare PRIMA del flip a
   public, non dopo (per evitare "i primi cento visitatori hanno visto
   la frase sbagliata").

5. **Penumbra-Bench submissions repo** (`Vadale/penumbra-bench-
   submissions`) ancora non creato (vedi P1 §5). Se vuoi che il primo
   bench-PR funzioni il giorno del lancio, crealo prima.

### Come flippare quando hai chiuso 1-3 (e idealmente 4-5)

```sh
# Dal terminale (richiede gh CLI autenticato, già configurato sul Mac):
gh repo edit Vadale/penumbra-arena --visibility public --accept-visibility-change-consequences

# Verifica
gh repo view Vadale/penumbra-arena --json visibility,url
```

**Avvertenza permanente**: la visibility change è hard-to-undo. Una
volta indicizzato da Google / clonato da bot / forkato, anche se
ri-privatizzi gli artefatti rimangono. Misura due volte, taglia una.

---

## P0 — Bloccanti prima del lancio pubblico

### 1. Email di security disclosure
**File**: `SECURITY.md`
**Cosa**: cambia `lemostream@proton.me` con una mail dedicata
(es. `security@penumbra-arena.org`) e aggiungi un blocco PGP key.

**Perché**: ricevere disclosure crypto via mail personale è OK pre-lancio,
ma dopo il lancio espone il tuo indirizzo personale e non è una
practice professionale.

**Tempo**: 15 min (registrare la mail) + 5 min (esportare PGP).

### 2. Hero screenshot
**File da creare**: `docs/hero.png`
**Spec**: `docs/HERO_IMAGE_SPEC.md`

Devi:
1. `docker compose up` (o avvia lo stack manualmente)
2. Aspettare ~5 minuti per popolare tutti i tile
3. Attivare FL (`POST /federated/start`) + Logistics (basta che giri qualche
   minuto perché si formino stockout)
4. Screenshot dell'intera dashboard a `2560×1440` con `Cmd+Shift+5`
5. Croppare a 1920×1080
6. `pngquant --quality=85-95 --speed 1 hero.png` per ridurre size
7. Salvare in `docs/hero.png`

**Perché**: la README sulla pagina GitHub mostra questa come prima cosa.
Senza, il progetto sembra abbandonato.

**Tempo**: 30 min.

### 3. OG image (social preview)
**File da creare**: `docs/og.png`
**Spec**: `docs/OG_IMAGE_SPEC.md`

Dimensioni esatte: 1200×630 px.

Devi:
1. Aprire Figma / Affinity / Sketch
2. Layout: 1/3 sinistra = wordmark + tagline; 2/3 destra = crop dell'hero
3. Export PNG 1×, < 600 KB
4. Salvare in `docs/og.png`
5. Editare `apps/web/index.html`:
   ```html
   <meta property="og:image" content="https://raw.githubusercontent.com/Vadale/penumbra-arena/main/docs/og.png" />
   <meta name="twitter:image" content="https://raw.githubusercontent.com/Vadale/penumbra-arena/main/docs/og.png" />
   ```

**Perché**: quando condividi il link GitHub su LinkedIn / X / Reddit,
questo è ciò che appare. Default Github cara di testo non bucha il feed.

**Tempo**: 45-60 min (Figma vs templating).

---

## P1 — Per il momento del lancio (settimana di Show HN)

### 4. Repo GitHub pubblico
- Trasformare `Vadale/penumbra-arena` da privato a pubblico
- Verificare che `LICENSE` + `LICENSE-DATA` siano committati
- Verificare che `.github/workflows/ci.yml` faccia il primo run verde
  (push a main triggera il workflow)
- Aggiungere topics: `reinforcement-learning`, `multi-agent`,
  `federated-learning`, `homomorphic-encryption`, `differential-privacy`,
  `benchmark`, `dataset`

**Tempo**: 30 min.

### 5. Repo benchmark submissions
**Cosa**: creare repo SEPARATO `Vadale/penumbra-bench-submissions` su
GitHub.

Contenuto minimo:
- `README.md` con istruzioni di submission
- `submissions/` (vuota all'inizio)
- Workflow che richiama il validator (copia di
  `.github/workflows/bench-validate.yml` da questo repo, ma adatta i path)

**Perché**: Penumbra-Bench Tier 3 prevede che gli external contributors
aprano PR su un repo dedicato — non sul main repo. Tiene separato il
"codice del benchmark" dalle "submission al benchmark".

**Tempo**: 1 ora.

### 6. Pubblicazione Hugging Face dei dataset
**Cosa**: pubblicare `state/datasets/standard/` + `state/datasets/large/`
+ `state/datasets/mega/` su Hugging Face Hub come dataset card.

Steps:
1. `pip install huggingface_hub`
2. `huggingface-cli login` (richiede token da hf.co/settings/tokens)
3. `huggingface-cli upload Vadale/penumbra-data state/datasets/ --repo-type dataset`
4. Aggiungere `README.md` (dataset card) sul repo HF con:
   - Citazione (vedi CITATION.cff)
   - License CC-BY-4.0 esplicita
   - Schema delle 7 modalità
   - Esempi di caricamento con `datasets.load_dataset()`

**Perché**: la USP "Penumbra-Data" del 3-in-1 richiede pubblicazione
esterna. Solo locale non vale per pubblicazione accademica.

**Tempo**: 1-2 ore.

### 7. arXiv submission
**File pronto**: `PAPER.md`

Steps:
1. Convertire `PAPER.md` in LaTeX (puoi usare `pandoc PAPER.md -o paper.tex`)
2. Aggiungere figure proper (un diagramma architetturale almeno)
3. Compilare bibliografia con BibTeX (le citation chiavi sono ancora
   placeholder — riempire con paper veri)
4. Submit ad arXiv (cs.CR primary, cs.LG cross-list)
5. Una volta assegnato l'ID, aggiornare:
   - `CITATION.cff` (campo `doi` o `eprint`)
   - `PAPER.md` (sostituire `2606.XXXXX` con l'ID reale)
   - `README.md` link arXiv

**Perché**: l'arXiv preprint è il primo artefatto del launch — la
roadmap lo mette in settimana 1.

**Tempo**: 4-6 ore (la conversione LaTeX + bibliografia è il grosso).

### 8. Demo video
**Cosa**: video di 2-3 minuti che mostra Penumbra live.

Suggested script:
1. (0:00-0:30) Apri dashboard, mostra agenti che si muovono, l'heatmap encrypted
2. (0:30-1:00) Clicca su una tile (CKKS demo) — mostra l'encrypt/decrypt
3. (1:00-1:30) Attiva FL, fai partire un round, mostra le metriche
4. (1:30-2:00) Apri `/bench`, mostra il leaderboard
5. (2:00-2:30) Terminale `pna` — un attacco demo
6. (2:30-3:00) Conclusione

Tools: `OBS Studio` (gratis) per la registrazione, `HandBrake` per la
compressione MP4 < 50 MB.

Upload su YouTube unlisted; link in README.

**Perché**: per il post HN/Reddit/LinkedIn, un video di 2-3 minuti
incrementa il click-through di ~3x sul testo.

**Tempo**: 2-3 ore (registrazione + edit + upload).

---

## P2 — Post-lancio (prima settimana)

### 9. Hacker News "Show HN" post
**Quando**: Tuesday/Wednesday 9 AM EST (15:00 ora italiana). Vedi
`OSS_GROWTH_PLAYBOOK.md` per la timing analysis.

**Titolo suggerito**: "Show HN: Penumbra – A privacy-preserving
perpetual multi-agent arena (MIT + CC-BY-4.0)"

**Body**: 200-300 parole; vedi `OSS_LAUNCH_ROADMAP.md` per il template.

Punti chiave da includere:
- 3-in-1 (teaching + benchmark + dataset)
- ~50k LOC, 454+ test, M4-friendly
- Demo link + screenshot
- arXiv link
- HF dataset link

**Perché**: HN è la single source of organic traffic più alta nella
launch window. 80% del traffico iniziale viene da qui se ti agganci
ai primi 30 (front page).

### 10. Reddit posts
Target subs (in ordine di priority):
- `r/MachineLearning` (gigante; mod-controlled; valido se passi)
- `r/cryptography` (cross-post)
- `r/Python` (volume + tooling angle)
- `r/programming` (generalist)

**Template**: stesso di HN ma adattato (HN preferisce il "show", Reddit
preferisce "ho fatto X, AMA").

### 11. LinkedIn long-form post
**Quando**: stesso giorno di HN.

**Lunghezza**: 1200-1800 caratteri (sweet spot per la timeline).

Punto: te + tecnologia. Personal angle, non corporate.

### 12. X/Twitter thread
**Quando**: stesso giorno.

**Lunghezza**: 8-12 tweet, ogni uno con uno screenshot diverso (heatmap,
barcode, leaderboard, FL round, ecc.).

### 13. Setup GitHub Sponsors / OpenCollective
**File**: `.github/FUNDING.yml` (placeholder già pronto)

Steps:
1. Registrare GitHub Sponsors → richiede 1099 K-1 / fiscal entity
2. (Alternativa) OpenCollective o ko-fi
3. Aggiornare `FUNDING.yml` con gli handle veri

**Perché**: averlo configurato dal giorno 1 = stars→sponsors funnel
funzionante. Senza, perdi conversion.

**Tempo**: 1 ora.

### 14. Setup dedicated email
**Quando**: dopo i primi 100 stars / submission.

Opzioni:
- `security@penumbra-arena.org` (richiede dominio)
- Indirizzo `Penumbra-Arena+security@protonmail.com` (gratis)

Aggiornare `SECURITY.md`.

---

## P3 — Continuous (oltre il primo mese)

### 15. ~~Generate_dataset.py shard refactor~~ — **DONE 2026-05-23**

Refactor shipped: `_ShardWriter` writes parquet incrementally every
`CHUNK_TICKS=100_000` ticks. Mega @ 5M ticks now succeeds in 50min
wall / 82 MB output / 253 shards across 7 modalities (see
`state/datasets/mega/`).

### 16. ~~PyG dependency add~~ — **DONE 2026-05-23**

`torch-geometric>=2.6` added to `packages/learning/pyproject.toml`.
`SupplyGraphEncoder` now uses `torch_geometric.nn.GATv2Conv`. 7/7
tests pass.

### 17. ~~Crypto auditor sign-off retroattivo~~ — **DONE 2026-05-23**

Crypto-auditor agent reviewed `packages/crypto/`, `packages/chain/`,
`packages/attacker/`, `packages/learning/penumbra_learning/federated.py`,
`packages/learning/penumbra_learning/federated_dp.py`. Verdict:
SAFE-FOR-RESEARCH + SAFE-FOR-DEMO. Full report in `SECURITY_AUDIT.md`
with 4 production blockers (2 fixed, 7 documented for follow-up).

### 18. arXiv ID nel BibTeX
Quando arXiv ti assegna l'ID dopo submission (P1 task #7), aggiorna:
- `PAPER.md` riga 11 (sostituire `2606.XXXXX`)
- `CITATION.cff` (aggiungere campo `doi`)
- `README.md` (link arXiv reale)

---

## Checklist riassuntiva

Pre-lancio (P0+P1):
- [ ] Email security dedicata + PGP
- [ ] hero.png catturato
- [ ] og.png creato
- [ ] Repo GitHub pubblico + topics
- [ ] Repo `penumbra-bench-submissions` separato
- [ ] HF dataset publish
- [ ] arXiv submit
- [ ] Demo video YouTube

Lancio (P2):
- [ ] HN Show post
- [ ] Reddit 4 subs
- [ ] LinkedIn long-form
- [ ] X thread 8-12 tweet
- [ ] FUNDING.yml handle veri
- [ ] Dominio + email dedicata

Continuous (P3):
- [x] ~~generate_dataset shard refactor~~ (done 2026-05-23, Mega 5M
      shipped: 82 MB / 253 shards / 50min wall)
- [x] ~~PyG dep upgrade~~ (done 2026-05-23, torch-geometric>=2.6 added)
- [x] ~~Crypto-auditor retro sign-off~~ (done 2026-05-23, see
      `SECURITY_AUDIT.md`)
- [ ] arXiv ID propagato nei file
- [x] ~~G2 subgroup membership check in Groth16~~ (closed 2026-05-24)
- [x] ~~Stake-weighted finality threshold~~ (closed 2026-05-24)
- [x] ~~Atomic `tmp+rename` writes for secrets/budget files~~ (closed 2026-05-24)
- [x] ~~Denser RDP order grid~~ (closed 2026-05-24, 12 → 60+ orders)
- [x] ~~Key zeroization where feasible~~ (closed 2026-05-24)
- [x] ~~VRF/timing tighter `compare_digest` comparisons~~ (closed 2026-05-24)
- [ ] Wesolowski VDF Miller-Rabin with random witnesses

Post-launch v2.0 / v3.0 planning (gates: 500+ stars OR 10+ bench
submissions; vedi i 3 doc):
- [x] ~~Phase 5 — CRYPTO_ATTACK_DEFENSE_PLAN.md~~ (shipped 2026-05-24)
- [x] ~~Phase 6a — INTER_SILO_INTEGRATION_PLAN.md~~ (shipped 2026-05-24)
- [x] ~~Phase 6b — OPERATOR_MODE_PLAN.md~~ (shipped 2026-05-24)
- [ ] 24h definitive stress test (we have only a 10-min smoke; the
      multi-hour run is required for the "no leak under sustained load"
      claim in the launch post)

---

Quando hai dubbi su uno specifico item, chiedimi e ti spiego nel
dettaglio (incluso comandi terminale precisi per upload HF, formato
arXiv, ecc.).
