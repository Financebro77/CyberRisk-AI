# CyberRisk AI — Knowledge Layer

**Design only — nothing here is implemented or wired to the runtime yet.**

This is the content home for everything the consultant agent knows that is not
computed by the loss engine: security standards, insurance guidance, threat
intelligence, regulatory requirements, industry reports, historical incidents,
and the structured benchmark datasets the engine calibrates from.

The layer is built on one rule:

> **Content is data, never code.**
> Adding a document, regulation, report, or dataset is a **file drop + one
> manifest entry**. The product code is written once and is driven entirely by
> the manifests — no code change is ever required to add knowledge.

---

## 1. Layout at a glance

| Path | Purpose |
|---|---|
| `manifests/` | The single source of truth (YAML, in git): every document and dataset, one entry each |
| `schemas/` | JSON Schemas that validate every manifest entry and every chunk/citation record |
| `corpus/` | Authored knowledge — standards, insurance, threat intel, regulatory, reports, incidents |
| `datasets/` | Structured quantitative tables that feed the engine calibration seam |
| `derived/` | **Generated, never authored, gitignored** — chunks, embeddings, index, ingestion state |
| `pipelines/` | Fixed design slots for the future ingest / embed / refresh pipeline package |
| `access/` | License-tier → role policy and the doc/dataset → tier catalog |

Full architecture and rationale: `../reports/knowledge_architecture.md`.

---

## 2. The "add a document" contract

### Add a document

