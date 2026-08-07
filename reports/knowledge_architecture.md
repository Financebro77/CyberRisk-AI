# Knowledge Layer Architecture — CyberRisk AI

**Status:** design + scaffold only. **No product code written.**
**Companion:** the scaffold lives in `knowledge/` (see `knowledge/README.md`); the
gap analysis this design closes is `reports/model_improvement_roadmap.md` and
the knowledge-gap report (`knowledge-gap-analysis.md` if saved).
**Scope:** modular knowledge layer supporting security standards, insurance
guidance, threat intelligence, regulatory requirements, industry reports,
historical incidents, and quantitative benchmark datasets — with RAG retrieval,
designed so new documents can be added without changing the codebase.

---

## 1. Design principles

1. **Content is data, never code.** Adding a document, a regulation, a report,
   or a dataset is a file-drop + one manifest entry. The product code is
   written once and driven entirely by manifests.
2. **Every fact carries provenance.** A Marsh-grade consultancy needs "every
   number traces to a source" to be literally true. Every retrievable unit
   ships a citation record; every report cites what it used.
3. **License-aware isolation.** The corpus mixes *public* (DBIR, NIST, DORA),
   *licensed* (Advisen/Cyence, IBM data), *proprietary* (Marsh practice
   reports), and *client-confidential* (a client's incident history).
   Retrieval must never cross those boundaries.
4. **Content vs. derived state.** Authored documents and datasets live in git.
   Chunks, embeddings, and the vector index are regenerable build artifacts,
   kept out of git.
5. **Hybrid retrieval, not pure vector search.** Semantic + keyword + metadata
   filters, because a clause citation ("DORA Art. 5(2)") is a metadata lookup,
   not a similarity search.
6. **One seam to the engine.** Structured datasets feed calibration through the
   existing `BenchmarkSet` contract (`src/cyberrisk/data/loaders.py`), so a
   new licensed dataset swaps in with zero engine changes.

---

## 2. Architecture at a glance

```
             ┌────────────────────────────────────────────────────────┐
             │                    KNOWLEDGE LAYER                       │
             │  manifests/  ← single source of truth (YAML, in git)    │
             │  corpus/     ← authored documents (in git)              │
             │  datasets/   ← structured tables (in git, or linked)    │
             │  schemas/    ← JSON Schemas validating everything       │
             │  access/     ← license tier → role policy               │
             └──────────────┬──────────────────────────────┬───────────┘
                            │                              │
              [ingest pipeline]                    [retrieval service]
        manifest → validate → chunk      query → scope/ACL → hybrid
        → embed → index → state.json     retrieve → rerank → citations
                            │                              │
        ┌───────────────────▼──────────────────────────────▼───────────┐
        │   derived/ (generated, gitignored): chunks, embeddings,      │
        │   index, ingestion state                                       │
        └───────────────────┬──────────────────────────────┬───────────┘
                            │                              │
        ┌───────────────────▼──────────────┐   ┌───────────▼───────────┐
        │  EXISTING ENGINE (unchanged)      │   │  CONSULTANT AGENT      │
        │  apply_benchmarks / BenchmarkSet  │   │  tools → numbers       │
        │  calibration, simulation, metrics │   │  knowledge → citations │
        └──────────────────────────────────┘   └────────────────────────┘
```

---

## 3. Folder structure

```
C:\Users\jahe-\cyberrisk\knowledge\
│
├── README.md
│       The "add-a-document" contract. Entry point for any contributor:
│       what a document is, the 3-step add flow, the schema rules, and
│       what must never be committed (licensed data, client data, derived/).
│
├── manifests\                          ← DATA-DRIVEN INDEXES (in git)
│   ├── corpus_manifest.yaml            The single source of truth for every document.
│   │                                   One entry per doc: id, domain, source, license
│   │                                   tier, version, content hash, chunking strategy,
│   │                                   embed model, refresh cadence, tags, status.
│   ├── dataset_manifest.yaml           Same, for structured datasets — plus `format`,
│   │                                   `schema`, and `targets:` naming the engine seam it
│   │                                   feeds (e.g. `calibration.apply_benchmarks`).
│   ├── domains.yaml                    The registered domain/category vocabulary. Adding a
│   │                                   NEW domain (e.g. "ai-risk") is a line here — not code.
│   └── manifest.example.yaml           A worked, copy-pasteable example for contributors
│                                       (one doc + one dataset).
│
├── schemas\                            ← VALIDATION BOUNDARY (JSON Schema)
│   ├── document.schema.json            Validates every corpus_manifest entry at ingest —
│   │                                   same "loud error at the boundary" pattern as
│   │                                   calibration.py. Malformed entries fail ingestion.
│   ├── dataset.schema.json             Validates dataset_manifest entries + the table
│   │                                   columns/units of each dataset file.
│   ├── chunk.schema.json               The chunk record emitted by the chunker (id, doc id,
│   │                                   content, section ref, char span, embedding hash).
│   └── citation.schema.json            The citation record attached to every retrieved unit
│                                       (doc id, source, version, chunk ref, page/paragraph,
│                                       retrieved_at, license tier). What the agent cites.
│
├── corpus\                             ← AUTHORED KNOWLEDGE (in git; one folder per doc)
│   │
│   ├── standards\                      Cyber security standards & frameworks
│   │   ├── nist-csf-2.0\              NIST CSF 2.0 functions/controls. Chunked PER CONTROL.
│   │   │                              Feeds a framework→factor mapping table.
│   │   ├── iso-27001\                 ISO/IEC 27001:2022 controls (A.5–A.8 Annex A).
│   │   ├── cis-controls\              CIS Critical Security Controls v8.
│   │   ├── nist-800-53\               800-53 controls for US public-sector clients.
│   │   ├── soc2\                      SOC 2 trust-service criteria.
│   │   └── pci-dss\                   PCI DSS v4 requirements.
│   │
│   ├── insurance\                     Coverage & market knowledge (mixed license tiers)
│   │   ├── wordings\                  Actual policy forms: cyber clauses, ransomware
│   │   │                              sub-limits, system-failure, dependent BI, BEC/crime
│   │   │                              split, war/silent-cyber exclusions. Chunked PER CLAUSE.
│   │   │                              Foundation for "would your policy respond?"
│   │   ├── market-terms\              Limits / retentions / attachment points by sector
│   │   │                              and revenue band. Answers "is a $25M limit typical?"
│   │   │                              against the MARKET, not just the client's own curve.
│   │   ├── pricing\                   Rate-on-line and premium tables (licensed tier).
│   │   │                              Feeds the pricing model.
│   │   └── claims-guides\             Claims handling, notification duties, BI/extra-
│   │                                  expense, statutory-defence coverage guidance.
│   │
│   ├── threat-intel\                  FAST-REFRESH, PERMISSIONED (the marketed "external
│   │   │                              threat intel" that the architecture diagram claims)
│   │   ├── campaigns\                 Active ransomware/extortion campaign reports.
│   │   │                              Chunked per campaign; freshness-boosted in retrieval.
│   │   ├── actors\                    Threat-actor profiles: TTPs, targets, tools, affiliates.
│   │   ├── sector-landscapes\         Per-industry attack patterns (replaces the coarse
│   │   │                              3-level _INDUSTRY_TARGETING map in tools.py).
│   │   └── vulnerabilities\           CVE / CISA-KEV digests. Mirrored to datasets/ so the
│   │                                  ENGINE can consume real exposure, not self-reported
│   │                                  `open_critical_vulns` ratings.
│   │
│   ├── regulatory\                    Per regulation, per revision. Chunked PER OBLIGATION,
│   │   │                              with thresholds/penalties kept as structured tables.
│   │   ├── dora\                      EU DORA (2022/2554): ICT risk, third-party, incident
│   │   │                              reporting, resilience testing — maps to scoring factors.
│   │   ├── nis2\                      NIS2 scope + board accountability.
│   │   ├── gdpr\                      72h notification, fines (4%/€20M) → breach severity.
│   │   ├── hipaa\                     OCR penalties, breach notification for US healthcare.
│   │   ├── sec\                       SEC cyber-disclosure rules (8-K/10-K) for listed clients.
│   │   ├── state-privacy\             US state privacy/breach laws.
│   │   ├── ai-act\                    EU AI Act 2026 — pairs with the future ai-risk domain.
│   │   └── solvency-ii\               Capital treatment if you advise insurers/captives.
│   │
│   ├── industry-reports\              The public benchmark & market reports. Chunked per
│   │   │                              chapter; key numbers ALSO lifted into datasets/ so the
│   │   │                              engine calibrates from the same source the RAG cites.
│   │   ├── ibm-codb\                  IBM Cost of a Data Breach (2024–).
│   │   ├── verizon-dbir\              Verizon DBIR (2024–2026).
│   │   ├── netdiligence\              NetDiligence Cyber Claims Study.
│   │   ├── hiscox\                    Hiscox Cyber Readiness.
│   │   ├── coalition\                 Coalition Cyber Claims / threat reports.
│   │   └── marsh-reports\             Your own practice reports (proprietary tier).
│   │
│   └── incidents\                     Historical event knowledge (feeds calibration, so
│       │                              severity stops being a "mock layer")
│       ├── curated\                   Hand-reviewed major incidents: narrative + structured
│       │                              facts (date, sector, vector, cost, downtime, response).
│       │                              Chunked per incident; record-schema queryable.
│       └── imported\                  Raw event-table imports (Advisen/Cyence-style) held as
│                                      source files; the same data is registered in datasets/.
│
├── datasets\                          ← STRUCTURED QUANTITATIVE TABLES (in git, or gitignored
│   │                                     for licensed files with a manifest entry)
│   ├── benchmarks\                    Feeds the engine calibration seam
│   │   ├── frequency\                 Breach/ransomware/BEC/cloud rates by sector (DBIR,
│   │   │                              Hiscox, IC3…). Supersedes the 16-row CSV.
│   │   ├── severity\                  Cost-per-record, breach sizes, ransom payments, by
│   │   │                              sector & data type (IBM, NetDiligence…). Replaces the
│   │   │                              mock severity layer.
│   │   └── sector\                    Sector exposure/claims tables (sector granularity).
│   ├── market\                        Pricing / rate / terms tables (licensed tier) →
│   │                                  pricing model + market-term benchmarking.
│   └── history\                       Per-engagement client loss/incident history
│       │                              (client-confidential tier). Feeds credibility.py,
│       │                              which is built but currently starved of data.
│
├── derived\                           ← GENERATED. NEVER AUTHORED. Gitignored. Rebuildable
│   │                                     from corpus + manifests + content hashes.
│   ├── chunks\                        Chunked, validated text per document (hash-keyed, so
│   │                                  unchanged docs aren't re-chunked).
│   ├── embeddings\                    Vector files per chunk (embedder-keyed — allows mixed
│   │                                  local/cloud embedders per license tier).
│   ├── index\                         The vector index + metadata store.
│   └── state\                         Ingestion state.json: what's indexed, at which content
│                                      hash, when. Makes re-ingestion incremental and idempotent.
│
├── pipelines\                         ← FIXED DESIGN SLOTS. Not implemented yet. The future
│   │                                     `src/cyberrisk/knowledge/` package fills these.
│   ├── ingest\                        manifest → validate → chunk → embed → index → state.
│   │                                  Reads ONLY manifests; this is what makes new documents
│   │                                  code-free.
│   ├── embed\                         Embedder registry (model per tier: cloud for public,
│   │                                  local/self-hosted for licensed & confidential).
│   └── refresh\                       Scheduled refresh: threat intel daily, incidents
│                                      monthly, reports annual, regulatory on revision.
│
└── access\
    ├── policies.yaml                  License tier → role → allowed operations (public /
    │                                  licensed / proprietary / client-confidential). The
    │                                  retrieval service enforces this before any query.
    └── catalog.yaml                   Resolves every doc/dataset id to its tier + scopes.
```

---

## 4. The "add a document without changing the codebase" contract

**To add a document** (the 3-step flow, documented in `knowledge/README.md`):

1. **Drop the file** into `corpus\<domain>\<subcategory>\`.
2. **Add one entry** to `corpus_manifest.yaml` — id, source, license tier,
   version, chunking strategy, refresh cadence, tags, status.
3. **Run `ingest`** — the pipeline validates the entry against
   `document.schema.json`, chunks, embeds, indexes, and records state. Done.

**To add a structured dataset**: same, but in `dataset_manifest.yaml`, with
`format` / `schema` / `targets:` naming the engine seam (e.g.
`targets: [calibration.apply_benchmarks]`). The loader resolves it to the
existing `BenchmarkSet` shape — the swap-in seam `data/loaders.py` documents.

**To add a new domain** (e.g. "ai-risk"): add a line to `domains.yaml` and a
folder under `corpus/`. Still data.

Example document entry:

```yaml
- id: "regulatory/dora/ict-risk"
  domain: regulatory
  category: regulation
  title: "DORA — ICT Risk Management (Regulation (EU) 2022/2554)"
  source: "EUR-Lex / European Commission"
  license_tier: public
  version: "2026.1"
  content_hash: "sha256:…"
  acquired_at: "2026-08-08"
  refresh_cadence: on_revision
  chunking: { strategy: by_clause, max_chars: 1200, overlap: 150 }
  embed_model: default
  tags: [dora, eu, ict-risk, third-party, incident-reporting]
  status: active
```

Example dataset entry:

```yaml
- id: "datasets/benchmarks/severity/ibm-codb-2026-sector"
  domain: benchmarks
  category: severity
  title: "IBM Cost of a Data Breach 2026 — sector table"
  source: "IBM (licensed purchase)"
  license_tier: licensed
  format: parquet
  schema: severity_sector_table
  version: "2026.1"
  acquired_at: "2026-08-08"
  refresh_cadence: annual
  targets: ["calibration.apply_benchmarks"]
```

---

## 5. Content-type → handling matrix

| Content type | Folder | Chunk unit | Retrieval | Refresh | Engine link |
|---|---|---|---|---|---|
| **Standards** | `corpus\standards\` | per control/requirement | semantic + control-id filter | on revision | framework→factor mapping (scoring) |
| **Insurance** | `corpus\insurance\` | per clause (wordings) / per row (terms) | semantic + coverage-type filter | quarterly; pricing at renewal | policy_transform guidance, future pricing model |
| **Threat intel** | `corpus\threat-intel\` + `datasets\` | per campaign/actor | semantic + TTP/target filter, **freshness boost** | daily / hourly | frequency + real attack-surface input |
| **Regulatory** | `corpus\regulatory\` | per obligation/clause | semantic + regulation filter; cite obligation id | on amendment | scoring factors + breach severity |
| **Industry reports** | `corpus\industry-reports\` | per chapter/table | semantic + year/sector filter | annual on publication | calibration citations (same source as datasets) |
| **Incidents** | `corpus\incidents\` + `datasets\` | per incident (record + narrative) | record lookup + semantic | monthly / on feed | severity calibration, credibility |
| **Benchmark datasets** | `datasets\benchmarks\` | **not chunked** — structured tables | numeric filter + summarising RAG | annual / on update | `BenchmarkSet` / `apply_benchmarks` |

---

## 6. The RAG flow (designed, implemented later in `src/cyberrisk/knowledge/`)

1. **Query routing** — classify the question as engine-tool (needs a number
   the loss engine computes), knowledge (needs a cited fact), or both.
2. **Scope & access guard** — resolve the user's role against
   `access/policies.yaml`, filter the corpus to permitted license tiers,
   hard-block any cross-client/confidential query.
3. **Hybrid retrieval** — semantic (vector index) ∪ keyword (BM25-style) ∪
   metadata filters (domain, sector, year, `status: active`), unioned then
   ranked.
4. **Rerank** — score by relevance × recency × source-quality tier; drop stale
   or deprecated docs.
5. **Citation bundle** — every retrieved unit carries a `citation.schema.json`
   record (doc id, source, version, chunk ref, page/paragraph, retrieved_at,
   license tier).
6. **Grounded generation** — the consultant composes the answer using only
   *engine numbers* (from the existing tools) + *cited knowledge* (from the
   citation bundle). Extend `safety.check_llm_output` to verify every cited id
   resolves and every figure matches a validated metric.
7. **Audit** — every answer's citation bundle is logged, making "every number
   traces to a source" verifiable post-hoc.

---

## 7. Open decisions (with recommendation)

- **D1 — Vector store:** abstract the index behind one interface; start with
  **FAISS or SQLite+sqlite-vec** (zero-ops, matches the current no-DB stack)
  and target **managed Postgres + pgvector** for production (metadata and
  vectors in one transactional store).
- **D2 — Embedding policy:** cloud embedder for public-tier content,
  **local/self-hosted** (Ollama already installed; sentence-transformers also
  works) for licensed and client-confidential content — so licensed data never
  leaves your environment.
- **D3 — Location:** `knowledge\` as a top-level sibling of `config\` /
  `data\` / `src\`, because it's neither engine input data nor engine config —
  it's a first-class content domain. (Alternative: `data\knowledge\`.)
- **D4 — License-tier granularity:** four tiers (public / licensed /
  proprietary / client-confidential). Extends cleanly to per-tenant scopes.

---

## 8. Current state of the scaffold

- `knowledge/` tree scaffolded (empty dirs, `.gitkeep` for non-derived dirs).
- `knowledge/README.md` — the add-a-document contract.
- `knowledge/manifests/` — `corpus_manifest.yaml`, `dataset_manifest.yaml`,
  `domains.yaml`, `manifest.example.yaml` (entries are worked **examples**,
  not live content).
- `knowledge/schemas/` — `document`, `dataset`, `chunk`, `citation` JSON
  Schema stubs.
- `knowledge/access/` — `policies.yaml` (tier → role → ops) and `catalog.yaml`
  (empty until content is registered).
- `knowledge/pipelines/` — empty design slots (`ingest/`, `embed/`, `refresh/`).
- `knowledge/derived/` — empty, gitignored.
- `.gitignore` — `knowledge/derived/` + licensed/confidential source folders
  ignored (with `!knowledge/**/.gitkeep` guard).

**Not implemented:** ingest/embed/refresh pipeline code, retrieval service,
RAG wiring into the consultant agent, framework→factor mapping, pricing model,
and any actual content. Those are the next stages, in the priority order of
the gap analysis (real severity data and pricing first).
