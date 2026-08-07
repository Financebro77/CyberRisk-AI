"""Input data schemas and loaders: validated models for firm profiles,
benchmark datasets, and the manifest-driven dataset loader.

Public entry points:
    load_benchmarks          -> BenchmarkSet  (from a CSV, e.g. calibration_benchmarks.csv)
    load_company_profile     -> CompanyProfile (validated)
    load_dataset_manifest    -> DatasetManifest (from knowledge/manifests/dataset_manifest.yaml)
    load_dataset             -> pd.DataFrame  (one manifest-registered dataset)
    to_benchmarks            -> list[BenchmarkRecord]  (DataFrame -> records)
    datasets_to_benchmarks   -> BenchmarkSet (aggregate manifest datasets)
    build_calibrated_config  -> ModelConfig  (frequency + severity overrides)
    apply_benchmark_frequencies -> ModelConfig (frequency overrides via engine seam)
"""

from cyberrisk.data.loaders import load_benchmarks, load_company_profile
from cyberrisk.data.schemas import BenchmarkRecord, BenchmarkSet
from cyberrisk.data.manifest import (
    DatasetManifest,
    DatasetManifestEntry,
    KNOWN_TARGETS,
    default_dataset_root,
    default_manifest_path,
    load_dataset_manifest,
    resolve_dataset_path,
    sha256_file,
    verify_content_hash,
)
from cyberrisk.data.dataset_loaders import (
    load_dataset,
    to_benchmarks,
    datasets_to_benchmarks,
    build_calibrated_config,
    apply_benchmark_frequencies,
)

__all__ = [
    "load_benchmarks",
    "load_company_profile",
    "BenchmarkRecord",
    "BenchmarkSet",
    "DatasetManifest",
    "DatasetManifestEntry",
    "KNOWN_TARGETS",
    "default_dataset_root",
    "default_manifest_path",
    "load_dataset_manifest",
    "resolve_dataset_path",
    "sha256_file",
    "verify_content_hash",
    "load_dataset",
    "to_benchmarks",
    "datasets_to_benchmarks",
    "build_calibrated_config",
    "apply_benchmark_frequencies",
]