1. **Drop the file** into `corpus\<domain>\<subcategory>\`.
2. **Add one entry** to `manifests/corpus_manifest.yaml` (id, source, license
   tier, version, chunking strategy, refresh cadence, tags, status).
3. **Run `ingest`** — the pipeline validates the entry against
   `schemas/document.schema.json`, chunks, embeds, indexes, and records state
   in `derived/state/`. Done.

### Add a structured dataset

Same flow, but into `manifests/dataset_manifest.yaml`, with `format` /
`schema` / `targets:` naming the engine seam it feeds (e.g.
`targets: [calibration.apply_benchmarks]`). The loader resolves it to the
existing `BenchmarkSet` shape in `src/cyberrisk/data/loaders.py` — the
swap-in seam that file already documents.

### Add a new domain (e.g. "ai-risk")

Add a line to `manifests/domains.yaml` and a folder under `corpus/`. Still data.

---

## 3. Hard rules

1. **Never edit `derived/`.** It is regenerated from `corpus/` + manifests +
   content hashes. If something looks wrong there, delete it and re-ingest.
2. **Never commit licensed, proprietary, or client-confidential content.**
   Those files live under `corpus/` or `datasets/` but are **gitignored** with
   an entry in the manifest; only the manifest entry is committed.
3. **No content without a manifest entry.** An unregistered file is invisible
   to the pipeline and must not be relied on.
4. **Every retrievable unit carries a citation.** The schema is in
   `schemas/citation.schema.json`. "Every number traces to a source" is the
   audit contract.
5. **Retrieval never crosses a license tier.** `access/policies.yaml` is
   enforced by the retrieval service before any query runs.

---

## 4. Manifest schema rules (summarised)

- **id** is unique, namespaced by location: `corpus/<domain>/<category>/<doc>`
  or `datasets/<group>/<category>/<table>`.
- **license_tier** is one of: `public | licensed | proprietary |
  client-confidential`. It drives embedding choice, gitignore handling, and
  retrieval scope.
- **content_hash** (sha256) is how `derived/state/` knows a doc is unchanged
  and can be skipped.
- **refresh_cadence** is one of: `daily | weekly | monthly | quarterly |
  annual | on_revision`.
- **status** is `active` or `deprecated`; deprecated content is excluded from
  retrieval.

Full validation lives in `schemas/*.schema.json`; the ingest pipeline rejects
anything that fails it — the same "loud error at the boundary" pattern the
engine uses in `src/cyberrisk/calibration.py`.

---

## 5. Current state

- `manifests/corpus_manifest.yaml` and `dataset_manifest.yaml` are the live
  registries (example docs/datasets registered active).
- `manifests/domains.yaml` lists the registered content-type domains; new
  domains are added there.
- `manifests/industry_taxonomy.yaml` lists the registered industries (Healthcare,
  Finance, Retail, Manufacturing, Energy, Government, Technology), each with the
  six uniform subcategories (Threat Landscape, Regulatory Requirements, Common
  Attack Vectors, Typical Insurance Claims, Recommended Security Controls, Loss
  Characteristics).  Industries are orthogonal to content-type domains: a
  document keeps its `domain` AND gains an `industry` + `taxonomy` subcategory
  list.  Adding an industry or subcategory is a YAML edit, never a code change.
- `schemas/` holds the document/dataset/chunk/citation JSON Schemas.
- `access/` holds the tier policy and the catalog.
- `pipelines/` (ingest/embed/refresh) are implemented as
  `src/cyberrisk/knowledge/` (ingest, embed, vector store, retrieval).

## 5.5 Historical cyber incidents

Incidents live as structured YAML under `corpus/incidents/curated/<incident>.yaml`
with ten fields: `company`, `industry` (taxonomy key), `attack_type`,
`attack_vector`, `root_cause`, `financial_loss` (USD), `operational_impact`,
`regulatory_consequences`, `insurance_implications`, `lessons_learned`, plus
`id` and `incident_date`.  To add an incident, drop a YAML file — the
`IncidentIndex` discovers it and the standard ingest pipeline embeds its
narrative for RAG.  The consultant can query incidents by field via the
`search_incidents` tool; relevant incidents also surface in RAG context.

## 6. Commands

```powershell
# 1. Ingest documents (PDF/MD/DOCX/HTML/TXT) -> derived/chunks + index
python -m cyberrisk.knowledge.pipeline

# 2. Embed chunks -> derived/vector.db (SQLite vector store)
python -m cyberrisk.knowledge.embed_pipeline --force

# 3. Query the vector store (retrieval only, no LLM)
python -m cyberrisk.knowledge.rag "DORA ICT risk management obligations"

# 4. AUTOMATIC UPDATE — drop new reports into knowledge/corpus/** and run:
python -m cyberrisk.knowledge.update
#   -> detects new files, auto-registers them, parses, chunks, embeds,
#      updates the vector DB, avoids duplicates, logs, and writes a report
#      (derived/update/report.json + derived/update/updates.log).
python -m cyberrisk.knowledge.update --report   # print the last report

# 5. VALIDATION — run all nine quality areas + report:
python -m cyberrisk.knowledge.validate
#   -> ingestion, chunk quality, embedding quality, semantic retrieval,
#      source attribution, citation accuracy, duplicate detection, latency,
#      hallucination resistance
#   -> PASS/FAIL per area with metrics
#   -> reports/knowledge_validation.md + derived/validation/report.json

# 6. POPULATE — quality-gated ingestion of approved authoritative sources:
python -m cyberrisk.knowledge.populate
#   -> only documents whose source is registered (and approved) in
#      knowledge/manifests/authoritative_sources.yaml are ingested
#   -> unapproved sources are skipped + logged
#   -> runs the 8-step workflow (register -> extract -> clean -> chunk ->
#      index -> embed -> vector DB)
#   -> reports/knowledge_population_report.md
```

## Authoritative sources + governance

`manifests/authoritative_sources.yaml` is the APPROVAL GATE: a document is
only ingested if its source is registered there as approved (with reliability,
licensing, and per-stage suitability). `knowledge/mappings/control_evidence.yaml`
documents which evidence sources support each control's model effect
(frequency vs severity) — documentation only, NO parameter changes. Document
quality metadata (publication date, confidence, usage, calibration_allowed)
lives alongside each source's documents. The AI consultant must always
distinguish external evidence / model output / professional judgement, and
never fabricate statistics or regulations.

The `update` command is the "no manual code changes" path: any supported file
(PDF/MD/DOCX/HTML/TXT/YAML) dropped anywhere under `knowledge/corpus/` is
auto-registered with defaults inferred from its path (domain, title, chunking,
content hash), then ingested + embedded. Auto-registered entries can be
enriched later in `corpus_manifest.yaml`. Both the update and the individual
pipelines are incremental: re-running skips unchanged documents/chunks.
The consultant agent retrieves context automatically when `derived/vector.db`
exists, and the hallucination guard (`src/agent/safety.py`) verifies citations
and document figures before an answer reaches a client.
