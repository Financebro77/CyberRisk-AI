"""Manifest-driven dataset loader — turn knowledge datasets into engine inputs.

The knowledge layer's ``knowledge/datasets/`` holds structured quantitative
tables (severity, frequency, sector, market, history).  This loader is the
code that turns those tables into what the engine already understands:

    * ``load_dataset(entry)``        -> pd.DataFrame (CSV/parquet/JSON/xlsx)
    * ``to_benchmarks(df, entry)``   -> list[BenchmarkRecord]
    * ``datasets_to_benchmarks()``   -> BenchmarkSet (the engine's interchange type)
    * ``build_calibrated_config()``  -> ModelConfig, frequency + severity overrides

The engine seam is unchanged: ``calibration.apply_benchmarks`` already turns a
``BenchmarkSet`` into scenario lambdas.  This loader extends that same seam to
severity parameters, so a dataset dropped into ``knowledge/datasets/`` +
registered in ``dataset_manifest.yaml`` can drive BOTH frequency and severity —
closing the "mock severity layer" gap with zero engine changes.

Column mapping: each manifest entry may carry a ``column_map`` that renames
raw table columns to the canonical ``BenchmarkRecord`` fields
(source, sector, metric, value, units, notes).  When a column_map is absent,
columns are matched by name.  The ``metric`` column may hold canonical values
(e.g. ``breach_frequency``) or a human label (e.g. ``Breach frequency``) that
this module normalises.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cyberrisk.calibration import ModelConfig
from cyberrisk.data.manifest import (
    DatasetManifest,
    DatasetManifestEntry,
    default_dataset_root,
    default_manifest_path,
    load_dataset_manifest,
    resolve_dataset_path,
    verify_content_hash,
)
from cyberrisk.data.schemas import BenchmarkRecord, BenchmarkSet

# ---------------------------------------------------------------------------
# Canonical BenchmarkRecord field names
# ---------------------------------------------------------------------------
_RECORD_FIELDS = ("source", "sector", "metric", "value", "units", "notes")

# ---------------------------------------------------------------------------
# Format readers — each format handled with its optional dependency absent
# failing with a clear, actionable error (never a raw ImportError).
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _read_parquet(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except ImportError as exc:  # pandas needs pyarrow/fastparquet
        raise RuntimeError(
            "Reading parquet requires 'pyarrow' or 'fastparquet'. "
            "Install with `pip install pyarrow`."
        ) from exc


def _read_json(path: Path) -> pd.DataFrame:
    return pd.read_json(path)


def _read_xlsx(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path)
    except ImportError as exc:  # pandas needs openpyxl (or xlrd)
        raise RuntimeError(
            "Reading xlsx requires 'openpyxl'. Install with `pip install openpyxl`."
        ) from exc


_READERS = {
    "csv": _read_csv,
    "parquet": _read_parquet,
    "json": _read_json,
    "xlsx": _read_xlsx,
}


def load_dataset(
    entry: DatasetManifestEntry,
    root: str | Path | None = None,
    verify: bool = True,
) -> pd.DataFrame:
    """Read one manifest-registered dataset into a DataFrame.

    Parameters
        entry    a validated DatasetManifestEntry
        root     knowledge/datasets root (defaults to the repo default)
        verify   when True (default), the file's sha256 is checked against the
                 manifest before reading — a stale registry is caught loudly.

    Returns
        pd.DataFrame of the table.

    Raises
        FileNotFoundError  no file resolves for the entry
        ValueError         content hash mismatch (when verify=True)
        RuntimeError       format's optional dependency is missing
    """
    path = resolve_dataset_path(entry, root)
    if verify:
        verify_content_hash(entry, path)
    reader = _READERS.get(entry.format)
    if reader is None:
        raise ValueError(
            f"unsupported format {entry.format!r} for {entry.id}; "
            f"supported: {', '.join(sorted(_READERS))}"
        )
    return reader(path)


# ---------------------------------------------------------------------------
# Metric normalisation: raw column value -> canonical metric name
# ---------------------------------------------------------------------------

# scenario key -> human label prefixes (used to canonicalise raw labels).
_SCENARIO_LABELS = {
    "breach": ("breach", "data breach", "data-break"),
    "ransomware": ("ransomware", "ransom"),
    "bec": ("bec", "business email compromise", "wire fraud", "email compromise"),
    "cloud_outage": ("cloud", "cloud outage", "saas", "third.party outage"),
    "bi": ("business interruption", "bi", "outage"),
    "supply_chain": ("supply.chain", "supply chain", "third.party compromise"),
    "ot_physical": ("ot", "physical", "ics", "scada"),
}

_CANONICAL_METRICS: dict[str, str] = {
    # frequency
    "breach_frequency": "breach_frequency",
    "ransomware_frequency": "ransomware_frequency",
    "bec_frequency": "bec_frequency",
    "cloud_outage_frequency": "cloud_outage_frequency",
    "bi_frequency": "bi_frequency",
    "supply_chain_frequency": "supply_chain_frequency",
    "ot_physical_frequency": "ot_physical_frequency",
    # severity scale
    "severity_breach": "severity_breach",
    "severity_ransomware": "severity_ransomware",
    "severity_bec": "severity_bec",
    "severity_cloud_outage": "severity_cloud_outage",
    "severity_bi": "severity_bi",
    "severity_supply_chain": "severity_supply_chain",
    "severity_ot_physical": "severity_ot_physical",
    # severity tail parameters
    "severity_mu_breach": "severity_mu_breach",
    "severity_mu_ransomware": "severity_mu_ransomware",
    "severity_mu_bec": "severity_mu_bec",
    "severity_mu_cloud_outage": "severity_mu_cloud_outage",
    "severity_mu_bi": "severity_mu_bi",
    "severity_mu_supply_chain": "severity_mu_supply_chain",
    "severity_mu_ot_physical": "severity_mu_ot_physical",
    "severity_sigma_breach": "severity_sigma_breach",
    "severity_sigma_ransomware": "severity_sigma_ransomware",
    "severity_sigma_bec": "severity_sigma_bec",
    "severity_sigma_cloud_outage": "severity_sigma_cloud_outage",
    "severity_sigma_bi": "severity_sigma_bi",
    "severity_sigma_supply_chain": "severity_sigma_supply_chain",
    "severity_sigma_ot_physical": "severity_sigma_ot_physical",
    "severity_revenue_exp_breach": "severity_revenue_exp_breach",
    "severity_revenue_exp_ransomware": "severity_revenue_exp_ransomware",
    "severity_revenue_exp_bec": "severity_revenue_exp_bec",
    "severity_revenue_exp_cloud_outage": "severity_revenue_exp_cloud_outage",
    "severity_revenue_exp_bi": "severity_revenue_exp_bi",
    "severity_revenue_exp_supply_chain": "severity_revenue_exp_supply_chain",
    "severity_revenue_exp_ot_physical": "severity_revenue_exp_ot_physical",
}

_METRIC_KIND = ("severity_revenue_exp", "severity_sigma", "severity_mu", "severity", "frequency")


def _canonical_for(scenario: str, kind: str) -> str | None:
    """Canonical metric name for a scenario + kind, or None if not registered.

    The canonical convention differs by kind:
        frequency          -> "<scenario>_frequency"       (ransomware_frequency)
        severity           -> "severity_<scenario>"        (severity_ransomware)
        severity_mu        -> "severity_mu_<scenario>"     (severity_mu_ransomware)
        severity_sigma     -> "severity_sigma_<scenario>"  (severity_sigma_ransomware)
        severity_revenue_exp -> "severity_revenue_exp_<scenario>"
    """
    if kind == "frequency":
        candidate = f"{scenario}_frequency"
    else:
        candidate = f"{kind}_{scenario}"
    return candidate if candidate in _CANONICAL_METRICS else None


def _normalise_metric(raw: str) -> str:
    """Map a raw metric value (canonical or human label) to a canonical name.

    Canonical convention, e.g. ``ransomware_frequency`` for frequency and
    ``severity_breach`` / ``severity_mu_breach`` / ``severity_sigma_breach`` /
    ``severity_revenue_exp_breach`` for severity.  Human labels
    (``"Ransomware frequency"``, ``"Breach severity"``) are normalised to that
    convention.
    """
    key = str(raw).strip().lower()
    if key in _CANONICAL_METRICS:
        return _CANONICAL_METRICS[key]
    # Human label: "<scenario label> <kind>" e.g. "Ransomware frequency" or
    # "Frequency of ransomware" — detect the scenario label and the kind, then
    # emit the canonical name.  severity_mu/sigma/revenue_exp are checked first
    # so "severity sigma" is not swallowed by the bare "severity" kind.
    for scenario, labels in _SCENARIO_LABELS.items():
        for label in labels:
            if label in key:
                for kind in _METRIC_KIND:
                    if kind in key:
                        canonical = _canonical_for(scenario, kind)
                        if canonical is not None:
                            return canonical
    # Normalised snake-case fallback.
    norm = key.replace(" ", "_").replace("-", "_").replace("/", "_").lower()
    if norm in _CANONICAL_METRICS:
        return _CANONICAL_METRICS[norm]
    return norm


# ---------------------------------------------------------------------------
# Row -> BenchmarkRecord
# ---------------------------------------------------------------------------


def _apply_column_map(
    row: dict[str, object],
    column_map: dict[str, str] | None,
) -> dict[str, object]:
    """Rename raw columns to canonical BenchmarkRecord fields via entry.column_map."""
    if not column_map:
        return row
    return {canonical: row[raw] for raw, canonical in column_map.items() if raw in row}


def to_benchmarks(
    df: pd.DataFrame,
    entry: DatasetManifestEntry,
    sector_default: str = "All",
) -> list[BenchmarkRecord]:
    """Convert a loaded dataset DataFrame into validated BenchmarkRecords.

    Parameters
        df              the table (from ``load_dataset``)
        entry           the manifest entry (its column_map governs renaming)
        sector_default  sector used when the row has no sector column

    Returns
        list[BenchmarkRecord], validated by pydantic — a malformed row raises
        loudly instead of propagating bad values into the engine.

    The value column may be stringly-typed in source files; it is coerced to
    float and a non-numeric value fails validation loudly.
    """
    records: list[BenchmarkRecord] = []
    for _, raw_row in df.iterrows():
        row = _apply_column_map(dict(raw_row), entry.column_map)

        def _get(name: str, default: object = None) -> object:
            return row.get(name, default) if name in row else default

        source = _get("source") or entry.source
        sector = _get("sector") or sector_default
        metric_raw = _get("metric")
        if metric_raw is None or pd.isna(metric_raw):
            raise ValueError(f"{entry.id}: row missing 'metric' column")
        value_raw = _get("value")
        if value_raw is None or pd.isna(value_raw):
            raise ValueError(f"{entry.id}: row missing 'value' column")
        units = _get("units") or ""
        notes = _get("notes") or ""

        records.append(
            BenchmarkRecord(
                source=str(source).strip(),
                sector=str(sector).strip(),
                metric=_normalise_metric(str(metric_raw)),
                value=float(value_raw),
                units=str(units).strip(),
                notes=str(notes).strip(),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Aggregate datasets -> BenchmarkSet, and drive the engine calibration seam
# ---------------------------------------------------------------------------


def datasets_to_benchmarks(
    manifest: DatasetManifest,
    *,
    domain: str | None = None,
    target: str | None = None,
    root: str | Path | None = None,
    verify: bool = True,
) -> BenchmarkSet:
    """Aggregate one or more datasets into a single BenchmarkSet.

    Parameters
        manifest  the validated dataset manifest
        domain    optional: only datasets of this domain (benchmarks/market/history)
        target    optional: only datasets targeting this engine seam
        root      dataset root (defaults to repo default)
        verify    content-hash check on each file (default True)

    Returns
        BenchmarkSet of all BenchmarkRecords across the selected datasets.
    """
    entries = manifest.active()
    if domain is not None:
        entries = [e for e in entries if e.domain == domain]
    if target is not None:
        entries = [e for e in entries if e.targets and target in e.targets]

    all_records: list[BenchmarkRecord] = []
    for entry in entries:
        df = load_dataset(entry, root=root, verify=verify)
        all_records.extend(to_benchmarks(df, entry))
    return BenchmarkSet(records=all_records)


# ---------------------------------------------------------------------------
# Build a calibrated ModelConfig from the manifest (frequency + severity)
# ---------------------------------------------------------------------------


def build_calibrated_config(
    config: ModelConfig,
    manifest: DatasetManifest | None = None,
    *,
    domain: str | None = None,
    target: str = "calibration.apply_benchmarks",
    root: str | Path | None = None,
    verify: bool = True,
) -> ModelConfig:
    """Apply manifest-registered benchmark datasets to a ModelConfig.

    Extends ``calibration.apply_benchmarks``: frequency metrics already
    override scenario lambdas through the existing seam; severity metrics are
    applied here so a dataset can also drive severity (scale / mu / sigma /
    revenue exponent) — the capability that closes the mock-severity gap.

    Parameters
        config    the base ModelConfig (from ``load_config``)
        manifest  the dataset manifest (defaults to the repo manifest)
        domain    optional: only apply datasets of this domain
        target    the engine seam to apply (default calibration.apply_benchmarks)
        root      dataset root (defaults to repo default)
        verify    content-hash check on each file (default True)

    Returns
        a NEW ModelConfig with frequency + severity overrides applied.  The
        input config is not mutated — reproducible from the manifest alone.

    Severity metrics use the canonical names ``severity_<scenario>`` (scale),
    ``severity_mu_<scenario>``, ``severity_sigma_<scenario>`` and
    ``severity_revenue_exp_<scenario>``.
    """
    if manifest is None:
        manifest = load_dataset_manifest(default_manifest_path())
    benchmarks = datasets_to_benchmarks(
        manifest, domain=domain, target=target, root=root, verify=verify
    )

    # Frequency: existing seam (calibration.apply_benchmarks) overrides lambdas.
    calibrated = apply_benchmark_frequencies(config, benchmarks)

    # Severity: apply severity metric overrides scenario-by-scenario.
    scenario_by_key = {s.key: s for s in calibrated.scenarios}
    for rec in benchmarks.records:
        metric = rec.metric
        # severity_<scenario> | severity_mu_<scenario> | severity_sigma_<scenario>
        # | severity_revenue_exp_<scenario>
        if not metric.startswith("severity"):
            continue
        rest = metric[len("severity"):].lstrip("_")  # e.g. "breach" | "mu_breach"
        if rest.startswith("mu_"):
            scenario_key, field = rest[3:], "mu"
        elif rest.startswith("sigma_"):
            scenario_key, field = rest[6:], "sigma"
        elif rest.startswith("revenue_exp_"):
            scenario_key, field = rest[12:], "revenue_exponent"
        else:
            scenario_key, field = rest, "scale"
        scenario = scenario_by_key.get(scenario_key)
        if scenario is None:
            raise ValueError(
                f"{metric!r} references unknown scenario {scenario_key!r}; "
                f"known scenarios: {sorted(scenario_by_key)}"
            )
        _apply_severity_override(calibrated, scenario_key, field, rec.value)

    return calibrated


def apply_benchmark_frequencies(
    config: ModelConfig,
    benchmarks: BenchmarkSet,
    sector: str = "All",
) -> ModelConfig:
    """Override scenario lambdas from benchmark frequency records.

    Thin wrapper over the existing engine seam ``calibration.apply_benchmarks``
    so callers of this loader do not need to import the calibration module.
    """
    from cyberrisk.calibration import apply_benchmarks

    return apply_benchmarks(config, benchmarks, sector=sector)


def _apply_severity_override(
    config: ModelConfig,
    scenario_key: str,
    field: str,
    value: float,
) -> None:
    """In-place severity override on a (fresh) ModelConfig's scenario.

    Kept as a module-private helper; the public contract is that
    ``build_calibrated_config`` returns a new config and never mutates the
    caller's object.  ``value`` is the absolute override for the named field:
        scale            severity scale ($)
        mu               lognormal mu
        sigma            lognormal sigma
        revenue_exponent revenue elasticity
    """
    for i, s in enumerate(config.scenarios):
        if s.key != scenario_key:
            continue
        if field == "revenue_exponent":
            config.scenarios[i] = s.model_copy(update={"revenue_exponent": value})
            return
        sev = s.severity
        new_sev = sev.model_copy(update={field: value})
        config.scenarios[i] = s.model_copy(update={"severity": new_sev})
        return
