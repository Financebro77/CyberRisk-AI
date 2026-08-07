"""Dataset manifest parsing — the single source of truth for knowledge datasets.

The knowledge layer's ``knowledge/manifests/dataset_manifest.yaml`` is the
registry that makes adding a dataset a *file drop + one manifest entry* with
no code change.  This module is the code-side contract for that registry:

    * validated pydantic models mirroring ``knowledge/schemas/dataset.schema.json``,
    * ``load_dataset_manifest`` — parse + validate the YAML,
    * ``resolve_dataset_path`` — map a manifest ``id`` (a namespaced relative
      path) onto a real file under ``knowledge/datasets/``,
    * ``verify_content_hash`` — check the manifest's ``sha256:`` hash against
      the actual file, so a stale registry is caught loudly,
    * ``KNOWN_TARGETS`` — the engine seams a dataset may feed; an unknown
      target fails validation instead of silently doing nothing.

This mirrors the engine's own philosophy (``calibration.py``, ``data/schemas.py``):
*validate at the boundary, fail loudly, never propagate bad values into the
modelling engine.*  The manifest is authoritative — this code never duplicates
the registry; it only reads it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Engine seams a dataset may feed.  Adding a new seam (e.g. a future pricing
# model) is a one-line addition here; until then an unknown target fails.
# ---------------------------------------------------------------------------
KNOWN_TARGETS: tuple[str, ...] = (
    "calibration.apply_benchmarks",
    "credibility.apply_credibility",
)

# Refresh cadences mirrored from the schema; used by the (future) refresh pipeline.
RefreshCadence = Literal[
    "daily", "weekly", "monthly", "quarterly", "annual", "on_revision"
]

# The four license tiers from the knowledge access policy.
LicenseTier = Literal[
    "public", "licensed", "proprietary", "client-confidential"
]

# Dataset file formats the loader can read.
DatasetFormat = Literal["csv", "parquet", "json", "xlsx"]


class DatasetManifestEntry(BaseModel):
    """One registered dataset, validated against dataset.schema.json.

    ``id`` is a namespaced relative path under ``knowledge/datasets/``, e.g.
    ``datasets/benchmarks/severity/ibm-codb-2026-sector``.  ``targets`` names
    the engine seam(s) the table feeds; ``content_hash`` pins the exact file.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(
        description="Unique, namespaced by location: datasets/<group>/<category>/<table>"
    )
    domain: str
    category: str
    title: str = Field(min_length=3)
    source: str = Field(min_length=2)
    license_tier: LicenseTier
    format: DatasetFormat
    # NOTE: the manifest YAML key is `schema` (matching dataset.schema.json).
    # Pydantic v2 warns if a field shadows BaseModel.schema, so the field is
    # named schema_name and aliased to `schema` at validation time.
    schema_name: str = Field(
        alias="schema",
        description="Named table schema this dataset conforms to",
    )
    version: str = Field(min_length=1)
    content_hash: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="sha256 of the source file; a stale manifest is caught at load",
    )
    acquired_at: str  # YYYY-MM-DD
    refresh_cadence: RefreshCadence
    tags: list[str] = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    status: Literal["active", "deprecated", "example"] = "active"
    # Optional metadata the loader uses to map raw table columns onto
    # BenchmarkRecord fields.  When absent, columns are matched by name.
    column_map: dict[str, str] | None = Field(
        default=None,
        description="Raw table column -> canonical field (source/sector/metric/value/units/notes)",
    )
    path: str | None = Field(
        default=None,
        description="Explicit relative path to the file under knowledge/datasets/ "
        "(default: derived from id)",
    )

    @field_validator("id")
    @classmethod
    def _id_namespaced(cls, v: str) -> str:
        if not v.startswith("datasets/"):
            raise ValueError(f"dataset id must start with 'datasets/', got {v!r}")
        return v

    @field_validator("targets")
    @classmethod
    def _known_targets(cls, v: list[str]) -> list[str]:
        unknown = [t for t in v if t not in KNOWN_TARGETS]
        if unknown:
            raise ValueError(
                f"unknown engine target(s) {unknown}; known targets: {KNOWN_TARGETS}"
            )
        return v

    def relative_path(self) -> Path:
        """The dataset file's path relative to the knowledge/datasets root."""
        if self.path is not None:
            return Path(self.path)
        # id = "datasets/<group>/<category>/<table>" -> strip the "datasets/" prefix.
        return Path(self.id.removeprefix("datasets/"))  # <group>/<category>/<table>

    def is_active(self) -> bool:
        return self.status == "active"


