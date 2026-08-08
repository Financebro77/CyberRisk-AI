# Knowledge Base Validation Report

Date: 2026-08-08
Areas: 9

## Summary

| # | Area | Status | Metric | Threshold |
|---|---|---|---|---|
| 1 | document_ingestion | PASS | 3 docs, 0 errors | 100% no errors |
| 2 | chunk_quality | PASS | 9/9 valid (100%) | >= 95% chunks valid |
| 3 | embedding_quality | FAIL | 0/0 valid (0%) | 100% valid |
| 4 | semantic_retrieval | FAIL | precision@1 = 0.00 (0/3) | precision@1 >= 0.8 |
| 5 | source_attribution | FAIL | no results | 100% present |
| 6 | citation_accuracy | FAIL | resolve rate = 0.00 (0/0) | resolve rate = 1.0 |
| 7 | duplicate_detection | PASS | 0/3 registered docs mistakenly flagged as new | 100% |
| 8 | retrieval_latency | PASS | p95 = 0.3ms across 6 queries | p95 < 200ms |
| 9 | hallucination_resistance | FAIL | no retrieved chunk | 0 fabricated figures pass |

## Details

### document_ingestion — PASS
- Metric: 3 docs, 0 errors
- Threshold: 100% no errors
  - all documents ingested without error

### chunk_quality — PASS
- Metric: 9/9 valid (100%)
- Threshold: >= 95% chunks valid
  - all chunks have section_ref + char_span + license_tier

### embedding_quality — FAIL
- Metric: 0/0 valid (0%)
- Threshold: 100% valid
  - all embeddings non-zero, normalized, deterministic

### semantic_retrieval — FAIL
- Metric: precision@1 = 0.00 (0/3)
- Threshold: precision@1 >= 0.8
  - query 'DORA ICT risk management frame...' -> none (expected corpus/regulatory/dora/ict-risk)
  - query 'ransomware leading cause of br...' -> none (expected corpus/industry-reports/verizon-dbir/dbir-2026-highlights)
  - query 'Change Healthcare ransomware c...' -> none (expected corpus/incidents/curated/change-healthcare-2024)

### source_attribution — FAIL
- Metric: no results
- Threshold: 100% present
  - no retrieved chunks

### citation_accuracy — FAIL
- Metric: resolve rate = 0.00 (0/0)
- Threshold: resolve rate = 1.0
  - all citations resolve

### duplicate_detection — PASS
- Metric: 0/3 registered docs mistakenly flagged as new
- Threshold: 100%
  - no registered doc is re-registered

### retrieval_latency — PASS
- Metric: p95 = 0.3ms across 6 queries
- Threshold: p95 < 200ms
  - p50=0.2ms, p95=0.3ms

### hallucination_resistance — FAIL
- Metric: no retrieved chunk
- Threshold: 0 fabricated figures pass
  - no retrieved chunk to test against

## Recommendations

- **embedding_quality FAILED** (0/0 valid (0%)). Review the details above and the relevant pipeline/tests.
- **semantic_retrieval FAILED** (precision@1 = 0.00 (0/3)). Review the details above and the relevant pipeline/tests.
- **source_attribution FAILED** (no results). Review the details above and the relevant pipeline/tests.
- **citation_accuracy FAILED** (resolve rate = 0.00 (0/0)). Review the details above and the relevant pipeline/tests.
- **hallucination_resistance FAILED** (no retrieved chunk). Review the details above and the relevant pipeline/tests.
