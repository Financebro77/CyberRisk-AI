"""Validated data schemas for input data.

Defines pydantic models for two input kinds:

1. Firm cyber profile (the raw assessment input to scoring).
2. Calibration benchmark records (from CSV, e.g. DBIR / IBM / Hiscox) that
   anchor scenario frequency/severity parameters.

Keeping these at the boundary means malformed inputs fail loudly with
actionable messages rather than propagating NaN / wrong units into the
modelling engine.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class BenchmarkRecord(BaseModel):
    """One row of a calibration benchmark dataset.

    Attributes
        source  benchmark source (e.g. "Verizon DBIR", "IBM CODB")
        sector  firm sector the benchmark applies to ("All" for economy-wide)
        metric  benchmark metric name (e.g. "breach_frequency")
        value   numeric value of the metric
        units   units of `value` (events_per_year / usd_per_record / ...)
        notes   provenance / interpretation for the calibration log
    """

    source: str
    sector: str
    metric: str
    value: float = Field(gt=0.0)
    units: str
    notes: str = ""

    @field_validator("value")
    @classmethod
    def _value_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"benchmark value must be positive, got {v}")
        return v


class BenchmarkSet(BaseModel):
    """Collection of benchmark records, grouped for lookup."""

    records: list[BenchmarkRecord]

    def filter(self, source: str | None = None, metric: str | None = None) -> list[BenchmarkRecord]:
        """Return records matching source/metric (case-insensitive substring)."""
        out = []
        for r in self.records:
            if source and source.lower() not in r.source.lower():
                continue
            if metric and metric.lower() not in r.metric.lower():
                continue
            out.append(r)
        return out

    def first_value(self, source: str, metric: str) -> float:
        """Single-value lookup: raises if not exactly one match."""
        matches = self.filter(source, metric)
        if len(matches) != 1:
            raise KeyError(f"expected 1 match for {source}/{metric}, got {len(matches)}")
        return matches[0].value

    @classmethod
    def from_csv(cls, path: str | Path) -> BenchmarkSet:
        """Parse a benchmark CSV into a validated BenchmarkSet."""
        import csv

        records: list[BenchmarkRecord] = []
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                records.append(BenchmarkRecord(**row))
        return cls(records=records)
