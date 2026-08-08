"""Document ingestion + embedding pipelines for the knowledge layer.

Turns authored documents (PDF, Markdown, DOCX, HTML, TXT) under
``knowledge/corpus/`` into a structured knowledge index
(``knowledge/derived/``), then embeds every chunk into a SQLite vector store
(``derived/vector.db``) with preserved metadata.  Both pipelines are
incremental (only new or modified files are processed).

Public entry points:
    load_ingest_config       -> IngestConfig (from YAML or defaults)
    IngestConfig             chunk sizing, overlap, formats, output root
    IngestDocument           one manifest-registered document
    IngestPipeline / IngestReport     ingest orchestrator
    EmbedPipeline / EmbedReport       embedding orchestrator
    HashEmbedder             deterministic dependency-free embedder
    VectorStore              SQLite vector store

The corpus manifest (``knowledge/manifests/corpus_manifest.yaml``) is the
single source of truth: adding a document is a file drop + one manifest entry.
"""

from cyberrisk.knowledge.config import (
    CHUNK_STRATEGIES,
    SECTION_STRATEGIES,
    PLAIN_STRATEGIES,
    SUPPORTED_FORMATS,
    IngestConfig,
    format_for_path,
    load_ingest_config,
)
from cyberrisk.knowledge.document import IngestDocument
from cyberrisk.knowledge.embedders import HashEmbedder, EmbedderRegistry
from cyberrisk.knowledge.embed_pipeline import EmbedPipeline, EmbedReport
from cyberrisk.knowledge.pipeline import IngestPipeline, IngestReport
from cyberrisk.knowledge.incidents import (
    Incident,
    IncidentIndex,
    default_incidents_dir,
    load_incident,
    load_incident_index,
    load_incidents_dir,
)
from cyberrisk.knowledge.rag import RetrievedChunk, Retriever
from cyberrisk.knowledge.taxonomy import (
    UNIFORM_SUBCATEGORIES,
    Industry,
    IndustryTaxonomy,
    TaxonomySubcategory,
    load_industry_taxonomy,
)
from cyberrisk.knowledge.mappings import (
    ControlEvidence,
    ControlMapping,
    load_control_mapping,
)
from cyberrisk.knowledge.populate import (
    PopulateReport,
    populate_corpus,
    write_population_report,
)
from cyberrisk.knowledge.sources import (
    SOURCE_CATEGORIES,
    Source,
    SourceRegistry,
    load_source_registry,
)
from cyberrisk.knowledge.update import (
    UpdateReport,
    auto_register_file,
    find_unregistered_files,
    run_update,
)
from cyberrisk.knowledge.validate import ValidationResult, validate_knowledge_base
from cyberrisk.knowledge.vector_store import VectorStore

__version__ = "0.1.0"

__all__ = [
    "CHUNK_STRATEGIES",
    "SECTION_STRATEGIES",
    "PLAIN_STRATEGIES",
    "SUPPORTED_FORMATS",
    "IngestConfig",
    "format_for_path",
    "load_ingest_config",
    "IngestDocument",
    "IngestPipeline",
    "IngestReport",
    "HashEmbedder",
    "EmbedderRegistry",
    "EmbedPipeline",
    "EmbedReport",
    "VectorStore",
    "Retriever",
    "RetrievedChunk",
    "Incident",
    "IncidentIndex",
    "default_incidents_dir",
    "load_incident",
    "load_incident_index",
    "load_incidents_dir",
    "UpdateReport",
    "auto_register_file",
    "find_unregistered_files",
    "run_update",
    "ValidationResult",
    "validate_knowledge_base",
    "SOURCE_CATEGORIES",
    "Source",
    "SourceRegistry",
    "load_source_registry",
    "ControlEvidence",
    "ControlMapping",
    "load_control_mapping",
    "PopulateReport",
    "populate_corpus",
    "write_population_report",
    "UNIFORM_SUBCATEGORIES",
    "Industry",
    "IndustryTaxonomy",
    "TaxonomySubcategory",
    "load_industry_taxonomy",
]