class DatasetManifest(BaseModel):
    """The full dataset registry (``datasets:`` section of the YAML)."""

    datasets: list[DatasetManifestEntry]

    def active(self) -> list[DatasetManifestEntry]:
        """Only ``status: active`` entries — deprecated/example are excluded."""
        return [d for d in self.datasets if d.is_active()]

    def by_domain(self, domain: str) -> list[DatasetManifestEntry]:
        return [d for d in self.active() if d.domain == domain]

    def by_target(self, target: str) -> list[DatasetManifestEntry]:
        return [d for d in self.active() if target in d.targets]


def default_dataset_root() -> Path:
    """Repo-root ``knowledge/datasets`` (repo root = 4 levels above this module)."""
    return Path(__file__).resolve().parent.parent.parent.parent / "knowledge" / "datasets"


def default_manifest_path() -> Path:
    """Repo-root ``knowledge/manifests/dataset_manifest.yaml``."""
    return Path(__file__).resolve().parent.parent.parent.parent / "knowledge" / "manifests" / "dataset_manifest.yaml"


def load_dataset_manifest(
    path: str | Path | None = None,
) -> DatasetManifest:
    """Load + validate the dataset manifest YAML.

    Parameters
        path  explicit manifest path (defaults to the repo's
              ``knowledge/manifests/dataset_manifest.yaml``)

    Returns
        DatasetManifest with every entry validated.  Raises loudly on a
        malformed entry or a missing ``datasets:`` key — the boundary-style
        validation the engine already uses.
    """
    path = Path(path) if path is not None else default_manifest_path()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "datasets" not in raw:
        raise ValueError(f"{path}: manifest must contain a top-level 'datasets:' list")
    return DatasetManifest(**raw)


def resolve_dataset_path(
    entry: DatasetManifestEntry,
    root: str | Path | None = None,
) -> Path:
    """Resolve a manifest entry to its file under the dataset root.

    Parameters
        entry  a validated DatasetManifestEntry
        root   knowledge/datasets root (defaults to the repo default)

    Returns
        absolute Path to the dataset file.

    Raises
        FileNotFoundError  when no file matching the entry's id exists.
    """
    root = Path(root) if root is not None else default_dataset_root()
    rel = entry.relative_path()
    # Try the exact relative path first, then as a glob so extensions are
    # tolerant (id has no extension; the file may be .csv/.parquet/.json/.xlsx).
    for candidate in (root / rel,):
        if candidate.exists():
            return candidate
    matches = sorted(root.glob(f"{rel}.*"))
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"no dataset file for id {entry.id!r} under {root} (expected {root / rel}.<ext>)"
    )


def sha256_file(path: str | Path) -> str:
    """Hex sha256 of a file, in the manifest's ``sha256:...`` form."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def verify_content_hash(
    entry: DatasetManifestEntry,
    path: str | Path,
) -> None:
    """Verify the manifest's content_hash matches the actual file.

    Raises
        ValueError  when the on-disk hash differs — the manifest is stale and
                    the entry must be re-registered rather than silently using
                    a different file than the registry claims.
    """
    actual = sha256_file(path)
    if actual != entry.content_hash:
        raise ValueError(
            f"content hash mismatch for {entry.id}: manifest {entry.content_hash}, "
            f"file {actual}. Re-register the entry (update content_hash) after changing the file."
        )
