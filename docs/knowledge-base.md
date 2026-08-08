# Knowledge Base

The knowledge base is the layer that **grounds the AI consultant's reasoning
in citable sources**. It is a curated, extensible corpus of regulatory texts,
standards, industry reports, threat intelligence, and historical incidents —
plus the structured benchmark datasets the engine calibrates from.

The guiding rule:

> **Content is data, never code.** Adding a document, regulation, report, or
> dataset is a **file drop + one manifest entry**. The product code is written
> once and driven entirely by the manifests — no code change is ever required
> to add knowledge.

---

## 1. Layout

```
knowledge/
├── corpus/                  # source documents you curate (the "what the AI knows")
│   ├── incidents/           #   breach/incident case data (curated + imported)
│   ├── industry-reports/    #   DBIR, IBM CODB, ENISA, Hiscox, NetDiligence...
│   ├── insurance/           #   wordings, claims guides, market terms
│   ├── regulatory/          #   GDPR, HIPAA, NIS2, DORA, AI Act, SEC...
│   ├── standards/           #   NIST CSF 2.0, NIST 800-53, ISO 27001, CIS...
│   ├── threat-intel/        #   threat landscape reports, actors, campaigns
│   └── vulnerability-data/  #   CISA KEV, CVE data
├── datasets/                # structured calibration data (CSV/JSON)
│   ├── benchmarks/          #   DBIR frequency, IBM CODB severity tables
│   ├── history/             #   historical incident series
│   └── market/              #   market-level pricing data
├── manifests/               # the single source of truth (YAML, in git)
├── mappings/                # taxonomy + source mappings
├── pipelines/               # ingest/embed/refresh pipeline config
├── schemas/                 # JSON schemas for documents and the manifest
└── derived/                 # generated chunks, embeddings, vector.db (gitignored)
```

---

## 2. Supported data sources

### 2.1 Document corpus (`knowledge/corpus/`)

The corpus is the natural-language knowledge the consultant retrieves from.
It is organised by domain (incidents, industry reports, insurance, regulatory,
standards, threat intel, vulnerability data).

**Supported file formats:**

| Format | Notes |
|---|---|
| `.md` / `.markdown` | Section-aware chunking on `#` headings |
| `.html` / `.htm` | Tags stripped; headings become sections |
| `.txt` | First non-empty line becomes the implicit title |
| `.pdf` | Via `pypdf` (optional `knowledge` extra) |
| `.docx` | Via `python-docx` (optional `knowledge` extra) |
| `.yaml` | Structured metadata / incident records |

### 2.2 Structured datasets (`knowledge/datasets/`)

Structured calibration data in **CSV or JSON**, with each record carrying a
`source`, `sector`, `metric`, `value`, `units`, and `notes` — so every
calibration number is traceable to a source. Loaded via
`cyberrisk.data.dataset_loaders`.

**Public, industry-standard sources referenced:**

- **Verizon DBIR** — sector breach frequency
- **IBM Cost of a Data Breach** — loss severity
- **ENISA Threat Landscape** — threat landscape reports
- **NIST** — frameworks and standards
- **CISA KEV** — known exploited vulnerabilities
- **Hiscox / NetDiligence** — cyber insurance market data

> **Licensing.** The repo ships **source code + curated example data only**.
> Public benchmark datasets are referenced **by calibration table, not
> bundled**. If you add proprietary licensed corpora (e.g. paid DBIR/CODB
> content), keep them out of version control and store the files locally under
> `knowledge/corpus/`, behind your own access controls.

---

## 3. The RAG process

Retrieval-augmented generation (RAG) is how the consultant **grounds its
answers in the corpus**. The pipeline is in `src/cyberrisk/knowledge/`.

### 3.1 Ingestion pipeline (offline)

```
corpus/ documents
   → extract   (per-format reader: md / html / txt / pdf / docx / yaml)
   → clean     (normalise, strip noise)
   → chunk     (section-aware or plain, per config)
   → embed     (HashEmbedder by default; pluggable via EmbedderRegistry)
   → store     (SQLite vector store, content-hash deduplicated)
   → index     (structured incident index, keyword-searchable)
```

Key properties:

- **Manifest-driven.** `knowledge/manifests/corpus_manifest.yaml` is the
  single source of truth for which documents are registered.
