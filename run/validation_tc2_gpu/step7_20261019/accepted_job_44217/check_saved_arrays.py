"""Independently audit downloaded F1 prediction values without Torch or raw data."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import gc
import hashlib
import json
import math
import sys

import numpy as np


ROOT_TEXT = r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code"
OUTPUT_TEXT = r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_194921_ca2d69de"
ROOT = Path("\\\\?\\" + ROOT_TEXT)
OUTPUT = Path("\\\\?\\" + OUTPUT_TEXT)
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019/accepted_job_44217"
RULES = ("native", "max", "top_0.001", "top_0.01", "top_0.05")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    out = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            out.update(block)
    return out.hexdigest().upper()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                                     allow_nan=False).encode("utf-8")).hexdigest().upper()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def expected_samples(value, cfg, index):
    pool = {row["path"]: row for row in value["fit_pool"]}
    chosen = value["runs"][str(cfg["run_seed"])][str(cfg["normal_train_n"])]
    check(len(chosen) == cfg["normal_train_n"] == len(set(chosen)), "Invalid frozen fit selection")
    check(all(path in pool for path in chosen), "Fit path outside frozen pool")
    normal = lambda row, defect: {"path": row["path"], "label": 0, "defect_type": defect, "mask_paths": []}
    groups = {"fit": [normal(pool[path], "") for path in chosen],
              "dev": [normal(row, "") for row in value["dev"]],
              "test": [normal(row, "good") for row in value["test"]["good"]]}
    for row in value["test"]["anomalies"]:
        check(row["label"] == 1, "Invalid anomaly label in frozen manifest")
        groups["test"].append({"path": row["path"], "label": 1, "defect_type": row["defect_type"],
                               "mask_paths": [mask["path"] for mask in row["masks"]]})
    sizes = {row["path"]: row["orig_hw"] for row in index}
    check(len(sizes) == len(index), "Duplicate cache index paths")
    for group in groups.values():
        for row in group:
            size = sizes[row["path"]]
            check(isinstance(size, list) and len(size) == 2 and all(type(n) is int and n > 0 for n in size),
                  "Invalid original image dimensions")
            row["orig_hw"] = size
    sets = [{row["path"] for row in groups[role]} for role in ("fit", "dev", "test")]
    check(not any(sets[a] & sets[b] for a, b in ((0, 1), (0, 2), (1, 2))), "Overlapping role samples")
    return groups


def main():
    design_path = ROOT / "configs/experiments_tc2_gpu.json"
    design = read(design_path)
    for name in ("src/tc2_gpu_runner.py", "src/scoring.py", "src/tc2_gpu_protocol.py"):
        check(sha(ROOT / name) == design["scientific_source_hashes"][name], "Scientific reference changed: " + name)
    fits = {row["run_key"]: row["configuration"] for row in design["fits"] if row["configuration"]["stage"] == "F1"}
    check(len(fits) == 8, "Expected all eight F1 configurations")
    index_path = OUTPUT / "experiments-index.json"
    index = read(index_path)
    check(sha(index_path) == "4E4DD33CE5985443B63F614D9B49949E8B8B665A74BD1AFA554B584945BD3FD1", "Wrong pinned index SHA256")
    check(index["job_id"] == "44217" and index["page_count"] == 2, "Wrong export snapshot")
    check(index["config_sha256"] == sha(design_path), "Export design differs")
    check(index["partial"] is False and index["snapshot_status"]["stage_complete"] is True, "Expected completed F1 snapshot")
    result_records = []
    observed_fit_paths = {}
    frozen_by_category = {}
    seen = set()
    total_maps = 0
    checked_score_vectors = 0
    non_rederived_native_vectors = 0
    for page in index["pages"]:
        base = OUTPUT / "remote" / ("page_%03d" % page["page_number"])
        directory = base / "run/tc2_gpu/results"
        dirs = sorted(path for path in directory.iterdir() if path.is_dir())
        check(len(dirs) == len(page["result_ids"]), "Page result count differs")
        page_keys = []
        for result in dirs:
            cfg = read(result / "config.yaml")
            key = "_".join([cfg["stage"], cfg["dataset"], cfg["category"], cfg["method"],
                            "s" + str(cfg["run_seed"]), "n" + str(cfg["normal_train_n"]), digest(cfg)[:12]])
            check(key in fits and cfg == fits[key] and key not in seen, "Duplicate or unexpected F1 configuration")
            check(cfg["method"] in ("padim", "patchcore") and cfg["category"] in ("cable", "screw") and cfg["run_seed"] == 17 and cfg["normal_train_n"] in (20, 50), "Unexpected F1 method or fit settings")
            seen.add(key)
            page_keys.append(key)
            evidence = read(result / "evidence.json")
            identity = evidence["identity"]
            check(identity["configuration"] == cfg and digest(identity) == result.name, "Result identity differs")
            check(identity["protocol_sha256"] == design["protocol_sha256"], "Wrong frozen protocol")
            manifest_name = "manifests/manifest_%s_%s.json" % (cfg["dataset"], cfg["category"])
            manifest_path = base / manifest_name
            manifest_sha = sha(manifest_path)
            check(manifest_sha == design["scientific_source_hashes"][manifest_name] == identity["manifest_sha256"],
                  "Frozen manifest mismatch")
            manifest = read(manifest_path)
            check(manifest["split_hash"] == identity["split_hash"], "Frozen split identity mismatch")
            cache_path = base / "run/tc2_gpu/feature_cache" / cfg["dataset"] / cfg["category"] / identity["cache"]["cache_id"] / "metadata.json"
            check(sha(cache_path) == identity["cache"]["metadata_sha256"], "Cache metadata fingerprint mismatch")
            groups = read(result / "samples.json")
            check(digest(groups) == identity["samples_sha256"], "Samples identity mismatch")
            check(groups == expected_samples(manifest, cfg, read(cache_path)["index"]), "Sample roles/order differ from frozen manifest")
            observed_fit_paths[(cfg["category"], cfg["method"], cfg["normal_train_n"])] = [row["path"] for row in groups["fit"]]
            frozen_by_category[cfg["category"]] = manifest
            fields = {role + "_" + suffix for role in ("dev", "test") for suffix in ("maps", "paths", "labels", "defect_types")}
            fields |= {role + "_score_" + rule for role in ("dev", "test") for rule in RULES}
            npz_path = result / "predictions.npz"
            npz_sha = sha(npz_path)
            artifact_lines = (result / "artifacts.sha256").read_text(encoding="utf-8").splitlines()
            artifacts = {line.split(None, 1)[1]: line.split(None, 1)[0] for line in artifact_lines}
            check(artifacts["predictions.npz"] == npz_sha and artifacts["samples.json"] == sha(result / "samples.json"),
                  "Array/sample payload differs from artifact manifest")
            roles = {}
            with np.load(npz_path, allow_pickle=False) as arrays:
                check(set(arrays.files) == fields and len(arrays.files) == len(fields), "Unexpected or duplicate NPZ fields")
                for role in ("dev", "test"):
                    items = groups[role]
                    maps = arrays[role + "_maps"]
                    check(maps.dtype == np.float32 and maps.shape == (len(items), 256, 256), "Wrong map dtype/shape")
                    check(bool(np.isfinite(maps).all()), "Non-finite map values")
                    for suffix, field in (("paths", "path"), ("labels", "label"), ("defect_types", "defect_type")):
                        vector = arrays[role + "_" + suffix]
                        check(vector.dtype.kind in ("i", "u") if suffix == "labels" else vector.dtype.kind == "U", "Unsafe metadata dtype")
                        check(np.array_equal(vector, np.asarray([row[field] for row in items])), "NPZ sample order or labels mismatch")
                    flat = maps.reshape(len(items), -1)
                    scores = {}
                    for rule in RULES:
                        vector = arrays[role + "_score_" + rule]
                        check(vector.dtype == np.float32 and vector.shape == (len(items),), "Wrong score dtype/shape")
                        check(bool(np.isfinite(vector).all()), "Non-finite image scores")
                        details = {"dtype": str(vector.dtype), "shape": list(vector.shape), "finite": True,
                                   "minimum": float(vector.min()), "maximum": float(vector.max())}
                        if rule == "native" and cfg["method"] == "patchcore":
                            details["map_rederivation"] = "Not applicable: weighted native score also depends on nearest-neighbor support."
                            non_rederived_native_vectors += 1
                        else:
                            if rule in ("native", "max"):
                                reference = flat.max(axis=1)
                            else:
                                count = math.ceil(float(rule.split("_")[1]) * flat.shape[1])
                                partition = np.partition(flat, flat.shape[1] - count, axis=1)
                                reference = partition[:, -count:].mean(axis=1, dtype=np.float64)
                                details["top_pixel_count"] = count
                                del partition
                            delta = np.abs(vector.astype(np.float64) - reference.astype(np.float64))
                            tolerance = 1e-5 + 1e-4 * np.abs(reference)
                            check(bool(np.all(delta <= tolerance)), "Map-derived image score differs: " + key + "/" + role + "/" + rule)
                            details.update({"map_rederivation": "passed", "max_absolute_error": float(delta.max()),
                                            "max_tolerance_fraction": float(np.max(delta / tolerance))})
                            checked_score_vectors += 1
                        scores[rule] = details
                    roles[role] = {"maps_dtype": str(maps.dtype), "maps_shape": list(maps.shape), "maps_finite": True,
                                   "maps_minimum": float(maps.min()), "maps_maximum": float(maps.max()),
                                   "maps_negative_values": int(np.count_nonzero(maps < 0)), "sample_metadata_matches": True,
                                   "scores": scores}
                    total_maps += len(items)
                    del maps, flat, vector
                    gc.collect()
            result_records.append({"run_key": key, "result_identity_sha256": result.name,
                                   "predictions_sha256": npz_sha, "samples_sha256": sha(result / "samples.json"),
                                   "configuration_file_sha256": sha(result / "config.yaml"),
                                   "evidence_sha256": sha(result / "evidence.json"),
                                   "artifact_manifest_sha256": sha(result / "artifacts.sha256"),
                                   "frozen_manifest_sha256": manifest_sha, "cache_metadata_sha256": sha(cache_path),
                                   "configuration_matches_frozen_fit": True, "frozen_configuration": cfg, "fit_sample_count": len(groups["fit"]), "fit_paths_sha256": digest([row["path"] for row in groups["fit"]]), "roles": roles})
            print("Passed arrays:", key, flush=True)
        check(set(page_keys) == set(page["result_ids"]), "Page result IDs differ")
    check(seen == set(fits), "Missing F1 results")
    b0_path = ROOT / "run/validation_tc2_gpu/step7_20261019/accepted_job_44053/verification.json"
    b0 = read(b0_path)
    check(b0["status"] == "passed" and b0["stage_complete"] is True, "Accepted N100 baseline missing")
    nested_checks = []
    for category in ("cable", "screw"):
        stored = frozen_by_category[category]["runs"]["17"]
        check(stored["20"] == stored["50"][:20] and stored["50"] == stored["100"][:50], "Frozen training lists are not ordered nested prefixes")
        baseline_samples = []
        for method in ("padim", "patchcore"):
            check(observed_fit_paths[(category, method, 20)] == stored["20"] and observed_fit_paths[(category, method, 50)] == stored["50"], "F1 sample selection differs from nested frozen lists")
            candidates = [row for row in b0["results"] if row["category"] == category and row["method"] == method and row["run_seed"] == 17 and row["normal_train_n"] == 100]
            check(len(candidates) == 1, "Baseline must contain one N100 result per category/method")
            prior = candidates[0]
            sample_path = Path("\\\\?\\" + b0["result_page_locations"][prior["run_key"]]) / prior["path"] / "samples.json"
            previous = read(sample_path)
            check([row["path"] for row in previous["fit"]] == stored["100"], "Accepted N100 sample order differs from frozen baseline")
            baseline_samples.append({"run_key": prior["run_key"], "samples_sha256": sha(sample_path), "fit_count": len(previous["fit"])})
        check(observed_fit_paths[(category, "padim", 20)] == observed_fit_paths[(category, "patchcore", 20)] and observed_fit_paths[(category, "padim", 50)] == observed_fit_paths[(category, "patchcore", 50)], "Both methods must use identical normal training lists")
        nested_checks.append({"category": category, "seed": 17, "n20_equals_first_20_of_n50": True, "n50_equals_first_50_of_n100": True,
                              "both_methods_identical": True, "n100_matches_accepted_b0": True, "baseline_samples": baseline_samples})
    report = {"status": "passed", "job_id": "44217", "stage_id": "F1", "snapshot_partial": False, "stage_accepted": False, "stage_acceptance": "pending_root_acceptance", "stage_complete": True, "created_utc": datetime.now(timezone.utc).isoformat(),
              "audit_script_sha256": sha(Path(__file__)), "design_sha256": sha(design_path), "index_sha256": sha(index_path),
              "python": sys.version, "numpy": np.__version__, "results_checked": len(result_records),
              "maps_checked": total_maps, "map_derived_score_vectors_checked": checked_score_vectors,
              "results_array_values_rechecked": len(result_records), "results_previous_array_audit_reused": 0, "nested_training_subsets": nested_checks, "accepted_b0_verification_sha256": sha(b0_path),
              "weighted_patchcore_native_vectors_checked_for_finite_dtype_shape_only": non_rederived_native_vectors,
              "comparison_tolerance": {"absolute": 1e-5, "relative": 1e-4, "source": "Accepted validate_predictions contract"},
              "limitations": ["Raw image/mask bytes and cache NPY layers were not downloaded; original sizes match hash-bound cache metadata.",
                              "Pixel metrics are covered by remote full verification and were not locally recomputed.",
                              "PatchCore weighted native scores cannot be reconstructed from saved maps alone; dtype, shape and finiteness were checked."],
              "results": result_records}
    target = AUDIT / "saved_arrays_verification.json"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "results_checked", "maps_checked", "map_derived_score_vectors_checked")}), flush=True)


if __name__ == "__main__":
    main()
