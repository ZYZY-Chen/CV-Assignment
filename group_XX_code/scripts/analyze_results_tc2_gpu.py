"""Hash-bound CPU analysis of the accepted TC2 GPU experiments."""
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
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import statistics
import sys

CONFIG = "configs/analysis_tc2_gpu.json"
DESIGN = "configs/experiments_tc2_gpu.json"
PROTOCOL = "3098B6A86DBA64EE439BFE61C7A4FCFFCD082371D5A80FFBC7940997ED6A1ED1"
LOCO_COLLECTOR = "09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967"
AUDIT = "run/validation_tc2_gpu/step7_20261019"
RULES = ("native", "max", "top_0.001", "top_0.01", "top_0.05")
CATS = ("bottle", "cable", "capsule", "screw", "tile", "wood")
SEEDS = (17, 29, 43)
METRICS = ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall", "pixel_auroc", "pixel_ap")
RESULT_FILES = ("config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json", "artifacts.sha256", "SUCCESS")
ANALYSIS_FILES = ("analysis.json", "analysis.csv", "evidence.json", "analysis.sha256", "SUCCESS")


def local(path):
    path = Path(path)
    return Path("\\\\?\\" + str(path.absolute())) if os.name == "nt" and not str(path).startswith("\\\\?\\") else path


