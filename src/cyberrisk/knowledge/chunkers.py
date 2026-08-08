"""Semantic chunking — turn an extracted document into retrievable chunks.

Two strategies (mapped from the manifest's ``chunking.strategy`` via the
config's strategy_registry):

    section   (by_chapter + domain aliases)  — one chunk per section/heading.
              This is the "semantic" chunker: a DORA obligation, a NIST
              control, a campaign report is kept whole so a retrieved chunk
              is a complete, meaningful unit.
    plain     (no heading structure)         — paragraph-merge up to max_chars,
              then fixed-size with overlap for overflow.  Used for TXT/PDF/
              DOCX that carry no section headings.

Every chunk:
    * respects the manifest's max_chars / overlap,
    * carries ``section_ref`` (the heading path, prefixed with the doc title),
    * records ``char_span`` (start/end in the cleaned source) so a citation
      can point at the exact location,
    * is validated against knowledge/schemas/chunk.schema.json by the writer.

Chunks below the config's ``min_chunk_chars`` are dropped (whitespace-only or
one-line noise) unless they are the entire document.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyberrisk.knowledge.cleaners import split_paragraphs
from cyberrisk.knowledge.config import IngestConfig
from cyberrisk.knowledge.extractors import ExtractedDocument


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of a document."""

    doc_id: str
    ordinal: int  # 1-based position within the document
    content: str
    section_ref: str  # heading path, prefixed with doc title
    char_start: int
    char_end: int
    license_tier: str

    @property
    def char_span(self) -> dict[str, int]:
        return {"start": self.char_start, "end": self.char_end}


def _heading_path(prefix: str, heading: str) -> str:
    """Build a section_ref: title > heading (or just title for the root)."""
    if not heading:
        return prefix or ""
    return f"{prefix} > {heading}" if prefix else heading


def _trim_to_max(content: str, max_chars: int) -> str:
    """Trim content to fit max_chars at a word boundary."""
    if len(content) <= max_chars:
        return content
    cut = content[:max_chars]
    # cut back to the last space boundary
    space = cut.rfind(" ")
    if space > max_chars * 3 // 4:
        cut = cut[:space]
    return cut.rstrip()


def chunk_sections(
    doc: ExtractedDocument,
    title: str,
    doc_id: str,
    license_tier: str,
    config: IngestConfig,
    max_chars: int,
    overlap: int,
) -> list[Chunk]:
    """Section-based chunking: one chunk per section.

    Sections longer than max_chars are sub-split at paragraph boundaries then
    by fixed size with overlap, keeping the section_ref on every sub-chunk.

    Falls back to ``chunk_plain`` when the document has no sections (e.g. a
    single-block YAML incident or a headingless extract) so a section-strategy
    document never yields zero chunks.
    """
    if not doc.sections:
        return chunk_plain(doc, title, doc_id, license_tier, config, max_chars, overlap)

    chunks: list[Chunk] = []
    ordinal = 0
    for i, section in enumerate(doc.sections, start=1):
        ref = _heading_path(title, section.heading)
        body = section.text
        # A section shorter than min_chunk_chars is dropped as noise unless it
        # is the document's only section.
        if len(body) < config.min_chunk_chars and len(doc.sections) > 1:
            continue
        if len(body) <= max_chars:
            ordinal += 1
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    ordinal=ordinal,
                    content=_trim_to_max(body, max_chars),
                    section_ref=ref,
                    char_start=section.start_char,
                    char_end=section.start_char + len(body),
                    license_tier=license_tier,
                )
            )
            continue
        # Long section: sub-split by paragraph, then fixed-size with overlap.
        for sub in _subsplit_long(body, max_chars, overlap, config):
            ordinal += 1
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    ordinal=ordinal,
                    content=sub,
                    section_ref=ref,
                    char_start=section.start_char,
                    char_end=section.start_char + len(body),
                    license_tier=license_tier,
                )
            )
    return chunks


