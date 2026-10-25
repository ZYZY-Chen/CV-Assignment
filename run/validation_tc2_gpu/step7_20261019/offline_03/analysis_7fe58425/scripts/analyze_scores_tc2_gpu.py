"""Verify formal PatchCore scores and publish immutable, per-run I1/I2 analyses.

The analysis is CPU-only: saved image scores are evaluated with metric_core.
Pixel metrics remain references to the previously validated result artifacts.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import uuid
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metric_core import METRIC_POLICY_VERSION, binary_auroc_ap, binary_inputs, finite_scores
import tc2_gpu_protocol as p

DESIGN_FILE = "configs/experiments_tc2_gpu.json"
ANALYSIS_FILE = "scripts/analyze_scores_tc2_gpu.py"
ANALYSIS_ARTIFACTS = ("analysis.json", "analysis.csv", "evidence.json")
RESULT_ARTIFACTS = ("config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json")
METRIC_POLICY = {"version": METRIC_POLICY_VERSION, "ties": "equal-score threshold groups",
                 "threshold_percentile": 95.0, "percentile_method": "linear", "decision": "score > threshold",
                 "pixel_scope": "all pixels at original resolution"}
STAGE_RULES = {"I1_seed17": ("native", "max", "top_0.01"),
               "I1_all_seeds": ("native", "max", "top_0.01"),
               "I2": ("top_0.001", "top_0.05")}
CSV_FIELDS = ("stage", "run_key", "dataset", "category", "method", "run_seed", "score_rule",
              "n_dev", "n_good", "n_anomaly", "image_auroc", "image_ap", "threshold_95pct",
              "normal_fpr", "anomaly_recall", "per_defect_recall", "delta_image_auroc_vs_native",
              "delta_image_ap_vs_native", "delta_normal_fpr_vs_native", "delta_anomaly_recall_vs_native",
              "result_path", "result_identity_sha256", "pixel_metrics_reference")


def local_path(path):
    """Use extended Windows paths for reads of deeply nested downloaded evidence."""
    path = Path(path).absolute()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(path))
    return path


def read(path):
    return json.loads(local_path(path).read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with local_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def _write(path, value):
    with local_path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n")


def _identifier(value):
    if not isinstance(value, str) or re.fullmatch("[0-9A-F]{64}", value) is None:
        raise ValueError("Require an uppercase SHA256 identity")
    return value


def _relative_directory(root, directory):
    root, directory = Path(root).absolute(), Path(directory).absolute()
    relative = directory.relative_to(root).as_posix()
    p.inside(root, relative)
    return relative


def _manifest(directory, name, artifacts):
    rows = local_path(directory / name).read_text(encoding="utf-8").splitlines()
    observed = {}
    for row in rows:
        value, member = row.split(None, 1)
        _identifier(value)
        if member not in artifacts or member in observed or sha(p.inside(directory, member)) != value:
            raise ValueError("Artifact manifest contains a duplicate, unknown or changed file")
        observed[member] = value
    if len(rows) != len(artifacts) or set(observed) != set(artifacts):
        raise ValueError("Artifact manifest is incomplete")
    return observed


def _compare(expected, actual):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            raise ValueError("Saved image metric fields differ")
        for key in expected:
            _compare(expected[key], actual[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            raise ValueError("Saved image metric lists differ")
        for left, right in zip(expected, actual):
            _compare(left, right)
    elif isinstance(expected, float):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(expected - actual) > 1e-12:
            raise ValueError("Saved image metrics differ by more than absolute 1e-12")
    elif type(expected) is not type(actual) or expected != actual:
        raise ValueError("Saved image metric metadata differs")


def image_metrics(labels, test_scores, dev_scores, defect_types):
    """Reproduce the accepted normal-dev threshold and binary image metrics."""
    labels, test_scores = binary_inputs(labels, test_scores)
    dev_scores = finite_scores(dev_scores, "development scores")
    if len(defect_types) != len(labels) or not all(isinstance(value, str) for value in defect_types):
        raise ValueError("Defect types must match image labels")
    if any((label == 0) != (defect == "good") for label, defect in zip(labels, defect_types)):
        raise ValueError("Normal and anomalous defect types disagree with labels")
    auroc, ap = binary_auroc_ap(labels, test_scores)
    threshold = normal_dev_threshold(dev_scores)
    prediction = test_scores > threshold
    return {"image_auroc": auroc, "image_ap": ap, "threshold_95pct": threshold,
            "normal_fpr": float(prediction[labels == 0].mean()),
            "anomaly_recall": float(prediction[labels == 1].mean()),
            "per_defect_recall": {defect: float(prediction[np.asarray([item == defect for item in defect_types])].mean())
                                  for defect in sorted(set(defect_types) - {"good"})}}


def normal_dev_threshold(dev_scores):
    """Reproduce NumPy 1.26 linear interpolation across NumPy versions.

    The accepted environment computes the adjacent FP32 difference before the
    float64 interpolation. NumPy 2 changed scalar promotion for this operation.
    Explicit float64 interpolation preserves the accepted saved thresholds.
    """
    ordered = np.sort(finite_scores(dev_scores, "development scores"))
    position = np.float64(len(ordered) - 1) * np.float64(0.95)
    lower = int(np.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    fraction = np.float64(position - lower)
    difference = np.float64(np.subtract(ordered[upper], ordered[lower]))
    if fraction < 0.5:
        return float(np.float64(ordered[lower]) + difference * fraction)
    return float(np.float64(ordered[upper]) - difference * (np.float64(1.0) - fraction))


def load_stage(root, stage):
    """Bind analysis scope to the approved frozen fits and accepted source hashes."""
    root = Path(root).resolve()
    design = read(root / DESIGN_FILE)
    if design.get("workflow_id") != "tc2_gpu" or design.get("protocol_sha256") != p.PROTOCOL_SHA256:
        raise ValueError("Analysis design belongs to another workflow or protocol")
    scientific = design["scientific_source_hashes"]
    if len(scientific) != 31 or any(sha(p.inside(root, name)) != value for name, value in scientific.items()):
        raise ValueError("Accepted scientific sources have changed")
    plan = p.build_plan(root)["fits"]
    if design["fits"] != plan:
        raise ValueError("Analysis design changed the frozen fit matrix")
    matches = [value for value in design["stages"] if value["stage_id"] == stage]
    if stage not in STAGE_RULES or len(matches) != 1 or matches[0]["kind"] != "analysis":
        raise ValueError("Select an approved I1/I2 analysis stage")
    selected = matches[0]
    if selected["score_rules"] != list(STAGE_RULES[stage]):
        raise ValueError("Analysis score rules differ from the frozen protocol")
    seeds = (17,) if stage == "I1_seed17" else (17, 29, 43)
    expected = [value["run_key"] for value in plan if value["configuration"]["method"] == "patchcore"
                and value["configuration"]["stage"] in ("B0", "R0")
                and value["configuration"]["run_seed"] in seeds]
    if selected["source_run_keys"] != expected or selected["expected_rows"] != len(expected) * len(STAGE_RULES[stage]):
        raise ValueError("Analysis sources or expected row counts differ from the frozen scope")
    sources = {name: sha(root / name) for name in (ANALYSIS_FILE, DESIGN_FILE, "src/metric_core.py", "src/tc2_gpu_protocol.py")}
    return design, selected, sources


def _cache_metadata(root, evidence, identity, value):
    cached = evidence["cache_identity"]
    cache_id = p.digest(cached)
    frozen, _, _ = p.contract(root)
    expected_extraction = {name: identity["sources"][name] for name in p.CACHE_SOURCES}
    if (cached.get("format") != "tc2_gpu_fp32_npy_1" or cached.get("namespace") != "formal"
            or cached.get("dtype") != "float32" or cached.get("protocol_sha256") != p.PROTOCOL_SHA256
            or cached.get("dataset") != value["dataset"] or cached.get("category") != value["category"]
            or cached.get("manifest_sha256") != identity["manifest_sha256"]
            or cached.get("split_hash") != value["split_hash"] or cached.get("images") != p.image_entries(value)
            or cached.get("extraction_sources") != expected_extraction or cached.get("software") != identity["software"]
            or cached.get("hardware") != identity["hardware"] or cached.get("execution") != p.EXECUTION
            or cached.get("preprocessing") != frozen["preprocessing"] or cached.get("backbone") != frozen["backbone"]):
        raise ValueError("Saved cache identity does not match the frozen input manifest")
    _identifier(cached["weights_sha256"])
    directory = p.inside(root, "/".join(("run/tc2_gpu/feature_cache", value["dataset"], value["category"], cache_id)))
    meta, marker = read(directory / "metadata.json"), read(directory / "COMPLETE")
    if marker != {"status": "complete", "cache_id": cache_id, "metadata_sha256": sha(directory / "metadata.json")}:
        raise ValueError("Saved cache metadata completion marker differs")
    if meta["identity"] != cached or meta["cache_id"] != cache_id:
        raise ValueError("Saved cache metadata differs from the result identity")
    fingerprint = {"cache_id": cache_id, "metadata_sha256": sha(directory / "metadata.json"),
                   "layer_hashes": {name: entry["sha256"] for name, entry in meta["layers"].items()}}
    if identity["cache"] != fingerprint or set(meta["layers"]) != set(p.SHAPES):
        raise ValueError("Saved result cache metadata or layer hashes differ")
    index = meta["index"]
    if [row["path"] for row in index] != [row["path"] for row in p.image_entries(value)]:
        raise ValueError("Saved cache image index differs from the frozen manifest")
    for row in index:
        if (set(row) != {"path", "orig_hw"} or not isinstance(row["orig_hw"], list) or len(row["orig_hw"]) != 2
                or any(type(size) is not int or size <= 0 for size in row["orig_hw"])):
            raise ValueError("Saved cache original image dimensions are invalid")
    for layer, shape in p.SHAPES.items():
        entry = meta["layers"][layer]
        if set(entry) != {"dtype", "shape", "sha256"} or entry["dtype"] != "float32" or entry["shape"] != [len(index), *shape]:
            raise ValueError("Saved cache layer shape or precision differs")
        _identifier(entry["sha256"])
    return index, {"path": _relative_directory(root, directory), "metadata_sha256": fingerprint["metadata_sha256"],
                   "complete_sha256": sha(directory / "COMPLETE")}


def _prediction_scores(path, groups):
    expected = {role + "_" + suffix for role in ("dev", "test") for suffix in ("maps", "paths", "labels", "defect_types")}
    expected |= {role + "_score_" + rule for role in ("dev", "test") for rule in p.RULES}
    with zipfile.ZipFile(local_path(path)) as archive:
        members = archive.namelist()
        if len(members) != len(expected) or set(members) != {name + ".npy" for name in expected}:
            raise ValueError("Prediction archive fields differ from the five-score schema")
        # Only inspect map headers; full map validation is the preceding formal-run check.
        for role in ("dev", "test"):
            with archive.open(role + "_maps.npy") as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, order, dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, order, dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError("Unsupported saved map header version")
            if dtype != np.float32 or order or shape != (len(groups[role]), 256, 256):
                raise ValueError("Saved map header precision or dimensions differ")
    scores = {}
    with np.load(local_path(path), allow_pickle=False) as archive:
        for role in ("dev", "test"):
            items = groups[role]
            for suffix, field in (("paths", "path"), ("labels", "label"), ("defect_types", "defect_type")):
                array = archive[role + "_" + suffix]
                bad_dtype = array.dtype.kind not in ("i", "u") if suffix == "labels" else array.dtype.kind != "U"
                if bad_dtype or array.shape != (len(items),) or not np.array_equal(array, np.asarray([item[field] for item in items])):
                    raise ValueError("Saved prediction metadata or image order differs")
            for rule in p.RULES:
                score = archive[role + "_score_" + rule]
                if score.dtype != np.float32 or score.shape != (len(items),) or not np.isfinite(score).all():
                    raise ValueError("Saved image scores must be finite FP32 vectors")
                scores[role + "_score_" + rule] = score
    return scores


def verify_source_result(root, record, design):
    """Validate immutable source bytes and independently recompute image metrics."""
    root = Path(root).resolve()
    identifier = _identifier(record["identity_sha256"])
    relative = "run/tc2_gpu/results/" + identifier
    if record["path"] != relative:
        raise ValueError("Analysis sources must use the canonical formal result path")
    directory = p.inside(root, relative)
    if {item.name for item in local_path(directory).iterdir()} != {*RESULT_ARTIFACTS, "artifacts.sha256", "SUCCESS"}:
        raise ValueError("Formal source files are missing or unexpected")
    for name in (*RESULT_ARTIFACTS, "artifacts.sha256", "SUCCESS"):
        if not local_path(p.inside(directory, name)).is_file():
            raise ValueError("Formal source artifact is not a regular file")
    hashes = _manifest(directory, "artifacts.sha256", RESULT_ARTIFACTS)
    if read(directory / "SUCCESS") != {"status": "passed", "namespace": "formal", "identity_sha256": identifier,
                                       "artifacts_sha256": sha(directory / "artifacts.sha256")}:
        raise ValueError("Formal result completion marker differs")
    cfg, evidence = read(directory / "config.yaml"), read(directory / "evidence.json")
    identity = evidence["identity"]
    if (p.digest(identity) != identifier or identity.get("namespace") != "formal"
            or identity.get("protocol_sha256") != p.PROTOCOL_SHA256 or cfg != identity["configuration"]):
        raise ValueError("Formal result identity differs")
    specs = [value["configuration"] for value in design["fits"] if value["run_key"] == record["run_key"]]
    if len(specs) != 1 or cfg != specs[0] or cfg["method"] != "patchcore" or cfg["stage"] not in ("B0", "R0"):
        raise ValueError("Analysis source is outside the frozen B0/R0 PatchCore scope")
    expected_sources = {name: design["scientific_source_hashes"][name] for name in p.SOURCE_FILES}
    if identity["sources"] != expected_sources or any(sha(p.inside(root, name)) != value for name, value in expected_sources.items()):
        raise ValueError("Formal result scientific source identity differs")
    if evidence["runtime"]["software"] != identity["software"] or any(evidence["runtime"].get(name) != identity["hardware"].get(name) for name in ("gpu", "driver", "cuda_build")):
        raise ValueError("Formal result runtime and scientific identity disagree")
    if read(directory / "validation.json") != {"status": "passed", "identity_sha256": identifier,
            "metric_abs_tolerance": 1e-12, "prediction_dtype": "float32", "saved_metric_reproduction": True}:
        raise ValueError("Formal source lacks complete saved-result validation")
    value, manifest_hash = p.manifest(root, cfg["dataset"], cfg["category"])
    raw = p.digest({"images": p.image_entries(value), "masks": [mask for row in value["test"]["anomalies"] for mask in row["masks"]]})
    if identity["manifest_sha256"] != manifest_hash or identity["split_hash"] != value["split_hash"] or identity["raw_inputs_sha256"] != raw:
        raise ValueError("Formal source frozen input fingerprints differ")
    index, cache_record = _cache_metadata(root, evidence, identity, value)
    expected_groups = p.samples(value, cfg["run_seed"], cfg["normal_train_n"])
    sizes = {item["path"]: item["orig_hw"] for item in index}
    for group in expected_groups.values():
        for item in group:
            item["orig_hw"] = sizes[item["path"]]
    groups = read(directory / "samples.json")
    if groups != expected_groups or p.digest(groups) != identity["samples_sha256"]:
        raise ValueError("Formal source samples differ from frozen lists and cache dimensions")
    scores = _prediction_scores(directory / "predictions.npz", groups)
    metrics = read(directory / "metrics.json")
    if set(metrics) != {"image", "pixel", "metric_policy"} or metrics.get("metric_policy") != METRIC_POLICY or set(metrics.get("image", {})) != set(p.RULES):
        raise ValueError("Source metric policy or saved image rules differ")
    pixel = metrics.get("pixel")
    if (not isinstance(pixel, dict) or set(pixel) != {"pixel_auroc", "pixel_ap", "n_pixels", "n_positive_pixels"}
            or any(not isinstance(pixel[key], (int, float)) or isinstance(pixel[key], bool) or not math.isfinite(pixel[key]) or not 0 <= pixel[key] <= 1 for key in ("pixel_auroc", "pixel_ap"))
            or type(pixel["n_pixels"]) is not int or type(pixel["n_positive_pixels"]) is not int
            or not 0 < pixel["n_positive_pixels"] < pixel["n_pixels"]
            or pixel["n_pixels"] != sum(item["orig_hw"][0] * item["orig_hw"][1] for item in groups["test"])):
        raise ValueError("Saved source pixel reference is incomplete")
    image = {}
    labels = np.asarray([item["label"] for item in groups["test"]], dtype=np.uint8)
    defects = [item["defect_type"] for item in groups["test"]]
    for rule in p.RULES:
        image[rule] = image_metrics(labels, scores["test_score_" + rule], scores["dev_score_" + rule], defects)
        _compare(image[rule], metrics["image"][rule])
    source = {"run_key": record["run_key"], "path": relative, "identity_sha256": identifier,
              "artifacts_sha256": sha(directory / "artifacts.sha256"), "artifact_hashes": hashes,
              "cache_metadata": cache_record, "configuration": cfg}
    pixel_reference = {"path": relative + "/metrics.json", "sha256": hashes["metrics.json"], "field": "pixel",
                       "validation_path": relative + "/validation.json", "validation_sha256": hashes["validation.json"],
                       "recomputed_by_analysis": False}
    return {"source": source, "image": image, "pixel_reference": pixel_reference,
            "n_dev": len(groups["dev"]), "n_good": int((labels == 0).sum()), "n_anomaly": int((labels == 1).sum())}


def _assemble(root, stage, records):
    design, selected, sources = load_stage(root, stage)
    if not isinstance(records, list) or len(records) != len(selected["source_run_keys"]):
        raise ValueError("Supply exactly the required source result records")
    if any(not isinstance(item, dict) for item in records) or len({item["run_key"] for item in records}) != len(records):
        raise ValueError("Source run keys are missing or duplicated")
    lookup = {item["run_key"]: item for item in records}
    if set(lookup) != set(selected["source_run_keys"]):
        raise ValueError("Analysis sources do not match the selected stage")
    verified = [verify_source_result(root, lookup[key], design) for key in selected["source_run_keys"]]
    identity = {"schema_version": "1.0", "namespace": "formal", "workflow_id": "tc2_gpu",
                "protocol_sha256": p.PROTOCOL_SHA256, "stage": stage, "score_rules": selected["score_rules"],
                "sources": [value["source"] for value in verified], "analysis_sources": sources,
                "metric_policy": METRIC_POLICY, "image_metric_abs_tolerance": 1e-12,
                "pixel_policy": "Reference immutable, previously validated pixel metrics without recomputation"}
    rows = []
    for result in verified:
        source = result["source"]
        cfg, native = source["configuration"], result["image"]["native"]
        for rule in selected["score_rules"]:
            metric = result["image"][rule]
            row = {"stage": stage, "run_key": source["run_key"], "dataset": cfg["dataset"],
                   "category": cfg["category"], "method": cfg["method"], "run_seed": cfg["run_seed"],
                   "score_rule": rule, "n_dev": result["n_dev"], "n_good": result["n_good"],
                   "n_anomaly": result["n_anomaly"], **metric,
                   **{"delta_" + key + "_vs_native": metric[key] - native[key]
                      for key in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall")},
                   "result_path": source["path"], "result_identity_sha256": source["identity_sha256"],
                   "pixel_metrics_reference": result["pixel_reference"]}
            rows.append(row)
    if len(rows) != selected["expected_rows"] or len({(row["run_key"], row["score_rule"]) for row in rows}) != len(rows):
        raise ValueError("Analysis row count or unique run/rule combinations differ")
    identity["rows_sha256"] = p.digest(rows)
    identifier = p.digest(identity)
    analysis = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "stage": stage, "identity_sha256": identifier,
                "source_count": len(verified), "row_count": len(rows), "score_rules": selected["score_rules"],
                "metric_policy": METRIC_POLICY, "rows": rows}
    return identity, analysis


def _csv(analysis):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for source in analysis["rows"]:
        row = dict(source)
        for name in ("per_defect_recall", "pixel_metrics_reference"):
            row[name] = p.canonical(row[name])
        writer.writerow(row)
    return stream.getvalue()


def _runtime():
    versions = {"python": platform.python_version()}
    for name in ("numpy",):
        versions[name] = metadata.version(name)
    return {"device": "cpu", "software": versions, "platform": platform.platform(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "cpu_threads": os.environ.get("SLURM_CPUS_PER_TASK"),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(), "torch_imported_by_analysis": False,
            "map_arrays_loaded": False, "feature_arrays_loaded": False, "pixel_metrics_recomputed": False}


def _record(root, directory, analysis, reuse=None):
    value = {"status": "passed", "stage": analysis["stage"], "path": _relative_directory(root, directory),
             "identity_sha256": analysis["identity_sha256"], "rows": analysis["row_count"],
             "source_run_keys": list(dict.fromkeys(row["run_key"] for row in analysis["rows"]))}
    if reuse is not None:
        value["reuse"] = reuse
    return value


def verify_analysis(root, directory, expected_stage=None, *, recompute=True, _staging=False):
    """Check all five immutable files and, by default, reproduce every image row."""
    root, directory = Path(root).resolve(), Path(directory).absolute()
    relative = _relative_directory(root, directory)
    if not relative.startswith("run/tc2_gpu/summaries/"):
        raise ValueError("Analysis verification requires the canonical formal summary directory")
    if {item.name for item in local_path(directory).iterdir()} != {*ANALYSIS_ARTIFACTS, "analysis.sha256", "SUCCESS"}:
        raise ValueError("Analysis files are missing or unexpected")
    for name in (*ANALYSIS_ARTIFACTS, "analysis.sha256", "SUCCESS"):
        if not local_path(p.inside(directory, name)).is_file():
            raise ValueError("Analysis artifact must be a regular file")
    _manifest(directory, "analysis.sha256", ANALYSIS_ARTIFACTS)
    evidence, analysis = read(directory / "evidence.json"), read(directory / "analysis.json")
    identity = evidence["identity"]
    identifier, stage = p.digest(identity), analysis["stage"]
    if (stage not in STAGE_RULES or (expected_stage is not None and stage != expected_stage)
            or identity.get("namespace") != "formal" or identity.get("stage") != stage
            or identity.get("protocol_sha256") != p.PROTOCOL_SHA256 or analysis["identity_sha256"] != identifier):
        raise ValueError("Analysis stage, namespace or identity differs")
    allowed_partial = _staging and directory.name.startswith("." + identifier + ".partial.")
    if directory.parent != p.inside(root, "run/tc2_gpu/summaries/" + stage) or (directory.name != identifier and not allowed_partial):
        raise ValueError("Analysis must use its immutable canonical identity directory")
    if read(directory / "SUCCESS") != {"status": "passed", "namespace": "formal", "identity_sha256": identifier,
                                      "analysis_manifest_sha256": sha(directory / "analysis.sha256")}:
        raise ValueError("Analysis completion marker differs")
    design, selected, source_hashes = load_stage(root, stage)
    if (identity["analysis_sources"] != source_hashes or identity["score_rules"] != selected["score_rules"]
            or [source["run_key"] for source in identity["sources"]] != selected["source_run_keys"]
            or analysis["row_count"] != selected["expected_rows"] or analysis["row_count"] != len(analysis["rows"])
            or analysis["source_count"] != len(selected["source_run_keys"]) or analysis["score_rules"] != selected["score_rules"]
            or identity["metric_policy"] != METRIC_POLICY or analysis["metric_policy"] != METRIC_POLICY
            or identity["image_metric_abs_tolerance"] != 1e-12 or identity.get("rows_sha256") != p.digest(analysis["rows"])):
        raise ValueError("Analysis configuration, row count or source fingerprints differ")
    expected_pairs = [(key, rule) for key in selected["source_run_keys"] for rule in selected["score_rules"]]
    if [(row["run_key"], row["score_rule"]) for row in analysis["rows"]] != expected_pairs:
        raise ValueError("Analysis run/rule rows are duplicated, reordered or outside the frozen scope")
    if evidence.get("validation") != {"source_artifacts_verified": True, "image_metrics_recomputed": True,
            "image_metric_abs_tolerance": 1e-12, "pixel_metrics_recomputed": False, "feature_arrays_loaded": False}:
        raise ValueError("Analysis validation evidence differs")
    if evidence.get("runtime", {}).get("device") != "cpu":
        raise ValueError("Analysis evidence must declare CPU evaluation")
    if local_path(directory / "analysis.csv").read_text(encoding="utf-8") != _csv(analysis):
        raise ValueError("CSV rows differ from the structured analysis")
    if recompute:
        records = [{key: source[key] for key in ("run_key", "path", "identity_sha256")} for source in identity["sources"]]
        reproduced_identity, reproduced = _assemble(root, stage, records)
        if reproduced_identity != identity:
            raise ValueError("Analysis source artifacts or effective identity changed")
        _compare(reproduced, analysis)
    return _record(root, directory, analysis)


def analyze(root, stage, result_records, output_directory):
    """Publish a fresh immutable analysis, or verify and reuse an intact match."""
    root, output_directory = Path(root).resolve(), Path(output_directory).absolute()
    if output_directory != p.inside(root, "run/tc2_gpu/summaries/" + stage):
        raise ValueError("Output must be the selected stage's canonical formal summary parent")
    identity, analysis = _assemble(root, stage, result_records)
    identifier = analysis["identity_sha256"]
    target = p.inside(output_directory, identifier)
    with p.exclusive(output_directory, identifier):
        if target.exists():
            verified = verify_analysis(root, target, stage)
            return {**verified, "reuse": "skipped"}
        partial = p.inside(output_directory, "." + identifier + ".partial." + uuid.uuid4().hex[:8])
        local_path(partial).mkdir()
        try:
            _write(partial / "analysis.json", analysis)
            with local_path(partial / "analysis.csv").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(_csv(analysis))
            _write(partial / "evidence.json", {"identity": identity, "runtime": _runtime(),
                "validation": {"source_artifacts_verified": True, "image_metrics_recomputed": True,
                    "image_metric_abs_tolerance": 1e-12, "pixel_metrics_recomputed": False, "feature_arrays_loaded": False}})
            with local_path(partial / "analysis.sha256").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write("".join(sha(partial / name) + "  " + name + "\n" for name in ANALYSIS_ARTIFACTS))
            _write(partial / "SUCCESS", {"status": "passed", "namespace": "formal", "identity_sha256": identifier,
                "analysis_manifest_sha256": sha(partial / "analysis.sha256")})
            verify_analysis(root, partial, stage, _staging=True)
            if target.exists():
                raise FileExistsError("Analysis target already exists; preserve both directories")
            local_path(partial).rename(local_path(target))
            return _record(root, target, analysis, "created")
        except BaseException as error:
            marker = local_path(partial / "SUCCESS")
            if marker.is_file():
                marker.unlink()
            if local_path(partial).is_dir() and not local_path(partial / "FAILED.json").exists():
                _write(partial / "FAILED.json", {"status": "failed", "error": type(error).__name__ + ": " + str(error)})
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=tuple(STAGE_RULES))
    parser.add_argument("--index", required=True, type=Path, help="JSON list of source records, or an object containing results")
    parser.add_argument("--output", required=True, type=Path, help="Canonical summaries/STAGE parent; a fresh identity directory is appended")
    args = parser.parse_args()
    index = read(args.index)
    records = index["results"] if isinstance(index, dict) else index
    print(json.dumps(analyze(args.root, args.stage, records, args.output), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