def inside(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or relative.startswith("/") or any(part in ("", ".", "..") for part in relative.split("/")):
        raise ValueError("Unsafe relative artifact path")
    path = local(Path(root).absolute().joinpath(*PurePosixPath(relative).parts))
    for parent in (path, *path.parents):
        attributes = parent.lstat().st_file_attributes if os.name == "nt" and parent.exists() else 0
        if parent.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise ValueError("Linked artifact paths are not accepted")
    return path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest().upper()


def sha(path):
    result = hashlib.sha256()
    with local(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest().upper()


def read(path):
    def reject(value):
        raise ValueError("Non-finite JSON constant: " + value)
    def pairs(items):
        result = {}
        for key, value in items:
            checked(key not in result, "Duplicate JSON object key: " + key)
            result[key] = value
        return result
    def number(value):
        result = float(value)
        checked(math.isfinite(result), "Non-finite JSON number")
        return result
    return json.loads(local(path).read_text(encoding="utf-8"), parse_constant=reject, object_pairs_hook=pairs, parse_float=number)


def write(path, value):
    path = local(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False); stream.write("\n")
    os.replace(temporary, path)


def checked(condition, message):
    if not condition:
        raise ValueError(message)


def mean_std(values):
    values = list(values)
    checked(bool(values) and all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in values), "Statistics require finite observations")
    return {"mean": statistics.mean(values), "std": statistics.stdev(values) if len(values) > 1 else None, "n": len(values), "ddof": 1}


def source_hashes(root, config):
    return {name: sha(inside(root, name)) for name in config["analysis_sources"]}


def job_resources(verification):
    """Keep scheduler evidence distinct from per-method timing and GPU peaks."""
    fields = ("slurm_state", "exit_code", "elapsed", "node", "slurm_max_rss_kib", "child_peak_rss_kib")
    return {"scope": "job-level scheduler/child-process evidence; not per-method CPU memory or inference latency", **{name: verification.get(name) for name in fields}}


def locate(verification, relative):
    candidates = [Path(value) for value in verification.get("result_page_locations", {}).values()]
    source = local(verification["source_directory"])
    candidates.extend(source.glob("remote/page_*")); candidates.extend(source.glob("page_*"))
    for page in candidates:
        candidate = inside(page, relative)
        if candidate.is_file():
            return candidate
    raise ValueError("Accepted local artifact is unavailable: " + relative)


def plan(root):
    root = Path(root).absolute(); config = read(inside(root, CONFIG)); design = read(inside(root, DESIGN))
    analysis_sources = source_hashes(root, config)
    master = read(inside(root, AUDIT + "/setup_status.json"))
    checked(master.get("step_7_complete") is True and master.get("verified_formal_fits") == 66 and master.get("verified_analysis_rows") == 108, "Complete step-7 acceptance is required")
    checked(master["design_sha256"] == sha(inside(root, DESIGN)) == config["design_sha256"], "Frozen design fingerprint differs")
    protected = {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **master["experiment_sources"]}
    checked(len(protected) == 44 and all(sha(inside(root, name)) == value for name, value in protected.items()), "The 44 protected source files differ")
    checked(sha(inside(root, "scripts/collect_experiments_loco_tc2_gpu.py")) == LOCO_COLLECTOR, "Accepted LOCO collection source differs")
    stages, results, analyses, caches = [], [], [], {}
    accepted = master["accepted_step_7_stages"]
    checked([entry["stage_id"] for entry in accepted] == [entry["stage_id"] for entry in design["stages"]], "All twelve ordered accepted stages are required")
    fits = {entry["run_key"]: entry["configuration"] for entry in design["fits"]}
    for entry in accepted:
        verification_path = inside(root, entry["record"])
        checked(sha(verification_path) == entry["record_sha256"], "Accepted stage record changed")
        verification = read(verification_path)
        directory = verification_path.parent
        raw_path = directory / "remote_setup_status.json"
        raw = read(raw_path)
        checked(sha(raw_path) == entry["remote_status_sha256"] and raw["status"] == "passed" and raw["stage_complete"] is True, "Accepted remote stage status differs")
        hashes = read(directory / "archive_file_hashes.json")
        stages.append({"stage_id": entry["stage_id"], "job_id": entry["job_id"], "status_path": "run/validation_tc2_gpu/step7_job_" + entry["job_id"] + "/setup_status.json", "status_sha256": entry["remote_status_sha256"], "acceptance_record": entry["record"], "acceptance_sha256": entry["record_sha256"], "index_sha256": entry["index_sha256"], "accepted_job_resources": job_resources(verification)})
        for record in raw["results"]:
            relative = record["path"]; files = {}
            for name in RESULT_FILES:
                path = relative + "/" + name
                checked(path in hashes and sha(locate(verification, path)) == hashes[path], "Accepted result artifact changed")
                files[name] = hashes[path]
            cfg = read(locate(verification, relative + "/config.yaml"))
            evidence = read(locate(verification, relative + "/evidence.json"))
            checked(cfg == fits[record["run_key"]] and evidence["identity"]["configuration"] == cfg and digest(evidence["identity"]) == record["identity_sha256"], "Result identity differs from the frozen fit")
            results.append({"run_key": record["run_key"], "path": relative, "identity_sha256": record["identity_sha256"], "configuration": cfg, "files": files})
        for record in raw.get("analyses", []):
            relative = record["path"]; files = {name: hashes[relative + "/" + name] for name in ANALYSIS_FILES}
            checked(all(sha(locate(verification, relative + "/" + name)) == value for name, value in files.items()), "Accepted score analysis changed")
            analyses.append({"stage_id": entry["stage_id"], "path": relative, "identity_sha256": record["identity_sha256"], "rows": record["rows"], "files": files})
        for record in raw["caches"]:
            relative = record["path"]
            files = {name: hashes[relative + "/" + name] for name in ("metadata.json", "COMPLETE")}
            checked(all(sha(locate(verification, relative + "/" + name)) == value for name, value in files.items()), "Accepted cache metadata changed")
            value = {"dataset": record["identity"]["dataset"], "category": record["identity"]["category"], "path": relative, "files": files, "layer_hashes": record["layer_hashes"]}
            checked(relative not in caches or caches[relative] == value, "A cache has conflicting accepted fingerprints")
            caches[relative] = value
    checked(len(results) == 66 and len({row["identity_sha256"] for row in results}) == 66 and {row["run_key"] for row in results} == set(fits), "Expected exactly 66 unique accepted fits")
    checked(len(caches) == 8 and len(analyses) == 3 and sum(row["rows"] for row in analyses) == 108, "Expected eight caches and three score analyses")
    return {"schema_version": "1.0", "workflow_id": "tc2_gpu", "protocol_sha256": PROTOCOL, "config_sha256": sha(inside(root, CONFIG)), "design_sha256": sha(inside(root, DESIGN)), "step7_acceptance_sha256": sha(inside(root, AUDIT + "/setup_status.json")), "expected_total_fits": 66, "expected_analysis_rows": 108, "source_rows": 108, "unique_pc_analysis_rows": 90, "protected_sources": protected, "analysis_sources": analysis_sources, "loco_collector_sha256": LOCO_COLLECTOR, "stages": stages, "results": results, "caches": list(caches.values()), "analyses": analyses}


def validate_registry(root, registry):
    checked(registry.get("protocol_sha256") == PROTOCOL and registry.get("expected_total_fits") == 66 and len(registry.get("results", [])) == 66 and registry.get("expected_analysis_rows") == 108, "Invalid analysis input registry")
    design = read(inside(root, DESIGN)); config = read(inside(root, CONFIG))
    checked(sha(inside(root, DESIGN)) == registry["design_sha256"] == config["design_sha256"] and sha(inside(root, CONFIG)) == registry["config_sha256"] and source_hashes(root, config) == registry["analysis_sources"], "Analysis or design sources changed")
    protected = registry["protected_sources"]
    original = read(inside(root, registry["stages"][0]["status_path"]))["experiment_sources"]
    checked(protected == {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **original} and len(protected) == 44 and all(sha(inside(root, name)) == value for name, value in protected.items()), "Protected experiment sources changed")
    checked(sha(inside(root, "scripts/collect_experiments_loco_tc2_gpu.py")) == registry["loco_collector_sha256"] == LOCO_COLLECTOR, "LOCO provenance differs")
    checked([row["stage_id"] for row in registry["stages"]] == [row["stage_id"] for row in design["stages"]], "Stage dependency order differs")
    for entry in registry["stages"]:
        checked(sha(inside(root, entry["status_path"])) == entry["status_sha256"], "Accepted remote status changed")
        status = read(inside(root, entry["status_path"]))
        checked(status["status"] == "passed" and status["stage_complete"] and status["job_id"] == entry["job_id"], "A required experiment is incomplete")
        pointer = inside(root, "run/validation_tc2_gpu/last_experiments_" + entry["stage_id"] + "_job.txt")
        checked(pointer.read_text().strip() == entry["job_id"], "Accepted stage is no longer the latest submitted stage")
    fits = {row["run_key"]: row["configuration"] for row in design["fits"]}
    checked({row["run_key"] for row in registry["results"]} == set(fits) and len({row["identity_sha256"] for row in registry["results"]}) == 66, "Fit registry has omissions or duplicates")
    records = []
    for record in registry["results"]:
        checked(record["configuration"] == fits[record["run_key"]] and set(record["files"]) == set(RESULT_FILES), "Fit configuration or file schema differs")
        directory = inside(root, record["path"])
        checked({path.name for path in directory.iterdir()} == set(RESULT_FILES), "Formal result contains extra or missing files")
        checked(all(sha(directory / name) == value for name, value in record["files"].items()), "A formal result artifact changed")
        cfg = read(directory / "config.yaml"); evidence = read(directory / "evidence.json")
        checked(cfg == record["configuration"] and digest(evidence["identity"]) == record["identity_sha256"], "Formal result identity differs")
        checked(read(directory / "validation.json")["status"] == "passed", "Saved result metric verification is missing")
        records.append({**record, "directory": directory, "metrics": read(directory / "metrics.json"), "evidence": evidence, "samples": read(directory / "samples.json")})
    pc_rows = {}; checkpoint = []
    for analysis in registry["analyses"]:
        directory = inside(root, analysis["path"])
        checked(all(sha(directory / name) == value for name, value in analysis["files"].items()), "A saved-score analysis changed")
        value = read(directory / "analysis.json")
        checked(value["identity_sha256"] == analysis["identity_sha256"] and value["row_count"] == analysis["rows"], "Saved-score analysis identity differs")
        if analysis["stage_id"] == "I1_seed17":
            checkpoint = value["rows"]
        else:
            for row in value["rows"]:
                key = (row["result_identity_sha256"], row["score_rule"])
                checked(key not in pc_rows, "Saved-score analysis duplicates a source rule")
                pc_rows[key] = row
    checked(len(pc_rows) == 90 and len(checkpoint) == 18 and all({key: value for key, value in pc_rows[(row["result_identity_sha256"], row["score_rule"])].items() if key != "stage"} == {key: value for key, value in row.items() if key != "stage"} for row in checkpoint), "Checkpoint overlap or unique analysis count differs")
    by_id = {record["identity_sha256"]: record for record in records}
    for (identifier, rule), row in pc_rows.items():
        checked(identifier in by_id and by_id[identifier]["configuration"]["method"] == "patchcore", "Analysis references an unknown source result")
        for metric in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall", "threshold_95pct"):
            checked(abs(row[metric] - by_id[identifier]["metrics"]["image"][rule][metric]) <= 1e-12, "Analysis and source image metrics disagree")
    for cache in registry["caches"]:
        checked(all(sha(inside(root, cache["path"] + "/" + name)) == value for name, value in cache["files"].items()), "Cache metadata changed")
    checked(len(registry["caches"]) == 8 and len(registry["analyses"]) == 3, "Expected eight caches and three analyses")
    return records


def runtime_gate(root, config, job):
    checked(re.fullmatch(r"[0-9]+", job) is not None and os.environ.get("SLURM_JOB_ID") == job, "A matching SLURM CPU job is required")
    checked(os.environ.get("CUDA_VISIBLE_DEVICES") in ("", "-1") and not os.environ.get("SLURM_JOB_GPUS") and not os.environ.get("SLURM_STEP_GPUS"), "Analysis refuses a visible or allocated GPU")
    checked(os.environ.get("SLURM_CPUS_PER_TASK") == "2" and os.environ.get("SLURM_MEM_PER_NODE") == "8192" and os.environ.get("SLURM_JOB_PARTITION") == "MGPU-TC2" and os.environ.get("SLURM_JOB_QOS", "normal") == "normal", "Analysis CPU allocation differs from the approved resources")
    checked(sys.version_info[:2] == (3, 10) and metadata.version("numpy") == "1.26.4" and metadata.version("pillow") == "12.3.0", "Accepted CPU environment differs")
    checked(shutil.disk_usage(root).free >= config["resources"]["minimum_free_bytes"], "At least 8 GiB of free storage is required")
    checked("torch" not in sys.modules, "Analysis must not import Torch")
    return {"device": "cpu", "python": sys.version.split()[0], "numpy": metadata.version("numpy"), "pillow": metadata.version("pillow"), "node": os.environ.get("SLURM_JOB_NODELIST"), "job_id": job, "cpus": 2, "memory_mib": 8192, "gpus": 0}


def flat_record(record, rule, group="pooled"):
    cfg, metrics = record["configuration"], record["metrics"]
    value = metrics if group == "pooled" else metrics["groups"][group]
    image, pixel = value["image"][rule], value["pixel"]
    return {"run_key": record["run_key"], "result_identity_sha256": record["identity_sha256"], "dataset": cfg["dataset"], "category": cfg["category"], "method": cfg["method"], "run_seed": cfg["run_seed"], "normal_train_n": cfg["normal_train_n"], "stage": cfg["stage"], "score_rule": rule, "group": group, **image, **pixel, "n_dims": cfg.get("padim", {}).get("n_dims"), "coreset_ratio": cfg.get("patchcore", {}).get("coreset_ratio"), "sampling": cfg.get("patchcore", {}).get("sampling"), "layers": cfg["layers"], "parameter": canonical(cfg.get(cfg["method"], {})) + ";layers=" + ",".join(cfg["layers"])}


def aggregate_tables(records):
    baseline_records = [row for row in records if row["configuration"]["stage"] in ("B0", "R0")]
    checked(len(baseline_records) == 36, "Main baseline must contain exactly 36 fits")
    baseline = [flat_record(record, rule) for record in baseline_records for rule in RULES]
    macros = []
    for method in ("padim", "patchcore"):
        for rule in RULES:
            for seed in SEEDS:
                rows = [row for row in baseline if (row["method"], row["score_rule"], row["run_seed"]) == (method, rule, seed)]
                checked(len(rows) == 6 and {row["category"] for row in rows} == set(CATS), "A macro requires all six unique categories")
                macros.append({"method": method, "score_rule": rule, "run_seed": seed, "n_categories": 6, **{metric: statistics.mean(row[metric] for row in rows) for metric in METRICS}})
    summaries = []
    for method in ("padim", "patchcore"):
        for rule in RULES:
            rows = [row for row in macros if (row["method"], row["score_rule"]) == (method, rule)]
            summaries.append({"method": method, "score_rule": rule, "n_seeds": 3, "ddof": 1, **{metric + suffix: mean_std(row[metric] for row in rows)[key] for metric in METRICS for suffix, key in (("_mean", "mean"), ("_std", "std"))}})
    improvement = []
    for row in baseline:
        if row["method"] != "patchcore":
            continue
        matches = {other["score_rule"]: other for other in baseline if other["result_identity_sha256"] == row["result_identity_sha256"]}
        improvement.append({**row, **{"delta_" + metric + "_vs_" + reference: row[metric] - matches[reference][metric] for reference in ("native", "max") for metric in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall")}})
    paired = []
    for rule in RULES:
        for reference in ("native", "max"):
            for seed in SEEDS:
                rows = [row for row in improvement if row["score_rule"] == rule and row["run_seed"] == seed]
                paired.append({"score_rule": rule, "reference_rule": reference, "run_seed": seed, "n_categories": 6, **{metric: statistics.mean(row["delta_" + metric + "_vs_" + reference] for row in rows) for metric in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall")}})
    ablations = [flat_record(record, rule) for record in records if record["configuration"]["dataset"] == "mvtec_ad" and record["configuration"]["category"] in ("cable", "screw") for rule in RULES]
    loco = [flat_record(record, rule, group) for record in records if record["configuration"]["dataset"] == "mvtec_loco" for group in ("logical_anomalies", "structural_anomalies", "pooled") for rule in RULES]
    image_rows = [flat_record(record, rule) for record in records if record["configuration"]["dataset"] == "mvtec_ad" for rule in RULES] + loco
    pixel_rows = [{key: row[key] for key in ("run_key", "result_identity_sha256", "dataset", "category", "method", "run_seed", "normal_train_n", "stage", "group", "pixel_auroc", "pixel_ap", "n_pixels", "n_positive_pixels")} for row in image_rows if row["score_rule"] == "native"]
    resources = []
    for record in records:
        cfg, evidence = record["configuration"], record["evidence"]
        detail, timings = evidence["method_detail"], evidence["timings"]
        n = len(record["samples"]["dev"]) + len(record["samples"]["test"])
        if cfg["method"] == "patchcore":
            storage = detail["memory_bank_kept"] * detail["embedding_channels"] * 4
        else:
            dimensions = cfg["padim"]["n_dims"]
            grid = detail.get("model_grid_hw", [64, 64])
            storage = grid[0] * grid[1] * (dimensions + dimensions * dimensions) * 4 + 8 * dimensions
        resources.append({**{key: flat_record(record, "native")[key] for key in ("run_key", "category", "dataset", "method", "run_seed", "normal_train_n", "stage", "n_dims", "coreset_ratio", "sampling", "layers")}, **timings, "predict_ms_per_image": timings["predict_seconds"] * 1000 / n, "prediction_image_count": n, "dev_image_count": len(record["samples"]["dev"]), "test_image_count": len(record["samples"]["test"]), "prediction_scope": "cached model computation over dev plus test; excludes feature I/O, warmup, readback and extraction", "model_tensor_bytes": storage, "model_storage_estimated": True, "storage_scope": "FP32 bank or Gaussian tensors plus PaDiM int64 selected indices; excludes Python metadata", "memory_bank_kept": detail.get("memory_bank_kept"), "memory_bank_full": detail.get("memory_bank_full"), "embedding_channels": detail.get("embedding_channels"), "warmup_iterations": evidence.get("warmup_iterations", 20), "prediction_batch_size": evidence.get("prediction_batch_size", 1), "gpu_peak_allocated_mib": evidence["gpu_peak_allocated_bytes"] / 1024 ** 2, "gpu_peak_reserved_mib": evidence["gpu_peak_reserved_bytes"] / 1024 ** 2, "gpu_memory_scope": evidence["gpu_memory_scope"], "source_runtime": evidence["runtime"]})
    category_summary = []
    for category in CATS:
        for method in ("padim", "patchcore"):
            for rule in RULES:
                rows = [row for row in baseline if (row["category"], row["method"], row["score_rule"]) == (category, method, rule)]
                checked(len(rows) == 3, "Category summary requires three seeds")
                category_summary.append({"category": category, "method": method, "score_rule": rule, "n_seeds": 3, "ddof": 1, **{metric + suffix: mean_std(row[metric] for row in rows)[key] for metric in METRICS for suffix, key in (("_mean", "mean"), ("_std", "std"))}})
    paired_summary = []
    for rule in RULES:
        for reference in ("native", "max"):
            rows = [row for row in paired if (row["score_rule"], row["reference_rule"]) == (rule, reference)]
            paired_summary.append({"score_rule": rule, "reference_rule": reference, "n_seeds": 3, "ddof": 1, **{metric + suffix: mean_std(row[metric] for row in rows)[key] for metric in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall") for suffix, key in (("_mean", "mean"), ("_std", "std"))}})
    sampling_paired = []
    for seed in SEEDS:
        for rule in RULES:
            differences = []
            for category in ("cable", "screw"):
                rows = [row for row in ablations if row["method"] == "patchcore" and row["category"] == category and row["run_seed"] == seed and row["score_rule"] == rule and row["stage"] in ("B0", "R0", "C1", "C1R")]
                choices = {row["sampling"]: row for row in rows}
                checked(len(rows) == 2 and set(choices) == {"random", "coreset"}, "Sampling comparison requires matched category and seed")
                differences.append({metric: choices["random"][metric] - choices["coreset"][metric] for metric in METRICS})
            sampling_paired.append({"score_rule": rule, "run_seed": seed, "n_categories": 2, "comparison": "random_minus_coreset", **{metric: statistics.mean(row[metric] for row in differences) for metric in METRICS}})
    sampling_summary = [{"score_rule": rule, "n_seeds": 3, "n_categories": 2, "ddof": 1, "comparison": "random_minus_coreset", **{metric + suffix: mean_std(row[metric] for row in sampling_paired if row["score_rule"] == rule)[key] for metric in METRICS for suffix, key in (("_mean", "mean"), ("_std", "std"))}} for rule in RULES]
    tables = {"baseline": baseline, "baseline_macro": macros, "baseline_summary": summaries, "category_summary": category_summary, "improvement": improvement, "paired_improvement": paired, "paired_improvement_summary": paired_summary, "sampling_paired": sampling_paired, "sampling_summary": sampling_summary, "ablations": ablations, "loco": loco, "image_metrics": image_rows, "pixel_metrics": pixel_rows, "resources": resources, "size_recall": []}
    validate_tables(tables)
    return tables


def validate_tables(tables):
    checked(len(tables["baseline"]) == 180 and len(tables["baseline_macro"]) == 30 and len(tables["baseline_summary"]) == 10 and len(tables["improvement"]) == 90, "Baseline or analysis summary counts differ")
    checked(len(tables["image_metrics"]) == 370 and len(tables["pixel_metrics"]) == 74 and len(tables["loco"]) == 60 and len(tables["resources"]) == 66, "Canonical dataset/scope table counts differ")
    checked(len({(row["result_identity_sha256"], row["group"], row["score_rule"]) for row in tables["image_metrics"]}) == 370, "Image tables duplicate a source scope/rule")
    checked(all(row["ddof"] == 1 and row["n_seeds"] == 3 for row in tables["baseline_summary"]), "Three-seed summaries require sample standard deviation")
    macro_keys = {(row["method"], row["score_rule"], row["run_seed"]) for row in tables["baseline_macro"]}
    checked(len(macro_keys) == 30, "Macro table repeats a method, rule or seed")
    for row in tables["baseline_macro"]:
        values = [item for item in tables["baseline"] if (item["method"], item["score_rule"], item["run_seed"]) == (row["method"], row["score_rule"], row["run_seed"])]
        checked(len(values) == 6 and {item["category"] for item in values} == set(CATS), "A macro omits or duplicates a category")
        checked(all(abs(row[metric] - statistics.mean(item[metric] for item in values)) <= 1e-12 for metric in METRICS), "Macro table does not equal its six category inputs")
    for row in tables["baseline_summary"]:
        values = [item for item in tables["baseline_macro"] if (item["method"], item["score_rule"]) == (row["method"], row["score_rule"])]
        checked({item["run_seed"] for item in values} == set(SEEDS), "Summary omits a required seed")
        for metric in METRICS:
            result = mean_std(item[metric] for item in values)
            checked(abs(row[metric + "_mean"] - result["mean"]) <= 1e-12 and abs(row[metric + "_std"] - result["std"]) <= 1e-12, "Summary mean or sample standard deviation differs")
    pixel_values = {}
    for row in tables["image_metrics"]:
        key = (row["result_identity_sha256"], row["group"])
        values = (row["pixel_auroc"], row["pixel_ap"], row["n_pixels"], row["n_positive_pixels"])
        checked(key not in pixel_values or pixel_values[key] == values, "Changing an image score rule must not change pixel metrics")
        pixel_values[key] = values
        checked((row["dataset"] == "mvtec_ad" and row["group"] == "pooled") or (row["dataset"] == "mvtec_loco" and row["group"] in ("pooled", "logical_anomalies", "structural_anomalies")), "Dataset and evaluation scope differ")
    def finite(value):
        if isinstance(value, float):
            checked(math.isfinite(value), "Analysis tables contain a non-finite number")
        elif isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)
    finite(tables)
    for table_name, rows in tables.items():
        checked(isinstance(rows, list), "Every analysis table must contain a row list")
        for row in rows:
            if "run_seed" in row:
                checked(type(row["run_seed"]) is int and row["run_seed"] in SEEDS, "Analysis row seed is invalid")
            for key in ("n_seeds", "n_categories", "n_images", "normal_train_n", "n_pixels", "n_positive_pixels", "prediction_image_count", "model_tensor_bytes"):
                if key in row:
                    checked(type(row[key]) is int and row[key] > 0, "Analysis count must be a positive integer")
            for key in ("image_auroc", "image_ap", "pixel_auroc", "pixel_ap", "normal_fpr", "anomaly_recall", "recall"):
                if key in row:
                    lower = -1 - 1e-12 if table_name in ("paired_improvement", "sampling_paired") else -1e-12
                    checked(isinstance(row[key], (int, float)) and not isinstance(row[key], bool) and lower <= row[key] <= 1 + 1e-12, "Analysis metric lies outside its accepted range")
            for key, value in row.items():
                if key.endswith("_std") and value is not None:
                    checked(not isinstance(value, bool) and isinstance(value, (int, float)) and value >= 0, "Standard deviation must be nonnegative")
    return True


def masks_and_inputs(root, registry):
    """Verify original input bytes and compute union-mask area without pixel scores."""
    import numpy as np
    from PIL import Image
    areas, masks = {}, {}
    for cache in registry["caches"]:
        manifest_name = "manifests/manifest_" + cache["dataset"] + "_" + cache["category"] + ".json"
        manifest = read(inside(root, manifest_name))
        metadata_value = read(inside(root, cache["path"] + "/metadata.json"))
        sizes = {row["path"]: row["orig_hw"] for row in metadata_value["index"]}
        image_entries = manifest["dev"] + manifest["fit_pool"] + manifest["test"]["good"] + manifest["test"]["anomalies"]
        for image in image_entries:
            checked(sha(inside(root, "datasets/" + image["path"])) == image["sha256"], "Frozen original image changed")
        ordered = []
        for image in manifest["test"]["anomalies"]:
            height, width = sizes[image["path"]]
            union = np.zeros((height, width), dtype=np.bool_)
            for mask in image["masks"]:
                path = inside(root, "datasets/" + mask["path"])
                checked(sha(path) == mask["sha256"], "Frozen original mask changed")
                with Image.open(path) as opened:
                    array = np.asarray(opened.convert("L")) > 0
                checked(array.shape == union.shape, "Original mask dimensions differ")
                union |= array
            area = int(union.sum()); fraction = area / (height * width)
            areas[image["path"]] = {"dataset": cache["dataset"], "category": cache["category"], "path": image["path"], "area_pixels": area, "original_pixels": height * width, "area_fraction": fraction}
            masks[image["path"]] = image["masks"]
            ordered.append((fraction, image["path"]))
        ordered.sort(); count = max(1, math.ceil(len(ordered) * 0.25))
        for _, path in ordered:
            areas[path]["size_group"] = "middle"
        for _, path in ordered[:count]:
            areas[path]["size_group"] = "small"
        for _, path in ordered[-count:]:
            areas[path]["size_group"] = "large"
    return areas, masks


def score_context(records, areas, tables):
    import numpy as np
    points = []; decisions = {}; distributions = []
    for record in records:
        cfg = record["configuration"]
        if cfg["stage"] not in ("B0", "R0", "B0_LOCO"):
            continue
        with np.load(record["directory"] / "predictions.npz", allow_pickle=False) as archive:
            for rule in RULES:
                scores = archive["test_score_" + rule]
                threshold = record["metrics"]["image"][rule]["threshold_95pct"]
                checked(scores.dtype == np.float32 and np.isfinite(scores).all() and scores.shape == (len(record["samples"]["test"]),), "Saved score vector differs")
                for item, value in zip(record["samples"]["test"], scores):
                    predicted = bool(float(value) > threshold)
                    point = {"dataset": cfg["dataset"], "category": cfg["category"], "method": cfg["method"], "run_seed": cfg["run_seed"], "score_rule": rule, "role": "test", "path": item["path"], "label": item["label"], "defect_type": item["defect_type"], "score": float(value), "threshold": threshold, "prediction": predicted, "result_identity_sha256": record["identity_sha256"]}
                    points.append(point)
                    if cfg["dataset"] == "mvtec_ad" and cfg["method"] == "patchcore":
                        distributions.append(point)
                    if cfg["run_seed"] == 17:
                        decisions[(cfg["dataset"], cfg["category"], item["path"], cfg["method"], rule)] = point
                if cfg["dataset"] == "mvtec_ad":
                    for size in ("small", "large"):
                        indices = [index for index, item in enumerate(record["samples"]["test"]) if item["path"] in areas and areas[item["path"]]["size_group"] == size]
                        checked(bool(indices), "Mask-size quartile is empty")
                        tables["size_recall"].append({"category": cfg["category"], "method": cfg["method"], "run_seed": cfg["run_seed"], "score_rule": rule, "size_group": size, "n_images": len(indices), "recall": float((scores[indices] > threshold).mean())})
    return points, decisions, distributions


def select_cases(records, areas, decisions):
    selected = []; candidates = []
    categories = [("mvtec_ad", category) for category in CATS] + [("mvtec_loco", category) for category in ("juice_bottle", "screw_bag")]
    for dataset, category in categories:
        baseline = [row for row in records if row["configuration"]["dataset"] == dataset and row["configuration"]["category"] == category and row["configuration"]["run_seed"] == 17 and row["configuration"]["stage"] in ("B0", "B0_LOCO")]
        checked({row["configuration"]["method"] for row in baseline} == {"padim", "patchcore"}, "Case baseline pair is missing")
        current = []
        for item in sorted(baseline[0]["samples"]["test"], key=lambda value: value["path"]):
            path = item["path"]
            scores = [decisions[(dataset, category, path, method, rule)] for method, rule in (("padim", "native"), ("patchcore", "native"), ("patchcore", "top_0.01"))]
            failure = any(value["prediction"] != bool(item["label"]) for value in scores)
            micro = path in areas and areas[path]["size_group"] == "small"
            row = {"dataset": dataset, "category": category, "group": item["defect_type"], "defect_type": item["defect_type"], "label": item["label"], "path": path, "is_real_failure": failure, "is_normal_false_positive": failure and item["label"] == 0, "is_micro_hard_case": micro, "source_result_ids": {record["configuration"]["method"]: record["identity_sha256"] for record in baseline}, "scores": scores, "eligible_under_group_quota": dataset == "mvtec_ad" or item["defect_type"] in ("logical_anomalies", "structural_anomalies")}
            current.append(row); candidates.append(row)
        if dataset == "mvtec_loco":
            choices = []
            for group in ("logical_anomalies", "structural_anomalies"):
                options = [row for row in current if row["defect_type"] == group]
                checked(bool(options), "A mandatory LOCO case group is absent")
                options.sort(key=lambda row: (not row["is_real_failure"], not row["is_micro_hard_case"], row["path"]))
                choices.append(options[0])
        else:
            options = sorted(current, key=lambda row: (not row["is_normal_false_positive"], not row["is_real_failure"], not row["is_micro_hard_case"], row["path"]))
            first = options[0]
            others = [row for row in current if row["path"] != first["path"]]
            others.sort(key=lambda row: (not (row["is_micro_hard_case"] and row["is_real_failure"]), not row["is_micro_hard_case"], not row["is_real_failure"], row["path"]))
            checked(bool(others), "A category needs two distinct qualitative examples")
            choices = [first, others[0]]
        selected.extend(dict(row) for row in choices)
    eligible_failures = [row for row in candidates if row["eligible_under_group_quota"] and row["is_real_failure"]]
    required = min(2, len(eligible_failures))
    while sum(row["is_real_failure"] for row in selected) < required:
        replacement = None
        for index, old in enumerate(selected):
            if old["is_real_failure"]:
                continue
            options = [row for row in eligible_failures if row["dataset"] == old["dataset"] and row["category"] == old["category"] and (row["dataset"] != "mvtec_loco" or row["group"] == old["group"]) and row["path"] not in {case["path"] for case in selected}]
            if options:
                replacement = index, min(options, key=lambda row: row["path"])
                break
        checked(replacement is not None, "Failure coverage is impossible under the fixed quotas")
        selected[replacement[0]] = dict(replacement[1])
    for row in selected:
        row["selection_reason"] = "normal_false_positive" if row["is_normal_false_positive"] else "small_mask_failure" if row["is_micro_hard_case"] and row["is_real_failure"] else "real_failure" if row["is_real_failure"] else "small_mask_control" if row["is_micro_hard_case"] else "fixed_lexicographic_control"
        row["selection_fallback"] = None if row["is_real_failure"] else "No prioritized failure was selected within this category/group quota; retain the fixed small-mask or path-order control."
    for category in ("juice_bottle", "screw_bag"):
        checked({row["group"] for row in selected if row["dataset"] == "mvtec_loco" and row["category"] == category} == {"logical_anomalies", "structural_anomalies"}, "LOCO cases must show one logical and one structural anomaly")
    selected_paths = {row["path"] for row in selected}
    for row in candidates:
        row["selected"] = row["path"] in selected_paths
        row["candidate_reason"] = "eligible_failure" if row["is_real_failure"] else "small_mask_candidate" if row["is_micro_hard_case"] else "normal_or_success_control"
        row["rejection_reason"] = None if row["selected"] else "outside_LOCO_anomaly_group_quota" if not row["eligible_under_group_quota"] else "fixed_per_category_group_quota_and_priority"
    available_fp = any(row["is_normal_false_positive"] for row in candidates)
    eligible_fp = any(row["is_normal_false_positive"] and row["eligible_under_group_quota"] for row in candidates)
    checked(not eligible_fp or any(row["is_normal_false_positive"] for row in selected), "An eligible normal false positive was omitted")
    checked(any(row["is_micro_hard_case"] for row in selected) or not any(row["is_micro_hard_case"] and row["eligible_under_group_quota"] for row in candidates), "An available small-mask case was omitted")
    checked(len(selected) <= 16 and sum(row["is_real_failure"] for row in selected) >= required, "Deterministic case coverage is incomplete")
    return selected, {"candidates": candidates, "real_failures_available": len(eligible_failures), "real_failures_selected": sum(row["is_real_failure"] for row in selected), "normal_false_positive_available": available_fp, "normal_false_positive_selected": any(row["is_normal_false_positive"] for row in selected), "micro_hard_case_selected": any(row["is_micro_hard_case"] for row in selected), "fallback_policy": "Keep exact category/group quotas and deterministic path-order controls; no test threshold changes."}


def export_cases(root, staging, records, cases, mask_sources):
    import numpy as np
    from PIL import Image
    lookup = {record["identity_sha256"]: record for record in records}; display = {}
    for number, case in enumerate(cases, 1):
        case_id = f"{number:03d}"; prefix = "cases/" + case_id
        directory = inside(staging, prefix); directory.mkdir(parents=True)
        source = inside(root, "datasets/" + case["path"])
        shutil.copyfile(source, directory / "image.png")
        with Image.open(source) as opened:
            width, height = opened.size
        union = np.zeros((height, width), dtype=np.bool_); masks = []
        for index, item in enumerate(mask_sources.get(case["path"], []), 1):
            raw = inside(root, "datasets/" + item["path"])
            output = prefix + "/masks/" + f"{index:03d}" + ".png"
            target = inside(staging, output); target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(raw, target)
            with Image.open(raw) as opened:
                union |= np.asarray(opened.convert("L")) > 0
            masks.append({**item, "output_path": output})
        Image.fromarray(union.astype(np.uint8) * 255).save(directory / "mask_union.png")
        case.update({"case_id": case_id, "image_path": prefix + "/image.png", "mask_path": prefix + "/mask_union.png", "raw_image_sha256": sha(source), "mask_sources": masks, "maps": {}})
        for method, identifier in case["source_result_ids"].items():
            record = lookup[identifier]
            index = next(index for index, item in enumerate(record["samples"]["test"]) if item["path"] == case["path"])
            with np.load(record["directory"] / "predictions.npz", allow_pickle=False) as archive:
                if identifier not in display:
                    upper = float(np.percentile(archive["dev_maps"], 99.5))
                    display[identifier] = upper if upper > 0 else 1.0
                array = archive["test_maps"][index]
                checked(array.shape == (256, 256) and array.dtype == np.float32 and np.isfinite(array).all(), "Selected map must be finite FP32 256x256")
                np.save(directory / (method + "_map.npy"), array, allow_pickle=False)
            case["maps"][method] = {"path": prefix + "/" + method + "_map.npy", "display_min": 0.0, "display_max": display[identifier], "display_calibration": "normal development maps, percentile 99.5", "same_map_for_native_and_top_0.01": True}
        write(directory / "case.json", case)


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with local(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, lineterminator="\n"); writer.writeheader()
        for source in rows:
            writer.writerow({key: canonical(value) if isinstance(value, (dict, list)) or value is None else value for key, value in source.items()})


def verify_output(directory, *, complete=True):
    directory = local(directory); tables = read(directory / "tables.json"); validate_tables(tables)
    for name, expected in tables.items():
        with (directory / "tables" / (name + ".csv")).open(encoding="utf-8", newline="") as stream:
            observed = list(csv.DictReader(stream))
        checked(len(observed) == len(expected), "CSV and JSON table row counts differ")
        for left, right in zip(expected, observed):
            for key, value in left.items():
                text = canonical(value) if isinstance(value, (dict, list)) or value is None else str(value)
                checked(right[key] == text, "CSV and JSON table values differ")
    cases = read(directory / "cases.json")
    checked(len(cases["cases"]) <= 16 and all(inside(directory, row["image_path"]).is_file() and inside(directory, row["mask_path"]).is_file() for row in cases["cases"]), "Case output is incomplete")
    plot = read(directory / "plot_manifest.json")
    checked(plot.get("status") == "passed" and plot.get("figure_count") == len(plot.get("figures", [])) and bool(plot.get("figures")), "Plot manifest is missing or incomplete")
    for figure in plot["figures"]:
        checked(figure["alignment_status"] in ("passed", "not_applicable"), "Figure alignment failed")
        for name, record in figure["files"].items():
            path = inside(directory, name)
            checked(path.stat().st_size == record["bytes"] and sha(path) == record["sha256"], "Figure, source data or QA artifact changed")
    if complete:
        lines = (directory / "artifacts.sha256").read_text().splitlines(); seen = set()
        for line in lines:
            expected, name = line.split("  ", 1)
            checked(name not in seen and sha(inside(directory, name)) == expected, "Published output artifact changed")
            seen.add(name)
        actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
        checked(actual == seen | {"artifacts.sha256", "SUCCESS"}, "Output contains an unmanifested artifact")
        success = read(directory / "SUCCESS"); provenance = read(directory / "provenance.json")
        checked(success["status"] == "passed" and success["namespace"] == "analysis" and success["artifacts_sha256"] == sha(directory / "artifacts.sha256") and success["identity_sha256"] == digest(provenance["identity"]), "Output completion marker differs")
        checked(sha(directory / "inputs.json") == provenance["identity"]["inputs_sha256"] and sha(directory / "analysis_config.json") == provenance["identity"]["analysis_config_sha256"], "Output input/configuration bytes differ")
    return {"status": "passed", "result_count": 66, "analysis_rows": 108, "unique_pc_analysis_rows": 90, "case_count": len(cases["cases"]), "tables_verified": True, "figures_verified": True, "source_artifacts_verified": True, "pixel_metrics_recomputed": False}


def run(root, inputs, job):
    root = Path(root).absolute(); inputs = local(inputs); registry = read(inputs); config = read(inside(root, CONFIG))
    job_directory = inside(root, "run/validation_tc2_gpu/step8_job_" + job); job_directory.mkdir(parents=True, exist_ok=True)
    status_path = job_directory / "setup_status.json"
    publication = None
    if status_path.exists():
        old = read(status_path)
        checked(old.get("job_id") == job and old.get("inputs_sha256") == sha(inputs) and old.get("status") != "passed", "Existing analysis job state cannot be replaced")
        publication = old.get("publication")
    sources = source_hashes(root, config)
    identity = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "stage": "analysis", "job_id": job, "protocol_sha256": PROTOCOL, "design_sha256": registry["design_sha256"], "inputs_sha256": sha(inputs), "analysis_config_sha256": sha(inside(root, CONFIG)), "sources": sources}
    identifier = digest(identity); relative = "run/tc2_gpu/summaries/analysis/" + identifier
    status = {"mode": "tc2_gpu_analysis", "stage_id": "analysis", "job_id": job, "status": "running", "phase": "validation", "step_8_complete": False, "analysis_path": relative, "identity_sha256": identifier, "inputs_sha256": sha(inputs), "config_sha256": identity["analysis_config_sha256"], "protocol_sha256": PROTOCOL, "sources": sources, "results_count": 66, "analysis_rows": 108}
    if publication is not None:
        status["publication"] = publication
    write(status_path, status); shutil.copyfile(inputs, job_directory / "analysis_inputs.json"); write(job_directory / "analysis_sources.json", sources); write(job_directory / "plan.json", identity)
    target = inside(root, relative); target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name("." + identifier + ".partial." + job); lock = target.with_name(identifier + ".lock")
    try:
        runtime = runtime_gate(root, config, job); write(job_directory / "resources.json", runtime)
        checked(not target.exists() and not staging.exists(), "Analysis output already exists; existing artifacts are preserved")
        with lock.open("x") as stream:
            stream.write(job + "\n")
        staging.mkdir()
        records = validate_registry(root, registry)
        tables = aggregate_tables(records)
        tables["shared_extraction"] = []
        for cache in registry["caches"]:
            value = read(inside(root, cache["path"] + "/metadata.json"))
            tables["shared_extraction"].append({"dataset": cache["dataset"], "category": cache["category"], "cache_path": cache["path"], "metadata_sha256": cache["files"]["metadata.json"], "images": len(value["index"]), "cache_array_bytes": sum(math.prod(layer["shape"]) * 4 for layer in value["layers"].values()), "write_pipeline_seconds": value["write_pipeline_seconds"], **value["extraction"], "scope": "one shared extraction per category; never multiplied by fits"})
        areas, masks = masks_and_inputs(root, registry)
        tables["mask_areas"] = list(areas.values())
        points, decisions, distributions = score_context(records, areas, tables)
        cases, case_summary = select_cases(records, areas, decisions)
        export_cases(root, staging, records, cases, masks)
        shutil.copyfile(inputs, staging / "inputs.json"); shutil.copyfile(inside(root, CONFIG), staging / "analysis_config.json")
        provenance = {"identity": identity, "runtime": runtime, "source_artifacts_verified": True, "pixel_metrics_recomputed": False, "checkpoint_rows_deduplicated": 18, "model_storage_estimated": True, "timing_scope": "accepted cached-model timings; no new model execution", "accepted_job_resources": [{"stage_id": entry["stage_id"], "job_id": entry["job_id"], "acceptance_record": entry["acceptance_record"], "acceptance_sha256": entry["acceptance_sha256"], **entry["accepted_job_resources"]} for entry in registry["stages"]], "mask_size_policy": "category-local anomaly-area fraction quartile ranks, image-path ties", "finished_at_utc": datetime.now(timezone.utc).isoformat()}
        write(staging / "provenance.json", provenance); write(staging / "tables.json", tables)
        (staging / "tables").mkdir()
        for name, rows in tables.items():
            write_csv(staging / "tables" / (name + ".csv"), rows)
        case_output = {"schema_version": "1.0", "selection_policy": config["case_policy"], "cases": cases, **case_summary}
        write(staging / "cases.json", case_output)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from plot_results_tc2_gpu import render_analysis
        context = {"tables": tables, "cases": cases, "resources": tables["resources"], "score_distributions": distributions, "mask_areas": list(areas.values()), "provenance": provenance}
        render_analysis(root, staging, context)
        verification = verify_output(staging, complete=False); write(staging / "verification.json", verification)
        checked(source_hashes(root, config) == sources and "torch" not in sys.modules, "Analysis source or CPU-only import boundary changed")
        files = sorted(path.relative_to(staging).as_posix() for path in staging.rglob("*") if path.is_file())
        (staging / "artifacts.sha256").write_text("".join(sha(inside(staging, name)) + "  " + name + "\n" for name in files), encoding="utf-8", newline="\n")
        write(staging / "SUCCESS", {"status": "passed", "namespace": "analysis", "job_id": job, "identity_sha256": identifier, "artifacts_sha256": sha(staging / "artifacts.sha256")})
        verify_output(staging)
        checked(not target.exists(), "Immutable output destination appeared during analysis")
        staging.rename(target)
        status.update({"status": "passed", "phase": "complete", "step_8_complete": True, "finished_at_utc": datetime.now(timezone.utc).isoformat(), "verification": verification})
        write(status_path, status)
        lock.unlink()
        return status
    except Exception as error:
        status.update({"status": "failed", "phase": "failed", "step_8_complete": False, "error": type(error).__name__ + ": " + str(error)})
        write(status_path, status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    planning = commands.add_parser("plan"); planning.add_argument("--root", required=True); planning.add_argument("--output", required=True)
    execution = commands.add_parser("run"); execution.add_argument("--root", required=True); execution.add_argument("--inputs", required=True); execution.add_argument("--job-id", required=True)
    args = parser.parse_args()
    if args.action == "plan":
        destination = local(args.output); checked(not destination.exists(), "Input registry output must be fresh")
        value = plan(args.root); write(destination, value)
        result = {"status": "planned", "path": str(args.output), "sha256": sha(destination), "results": 66, "analysis_rows": 108}
    else:
        result = run(args.root, args.inputs, args.job_id)
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
