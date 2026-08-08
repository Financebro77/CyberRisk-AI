"""CyberRisk retrieval-augmented generation layer (re-export shim).

The canonical RAG implementation lives in ``cyberrisk.knowledge``
(``src/cyberrisk/knowledge/rag.py``).  This package provides a convenience
namespace so the retrieval layer can be addressed as ``rag.*`` matching the
repository's logical structure, without moving or duplicating code.

    from rag import Retriever, RetrievedChunk       # == cyberrisk.knowledge.rag
    from rag import IngestDocument, HashEmbedder    # == cyberrisk.knowledge.*
"""

from __future__ import annotations

from cyberrisk.knowledge.embedders import EmbedderRegistry, HashEmbedder
from cyberrisk.knowledge.incidents import (
    Incident,
    IncidentIndex,
    load_incident,
    load_incident_index,
)
from cyberrisk.knowledge.rag import RetrievedChunk, Retriever
from cyberrisk.knowledge.vector_store import VectorStore

__all__ = [
    "EmbedderRegistry",
    "HashEmbedder",
    "Incident",
    "IncidentIndex",
    "RetrievedChunk",
    "Retriever",
    "VectorStore",
    "load_incident",
    "load_incident_index",
]
