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

- Folders scaffolded. No corpus content, no datasets, no pipeline code yet.
- `manifests/corpus_manifest.yaml` and `dataset_manifest.yaml` exist with the
  header + worked example from the design (entries are **examples**, marked as
  such — nothing is registered as live).
- `manifests/domains.yaml` lists the registered domains; new domains are added
  there.
- `schemas/` holds the four schema stubs (document, dataset, chunk, citation).
- `access/` holds the tier policy and the catalog (empty by design until
  content is registered).
