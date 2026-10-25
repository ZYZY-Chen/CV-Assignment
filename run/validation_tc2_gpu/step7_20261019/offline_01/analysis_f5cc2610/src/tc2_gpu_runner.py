"""Single-run execution and transactional validation of saved FP32 predictions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import math
import os
import time
import uuid
import numpy as np
from tc2_gpu_protocol import (EXECUTION, PROTOCOL_SHA256, RULES, accepted_inputs, build_plan, digest, exclusive,
    fingerprints, image_entries, inside, manifest, prepare_torch, read_json, samples, sha, versions, write_json)
from tc2_gpu_cache import CacheReader, cache_directory, cache_identity, input_index

ARTIFACTS = ("config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json")


def validate_config(ctx, cfg):
    if cfg["method"] not in ("padim", "patchcore") or cfg["execution"] != EXECUTION:
        raise ValueError("Unsupported method or execution configuration")
    seed = cfg["run_seed"]
    if type(seed) is not int or seed not in (17, 29, 43) or type(cfg["normal_train_n"]) is not int or cfg["normal_train_n"] < 2:
        raise ValueError("Invalid run seed or normal training count")
    if cfg[cfg["method"]]["dims_seed" if cfg["method"] == "padim" else "sampling_seed"] != seed:
        raise ValueError("Method seed must equal the scientific run seed")
    if ctx.namespace == "formal" and cfg not in [item["configuration"] for item in build_plan(ctx.root)["fits"]]:
        raise ValueError("Formal configuration is outside the frozen matrix")


def groups_with_sizes(value, cfg, index):
    result = samples(value, cfg["run_seed"], cfg["normal_train_n"])
    sizes = {row["path"]: row["orig_hw"] for row in index}
    for group in result.values():
        for item in group:
            item["orig_hw"] = sizes[item["path"]]
    return result


def raw_fingerprint(value):
    return digest({"images": image_entries(value), "masks": [mask for row in value["test"]["anomalies"] for mask in row["masks"]]})


def validate_predictions(groups, arrays, method):
    expected = {role + "_" + suffix for role in ("dev", "test") for suffix in ("maps", "paths", "labels", "defect_types")}
    expected |= {role + "_score_" + rule for role in ("dev", "test") for rule in RULES}
    if set(arrays) != expected:
        raise ValueError("Prediction fields must contain exactly the saved maps, sample metadata and five scores")
    for role in ("dev", "test"):
        items = groups[role]
        maps = arrays[role + "_maps"]
        if maps.dtype != np.float32 or maps.shape != (len(items), 256, 256) or not np.isfinite(maps).all():
            raise ValueError("Saved anomaly maps must be finite FP32 at the final resolution")
        for suffix, field in (("paths", "path"), ("labels", "label"), ("defect_types", "defect_type")):
            array = arrays[role + "_" + suffix]
            bad_dtype = array.dtype.kind not in ("i", "u") if suffix == "labels" else array.dtype.kind != "U"
            if bad_dtype:
                raise ValueError("Saved labels must be integers and strings must not use pickle/object arrays")
            if not np.array_equal(array, np.asarray([item[field] for item in items])):
                raise ValueError("Saved sample order or labels differ")
        flat = maps.reshape(len(items), -1)
        for rule in RULES:
            score = arrays[role + "_score_" + rule]
            if score.dtype != np.float32 or score.shape != (len(items),) or not np.isfinite(score).all():
                raise ValueError("Saved image scores must be finite FP32 vectors")
            if rule == "native" and method == "patchcore":
                continue
            if rule in ("native", "max"):
                reference = flat.max(axis=1)
            else:
                count = math.ceil(float(rule.split("_")[1]) * flat.shape[1])
                reference = np.partition(flat, flat.shape[1] - count, axis=1)[:, -count:].mean(axis=1, dtype=np.float64)
            if not np.allclose(score, reference, atol=1e-5, rtol=1e-4):
                raise ValueError("Map-based image score is inconsistent with saved final maps")


def compare_metrics(expected, actual):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            raise ValueError("Metric fields differ")
        for key in expected:
            compare_metrics(expected[key], actual[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("Metric list differs")
        for left, right in zip(expected, actual):
            compare_metrics(left, right)
    elif isinstance(expected, float):
        if not isinstance(actual, (int, float)) or not math.isfinite(expected) or not math.isfinite(actual) or abs(expected - actual) > 1e-12:
            raise ValueError("Saved metrics are not reproduced within absolute 1e-12")
    elif expected != actual:
        raise ValueError("Metric value or count differs")


def evaluate_saved(ctx, groups, arrays):
    import torch
    from evaluate import evaluate_all
    return evaluate_all(groups["test"], groups["dev"], torch.from_numpy(arrays["test_maps"]),
                        torch.from_numpy(arrays["dev_maps"]),
                        {rule: arrays["test_score_" + rule] for rule in RULES},
                        {rule: arrays["dev_score_" + rule] for rule in RULES}, ctx.datasets, torch.device("cpu"))


def read_predictions(path):
    with np.load(path, allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def verify_result(ctx, directory, expected_identity=None, *, recompute=True, _staging=False):
    directory = Path(directory)
    relative = directory.relative_to(ctx.output("results")).as_posix()
    inside(ctx.output("results"), relative)
    if {path.name for path in directory.iterdir()} != {*ARTIFACTS, "artifacts.sha256", "SUCCESS"}:
        raise ValueError("Result files are missing or unexpected")
    success = read_json(directory / "SUCCESS")
    evidence = read_json(directory / "evidence.json")
    identity = evidence["identity"]
    identifier = digest(identity)
    if identity["namespace"] != ctx.namespace or identity["protocol_sha256"] != PROTOCOL_SHA256:
        raise ValueError("Result belongs to a different namespace or protocol")
    if expected_identity is not None and identity != expected_identity:
        raise ValueError("Result does not match current effective configuration and inputs")
    if directory.name != identifier and not (_staging and directory.name.startswith("." + identifier + ".partial.")):
        raise ValueError("Result directory differs from its identity")
    if directory.parent != ctx.output("results"):
        raise ValueError("Result must be directly inside the canonical result directory")
    if success != {"status": "passed", "namespace": ctx.namespace, "identity_sha256": identifier,
                   "artifacts_sha256": sha(directory / "artifacts.sha256")}:
        raise ValueError("Completion marker or artifact manifest differs")
    rows = (directory / "artifacts.sha256").read_text(encoding="utf-8").splitlines()
    if len(rows) != len(ARTIFACTS):
        raise ValueError("Incomplete result artifact manifest")
    observed = set()
    for row in rows:
        value, name = row.split(None, 1)
        if name not in ARTIFACTS or name in observed or sha(inside(directory, name)) != value:
            raise ValueError("Result artifact fingerprint differs")
        observed.add(name)
    cfg = read_json(directory / "config.yaml")
    validate_config(ctx, cfg)
    if cfg != identity["configuration"] or identity["sources"] != fingerprints(ctx.root) or identity["software"] != versions():
        raise ValueError("Configuration, code or software identity differs")
    report = read_json(directory / "validation.json")
    if report != {"status": "passed", "identity_sha256": identifier, "metric_abs_tolerance": 1e-12,
                  "prediction_dtype": "float32", "saved_metric_reproduction": True}:
        raise ValueError("Result has not passed the required validation")
    groups = read_json(directory / "samples.json")
    if digest(groups) != identity["samples_sha256"]:
        raise ValueError("Sample list differs")
    arrays = read_predictions(directory / "predictions.npz")
    validate_predictions(groups, arrays, cfg["method"])
    if recompute:
        if sha(ctx.weights) != accepted_inputs(ctx.root, allow_local_summary=ctx.namespace == "validation")["weights_sha256"]:
            raise ValueError("Actual weight file differs from accepted inputs")
        value, manifest_hash = manifest(ctx.root, cfg["dataset"], cfg["category"]) if ctx.namespace == "formal" else (evidence["validation_manifest"], evidence["identity"]["manifest_sha256"])
        if manifest_hash != identity["manifest_sha256"] or raw_fingerprint(value) != identity["raw_inputs_sha256"]:
            raise ValueError("Manifest or raw input identity differs")
        index = input_index(ctx, value, include_masks=True)
        if groups_with_sizes(value, cfg, index) != groups:
            raise ValueError("Saved sample metadata differs from the manifest and actual images")
        cached = evidence["cache_identity"]
        if cached != cache_identity(ctx, value, manifest_hash, cached["hardware"]):
            raise ValueError("Cache extraction identity differs")
        with CacheReader(ctx, cache_directory(ctx, cached), cached) as reader:
            if reader.fingerprint != identity["cache"]:
                raise ValueError("Cache fingerprint differs")
        compare_metrics(read_json(directory / "metrics.json"), evaluate_saved(ctx, groups, arrays))
    return {"status": "passed", "path": str(directory), "identity_sha256": identifier, "namespace": ctx.namespace}


def execute(ctx, cfg, *, value=None, manifest_sha256=None, device="cuda"):
    validate_config(ctx, cfg)
    runtime = prepare_torch(ctx, device, cfg["run_seed"])
    import torch
    from padim_adapter import PaDiMConfig, fit_padim, predict_padim
    from patchcore_adapter import PatchCoreConfig, fit_patchcore, predict_patchcore
    if value is None:
        value, manifest_sha256 = manifest(ctx.root, cfg["dataset"], cfg["category"])
    elif ctx.namespace != "validation":
        raise ValueError("Alternate manifests cannot enter formal results")
    if (value["dataset"], value["category"]) != (cfg["dataset"], cfg["category"]):
        raise ValueError("Run target differs from manifest")
    expected_weight = accepted_inputs(ctx.root, allow_local_summary=ctx.namespace == "validation")["weights_sha256"]
    if sha(ctx.weights) != expected_weight:
        raise ValueError("Actual weight file changed")
    timing = {}
    begin = time.perf_counter()
    index = input_index(ctx, value, include_masks=True)
    cache_id = cache_identity(ctx, value, manifest_sha256, runtime)
    reader = CacheReader(ctx, cache_directory(ctx, cache_id), cache_id)
    timing["input_and_cache_verification_seconds"] = time.perf_counter() - begin
    try:
        groups = groups_with_sizes(value, cfg, index)
        identity = {"namespace": ctx.namespace, "protocol_sha256": PROTOCOL_SHA256, "configuration": cfg,
                    "manifest_sha256": manifest_sha256, "split_hash": value["split_hash"],
                    "raw_inputs_sha256": raw_fingerprint(value), "samples_sha256": digest(groups),
                    "cache": reader.fingerprint, "sources": fingerprints(ctx.root), "software": versions(),
                    "hardware": {name: runtime.get(name) for name in ("gpu", "driver", "cuda_build")}}
        identifier = digest(identity)
        target = inside(ctx.output("results"), identifier)
        with exclusive(target.parent, identifier):
            if target.exists():
                result = verify_result(ctx, target, identity, recompute=False)
                return {**result, "status": "skipped"}
            partial = inside(target.parent, "." + identifier + ".partial." + uuid.uuid4().hex[:8])
            partial.mkdir()
            try:
                def sync():
                    if device == "cuda":
                        torch.cuda.synchronize()

                def features(items):
                    arrays = reader.get([item["path"] for item in items], cfg["layers"])
                    return {name: torch.from_numpy(value).to(device) for name, value in arrays.items()}

                if device == "cuda":
                    torch.cuda.reset_peak_memory_stats()
                begin = time.perf_counter(); fit_features = features(groups["fit"]); sync()
                timing["fit_feature_read_transfer_seconds"] = time.perf_counter() - begin
                if cfg["method"] == "padim":
                    method_cfg = PaDiMConfig(**cfg["padim"], layers=tuple(cfg["layers"]), position_chunk_size=EXECUTION["padim_position_chunk_size"])
                    fit, predict = fit_padim, predict_padim
                else:
                    method_cfg = PatchCoreConfig(**cfg["patchcore"], query_chunk_size=EXECUTION["patchcore_query_chunk_size"],
                        bank_chunk_size=EXECUTION["patchcore_bank_chunk_size"], sampling_chunk_size=EXECUTION["patchcore_sampling_chunk_size"])
                    fit, predict = fit_patchcore, predict_patchcore
                sync(); begin = time.perf_counter(); model = fit(fit_features, method_cfg, device); sync()
                timing["fit_seconds"] = time.perf_counter() - begin
                del fit_features
                warm_features = features(groups["dev"][:1]); sync(); begin = time.perf_counter()
                for _ in range(EXECUTION["warmup_iterations"]):
                    predict(model, warm_features, method_cfg)
                sync(); timing["prediction_warmup_seconds"] = time.perf_counter() - begin
                del warm_features
                arrays = {}; timing["prediction_feature_io_seconds"] = 0.0; timing["predict_seconds"] = 0.0
                timing["prediction_readback_seconds"] = 0.0
                for role in ("dev", "test"):
                    maps, scores = [], {rule: [] for rule in RULES}
                    for item in groups[role]:
                        sync(); begin = time.perf_counter(); feats = features([item]); sync()
                        timing["prediction_feature_io_seconds"] += time.perf_counter() - begin
                        begin = time.perf_counter(); prediction = predict(model, feats, method_cfg); sync()
                        timing["predict_seconds"] += time.perf_counter() - begin
                        begin = time.perf_counter()
                        maps.append(prediction["anomaly_maps"].cpu().numpy())
                        for rule in RULES:
                            scores[rule].append(prediction["image_scores"][rule].cpu().numpy())
                        timing["prediction_readback_seconds"] += time.perf_counter() - begin
                    arrays[role + "_maps"] = np.concatenate(maps)
                    arrays[role + "_paths"] = np.asarray([item["path"] for item in groups[role]], dtype=str)
                    arrays[role + "_labels"] = np.asarray([item["label"] for item in groups[role]], dtype=np.uint8)
                    arrays[role + "_defect_types"] = np.asarray([item["defect_type"] for item in groups[role]], dtype=str)
                    arrays.update({role + "_score_" + rule: np.concatenate(scores[rule]) for rule in RULES})
                validate_predictions(groups, arrays, cfg["method"])
                begin = time.perf_counter(); metrics = evaluate_saved(ctx, groups, arrays)
                timing["evaluate_cpu_seconds"] = time.perf_counter() - begin
                begin = time.perf_counter()
                write_json(partial / "config.yaml", cfg)
                write_json(partial / "samples.json", groups)
                write_json(partial / "metrics.json", metrics)
                np.savez_compressed(partial / "predictions.npz", **arrays)
                timing["save_seconds"] = time.perf_counter() - begin
                begin = time.perf_counter(); reloaded = read_predictions(partial / "predictions.npz")
                for name in arrays:
                    if not np.array_equal(arrays[name], reloaded[name]):
                        raise ValueError("Prediction serialization changed array values")
                validate_predictions(groups, reloaded, cfg["method"])
                compare_metrics(metrics, evaluate_saved(ctx, groups, reloaded))
                timing["saved_metric_validation_cpu_seconds"] = time.perf_counter() - begin
                evidence = {"identity": identity, "cache_identity": cache_id, "runtime": runtime,
                            "method_detail": model.info, "timings": timing,
                            "warmup_iterations": 20, "prediction_batch_size": 1, "evaluation_device": "cpu",
                            "gpu_memory_scope": "fit feature transfer, fit, prediction warmup and prediction; no extraction",
                            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated() if device == "cuda" else None,
                            "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved() if device == "cuda" else None,
                            "finished_at_utc": datetime.now(timezone.utc).isoformat()}
                if ctx.namespace == "validation":
                    evidence["validation_manifest"] = value
                write_json(partial / "evidence.json", evidence)
                write_json(partial / "validation.json", {"status": "passed", "identity_sha256": identifier,
                    "metric_abs_tolerance": 1e-12, "prediction_dtype": "float32", "saved_metric_reproduction": True})
                (partial / "artifacts.sha256").write_text("".join(sha(partial / name) + "  " + name + "\n" for name in ARTIFACTS), encoding="utf-8")
                write_json(partial / "SUCCESS", {"status": "passed", "namespace": ctx.namespace,
                    "identity_sha256": identifier, "artifacts_sha256": sha(partial / "artifacts.sha256")})
                verify_result(ctx, partial, identity, recompute=False, _staging=True)
                if target.exists():
                    raise FileExistsError("Result publication target already exists")
                partial.rename(target)
                return {"status": "completed", "path": str(target), "identity_sha256": identifier, "namespace": ctx.namespace}
            except Exception as error:
                marker = partial / "SUCCESS"
                if marker.exists():
                    marker.unlink()
                write_json(partial / "FAILED.json", {"error": type(error).__name__ + ": " + str(error)})
                raise
    finally:
        reader.close()
