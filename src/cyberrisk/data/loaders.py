"""Data loaders: ingestion of benchmark / profile inputs into validated schemas.

The public interface is intentionally small and source-agnostic:

    load_benchmarks(path)  -> BenchmarkSet
    load_company_profile(dict)  -> CompanyProfile

`load_benchmarks` parses CSV rows (DBIR / IBM / Hiscox / NetDiligence) into
validated BenchmarkRecord objects.  The loader does NOT know about the
scenario model -- translating benchmark metrics into scenario frequency /
severity parameters is the job of `calibration.apply_benchmarks` (in
calibration.py).  This separation means a licensed proprietary loss dataset
(Advisen-style event tables) can be swapped in later by adding a second
loader that returns the same BenchmarkSet shape, with no changes to the
simulation engine.
"""

from __future__ import annotations

from pathlib import Path

from cyberrisk.data.schemas import BenchmarkSet
from cyberrisk.scoring import CompanyProfile


def load_benchmarks(path: str | Path) -> BenchmarkSet:
    """Load a benchmark CSV (DBIR / IBM / Hiscox / ...) into a validated set.

    See config/calibration_benchmarks.csv for the canonical format:
        source,sector,metric,value,units,notes
    """
    return BenchmarkSet.from_csv(path)


def load_company_profile(data: dict) -> CompanyProfile:
    """Validate a raw company cyber profile dict into a CompanyProfile.

    Accepts factor scores either as a nested "factor_scores" dict or as
    top-level keys (for CSV/Excel input convenience).
    """
    return CompanyProfile(**data)
