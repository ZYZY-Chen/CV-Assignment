"""Independently audit downloaded R0 prediction values without Torch or raw data."""
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
OUTPUT_TEXT = r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_170304_212fa7ce"
ROOT = Path("\\\\?\\" + ROOT_TEXT)
OUTPUT = Path("\\\\?\\" + OUTPUT_TEXT)
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019/pending_job_44121/attempt_20261019_170304_212fa7ce"
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
    fits = {row["run_key"]: row["configuration"] for row in design["fits"] if row["configuration"]["stage"] == "R0" and row["configuration"]["category"] == "bottle"}
    check(len(fits) == 4, "Expected four partial R0 bottle configurations")
    index_path = OUTPUT / "experiments-index.json"
    index = read(index_path)
    check(sha(index_path) == "F181D293FDA92F06E1E04CAEBDFFD75021D4565BF50C41C7E92DF5C8D5A6F8ED", "Wrong pinned index SHA256")
    check(index["job_id"] == "44121" and index["page_count"] == 1, "Wrong export snapshot")
    check(index["config_sha256"] == sha(design_path), "Export design differs")
    check(index["partial"] is True and index["snapshot_status"]["stage_complete"] is False, "Expected unaccepted partial snapshot")
    result_records = []
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
            check(key in fits and cfg == fits[key] and key not in seen, "Duplicate or unexpected R0 configuration")
            check(cfg["category"] == "bottle" and cfg["run_seed"] in (29, 43) and cfg["normal_train_n"] == 100, "Unexpected partial R0 fit settings")
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
                                   "configuration_matches_frozen_fit": True, "roles": roles})
            print("Passed arrays:", key, flush=True)
        check(set(page_keys) == set(page["result_ids"]), "Page result IDs differ")
    check(seen == set(fits), "Missing R0 results")
    report = {"status": "passed", "job_id": "44121", "stage_id": "R0", "snapshot_partial": True, "stage_accepted": False, "stage_complete": False, "created_utc": datetime.now(timezone.utc).isoformat(),
              "audit_script_sha256": sha(Path(__file__)), "design_sha256": sha(design_path), "index_sha256": sha(index_path),
              "python": sys.version, "numpy": np.__version__, "results_checked": len(result_records),
              "maps_checked": total_maps, "map_derived_score_vectors_checked": checked_score_vectors,
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