- **Content-hash dedup.** Re-running the pipeline is safe — unchanged files
  are skipped, changed files are re-ingested, the vector store updates
  incrementally.
- **Gitignored derived artifacts.** Chunks, embeddings, and `vector.db` live
  in `knowledge/derived/` (regenerated on demand, never committed).

### 3.2 Retrieval (at query time)

When the user asks a question, the agent controller retrieves context from
**two sources** (`_rag_context` in `agent_controller.py`):

1. **Semantic retrieval** — `Retriever.retrieve(query, top_k)` runs vector
   search over the embedded chunks (`Retriever.from_derived(...)` loads the
   store; `format_context(...)` renders the results for the prompt).
2. **Structured incident retrieval** — the incident index, matched by
   industry / attack-type keywords in the query.

Retrieved context is injected into the **per-turn system prompt** with strict
citation rules (`RAG_RULES`): the consultant must reference sources by
`[citation: chunk_id]`.

### 3.3 Safety properties

- Retrieval is **additive and never required** — the agent works even with an
  empty knowledge base.
- Retrieval failures are **swallowed** (never crash a consult); the agent just
  proceeds without context.
- The input-privacy guard redacts personal data before it reaches the model,
  and derived artifacts are gitignored by default.

---

## 4. How to add new knowledge

Adding knowledge is a **file drop + one command**. No code changes.

### 4.1 Add a document

```bash
# 1. Drop your document into the relevant corpus folder, e.g.
cp my_note.pdf knowledge/corpus/standards/nist-csf-2.0/

# 2. Run the automatic update pipeline — it detects, parses, chunks,
#    embeds, and updates the vector DB in one pass
python -m cyberrisk.knowledge.update
```

The pipeline automatically:

1. **Scans** `knowledge/corpus/**` for supported files not already in the
   manifest.
2. **Registers** each new file with metadata inferred from its path (domain,
   title, license, content hash).
3. **Extracts** text, **cleans** it, and **chunks** it.
4. **Embeds** the chunks (content-hash dedup avoids re-embedding).
5. **Updates** the SQLite vector store (`knowledge/derived/vector.db`).
6. **Logs** every action and writes a report.

**Useful flags:**

```bash
python -m cyberrisk.knowledge.update --force    # re-index everything (ignore cache)
python -m cyberrisk.knowledge.update --report   # print the last update report
```

### 4.2 Add a structured dataset

1. Place the file under `knowledge/datasets/` (e.g. `benchmarks/frequency/`).
2. Register it in `knowledge/manifests/dataset_manifest.yaml` with its schema
   mapping (which columns are source/sector/metric/value).
3. Run `python -m cyberrisk.knowledge.update` to load and validate it.

The engine consumes calibrated datasets through
`cyberrisk.data.dataset_loaders`, which coerces and validates every record so
a malformed row is surfaced rather than silently corrupting calibration.

### 4.3 The quality-gated path

For authoritative content (e.g. a curated regulatory text), the **populate**
command only ingests documents whose source is registered as **approved** in
the source registry (`knowledge/manifests/authoritative_sources.yaml`):

```bash
python -m cyberrisk.knowledge.populate
```

Unapproved sources are **skipped and logged**. The permissive `update` path is
for your own documents; the gated `populate` path is for authoritative corpus.

### 4.4 Validate your additions

The knowledge layer has a dedicated test suite and schema validation:

```bash
python -m pytest tests/test_knowledge_*.py -q        # ingestion/RAG/incidents
python -m pytest tests/validate/ -q                  # model-validation suite
```

Manifest entries are validated against the JSON schemas in
`knowledge/schemas/` (document, chunk, citation, dataset) before ingestion.

---

## 5. Governance rules

- **Never commit** licensed or client-confidential content to the repo —
  keep it in gitignored local paths behind your own access controls.
- **Never commit** derived artifacts (`knowledge/derived/`) — they are
  regenerable and may embed source text.
- Keep **manifests and `.gitkeep` files** committed; the underlying data must
  be re-sourced independently.
- The example benchmark CSVs under `knowledge/datasets/benchmarks/` are
  **intentional example data** (derived/curated) and are committed on purpose.

---

*Next: [architecture.md](architecture.md) for how the knowledge layer connects
to the agent, or [api.md](api.md) for the HTTP surface.*
