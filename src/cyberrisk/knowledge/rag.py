"""Retrieval-Augmented Generation — retrieval side.

``Retriever`` turns a user query into the top-k most relevant knowledge chunks
from the vector store, ranked by semantic similarity, and formats them as a
citation-carrying context block the consultant agent embeds in its system
prompt.

    query -> embed -> VectorStore.similarity -> rank by score
          -> RetrievedChunk(doc_id, chunk_id, content, metadata, score)
          -> format_context(): "[DOCUMENT 1] title | source | ... \n <content> \n [citation: chunk_id]"

The retrieval side is deliberately lightweight and engine-agnostic: it only
reads the vector store.  The LLM decides how to combine retrieved knowledge
with engine tool results (the agent's job, guided by the system prompt's RAG
rules).  The hallucination guard (src/agent/safety.py) verifies that claims
trace to either a tool metric or a retrieved chunk.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from cyberrisk.knowledge.config import load_ingest_config
from cyberrisk.knowledge.embedders import HashEmbedder
from cyberrisk.knowledge.vector_store import VectorStore


@dataclass(frozen=True)
class RetrievedChunk:
    """One retrieved knowledge chunk, with its citation + score."""

    doc_id: str
    chunk_id: str
    content: str
    metadata: dict
    score: float

    @property
    def title(self) -> str:
        return self.metadata.get("title", "")

    @property
    def source(self) -> str:
        return self.metadata.get("source", "")

    @property
    def publication_date(self) -> str:
        return self.metadata.get("publication_date", "")

    @property
    def category(self) -> str:
        return self.metadata.get("category", "")

    @property
    def industry(self) -> str:
        return self.metadata.get("industry", "")

    @property
    def section_ref(self) -> str:
        return self.metadata.get("section_ref", "")

    @property
    def citation(self) -> str:
        return f"[citation: {self.chunk_id}]"


class Retriever:
    """Ranked retrieval over the knowledge vector store.

    Parameters
        store       the VectorStore to search
        embedder    embedder for the query (defaults to HashEmbedder)
        top_k       default number of results to return
        min_score   minimum similarity score to include a chunk (filters
                    near-zero matches so irrelevant knowledge is not cited)
    """

    def __init__(
        self,
        store: VectorStore,
        embedder: HashEmbedder | None = None,
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> None:
        self.store = store
        self.embedder = embedder or HashEmbedder()
        self.top_k = top_k
        self.min_score = min_score

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Return the top-k chunks most similar to ``query``.

        The query is embedded with the same embedder used at index time, so
        the similarity is meaningful.  Results are already ranked (the store
        sorts by cosine similarity descending) and filtered by ``min_score``.
        """
        query_vec = self.embedder.embed(query)
        k = top_k or self.top_k
        hits = self.store.similarity(query_vec, k=max(1, k))
        out = []
        for hit in hits:
            if hit.get("score", 0.0) < self.min_score:
                continue
            out.append(
                RetrievedChunk(
                    doc_id=hit.get("doc_id", ""),
                    chunk_id=hit.get("chunk_id", ""),
                    content=hit.get("content", ""),
                    metadata=hit,
                    score=hit.get("score", 0.0),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Context formatting
    # ------------------------------------------------------------------

    def format_context(self, results: list[RetrievedChunk]) -> str:
        """Render retrieved chunks as a citation-carrying context block.

        Each chunk becomes:

            [DOCUMENT 1] <title> | <source> | <publication_date> | <category> | <industry>
            Confidence: <0-1>  Section: <section_ref>
            <content>
            [citation: <chunk_id>]

        The agent embeds this block in its system prompt and cites chunks by
        [citation: <chunk_id>].  The hallucination guard verifies citations
        resolve to a retrieved chunk.  Confidence and section are surfaced so
        the agent can copy them into its Source / Published / Confidence /
        Section attribution blocks (per the evidence & attribution rules).
        """
        if not results:
            return ""
        parts: list[str] = []
        for i, chunk in enumerate(results, start=1):
            header = " | ".join(
                part
                for part in (
                    chunk.title,
                    chunk.source,
                    chunk.publication_date,
                    chunk.category,
                    chunk.industry,
                )
                if part
            )
            attrs = []
            if chunk.metadata.get("confidence") is not None:
                attrs.append(f"Confidence: {chunk.metadata['confidence']}")
            if chunk.section_ref:
                attrs.append(f"Section: {chunk.section_ref}")
            attr_line = "  " + "  ".join(attrs) if attrs else ""
            parts.append(
                f"[DOCUMENT {i}] {header}\n{attr_line}\n{chunk.content}\n{chunk.citation}"
            )
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @classmethod
    def from_derived(
        cls,
        derived_root: str | Path | None = None,
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> "Retriever":
        """Build a Retriever from the default derived vector store.

        Raises
            FileNotFoundError  when the vector DB does not exist — the caller
            (e.g. the agent) should skip RAG silently if the store is absent.
        """
        cfg = load_ingest_config()
        root = Path(derived_root) if derived_root is not None else cfg.derived_path
        db = root / "vector.db"
        if not db.exists():
            raise FileNotFoundError(
                f"vector store not found at {db}; run the ingest + embed pipelines first"
            )
        return cls(store=VectorStore(db), top_k=top_k, min_score=min_score)


def main(argv: list[str] | None = None) -> int:
    """Interactive retrieval CLI: python -m cyberrisk.knowledge.rag "<query>"."""
    parser = argparse.ArgumentParser(
        prog="cyberrisk.knowledge.rag",
        description="Query the knowledge vector store (retrieval only, no LLM)",
    )
    parser.add_argument("query", nargs="*", help="Search query (or run interactively)")
    parser.add_argument("-k", type=int, default=5, help="Top-k results (default 5)")
    parser.add_argument("--min-score", type=float, default=0.1, help="Min similarity score")
    args = parser.parse_args(argv)

    try:
        retriever = Retriever.from_derived(top_k=args.k, min_score=args.min_score)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    query = " ".join(args.query)
    if query:
        _print_results(retriever, query)
        return 0

    print("Knowledge retrieval. Type a query, or blank to quit.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            break
        _print_results(retriever, q)
    return 0


def _print_results(retriever: Retriever, query: str) -> None:
    results = retriever.retrieve(query)
    print(f"\nQuery: {query}")
    if not results:
        print("  (no chunks above the min score)")
        return
    for i, chunk in enumerate(results, start=1):
        print(f"\n[{i}] score={chunk.score:.3f} | {chunk.title} | {chunk.source}")
        print(f"    {chunk.chunk_id}")
        print(f"    {chunk.content[:200]}{'...' if len(chunk.content) > 200 else ''}")


if __name__ == "__main__":
    raise SystemExit(main())
