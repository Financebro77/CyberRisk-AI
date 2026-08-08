"""Embedders — turn chunk text into fixed-dimension vectors.

The default embedder is a deterministic, dependency-free **feature-hash
embedder**: it tokenizes the text, feature-hashes each token to a dimension
and a sign, accumulates, and L2-normalizes.  It is:

    * deterministic    — the same text always yields the same vector,
    * offline          — no model download, no external service, no torch,
    * reproducible     — the pipeline and the (future) retrieval layer get
                         identical vectors across runs and machines.

This is deliberately NOT a semantic embedder (no learned semantics); it is
the zero-dependency baseline that makes the vector store work end-to-end.
A future optional ``sentence-transformers`` embedder can be registered behind
the same ``Embedder`` interface without changing the pipeline.

``embedding_hash`` (sha256 of the vector bytes) lets the pipeline detect
whether a chunk's embedding is current: same text + same embedder -> same hash.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

# Tokenize on runs of word characters / digits (lowercased).  Keeps the
# embedding stable across case and punctuation, which is right for a bag of
# words hash.
_TOKEN_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)

DEFAULT_DIM = 768


class HashEmbedder:
    """Deterministic feature-hash bag-of-words embedder (no dependencies)."""

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        if dim < 1:
            raise ValueError("embedding dim must be >= 1")
        self._dim = dim

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed(self, text: str) -> np.ndarray:
        """Return an L2-normalized (dim,) float32 vector for ``text``.

        Feature-hash each token to a dimension index and a sign, accumulate
        into a histogram, then L2-normalize.  Empty/short text yields a zero
        vector (normalization of a zero vector is a zero vector).
        """
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in _TOKEN_RE.findall(text.lower()):
            # Two independent hashes: one for dimension, one for sign.
            index = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16) % self.dim
            sign = 1 if int(hashlib.md5(token.encode("utf-8")).hexdigest()[8:16], 16) % 2 else -1
            vec[index] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def embed_many(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts into a (n, dim) float32 array."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.embed(t) for t in texts])

    def embedding_hash(self, text: str) -> str:
        """Stable sha256 hash of the vector bytes for ``text``."""
        return "sha256:" + hashlib.sha256(self.embed(text).tobytes()).hexdigest()

    # ------------------------------------------------------------------
    # Model identity (so a registry / store can tell embedders apart)
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return f"hash:{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim


class EmbedderRegistry:
    """Named embedders, so a future sentence-transformers embedder drops in.

    ``default`` maps to the dependency-free HashEmbedder.  Resolving an
    unknown name raises loudly rather than silently falling back to a model
    the caller didn't ask for.
    """

    def __init__(self, default_dim: int = DEFAULT_DIM) -> None:
        self._embedders: dict[str, HashEmbedder] = {}
        self._default = HashEmbedder(dim=default_dim)

    def register(self, name: str, embedder: HashEmbedder) -> None:
        self._embedders[name] = embedder

    def get(self, name: str | None = None) -> HashEmbedder:
        if name in (None, "", "default"):
            return self._default
        try:
            return self._embedders[name]
        except KeyError:
            raise KeyError(
                f"unknown embedder {name!r}; known: default, {', '.join(self._embedders)}"
            ) from None
