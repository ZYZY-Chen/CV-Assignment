"""Bounded paged experiment snapshots with standard-library verification."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import uuid

import importlib.util as _import_util
_bootstrap_spec = _import_util.spec_from_file_location(
    "_tc2_gpu_bootstrap", Path(__file__).resolve().parents[1] / "_bootstrap.py")
_bootstrap = _import_util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)
ROOT = _bootstrap.configure(__file__)
# Reuse the accepted pilot collector's path, hash and hostile-tar protections.
from scripts.tc2_gpu.collect.collect_pilot import (_extended, _plain, _job, _relative, _no_links, _inside,
    _sha, _bytes_sha, _read_bounded, _json, _encode, _digest, _tar_layout, _atomic_publish,
    PROTOCOL_SHA256, HEX, PHASE, ARTIFACTS, RESULT_FILES, SCIENCE_SOURCES, CACHE_SOURCES)

LIMIT = 512 * 1024 * 1024
MAX_PAGES = 32
MAX_MEMBERS = 512
MAX_INDEX = 8 * 1024 * 1024
from tc2_gpu_provenance import current_source_hashes

CONFIG = "configs/tc2_gpu/experiments.json"
MANIFEST = "experiments_export_manifest.json"
RECEIPT = "page_verification.json"
ANALYSIS_FILES = ("analysis.json", "analysis.csv", "evidence.json", "analysis.sha256", "SUCCESS")
JOB_FILES = {"setup_status.json", "plan.json", "resources.json", "experiment_sources.json",
             "result_summary.json", "analysis_index.json"}
CATEGORIES = {"mvtec_ad": ("bottle", "cable", "capsule", "screw", "tile", "wood"),
              "mvtec_loco": ("juice_bottle", "screw_bag")}
STAGES = ("B0", "H1", "H2", "C1", "I1_seed17", "R0", "C1R", "C2", "F1", "I1_all_seeds", "I2", "B0_LOCO")
EXPERIMENT_SOURCES = {CONFIG, "scripts/tc2_gpu/experiments/run_stages.py", "scripts/tc2_gpu/experiments/analyze_scores.py",
                      "scripts/tc2_gpu/slurm/run_stages.sh", "scripts/tc2_gpu/collect/collect_experiments.py",
                      "tests/test_experiments_tc2_gpu.py", "docs/experiment_history/implementation/STEP_07_EXPERIMENTS.md",
    'scripts/__init__.py',
    'scripts/tc2_gpu/__init__.py',
    'scripts/tc2_gpu/_bootstrap.py',
    'src/tc2_gpu_provenance.py',
    'scripts/tc2_gpu/experiments/__init__.py',
    'scripts/tc2_gpu/pilot/__init__.py',
    'scripts/tc2_gpu/collect/__init__.py',
    'scripts/tc2_gpu/workflow/__init__.py',
    'scripts/tc2_gpu/pilot/run_pilot.py',
    'scripts/tc2_gpu/collect/collect_pilot.py',
    'scripts/tc2_gpu/workflow/run_workflow.py'}
RULES = {"native", "max", "top_0.001", "top_0.01", "top_0.05"}
METRIC_POLICY = {"version": "tc2_gpu_tie_grouped", "ties": "equal-score threshold groups",
                 "threshold_percentile": 95.0, "percentile_method": "linear", "decision": "score > threshold",
                 "pixel_scope": "all pixels at original resolution"}
CSV_FIELDS = ("stage", "run_key", "dataset", "category", "method", "run_seed", "score_rule",
              "n_dev", "n_good", "n_anomaly", "image_auroc", "image_ap", "threshold_95pct",
              "normal_fpr", "anomaly_recall", "per_defect_recall", "delta_image_auroc_vs_native",
              "delta_image_ap_vs_native", "delta_normal_fpr_vs_native", "delta_anomaly_recall_vs_native",
              "result_path", "result_identity_sha256", "pixel_metrics_reference")
MANIFESTS = {"manifests/manifest_" + dataset + "_" + category + ".json"
             for dataset, categories in CATEGORIES.items() for category in categories}
PAGE = re.compile(r"page_([0-9]{3})\.tar\.gz\Z")


def _hex(value):
    if not isinstance(value, str) or not re.fullmatch(HEX, value):
        raise ValueError("Expected an uppercase SHA256 fingerprint")
    return value


def _stage_id(value):
    if value not in STAGES:
        raise ValueError("Stage is outside the approved experiment sequence")
    return value


def _result_path(value):
    _relative(value)
    if not re.fullmatch(r"run/tc2_gpu/results/" + HEX, value):
        raise ValueError("Result is outside the formal published directory")
    return value


def _cache_path(value):
    _relative(value)
    for dataset, categories in CATEGORIES.items():
        if re.fullmatch(r"run/tc2_gpu/feature_cache/" + dataset + "/(?:" + "|".join(categories) + ")/" + HEX, value):
            return value
    raise ValueError("Cache is outside the eight approved categories")


def _analysis_path(value):
    _relative(value)
    if not re.fullmatch(r"run/tc2_gpu/summaries/(?:I1_seed17|I1_all_seeds|I2)/" + HEX, value):
        raise ValueError("Analysis is outside the three approved summaries")
    return value


def _role(name, job_id):
    _relative(name)
    if name == CONFIG:
        return "experiment_configuration"
    if name in MANIFESTS:
        return "frozen_manifest"
    prefix = "run/validation_tc2_gpu/"
    if name in {prefix + "slurm-" + job_id + suffix for suffix in (".out", ".err")}:
        return "slurm_log"
    job_prefix = prefix + "step7_job_" + job_id + "/"
    if name.startswith(job_prefix):
        tail = name[len(job_prefix):]
        if tail in JOB_FILES:
            return "experiment_record"
        if PHASE.fullmatch(tail):
            return "phase_log"
    parent, _, filename = name.rpartition("/")
    if filename in ("metadata.json", "COMPLETE"):
        _cache_path(parent)
        return "cache_metadata"
    if filename in RESULT_FILES and parent.startswith("run/tc2_gpu/results/"):
        _result_path(parent)
        return "published_result"
    if filename in ANALYSIS_FILES and parent.startswith("run/tc2_gpu/summaries/"):
        _analysis_path(parent)
        return "published_analysis"
    raise ValueError("File is outside the experiment export whitelist: " + name)


def _design(value):
    if not isinstance(value, dict) or value.get("schema_version") != "1.0" or value.get("workflow_id") != "tc2_gpu" or value.get("protocol_sha256") != PROTOCOL_SHA256:
        raise ValueError("Experiment configuration has a different protocol or format")
    if value.get("maximum_export_bytes") != LIMIT or value.get("maximum_results_per_page") != 4:
        raise ValueError("Experiment export bounds differ from the approved design")
    for field, group in (("scientific_source_hashes", "workflow"), ("pilot_source_hashes", "pilot")):
        rows = value.get(field)
        if not isinstance(rows, dict) or rows != current_source_hashes(ROOT, group):
            raise ValueError("Current source fingerprint set differs")
        for name, digest in rows.items():
            _relative(name); _hex(digest)
    if not MANIFESTS.issubset(value["scientific_source_hashes"]):
        raise ValueError("All eight frozen manifests must be fingerprinted")
    fits = value.get("fits")
    if not isinstance(fits, list) or len(fits) != 66:
        raise ValueError("Experiment matrix must identify exactly 66 fits")
    lookup = {}
    for item in fits:
        if not isinstance(item, dict) or set(item) != {"run_key", "configuration"}:
            raise ValueError("Invalid experiment fit fields")
        cfg, key = item["configuration"], item["run_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]+", key) or key in lookup or not key.endswith(_digest(cfg)[:12]):
            raise ValueError("Duplicate fit key or configuration fingerprint differs")
        if cfg.get("category") not in CATEGORIES.get(cfg.get("dataset"), ()):
            raise ValueError("Fit category is outside the approved eight categories")
        lookup[key] = cfg
    if sum(cfg["dataset"] == "mvtec_ad" for cfg in lookup.values()) != 62:
        raise ValueError("AD and LOCO fit counts differ")
    stages = value.get("stages")
    if not isinstance(stages, list) or [item.get("stage_id") for item in stages] != list(STAGES):
        raise ValueError("Experiment stage order differs")
    keys = []
    for position, stage in enumerate(stages):
        if stage.get("predecessor") != (STAGES[position - 1] if position else None):
            raise ValueError("Stage predecessor differs")
        if stage.get("kind") not in ("fit", "analysis"):
            raise ValueError("Unsupported stage kind")
        runs = stage.get("run_keys")
        if not isinstance(runs, list) or len(set(runs)) != len(runs) or any(key not in lookup for key in runs):
            raise ValueError("Invalid stage run keys")
        if stage["kind"] == "fit":
            if any(lookup[key]["stage"] != stage["stage_id"] for key in runs):
                raise ValueError("Fit is assigned to a different stage")
            keys.extend(runs)
        elif runs or stage.get("expected_rows") not in (18, 54, 36):
            raise ValueError("Analysis scope differs")
    if len(keys) != 66 or set(keys) != set(lookup):
        raise ValueError("Stage matrix is incomplete or repeats fits")
    return lookup, {item["stage_id"]: item for item in stages}


def _status(value, job_id, design):
    lookup, stages = _design(design)
    if not isinstance(value, dict) or value.get("job_id") != job_id or value.get("mode") != "formal_experiment_stage":
        raise ValueError("Experiment record belongs to another job or mode")
    stage_id = _stage_id(value.get("stage_id")); stage = stages[stage_id]
    if value.get("status") not in ("running", "passed", "failed") or type(value.get("stage_complete")) is not bool or type(value.get("step_7_complete")) is not bool:
        raise ValueError("Experiment state is invalid")
    if value["stage_complete"] != (value["status"] == "passed") or (value["step_7_complete"] and (not value["stage_complete"] or stage_id != STAGES[-1])):
        raise ValueError("Experiment completion state is inconsistent")
    results = value.get("results", [])
    if not isinstance(results, list) or len(results) > len(stage["run_keys"]):
        raise ValueError("Unexpected stage result count")
    seen, paths = set(), set()
    for row in results:
        if not isinstance(row, dict) or row.get("run_key") not in stage["run_keys"] or row["run_key"] in seen:
            raise ValueError("Unexpected or duplicate stage run key")
        path = _result_path(row.get("path"))
        if path in paths:
            raise ValueError("Duplicate published result identity")
        seen.add(row["run_key"]); paths.add(path)
        cfg = lookup[row["run_key"]]
        if any(row.get(key) != cfg[key] for key in ("method", "dataset", "category", "run_seed", "normal_train_n")):
            raise ValueError("Stage result differs from its configured fit")
        if value["stage_complete"] and (row.get("verified") is not True or row.get("run_status") not in ("completed", "skipped")):
            raise ValueError("Passed stage contains an unverified result")
    analyses = value.get("analyses", [])
    if not isinstance(analyses, list) or len(analyses) > (1 if stage["kind"] == "analysis" else 0):
        raise ValueError("Unexpected analysis records")
    for row in analyses:
        if row.get("stage_id", row.get("stage")) != stage_id or row.get("rows") != stage["expected_rows"] or row.get("status") != "passed":
            raise ValueError("Analysis record differs from the approved stage")
        if _analysis_path(row["path"]).split("/")[-2] != stage_id:
            raise ValueError("Analysis belongs to another stage")
    if value["stage_complete"] and (seen != set(stage["run_keys"]) or len(analyses) != (stage["kind"] == "analysis")):
        raise ValueError("Passed stage has incomplete results or analysis")
    caches = value.get("caches", [])
    if not isinstance(caches, list) or len(caches) > 8:
        raise ValueError("Unexpected cache records")
    cache_paths = [_cache_path(row.get("pathcanonical", row.get("path"))) for row in caches]
    if len(set(cache_paths)) != len(cache_paths):
        raise ValueError("Duplicate cache records")
    if value["step_7_complete"]:
        _chain_evidence(value, design)
    return value


def _chain_evidence(status, design):
    """Final completion binds all stages; earlier local collections remain evidence."""
    lookup, stages = _design(design)
    completed = status.get("completed_stages")
    if not isinstance(completed, list) or [row.get("stage_id") for row in completed] != list(STAGES):
        raise ValueError("Final completion requires all twelve ordered stages")
    observed = set()
    for entry in completed:
        stage = stages[entry["stage_id"]]
        _job(entry.get("job_id", ""))
        if entry.get("status") != "passed" or entry.get("stage_complete") is not True or entry.get("design_sha256") != status["design_sha256"]:
            raise ValueError("Final dependency evidence contains an incomplete stage")
        if entry["stage_id"] != STAGES[-1]:
            _hex(entry.get("status_sha256"))
        elif entry.get("job_id") != status["job_id"]:
            raise ValueError("Final dependency evidence belongs to another current job")
        rows = entry.get("results")
        if not isinstance(rows, list) or [row.get("run_key") for row in rows] != stage["run_keys"]:
            raise ValueError("Final dependency evidence omits or repeats configured fits")
        for row in rows:
            cfg = lookup[row["run_key"]]
            if row.get("verified") is not True or row.get("run_status") not in ("completed", "skipped") or any(row.get(key) != cfg[key] for key in ("method", "dataset", "category", "run_seed", "normal_train_n")):
                raise ValueError("Final dependency fit evidence differs")
            if _result_path(row["path"]).split("/")[-1] != _hex(row.get("identity_sha256")) or row["run_key"] in observed:
                raise ValueError("Final dependency result identity repeats or differs")
            observed.add(row["run_key"])
        analyses = entry.get("analyses")
        if not isinstance(analyses, list) or len(analyses) != (stage["kind"] == "analysis"):
            raise ValueError("Final dependency analysis evidence is incomplete")
        for row in analyses:
            if row.get("stage_id", row.get("stage")) != entry["stage_id"] or row.get("status") != "passed" or row.get("rows") != stage["expected_rows"] or _analysis_path(row["path"]).split("/")[-1] != _hex(row.get("identity_sha256")):
                raise ValueError("Final dependency analysis identity or rows differ")
    if len(observed) != 66 or observed != set(lookup):
        raise ValueError("Final dependency evidence does not identify 66 unique fits")
    expected = [{**row, "complete": True} for row in design["checkpoints"]]
    if status.get("checkpoints") != expected:
        raise ValueError("Final checkpoint evidence is incomplete")


def _verify_remote_dependencies(root, status, design, design_bytes):
    if not status.get("step_7_complete"):
        return
    for entry in status["completed_stages"]:
        job_id, stage_id = entry["job_id"], entry["stage_id"]
        pointer = _inside(root, "run/validation_tc2_gpu/last_experiments_" + stage_id + "_job.txt")
        if _read_bounded(pointer, 64).decode("ascii").strip() != job_id:
            raise ValueError("Final dependency is no longer the latest submitted stage")
        status_name = "run/validation_tc2_gpu/step7_job_" + job_id + "/setup_status.json"
        raw = _read_bounded(_inside(root, status_name), MAX_INDEX)
        if stage_id != STAGES[-1] and _bytes_sha(raw) != entry["status_sha256"]:
            raise ValueError("Final predecessor status fingerprint changed")
        value = _json(raw)
        if any(value.get(key) != entry.get(key) for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")):
            raise ValueError("Final dependency summary differs from its actual stage record")
        _status(value, job_id, design)
        common = {CONFIG: design_bytes, status_name: raw}
        for name in MANIFESTS:
            common[name] = _read_bounded(_inside(root, name), MAX_INDEX)
        for cache in value.get("caches", []):
            directory = cache.get("pathcanonical", cache.get("path"))
            for name in ("metadata.json", "COMPLETE"):
                common[directory + "/" + name] = _read_bounded(_inside(root, directory + "/" + name), MAX_INDEX)
        groups = [[row] for row in value.get("results", [])] or [[]]
        for group in groups:
            names = {row["path"] + "/" + name for row in group for name in RESULT_FILES}
            names.update(row["path"] + "/" + name for row in value.get("analyses", []) for name in ANALYSIS_FILES)
            files = {**common, **_read_files(root, names, "", None)}
            manifest = {"stage_id": stage_id, "snapshot_status": value, "snapshot_sha256": _digest(value),
                        "partial": False, "config_sha256": _bytes_sha(design_bytes),
                        "result_ids": [row["run_key"] for row in group],
                        "analysis_ids": [row.get("stage_id", row.get("stage")) for row in value.get("analyses", [])]}
            _semantic(files, job_id, manifest)


def _runtime(value, design, *, job_id=None):
    expected = design["expected_hardware"]
    if not isinstance(value, dict) or value.get("device") != "cuda" or any(value.get(key) != expected[key] for key in ("gpu", "driver", "cuda_build")):
        raise ValueError("Runtime differs from the accepted GPU hardware")
    if value.get("tf32") is not False or value.get("autocast") is not False or not value.get("software"):
        raise ValueError("Runtime precision or software evidence is missing")
    _job(value.get("slurm_job_id", ""))
    if job_id is not None and value["slurm_job_id"] != job_id:
        raise ValueError("Runtime belongs to another allocation")
    return {key: value[key] for key in ("gpu", "driver", "cuda_build")}


def _expected_samples(value, cfg):
    def normal(row, defect):
        return {"path": row["path"], "label": 0, "defect_type": defect, "mask_paths": []}
    fit = {row["path"]: row for row in value["fit_pool"]}
    return {"fit": [normal(fit[path], "") for path in value["runs"][str(cfg["run_seed"])][str(cfg["normal_train_n"])]],
            "dev": [normal(row, "") for row in value["dev"]],
            "test": [normal(row, "good") for row in value["test"]["good"]] +
                    [{"path": row["path"], "label": 1, "defect_type": row["defect_type"],
                      "mask_paths": [mask["path"] for mask in row["masks"]]} for row in value["test"]["anomalies"]]}


def _artifact_manifest(files, prefix, name, expected_names):
    lines = files[prefix + name].decode("utf-8").splitlines()
    seen = set()
    for line in lines:
        parts = line.split(None, 1)
        if len(parts) != 2 or parts[1] not in expected_names or parts[1] in seen or parts[0] != _bytes_sha(files[prefix + parts[1]]):
            raise ValueError("Published artifact fingerprint differs")
        seen.add(parts[1])
    if seen != set(expected_names):
        raise ValueError("Published artifact manifest is incomplete")


def _semantic(files, job_id, manifest):
    if CONFIG not in files:
        raise ValueError("Every experiment page must contain its configuration")
    design = _json(files[CONFIG]); lookup, stages = _design(design)
    status_name = "run/validation_tc2_gpu/step7_job_" + job_id + "/setup_status.json"
    status = _status(_json(files[status_name]), job_id, design) if status_name in files else None
    snapshot = status or {"job_id": job_id, "status": "missing", "stage_id": manifest.get("stage_id"), "stage_complete": False, "step_7_complete": False}
    if manifest.get("snapshot_status") != snapshot or manifest.get("snapshot_sha256") != _digest(snapshot) or manifest.get("partial") is not (not snapshot["stage_complete"]):
        raise ValueError("Page state differs from its frozen job snapshot")
    if manifest.get("config_sha256") != _bytes_sha(files[CONFIG]):
        raise ValueError("Page configuration fingerprint differs")
    if status is not None and status.get("design_sha256") != _bytes_sha(files[CONFIG]):
        raise ValueError("Job configuration differs from its exported design")
    selected = manifest.get("result_ids")
    analyses_selected = manifest.get("analysis_ids")
    if not isinstance(selected, list) or len(selected) > 4 or len(set(selected)) != len(selected) or not isinstance(analyses_selected, list) or len(set(analyses_selected)) != len(analyses_selected):
        raise ValueError("Page selection count differs")
    expected_names = {name for name in files if _role(name, job_id) in ("experiment_configuration", "experiment_record", "phase_log", "slurm_log", "frozen_manifest")}
    frozen = {}
    for name in set(files) & MANIFESTS:
        if _bytes_sha(files[name]) != design["scientific_source_hashes"][name]:
            raise ValueError("Frozen manifest fingerprint differs")
        value = _json(files[name]); frozen[(value["dataset"], value["category"])] = value
    if status is None:
        if selected or analyses_selected or any(_role(name, job_id) not in ("experiment_configuration", "slurm_log") for name in files):
            raise ValueError("Queued snapshot may contain only configuration and SLURM logs")
        return snapshot
    if status["stage_complete"]:
        sources = status.get("experiment_sources")
        if not isinstance(sources, dict) or set(sources) != EXPERIMENT_SOURCES:
            raise ValueError("Passed stage is missing its seven source fingerprints")
        for name, fingerprint in sources.items():
            _relative(name); _hex(fingerprint)
        if stages[status["stage_id"]]["kind"] == "fit":
            _runtime(status.get("runtime"), design, job_id=job_id)
    cache_by_id = {}
    for row in status.get("caches", []):
        directory = row.get("pathcanonical", row.get("path")); prefix = directory + "/"
        available = {prefix + "metadata.json", prefix + "COMPLETE"} & set(files)
        if not available:
            continue
        if len(available) != 2:
            raise ValueError("Cache metadata and completion marker must travel together")
        expected_names.update(available)
        meta = _json(files[prefix + "metadata.json"]); complete = _json(files[prefix + "COMPLETE"])
        identity = meta["identity"]; identifier = _digest(identity)
        if directory.split("/")[-1] != identifier or meta.get("cache_id") != identifier:
            raise ValueError("Cache path differs from its identity")
        if complete != {"status": "complete", "cache_id": identifier, "metadata_sha256": _bytes_sha(files[prefix + "metadata.json"])}:
            raise ValueError("Cache completion marker differs")
        for key, expected in {"namespace": "formal", "protocol_sha256": PROTOCOL_SHA256,
                              "dtype": "float32", "format": "tc2_gpu_fp32_npy_1"}.items():
            if identity.get(key) != expected:
                raise ValueError("Cache identity differs at " + key)
        dataset, category = identity.get("dataset"), identity.get("category")
        if (dataset, category) not in frozen:
            raise ValueError("Cache is missing its frozen manifest")
        source = frozen[(dataset, category)]
        manifest_name = "manifests/manifest_" + dataset + "_" + category + ".json"
        if identity.get("manifest_sha256") != design["scientific_source_hashes"][manifest_name] or identity.get("split_hash") != source["split_hash"]:
            raise ValueError("Cache manifest or split fingerprint differs")
        images = [{"path": item["path"], "sha256": item["sha256"]} for item in source["dev"] + source["fit_pool"] + source["test"]["good"] + source["test"]["anomalies"]]
        if identity.get("images") != images or [item["path"] for item in meta["index"]] != [item["path"] for item in images]:
            raise ValueError("Cache image order differs from its frozen manifest")
        count = len(images)
        shapes = {"layer1": [count, 64, 64, 64], "layer2": [count, 128, 32, 32], "layer3": [count, 256, 16, 16]}
        if set(meta["layers"]) != set(shapes):
            raise ValueError("Cache must contain all three FP32 raw layers")
        for name, shape in shapes.items():
            layer = meta["layers"][name]
            if set(layer) != {"dtype", "shape", "sha256"} or layer["dtype"] != "float32" or layer["shape"] != shape:
                raise ValueError("Cache layer precision or dimensions differ")
            _hex(layer["sha256"])
        fingerprint = {"cache_id": identifier, "metadata_sha256": complete["metadata_sha256"], "layer_hashes": {name: item["sha256"] for name, item in meta["layers"].items()}}
        if identity.get("extraction_sources") != {name: design["scientific_source_hashes"][name] for name in CACHE_SOURCES}:
            raise ValueError("Cache extraction code differs from accepted scientific sources")
        if row.get("identity") != identity or any(row.get(key) != fingerprint[key] for key in ("metadata_sha256", "layer_hashes")):
            raise ValueError("Stage cache evidence differs from published metadata")
        cache_by_id[identifier] = (identity, fingerprint, source, {item["path"]: item["orig_hw"] for item in meta["index"]})
    records = {row["run_key"]: row for row in status.get("results", [])}
    if any(key not in records for key in selected):
        raise ValueError("Page references a result absent from its snapshot")
    for key in selected:
        row = records[key]; prefix = row["path"] + "/"
        names = {prefix + name for name in RESULT_FILES}
        if not names.issubset(files):
            raise ValueError("A page may not split or omit published result artifacts")
        expected_names.update(names)
        cfg = _json(files[prefix + "config.yaml"])
        if cfg != lookup[key]:
            raise ValueError("Published effective configuration differs from its frozen fit")
        evidence = _json(files[prefix + "evidence.json"]); identity = evidence["identity"]; identifier = _digest(identity)
        if identity.get("namespace") != "formal" or identity.get("protocol_sha256") != PROTOCOL_SHA256 or identity.get("configuration") != cfg or identifier != row["path"].split("/")[-1] or row.get("identity_sha256") != identifier:
            raise ValueError("Published result identity differs")
        if identity.get("sources") != {name: design["scientific_source_hashes"][name] for name in SCIENCE_SOURCES}:
            raise ValueError("Published result differs from accepted scientific source fingerprints")
        cache_id = identity["cache"]["cache_id"]
        if cache_id not in cache_by_id:
            raise ValueError("Published result is missing its referenced cache metadata")
        cache_identity, fingerprint, frozen_manifest, original_sizes = cache_by_id[cache_id]
        if identity["cache"] != fingerprint or evidence.get("cache_identity") != cache_identity:
            raise ValueError("Published result cache evidence differs")
        raw = _digest({"images": cache_identity["images"], "masks": [mask for item in frozen_manifest["test"]["anomalies"] for mask in item["masks"]]})
        if identity.get("manifest_sha256") != cache_identity["manifest_sha256"] or identity.get("split_hash") != frozen_manifest["split_hash"] or identity.get("raw_inputs_sha256") != raw:
            raise ValueError("Published result frozen input identity differs")
        hardware = _runtime(evidence.get("runtime"), design)
        if identity.get("hardware") != hardware or identity.get("software") != evidence["runtime"]["software"] or identity["software"] != cache_identity.get("software") or cache_identity.get("hardware") != hardware:
            raise ValueError("Result, cache and runtime identities differ")
        if stages[status["stage_id"]]["kind"] == "fit" and identity["software"] != status["runtime"]["software"]:
            raise ValueError("Result software differs from its stage runtime")
        success = _json(files[prefix + "SUCCESS"])
        if success != {"status": "passed", "namespace": "formal", "identity_sha256": identifier, "artifacts_sha256": _bytes_sha(files[prefix + "artifacts.sha256"])}:
            raise ValueError("Published result completion marker differs")
        _artifact_manifest(files, prefix, "artifacts.sha256", ARTIFACTS)
        if _json(files[prefix + "validation.json"]) != {"status": "passed", "identity_sha256": identifier, "metric_abs_tolerance": 1e-12, "prediction_dtype": "float32", "saved_metric_reproduction": True}:
            raise ValueError("Published result has not passed FP32 prediction and metric validation")
        samples = _json(files[prefix + "samples.json"])
        if _digest(samples) != identity.get("samples_sha256") or set(samples) != {"fit", "dev", "test"}:
            raise ValueError("Result sample fingerprint differs")
        expected_samples = _expected_samples(frozen_manifest, cfg)
        for role in expected_samples:
            actual = samples[role]
            if len(actual) != len(expected_samples[role]):
                raise ValueError("Result sample counts differ from the frozen manifest")
            for item, expected in zip(actual, expected_samples[role]):
                if set(item) != {*expected, "orig_hw"} or any(item[name] != value for name, value in expected.items()) or not isinstance(item["orig_hw"], list) or len(item["orig_hw"]) != 2 or any(type(n) is not int or n < 1 for n in item["orig_hw"]):
                    raise ValueError("Result sample order, labels, masks or original dimensions differ")
                if item["orig_hw"] != original_sizes[item["path"]]:
                    raise ValueError("Result original dimensions differ from its cache index")
        metrics = _json(files[prefix + "metrics.json"])
        if set(metrics) != {"image", "pixel", "metric_policy"} or set(metrics["image"]) != RULES or metrics["metric_policy"] != METRIC_POLICY:
            raise ValueError("Saved result metric policy or five image rules differ")
        if set(metrics["pixel"]) != {"pixel_auroc", "pixel_ap", "n_pixels", "n_positive_pixels"} or metrics["pixel"]["n_pixels"] != sum(item["orig_hw"][0] * item["orig_hw"][1] for item in samples["test"]):
            raise ValueError("Saved result pixel scope differs from original test dimensions")
    analysis_records = {row.get("stage_id", row.get("stage")): row for row in status.get("analyses", [])}
    if any(key not in analysis_records for key in analyses_selected):
        raise ValueError("Page references an analysis absent from its snapshot")
    for key in analyses_selected:
        row = analysis_records[key]; prefix = row["path"] + "/"
        names = {prefix + name for name in ANALYSIS_FILES}
        if not names.issubset(files):
            raise ValueError("Published analysis files must travel together")
        expected_names.update(names)
        _artifact_manifest(files, prefix, "analysis.sha256", ("analysis.json", "analysis.csv", "evidence.json"))
        evidence = _json(files[prefix + "evidence.json"])
        identity = evidence.get("identity"); identifier = _digest(identity)
        if identifier != row["path"].split("/")[-1] or row.get("identity_sha256") != identifier:
            raise ValueError("Published analysis identity differs")
        result = _json(files[prefix + "analysis.json"]); stage = stages[key]
        sources = identity.get("sources")
        if (identity.get("namespace") != "formal" or identity.get("protocol_sha256") != PROTOCOL_SHA256
                or identity.get("stage") != key or result.get("stage") != key or result.get("identity_sha256") != identifier
                or identity.get("score_rules") != stage["score_rules"] or result.get("score_rules") != stage["score_rules"]
                or result.get("row_count") != stage["expected_rows"] or result.get("row_count") != len(result.get("rows", []))
                or result.get("source_count") != len(stage["source_run_keys"]) or not isinstance(sources, list)
                or [source.get("run_key") for source in sources] != stage["source_run_keys"]
                or identity.get("metric_policy") != METRIC_POLICY or result.get("metric_policy") != METRIC_POLICY
                or identity.get("image_metric_abs_tolerance") != 1e-12 or identity.get("rows_sha256") != _digest(result["rows"])):
            raise ValueError("Published analysis scope, rules, row counts or source identities differ")
        expected_sources = {"scripts/tc2_gpu/experiments/analyze_scores.py": status["experiment_sources"]["scripts/tc2_gpu/experiments/analyze_scores.py"],
                            CONFIG: _bytes_sha(files[CONFIG]), "src/metric_core.py": design["scientific_source_hashes"]["src/metric_core.py"],
                            "src/tc2_gpu_protocol.py": design["scientific_source_hashes"]["src/tc2_gpu_protocol.py"]}
        if identity.get("analysis_sources") != expected_sources:
            raise ValueError("Analysis source fingerprints differ from the accepted stage")
        for source in sources:
            if _result_path(source["path"]).split("/")[-1] != source.get("identity_sha256") or source.get("configuration") != lookup[source["run_key"]] or set(source.get("artifact_hashes", {})) != set(ARTIFACTS):
                raise ValueError("Analysis source provenance differs")
            for fingerprint in [source["artifacts_sha256"], *source["artifact_hashes"].values()]:
                _hex(fingerprint)
        if [(item.get("run_key"), item.get("score_rule")) for item in result["rows"]] != [(run, rule) for run in stage["source_run_keys"] for rule in stage["score_rules"]]:
            raise ValueError("Analysis rows repeat, omit or reorder configured run/rule pairs")
        if evidence.get("validation") != {"source_artifacts_verified": True, "image_metrics_recomputed": True,
                "image_metric_abs_tolerance": 1e-12, "pixel_metrics_recomputed": False, "feature_arrays_loaded": False} or evidence.get("runtime", {}).get("device") != "cpu":
            raise ValueError("Analysis validation or CPU runtime evidence differs")
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for item in result["rows"]:
            csv_row = dict(item)
            for field in ("per_defect_recall", "pixel_metrics_reference"):
                csv_row[field] = json.dumps(csv_row[field], sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
            writer.writerow(csv_row)
        if files[prefix + "analysis.csv"].decode("utf-8") != output.getvalue():
            raise ValueError("Analysis CSV differs from structured rows")
        marker = _json(files[prefix + "SUCCESS"])
        if marker != {"status": "passed", "namespace": "formal", "identity_sha256": identifier, "analysis_manifest_sha256": _bytes_sha(files[prefix + "analysis.sha256"])}:
            raise ValueError("Published analysis completion marker differs")
    if expected_names != set(files):
        raise ValueError("Page contains unreferenced or unexpected artifacts")
    return snapshot


def _tar_size(files, manifest):
    values = [(MANIFEST, _encode(manifest)), *files.items()]
    total = sum(512 + ((len(data) + 511) // 512) * 512 for _, data in values) + 1024
    return ((total + 10239) // 10240) * 10240


def _read_files(root, names, status_name, status_bytes):
    files, total = {}, 0
    for name in sorted(names):
        path = _inside(root, name)
        if not path.is_file() or path.stat().st_size > LIMIT - total:
            raise ValueError("Missing source or page exceeds the 512 MiB limit")
        data = status_bytes if name == status_name else _read_bounded(path, LIMIT - total)
        total += len(data); files[name] = data
    return files


def _write_page(path, files, manifest):
    if _tar_size(files, manifest) > LIMIT:
        raise ValueError("Page exceeds the 512 MiB decompressed limit")
    temporary = path.with_name("." + path.name + ".partial." + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.USTAR_FORMAT) as package:
                for name, data in [(MANIFEST, _encode(manifest)), *files.items()]:
                    item = tarfile.TarInfo(name); item.size, item.mode = len(data), 0o600
                    package.addfile(item, io.BytesIO(data))
            stream.flush(); os.fsync(stream.fileno())
        if temporary.stat().st_size > LIMIT:
            raise ValueError("Page exceeds the 512 MiB compressed limit")
        digest = _sha(temporary); _atomic_publish(temporary, path)
        return digest
    finally:
        if temporary.exists():
            temporary.unlink()


def export_pages(root, job_id, directory, stage_id=None):
    job_id = _job(job_id)
    if stage_id is not None:
        _stage_id(stage_id)
    if not Path(directory).is_absolute():
        raise ValueError("Export directory must be absolute")
    root, directory = _extended(root), _extended(directory)
    _no_links(root); _no_links(directory)
    if not root.is_dir() or directory.exists() or not directory.parent.is_dir():
        raise ValueError("Export requires an existing root and parent, and a fresh directory")
    relative_directory = directory.relative_to(root).as_posix()
    if not re.fullmatch(r"tmp/experiments-" + job_id + r"-[A-Za-z0-9_-]{1,96}", relative_directory):
        raise ValueError("Export directory must be a fresh job-specific directory below root/tmp")
    design_bytes = _read_bounded(_inside(root, CONFIG), MAX_INDEX)
    design = _json(design_bytes); _design(design)
    prefix = "run/validation_tc2_gpu/step7_job_" + job_id + "/"
    status_name = prefix + "setup_status.json"; status_path = _inside(root, status_name)
    status_bytes = _read_bounded(status_path, MAX_INDEX) if status_path.is_file() else None
    status = _status(_json(status_bytes), job_id, design) if status_bytes is not None else None
    if status is not None:
        if stage_id is not None and stage_id != status["stage_id"]:
            raise ValueError("Requested stage differs from the job snapshot")
        stage_id = status["stage_id"]
        _verify_remote_dependencies(root, status, design, design_bytes)
    snapshot = status or {"job_id": job_id, "status": "missing", "stage_id": stage_id, "stage_complete": False, "step_7_complete": False}
    common = {CONFIG}
    for suffix in (".out", ".err"):
        name = "run/validation_tc2_gpu/slurm-" + job_id + suffix
        if _inside(root, name).is_file():
            common.add(name)
    results, analyses = [], []
    if status is not None:
        for path in status_path.parent.iterdir():
            if path.name in JOB_FILES or PHASE.fullmatch(path.name):
                _no_links(path)
                if path.is_file():
                    common.add(prefix + path.name)
        common.update(MANIFESTS)
        for row in status.get("caches", []):
            path = row.get("pathcanonical", row.get("path"))
            if _inside(root, path + "/COMPLETE").is_file():
                common.update(path + "/" + name for name in ("metadata.json", "COMPLETE"))
        for row in status.get("results", []):
            if _inside(root, row["path"] + "/SUCCESS").is_file():
                results.append(row)
            elif status["stage_complete"]:
                raise ValueError("Passed stage has a missing result completion marker")
        for row in status.get("analyses", []):
            if _inside(root, row["path"] + "/SUCCESS").is_file():
                analyses.append(row)
            elif status["stage_complete"]:
                raise ValueError("Passed stage has a missing analysis completion marker")
    common_bytes = _read_files(root, common, status_name, status_bytes)
    common_bytes[CONFIG] = design_bytes
    groups = []
    for dataset, categories in CATEGORIES.items():
        for category in categories:
            selected = [row for row in results if (row["dataset"], row["category"]) == (dataset, category)]
            while selected:
                group = []
                size = sum(len(data) for data in common_bytes.values()) + 2 * 1024 * 1024
                while selected and len(group) < 4:
                    row = selected[0]
                    result_size = sum(_inside(root, row["path"] + "/" + name).stat().st_size for name in RESULT_FILES)
                    if size + result_size > LIMIT:
                        if not group:
                            raise ValueError("A complete result exceeds the unchanged 512 MiB page limit")
                        break
                    group.append(selected.pop(0)); size += result_size
                groups.append(group)
    if not groups:
        groups = [[]]
    if len(groups) > MAX_PAGES:
        raise ValueError("Collection exceeds the 32-page bound")
    directory.mkdir()
    export_id = uuid.uuid4().hex.upper(); created = datetime.now(timezone.utc).isoformat()
    whole_results = [row["run_key"] for row in results]
    whole_analyses = [row.get("stage_id", row.get("stage")) for row in analyses]
    pages = []
    for number, group in enumerate(groups, 1):
        names = set()
        for row in group:
            names.update(row["path"] + "/" + name for name in RESULT_FILES)
        for row in analyses:
            names.update(row["path"] + "/" + name for name in ANALYSIS_FILES)
        files = {**common_bytes, **_read_files(root, names, status_name, status_bytes)}
        if len(files) >= MAX_MEMBERS:
            raise ValueError("Page contains too many source files")
        rows = [{"path": name, "size": len(data), "sha256": _bytes_sha(data), "role": _role(name, job_id)} for name, data in sorted(files.items())]
        manifest = {"schema_version": "1.0", "export_id": export_id, "job_id": job_id,
                    "stage_id": stage_id, "page_number": number, "page_count": len(groups),
                    "result_ids": [row["run_key"] for row in group], "analysis_ids": whole_analyses,
                    "whole_result_ids": whole_results, "whole_analysis_ids": whole_analyses,
                    "snapshot_status": snapshot, "snapshot_sha256": _digest(snapshot),
                    "config_sha256": _bytes_sha(design_bytes), "partial": not snapshot["stage_complete"],
                    "created_utc": created, "files": rows,
                    "validation_scope": {"cache_array_bytes_downloaded": False, "prediction_arrays_loaded_locally": False}}
        _semantic(files, job_id, manifest)
        name = "page_" + f"{number:03d}" + ".tar.gz"
        path = directory / name; digest = _write_page(path, files, manifest)
        pages.append({"name": name, "sha256": digest, "bytes": path.stat().st_size,
                      "page_number": number, "result_ids": manifest["result_ids"], "analysis_ids": whole_analyses})
    index = {"schema_version": "1.0", "export_id": export_id, "job_id": job_id, "stage_id": stage_id,
             "page_count": len(pages), "pages": pages, "whole_result_ids": whole_results,
             "whole_analysis_ids": whole_analyses, "snapshot_status": snapshot,
             "snapshot_sha256": _digest(snapshot), "config_sha256": _bytes_sha(design_bytes),
             "partial": not snapshot["stage_complete"], "created_utc": created}
    _validate_index(index, job_id)
    index_path = directory / "index.json"
    with index_path.open("xb") as stream:
        stream.write(_encode(index)); stream.flush(); os.fsync(stream.fileno())
    return {"job_id": job_id, "directory": _plain(directory), "index_path": _plain(index_path),
            "index_sha256": _sha(index_path), "pages": pages, "page_count": len(pages),
            "partial": index["partial"], "stage_id": stage_id,
            "stage_complete": snapshot["stage_complete"], "step_7_complete": snapshot["step_7_complete"]}


def _validate_index(index, job_id):
    if not isinstance(index, dict) or index.get("schema_version") != "1.0" or index.get("job_id") != job_id or not re.fullmatch(r"[0-9A-F]{32}", index.get("export_id", "")):
        raise ValueError("Collection index job, format or export identity differs")
    if index.get("stage_id") is not None:
        _stage_id(index["stage_id"])
    snapshot = index.get("snapshot_status")
    if not isinstance(snapshot, dict) or snapshot.get("job_id") != job_id or snapshot.get("stage_id") != index.get("stage_id") or snapshot.get("status") not in ("running", "passed", "failed", "missing"):
        raise ValueError("Collection snapshot is invalid")
    if type(snapshot.get("stage_complete")) is not bool or type(snapshot.get("step_7_complete")) is not bool or snapshot["stage_complete"] != (snapshot["status"] == "passed") or index.get("partial") is not (not snapshot["stage_complete"]) or index.get("snapshot_sha256") != _digest(snapshot):
        raise ValueError("Collection completion state differs")
    _hex(index.get("config_sha256"))
    pages = index.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES or type(index.get("page_count")) is not int or index["page_count"] != len(pages):
        raise ValueError("Collection page count differs")
    all_results, total = [], 0
    for number, page in enumerate(pages, 1):
        if not isinstance(page, dict) or set(page) != {"name", "sha256", "bytes", "page_number", "result_ids", "analysis_ids"} or page["name"] != f"page_{number:03d}.tar.gz" or page["page_number"] != number:
            raise ValueError("Collection pages must have canonical consecutive names")
        _hex(page["sha256"])
        if type(page["bytes"]) is not int or not 0 < page["bytes"] <= LIMIT:
            raise ValueError("Collection compressed page size exceeds its bound")
        total += page["bytes"]
        if not isinstance(page["result_ids"], list) or len(page["result_ids"]) > 4 or any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]+", key) for key in page["result_ids"]):
            raise ValueError("Collection page result selection differs")
        if page["analysis_ids"] != index.get("whole_analysis_ids"):
            raise ValueError("Collection analysis selection differs")
        all_results.extend(page["result_ids"])
    whole_results, whole_analyses = index.get("whole_result_ids"), index.get("whole_analysis_ids")
    if not isinstance(whole_results, list) or not isinstance(whole_analyses, list) or len(set(whole_analyses)) != len(whole_analyses) or any(key not in ("I1_seed17", "I1_all_seeds", "I2") for key in whole_analyses):
        raise ValueError("Collection global selection is invalid")
    if total > 16 * 1024**3 or len(set(all_results)) != len(all_results) or set(all_results) != set(whole_results) or len(all_results) != len(whole_results):
        raise ValueError("Collection repeats or omits result identities, or exceeds its total bound")
    return index


def _index(path, job_id):
    path = _extended(path); _no_links(path)
    return _validate_index(_json(_read_bounded(path, MAX_INDEX)), _job(job_id))


def verify_index(path, expected_sha, job_id):
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", str(expected_sha)) or _sha(path) != expected_sha.upper():
        raise ValueError("Collection index SHA256 differs")
    index = _index(path, job_id)
    return {"status": "verified", "job_id": job_id, "stage_id": index["stage_id"],
            "index_sha256": _sha(path), "page_count": index["page_count"], "pages": index["pages"],
            "partial": index["partial"], "stage_complete": False, "step_7_complete": False,
            "remote_stage_complete": index["snapshot_status"]["stage_complete"]}


def _check_page(files, manifest, index, page, job_id):
    fields = ("schema_version", "export_id", "job_id", "stage_id", "page_count", "whole_result_ids",
              "whole_analysis_ids", "snapshot_status", "snapshot_sha256", "config_sha256", "partial", "created_utc")
    if any(manifest.get(key) != index.get(key) for key in fields) or any(manifest.get(key) != page[key] for key in ("page_number", "result_ids", "analysis_ids")):
        raise ValueError("Page belongs to another snapshot, index or selection")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != len(files):
        raise ValueError("Page manifest file count differs")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256", "role"}:
            raise ValueError("Page artifact record fields differ")
        name = _relative(row["path"])
        if name not in files or name in seen or row["role"] != _role(name, job_id) or type(row["size"]) is not int or row["size"] != len(files[name]) or row["sha256"] != _bytes_sha(files[name]):
            raise ValueError("Page file hash, size or role differs")
        seen.add(name)
    if seen != set(files):
        raise ValueError("Page manifest does not identify every member")
    return _semantic(files, job_id, manifest)


def verify_archive(archive, expected_sha, job_id, destination, index_path):
    job_id = _job(job_id); archive, destination = _extended(archive), _extended(destination)
    _no_links(archive); _no_links(destination)
    index = _index(index_path, job_id)
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", str(expected_sha)):
        raise ValueError("Expected archive SHA256 is invalid")
    pages = [page for page in index["pages"] if page["sha256"] == expected_sha.upper()]
    if len(pages) != 1:
        raise ValueError("Archive fingerprint does not identify exactly one index page")
    page = pages[0]
    if not archive.is_file() or archive.stat().st_size != page["bytes"] or _sha(archive) != expected_sha.upper():
        raise ValueError("Page archive size or SHA256 differs")
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Extraction requires a fresh destination with an existing parent")
    files, observed, total = {}, set(), 0
    with tempfile.TemporaryFile(dir=archive.parent) as raw:
        length = 0
        with gzip.open(archive, "rb") as compressed:
            while True:
                block = compressed.read(min(1024 * 1024, LIMIT - length + 1))
                if not block:
                    break
                length += len(block)
                if length > LIMIT:
                    raise ValueError("Page exceeds the 512 MiB decompressed bound")
                raw.write(block)
        raw.seek(0); _tar_layout(raw, length)
        with tarfile.open(fileobj=raw, mode="r:") as package:
            for item in package:
                name = _relative(item.name)
                if name.casefold() in {value.casefold() for value in observed} or len(observed) >= MAX_MEMBERS or not item.isfile() or item.pax_headers or item.size < 0 or item.size > LIMIT - total:
                    raise ValueError("Duplicate, unsafe or oversized page member")
                observed.add(name)
                if name != MANIFEST:
                    _role(name, job_id)
                total += item.size; stream = package.extractfile(item)
                if stream is None:
                    raise ValueError("Unreadable page member")
                data = stream.read(item.size + 1)
                if len(data) != item.size:
                    raise ValueError("Page member length differs")
                files[name] = data
    if MANIFEST not in files:
        raise ValueError("Page manifest is absent")
    manifest_bytes = files.pop(MANIFEST); manifest = _json(manifest_bytes)
    snapshot = _check_page(files, manifest, index, page, job_id)
    destination.mkdir()
    for name, data in [(MANIFEST, manifest_bytes), *files.items()]:
        path = _inside(destination, name); path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        if _sha(path) != _bytes_sha(data):
            raise ValueError("Extracted bytes differ from verified source")
    receipt = {"status": "verified", "job_id": job_id, "export_id": index["export_id"],
               "index_sha256": _sha(index_path), "archive_sha256": page["sha256"],
               "page_number": page["page_number"], "file_count": len(files),
               "manifest_sha256": _bytes_sha(manifest_bytes), "stage_complete": False, "step_7_complete": False}
    with (destination / RECEIPT).open("xb") as stream:
        stream.write(_encode(receipt))
    return {**receipt, "destination": _plain(destination), "stage_id": index["stage_id"],
            "partial": index["partial"], "remote_stage_complete": snapshot["stage_complete"],
            "cache_array_bytes_downloaded": False, "prediction_arrays_loaded_locally": False}


def verify_collection(index_path, directory, job_id):
    job_id = _job(job_id); index = _index(index_path, job_id); directory = _extended(directory)
    _no_links(directory)
    for page in index["pages"]:
        page_directory = _inside(directory, "page_" + f"{page['page_number']:03d}")
        manifest_path = _inside(page_directory, MANIFEST); receipt_path = _inside(page_directory, RECEIPT)
        receipt = _json(_read_bounded(receipt_path, MAX_INDEX))
        if receipt.get("status") != "verified" or receipt.get("job_id") != job_id or receipt.get("export_id") != index["export_id"] or receipt.get("index_sha256") != _sha(index_path) or receipt.get("archive_sha256") != page["sha256"] or receipt.get("page_number") != page["page_number"]:
            raise ValueError("Collection page has no matching verification receipt")
        manifest_bytes = _read_bounded(manifest_path, MAX_INDEX)
        if receipt.get("manifest_sha256") != _bytes_sha(manifest_bytes):
            raise ValueError("Collection page manifest differs from verified bytes")
        manifest = _json(manifest_bytes)
        names = [row["path"] for row in manifest["files"]]
        files = _read_files(page_directory, names, "", None)
        actual = {path.relative_to(page_directory).as_posix() for path in page_directory.rglob("*") if path.is_file()}
        if actual != set(names) | {MANIFEST, RECEIPT}:
            raise ValueError("Extracted collection page contains missing or extra files")
        _check_page(files, manifest, index, page, job_id)
    snapshot = index["snapshot_status"]
    if snapshot["stage_complete"]:
        keys = [row["run_key"] for row in snapshot.get("results", [])]
        analyses = [row.get("stage_id", row.get("stage")) for row in snapshot.get("analyses", [])]
        if set(keys) != set(index["whole_result_ids"]) or len(keys) != len(index["whole_result_ids"]) or analyses != index["whole_analysis_ids"]:
            raise ValueError("Completed collection does not contain every published stage result")
    return {"status": "verified", "job_id": job_id, "stage_id": index["stage_id"],
            "index_sha256": _sha(index_path), "page_count": index["page_count"],
            "result_count": len(index["whole_result_ids"]), "analysis_count": len(index["whole_analysis_ids"]),
            "partial": index["partial"], "stage_complete": snapshot["stage_complete"],
            "step_7_complete": snapshot["step_7_complete"],
            "completion_scope": "current_stage_and_remote_dependency_evidence",
            "cache_array_bytes_downloaded": False, "prediction_arrays_loaded_locally": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("export")
    export.add_argument("--root", required=True); export.add_argument("--job-id", required=True)
    export.add_argument("--directory", required=True); export.add_argument("--stage")
    verify = commands.add_parser("verify")
    for argument in ("archive", "sha256", "job-id", "destination", "index"):
        verify.add_argument("--" + argument, required=True)
    index = commands.add_parser("verify-index")
    for argument in ("index", "sha256", "job-id"):
        index.add_argument("--" + argument, required=True)
    collection = commands.add_parser("verify-collection")
    for argument in ("index", "directory", "job-id"):
        collection.add_argument("--" + argument, required=True)
    args = parser.parse_args()
    if args.action == "export":
        result = export_pages(args.root, args.job_id, args.directory, args.stage)
    elif args.action == "verify":
        result = verify_archive(args.archive, args.sha256, args.job_id, args.destination, args.index)
    elif args.action == "verify-index":
        result = verify_index(args.index, args.sha256, args.job_id)
    else:
        result = verify_collection(args.index, args.directory, args.job_id)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