def _subsplit_long(
    body: str,
    max_chars: int,
    overlap: int,
    config: IngestConfig,
) -> list[str]:
    """Split an over-long section into chunks at paragraph boundaries, then
    by fixed size with overlap for any paragraph still too long."""
    out: list[str] = []
    paragraphs = split_paragraphs(body)
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if len(para) > max_chars:
            # Flush the accumulated paragraph group, then fixed-split this one.
            if current:
                out.append("\n\n".join(current))
                current, current_len = [], 0
            out.extend(_fixed_split(para, max_chars, overlap, config))
            continue
        if current_len + len(para) + 2 > max_chars and current:
            out.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(para)
        current_len += len(para) + 2
    if current:
        out.append("\n\n".join(current))
    # Drop noise below the minimum.
    return [c for c in out if len(c) >= config.min_chunk_chars]


def _fixed_split(
    text: str,
    max_chars: int,
    overlap: int,
    config: IngestConfig,
) -> list[str]:
    """Fixed-size split with overlap, trimmed at word boundaries."""
    out: list[str] = []
    start = 0
    step = max(1, max_chars - overlap)
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        chunk = _trim_to_max(text[start:end], max_chars)
        if len(chunk) >= config.min_chunk_chars:
            out.append(chunk)
        if end >= n:
            break
        start += step
    return out


def chunk_plain(
    doc: ExtractedDocument,
    title: str,
    doc_id: str,
    license_tier: str,
    config: IngestConfig,
    max_chars: int,
    overlap: int,
) -> list[Chunk]:
    """Plain chunking: paragraph-merge, then fixed-size for overflow.

    For documents with no section structure (TXT/PDF/DOCX).  The whole
    document is one section_ref (the title).
    """
    chunks: list[Chunk] = []
    ordinal = 0
    text = doc.text
    ref = title or doc_id
    if len(text) <= max_chars:
        if len(text) >= config.min_chunk_chars:
            ordinal += 1
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    ordinal=ordinal,
                    content=text,
                    section_ref=ref,
                    char_start=0,
                    char_end=len(text),
                    license_tier=license_tier,
                )
            )
        return chunks

    paragraphs = split_paragraphs(text)
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                ordinal = _emit_merged(ordinal, current, chunks, doc_id, ref, license_tier)
                current, current_len = [], 0
            for sub in _fixed_split(para, max_chars, overlap, config):
                if len(sub) >= config.min_chunk_chars:
                    ordinal += 1
                    chunks.append(
                        Chunk(
                            doc_id=doc_id,
                            ordinal=ordinal,
                            content=sub,
                            section_ref=ref,
                            char_start=0,
                            char_end=len(text),
                            license_tier=license_tier,
                        )
                    )
            continue
        if current_len + len(para) + 2 > max_chars and current:
            ordinal = _emit_merged(ordinal, current, chunks, doc_id, ref, license_tier)
            current, current_len = [], 0
        current.append(para)
        current_len += len(para) + 2
    if current:
        ordinal = _emit_merged(ordinal, current, chunks, doc_id, ref, license_tier)
    return chunks


def _emit_merged(
    ordinal: int,
    paragraphs: list[str],
    chunks: list[Chunk],
    doc_id: str,
    ref: str,
    license_tier: str,
) -> int:
    """Emit one chunk from a merged paragraph group; return the next ordinal."""
    content = "\n\n".join(paragraphs)
    if len(content) >= 20:  # min viable chunk
        ordinal += 1
        chunks.append(
            Chunk(
                doc_id=doc_id,
                ordinal=ordinal,
                content=content,
                section_ref=ref,
                char_start=0,
                char_end=len(content),
                license_tier=license_tier,
            )
        )
    return ordinal


def chunk_document(
    doc: ExtractedDocument,
    doc_id: str,
    title: str,
    license_tier: str,
    strategy: str,
    max_chars: int,
    overlap: int,
    config: IngestConfig,
) -> list[Chunk]:
    """Dispatch to the section or plain chunker for a manifest strategy."""
    chunker = config.chunker_for_strategy(strategy)
    if chunker == "section":
        return chunk_sections(
            doc, title, doc_id, license_tier, config, max_chars, overlap
        )
    if chunker == "plain":
        return chunk_plain(
            doc, title, doc_id, license_tier, config, max_chars, overlap
        )
    raise ValueError(f"unknown chunker implementation {chunker!r}")
