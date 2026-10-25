"""Audit I1 all-seed provenance and table structure independently without loading arrays."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import io
import json
import math
import sys

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
sys.path.insert(0, str(ROOT / "scripts"))
from collect_experiments_tc2_gpu import _extended

OUTPUT = _extended(Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_195436_8b9162cf"))
BASE = OUTPUT / "remote/page_001"
IDENTIFIER = "B1109EDA0A660F81E39B6B9E04CA2B60C917F65EEBBDDEDA08E22B608A818AD7"
DIRECTORY = BASE / "run/tc2_gpu/summaries/I1_all_seeds" / IDENTIFIER
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019/accepted_job_44227"
FIELDS = ("stage", "run_key", "dataset", "category", "method", "run_seed", "score_rule", "n_dev", "n_good", "n_anomaly",
          "image_auroc", "image_ap", "threshold_95pct", "normal_fpr", "anomaly_recall", "per_defect_recall",
          "delta_image_auroc_vs_native", "delta_image_ap_vs_native", "delta_normal_fpr_vs_native", "delta_anomaly_recall_vs_native",
          "result_path", "result_identity_sha256", "pixel_metrics_reference")
RESULT_FILES = ("config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with _extended(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def read(path):
    return json.loads(_extended(path).read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest().upper()


def manifest(directory, filename, names):
    lines = _extended(directory / filename).read_text(encoding="utf-8").splitlines()
    result = {}
    for line in lines:
        value, name = line.split(None, 1)
        check(name in names and name not in result, "Duplicate/unexpected manifest artifact")
        check(sha(directory / name) == value, "Artifact hash mismatch: " + name)
        result[name] = value
    check(set(result) == set(names), "Incomplete artifact manifest")
    return result


def main():
    index_path = OUTPUT / "experiments-index.json"
    index_sha = sha(index_path)
    check(index_sha == "C94A020C0B6B89B51BB7DB1D39528506ACCCBD0437CA441CFD951937C7697A82", "Wrong pinned export index")
    design_path = ROOT / "configs/experiments_tc2_gpu.json"
    design = read(design_path)
    check(sha(design_path) == read(index_path)["config_sha256"], "Design/export mismatch")
    stage = next(row for row in design["stages"] if row["stage_id"] == "I1_all_seeds")
    check(stage["kind"] == "analysis" and stage["run_keys"] == [] and stage["expected_rows"] == 54, "Wrong analysis scope")
    check(stage["score_rules"] == ["native", "max", "top_0.01"] and len(stage["source_run_keys"]) == 18, "Wrong rule/source scope")
    fits = {row["run_key"]: row["configuration"] for row in design["fits"]}
    check(all(fits[key]["stage"] in ("B0", "R0") and fits[key]["method"] == "patchcore" and fits[key]["run_seed"] in (17, 29, 43) and fits[key]["normal_train_n"] == 100
              for key in stage["source_run_keys"]), "Analysis source is outside frozen baseline PatchCore selection")
    check({p.name for p in DIRECTORY.iterdir()} == {"analysis.json", "analysis.csv", "evidence.json", "analysis.sha256", "SUCCESS"}, "Unexpected analysis directory members")
    analysis_hashes = manifest(DIRECTORY, "analysis.sha256", ("analysis.json", "analysis.csv", "evidence.json"))
    check(read(DIRECTORY / "SUCCESS") == {"status": "passed", "namespace": "formal", "identity_sha256": IDENTIFIER,
          "analysis_manifest_sha256": sha(DIRECTORY / "analysis.sha256")}, "Wrong analysis success marker")
    evidence, analysis = read(DIRECTORY / "evidence.json"), read(DIRECTORY / "analysis.json")
    identity = evidence["identity"]
    check(digest(identity) == IDENTIFIER == analysis["identity_sha256"], "Analysis canonical identity mismatch")
    check(identity["namespace"] == "formal" and identity["stage"] == analysis["stage"] == "I1_all_seeds", "Wrong namespace/stage")
    check(identity["protocol_sha256"] == design["protocol_sha256"], "Wrong frozen protocol")
    source_hashes = {name: sha(ROOT / name) for name in ("scripts/analyze_scores_tc2_gpu.py", "configs/experiments_tc2_gpu.json",
                                                       "src/metric_core.py", "src/tc2_gpu_protocol.py")}
    check(identity["analysis_sources"] == source_hashes, "Analysis source code/design identity mismatch")
    check(identity["score_rules"] == analysis["score_rules"] == stage["score_rules"], "Rule ordering mismatch")
    check(identity["rows_sha256"] == digest(analysis["rows"]), "Rows canonical digest mismatch")
    check(analysis["source_count"] == 18 and analysis["row_count"] == len(analysis["rows"]) == 54, "Wrong row count")
    check(identity["image_metric_abs_tolerance"] == 1e-12 and analysis["metric_policy"] == identity["metric_policy"], "Metric policy mismatch")
    check(identity["metric_policy"] == {"version": "tc2_gpu_tie_grouped", "ties": "equal-score threshold groups",
          "threshold_percentile": 95.0, "percentile_method": "linear", "decision": "score > threshold",
          "pixel_scope": "all pixels at original resolution"}, "Unexpected metric policy")
    check([source["run_key"] for source in identity["sources"]] == stage["source_run_keys"], "Source order/uniqueness mismatch")
    acceptances = {}
    for accepted_stage, job_id, expected_count in (("B0", "44053", 12), ("R0", "44121", 24)):
        path = ROOT / ("run/validation_tc2_gpu/step7_20261019/accepted_job_" + job_id + "/verification.json")
        value = read(path)
        check(value["status"] == "passed" and value["stage_complete"] and value["results_verified"] == expected_count, "Baseline acceptance missing")
        for name, expected_hash in value["reports"].items():
            check(sha(path.parent / name) == expected_hash, "Accepted baseline audit changed: " + name)
        acceptances[accepted_stage] = {"path": path, "value": value, "sha256": sha(path)}
    accepted_records = {row["run_key"]: row for item in acceptances.values() for row in item["value"]["results"]}
    source_reports, saved_metrics, sample_counts = [], {}, {}
    for source in identity["sources"]:
        key = source["run_key"]
        prior = accepted_records[key]
        accepted = acceptances[fits[key]["stage"]]["value"]
        check(source["configuration"] == fits[key], "Frozen source configuration mismatch")
        check(source["path"] == prior["path"] and source["identity_sha256"] == prior["identity_sha256"], "Accepted baseline result identity mismatch")
        old_base = _extended(Path(accepted["result_page_locations"][key]))
        old_result = old_base / source["path"]
        file_hashes = manifest(old_result, "artifacts.sha256", RESULT_FILES)
        check(source["artifact_hashes"] == file_hashes and source["artifacts_sha256"] == sha(old_result / "artifacts.sha256"), "Analysis references changed baseline artifacts")
        check(read(old_result / "SUCCESS") == {"status": "passed", "namespace": "formal", "identity_sha256": source["identity_sha256"],
              "artifacts_sha256": source["artifacts_sha256"]}, "Source success marker mismatch")
        source_evidence = read(old_result / "evidence.json")
        source_identity = source_evidence["identity"]
        check(digest(source_identity) == source["identity_sha256"] and source_identity["configuration"] == fits[key], "Source scientific identity mismatch")
        cfg = fits[key]
        frozen_name = "manifests/manifest_%s_%s.json" % (cfg["dataset"], cfg["category"])
        frozen_hash = design["scientific_source_hashes"][frozen_name]
        check(sha(BASE / frozen_name) == sha(old_base / frozen_name) == frozen_hash == source_identity["manifest_sha256"], "Frozen source manifest changed")
        frozen = read(BASE / frozen_name)
        check(frozen["split_hash"] == source_identity["split_hash"], "Frozen split mismatch")
        cache = source["cache_metadata"]
        for name, field in (("metadata.json", "metadata_sha256"), ("COMPLETE", "complete_sha256")):
            check(sha(BASE / cache["path"] / name) == sha(old_base / cache["path"] / name) == cache[field], "Analysis source cache metadata changed")
        check(cache["metadata_sha256"] == source_identity["cache"]["metadata_sha256"], "Cache/result binding mismatch")
        cache_meta = read(BASE / cache["path"] / "metadata.json")
        check(digest(cache_meta["identity"]) == source_identity["cache"]["cache_id"], "Cache identity mismatch")
        check(cache_meta["identity"] == source_evidence["cache_identity"], "Cache scientific identity mismatch")
        check(read(old_result / "validation.json")["saved_metric_reproduction"] is True, "Source full validation missing")
        groups = read(old_result / "samples.json")
        sample_counts[key] = {"n_dev": len(groups["dev"]), "n_good": sum(x["label"] == 0 for x in groups["test"]),
                              "n_anomaly": sum(x["label"] == 1 for x in groups["test"])}
        saved_metrics[key] = read(old_result / "metrics.json")
        source_reports.append({"run_key": key, "result_identity_sha256": source["identity_sha256"], "path": source["path"],
                               "accepted_source_stage": cfg["stage"], "accepted_source_page": accepted["result_page_locations"][key], "artifact_hashes": file_hashes,
                               "artifact_manifest_sha256": source["artifacts_sha256"], "frozen_manifest_sha256": frozen_hash,
                               "split_hash": frozen["split_hash"], "cache_metadata": cache})
    pairs = [(key, rule) for key in stage["source_run_keys"] for rule in stage["score_rules"]]
    check([(row["run_key"], row["score_rule"]) for row in analysis["rows"]] == pairs, "Row ordering/uniqueness mismatch")
    delta_fields_checked = 0
    for row in analysis["rows"]:
        key, rule = row["run_key"], row["score_rule"]
        source = next(value for value in identity["sources"] if value["run_key"] == key)
        cfg = fits[key]
        check(set(row) == set(FIELDS), "Unexpected row fields")
        check(row["stage"] == "I1_all_seeds" and all(row[field] == cfg[field] for field in ("dataset", "category", "method", "run_seed")), "Row metadata mismatch")
        check(all(row[field] == value for field, value in sample_counts[key].items()), "Row sample counts mismatch")
        check(row["result_path"] == source["path"] and row["result_identity_sha256"] == source["identity_sha256"], "Row/source identity mismatch")
        metric, native = saved_metrics[key]["image"][rule], saved_metrics[key]["image"]["native"]
        check(all(row[field] == value for field, value in metric.items()), "Analysis differs from source saved image metric")
        for field in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall"):
            actual = row["delta_" + field + "_vs_native"]
            check(math.isfinite(actual) and abs(actual - (metric[field] - native[field])) <= 1e-12, "Wrong native-relative delta")
            delta_fields_checked += 1
        check(row["pixel_metrics_reference"] == {"path": source["path"] + "/metrics.json", "sha256": source["artifact_hashes"]["metrics.json"],
              "field": "pixel", "validation_path": source["path"] + "/validation.json", "validation_sha256": source["artifact_hashes"]["validation.json"],
              "recomputed_by_analysis": False}, "Pixel reference is not bound to accepted source")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in analysis["rows"]:
        copy = dict(row)
        for field in ("per_defect_recall", "pixel_metrics_reference"):
            copy[field] = canonical(copy[field])
        writer.writerow(copy)
    check(_extended(DIRECTORY / "analysis.csv").read_text(encoding="utf-8") == buffer.getvalue(), "CSV/JSON content or ordering mismatch")
    check(evidence["validation"] == {"source_artifacts_verified": True, "image_metrics_recomputed": True,
          "image_metric_abs_tolerance": 1e-12, "pixel_metrics_recomputed": False, "feature_arrays_loaded": False}, "Analysis validation declaration mismatch")
    runtime = evidence["runtime"]
    check(runtime["device"] == "cpu" and runtime["slurm_job_id"] == "44227" and runtime["cpu_threads"] == "2", "CPU/job runtime mismatch")
    for flag in ("torch_imported_by_analysis", "map_arrays_loaded", "feature_arrays_loaded", "pixel_metrics_recomputed"):
        check(runtime[flag] is False, "Unexpected analysis runtime activity declaration")
    status_path = BASE / "run/validation_tc2_gpu/step7_job_44227/setup_status.json"
    status = read(status_path)
    check(status["status"] == "passed" and status["stage_complete"] and status["results"] == [], "Analysis stage unexpectedly fitted results")
    check(len(status["phases"]) == 1 and status["phases"][0]["phase"] == "phase_001_analyze" and status["phases"][0]["exit_code"] == 0, "Unexpected fit/extract phase")
    check(status["runtime"]["device"] == "cpu" and status["runtime"]["torch_imported"] is False, "Unexpected controller runtime")
    all_hashes = {name: sha(DIRECTORY / name) for name in ("analysis.json", "analysis.csv", "evidence.json", "analysis.sha256", "SUCCESS")}
    report = {"status": "passed", "job_id": "44227", "stage_id": "I1_all_seeds", "created_utc": datetime.now(timezone.utc).isoformat(),
              "index_sha256": index_sha, "design_sha256": sha(design_path), "analysis_identity_sha256": IDENTIFIER,
              "analysis_artifact_hashes": all_hashes, "audit_script_sha256": sha(Path(__file__)),
              "accepted_stage_verifications": {key: {"path": str(value["path"]), "sha256": value["sha256"]} for key, value in acceptances.items()}, "remote_status_sha256": sha(status_path),
              "source_count": 18, "row_count": 54, "delta_fields_checked": delta_fields_checked,
              "canonical_identity_passed": True, "completion_manifest_passed": True, "csv_json_exact_match": True,
              "row_order_and_uniqueness_passed": True, "source_artifacts_identical_to_accepted_baselines": True,
              "cpu_no_refit_declarations_consistent": True, "analysis_source_hashes": source_hashes, "sources": source_reports,
              "limitations": ["This provenance audit compares saved metrics and relative deltas; independent score-based metric recomputation is a separate audit.",
                              "No-refit and no-array-load findings rely on the accepted code, hash-bound runtime declarations and single analysis phase; this is not an operating-system execution trace.",
                              "Source NPZ files were streamed only for SHA256; arrays, raw images, raw masks and cache NPY layers were not loaded, and pixel metrics were not recomputed."]}
    AUDIT.mkdir(parents=True, exist_ok=True)
    with (AUDIT / "analysis_provenance_verification.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "source_count", "row_count", "delta_fields_checked")}), flush=True)


if __name__ == "__main__":
    main()
