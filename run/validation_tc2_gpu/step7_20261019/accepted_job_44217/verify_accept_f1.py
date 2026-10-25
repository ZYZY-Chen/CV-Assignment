"""Verify the complete F1 collection and bind the partial-result audit evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
ROOT = AUDIT.parents[2]
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_194921_ca2d69de")
INDEX_SHA = "4E4DD33CE5985443B63F614D9B49949E8B8B665A74BD1AFA554B584945BD3FD1"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as collector
from pilot_tc2_gpu import atomic_json

read = lambda path: json.loads(collector._extended(path).read_text(encoding="utf-8"))
sha = collector._sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


ledger = read(AUDIT / "setup_status.json")
design = read(ROOT / "configs/experiments_tc2_gpu.json")
spec = next(row for row in design["stages"] if row["stage_id"] == "F1")
index_path = SOURCE / "experiments-index.json"
index_check = collector.verify_index(index_path, INDEX_SHA, "44217")
index = read(index_path)
for page in index["pages"]:
    archive = SOURCE / page["name"]
    require(sha(archive) == page["sha256"] and archive.stat().st_size == page["bytes"], "Archive bytes differ")
collection = collector.verify_collection(index_path, SOURCE / "remote", "44217")
require(collection["status"] == "verified" and collection["stage_id"] == "F1" and collection["partial"] is False
        and collection["stage_complete"] is True and collection["step_7_complete"] is False
        and collection["result_count"] == 8 and collection["analysis_count"] == 0 and collection["page_count"] == 2,
        "Completed collection scope differs")
page_root = SOURCE / "remote/page_001"
job_root = page_root / "run/validation_tc2_gpu/step7_job_44217"
remote, resources = read(job_root / "setup_status.json"), read(job_root / "resources.json")
require(remote["mode"] == "formal_experiment_stage" and remote["stage_id"] == "F1" and remote["job_id"] == "44217"
        and remote["status"] == "passed" and remote["stage_complete"] is True and remote["step_7_complete"] is False,
        "Unexpected completed stage state")
require([row["run_key"] for row in remote["results"]] == spec["run_keys"]
        and all(row["run_status"] == "completed" and row["verified"] is True and row["accepted_pilot_reuse"] is False
                for row in remote["results"]) and remote["analyses"] == [], "Returned results differ from the planned prefix")
expected_phases = ["phase_%03d_extract" % number for number in range(1, 3)]
expected_phases += ["phase_%03d_%s" % (number, "run" if number % 2 else "verify") for number in range(3, 19)]
require([row["phase"] for row in remote["phases"]] == expected_phases
        and all(row["exit_code"] == 0 for row in remote["phases"]), "Completed phases differ")
require(ledger["verified_formal_fits"] == 54 and ledger["core_checkpoint_complete"] is True
        and [row["stage_id"] for row in ledger["accepted_step_7_stages"]] == ["B0", "H1", "H2", "C1", "I1_seed17", "R0", "C1R", "C2"],
        "Prior local acceptance differs")
chain = remote["preflight"]["completed_stages"]
require([row["stage_id"] for row in chain] == [row["stage_id"] for row in ledger["accepted_step_7_stages"]],
        "Prior stage chain differs")
for embedded, accepted in zip(chain, ledger["accepted_step_7_stages"]):
    accepted_path = ROOT / accepted["record"]
    raw_path = accepted_path.parent / "remote_setup_status.json"
    previous = read(raw_path)
    require(sha(accepted_path) == accepted["record_sha256"]
            and sha(raw_path) == accepted["remote_status_sha256"] == embedded["status_sha256"]
            and all(embedded[key] == previous[key] for key in
                    ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")),
            "An accepted predecessor changed")
dependency = {"stage_id": "C2", "job_id": "44198",
              "status_sha256": ledger["accepted_step_7_stages"][-1]["remote_status_sha256"]}
require(remote["predecessor"] == remote["preflight"]["predecessor"] == dependency
        and remote["preflight"]["status"] == "passed", "Predecessor differs")
require(remote["experiment_sources"] == ledger["experiment_sources"]
        and remote["design_sha256"] == sha(ROOT / "configs/experiments_tc2_gpu.json") == ledger["design_sha256"],
        "Experiment identity differs")
protected = {**remote["experiment_sources"], **design["scientific_source_hashes"], **design["pilot_source_hashes"]}
require(all(sha(ROOT / name) == value for name, value in protected.items()), "A protected source changed")
source_receipt = read(job_root / "experiment_sources.json")
require(source_receipt["files"] == remote["experiment_sources"] and source_receipt["submission"] == remote["submission"]
        and remote["submission"]["source_sha256"] == remote["submission"]["submitted_sha256"]
        == ledger["experiment_sources"]["scripts/slurm/experiments_tc2_gpu.sh"], "Publication identity differs")
require(read(job_root / "plan.json") == {"stage": spec, "design_sha256": remote["design_sha256"]}, "Stage plan differs")
prior_gpu = read(AUDIT / "accepted_job_44103/remote_setup_status.json")
require(resources["requested"] == spec["resources"] and resources["runtime"] == remote["runtime"]
        and all(remote["runtime"][key] == value for key, value in prior_gpu["runtime"].items() if key != "slurm_job_id")
        and remote["runtime"]["slurm_job_id"] == "44217"
        and resources["slurm_environment"] == {"SLURM_JOB_ID": "44217", "SLURM_JOB_PARTITION": "MGPU-TC2",
            "SLURM_JOB_NODELIST": "TC2N01", "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_NODE": "24576",
            "SLURM_JOB_QOS": "normal"}, "Actual resources or runtime differ")
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8-sig")
require(re.search(r"(?m)^44217\s+\S+\s+COMPLETED\s+0:0\s+00:18:21\s+TC2N01\s+2\s+24G", terminal)
        and re.search(r"(?m)^44217\.batch\s+batch\s+COMPLETED\s+0:0\s+00:18:21\s+TC2N01\s+2\s+5263968K", terminal),
        "Successful SLURM completion is absent")
files = {}
for page in index["pages"]:
    directory = SOURCE / "remote" / ("page_%03d" % page["page_number"])
    for row in read(directory / "experiments_export_manifest.json")["files"]:
        require(row["path"] not in files or files[row["path"]] == row["sha256"], "Repeated page metadata differs")
        files[row["path"]] = row["sha256"]
require(len(files) == 120, "Unexpected payload coverage")
prior_cache_stage = read(AUDIT / "accepted_job_44103/remote_setup_status.json")
require(remote["caches"] == prior_cache_stage["caches"], "Cache identities differ from accepted C1")
caches = []
for row in remote["caches"]:
    meta_path = page_root / row["path"] / "metadata.json"
    metadata = read(meta_path)
    require(sha(meta_path) == row["metadata_sha256"]
            and all(layer["dtype"] == "float32" for layer in metadata["layers"].values()), "Cache metadata differs")
    caches.append({"category": row["identity"]["category"], "images": len(metadata["index"]),
                   "metadata_sha256": row["metadata_sha256"]})
require(len(caches) == 2 and sum(row["images"] for row in caches) == 854, "Cache coverage differs")
arrays, metrics = read(HERE / "saved_arrays_verification.json"), read(HERE / "independent_image_metrics.json")
require(arrays["status"] == "passed" and arrays["job_id"] == "44217" and arrays["stage_id"] == "F1"
        and arrays["results_checked"] == 8 and arrays["maps_checked"] == 1676
        and arrays["index_sha256"] == INDEX_SHA and arrays["design_sha256"] == remote["design_sha256"]
        and arrays["audit_script_sha256"] == sha(HERE / "check_saved_arrays.py")
        and arrays["map_derived_score_vectors_checked"] == 72
        and arrays["weighted_patchcore_native_vectors_checked_for_finite_dtype_shape_only"] == 8, "Array audit differs")
require(metrics["status"] == "passed" and metrics["stage_id"] == "F1" and metrics["result_count"] == 8
        and metrics["rule_count"] == 40 and metrics["maximum_absolute_error"] <= 1e-12, "Metric audit differs")
lookup = {row["identity_sha256"]: row for row in remote["results"]}
require({row["result_identity_sha256"] for row in arrays["results"]} == set(lookup)
        == {row["identity_sha256"] for row in metrics["results"]}, "Independent result coverage differs")
for row in arrays["results"]:
    result = lookup[row["result_identity_sha256"]]
    require(row["run_key"] == result["run_key"] and row["configuration_matches_frozen_fit"] is True,
            "Array configuration differs")
    for field, name in (("predictions_sha256", "predictions.npz"), ("samples_sha256", "samples.json"),
                        ("configuration_file_sha256", "config.yaml"), ("evidence_sha256", "evidence.json"),
                        ("artifact_manifest_sha256", "artifacts.sha256")):
        require(row[field] == files[result["path"] + "/" + name], "Array evidence refers to different bytes")
    require(row["cache_metadata_sha256"] == next(value["metadata_sha256"] for value in caches if value["category"] == result["category"])
            and row["frozen_manifest_sha256"] == design["scientific_source_hashes"]["manifests/manifest_mvtec_ad_" + result["category"] + ".json"],
            "Array input identity differs")
for row in metrics["results"]:
    result = lookup[row["identity_sha256"]]
    require(row["relative_path"] == result["path"] and row["max_abs_error"] <= 1e-12 and row["rule_count"] == 5,
            "Metric identity or coverage differs")
    for name, value in row["artifact_hashes"].items():
        require(value == files[result["path"] + "/" + name], "Metric evidence refers to different bytes")
require(metrics["job_id"] == "44217" and metrics["index_sha256"] == INDEX_SHA
        and metrics["design_sha256"] == remote["design_sha256"]
        and metrics["audit_script_sha256"] == sha(HERE / "independent_image_metrics_check.py"), "Metric evidence binding differs")
require(arrays["results_array_values_rechecked"] == 8 and arrays["results_previous_array_audit_reused"] == 0
        and metrics["prior_recomputation_reused_after_exact_hash_match"] == 0
        and metrics["newly_recomputed_from_final_snapshot"] == 8, "All eight results require independent checks")
b0_root = AUDIT / "accepted_job_44053"
require(arrays["accepted_b0_verification_sha256"] == sha(b0_root / "verification.json"), "Baseline acceptance differs")
b0_results = {row["run_key"]: row for row in read(b0_root / "remote_setup_status.json")["results"]}
b0_files = read(b0_root / "archive_file_hashes.json")
nesting = arrays["nested_training_subsets"]
require({row["category"] for row in nesting} == {"cable", "screw"} and len(nesting) == 2, "Nested subset coverage differs")
for row in nesting:
    require(row["seed"] == 17 and all(row[key] is True for key in ("n20_equals_first_20_of_n50",
        "n50_equals_first_50_of_n100", "both_methods_identical", "n100_matches_accepted_b0")), "Few-shot nesting differs")
    require(len(row["baseline_samples"]) == 2, "Both baseline methods must be bound")
    for baseline in row["baseline_samples"]:
        result = b0_results[baseline["run_key"]]
        require(result["category"] == row["category"] and result["run_seed"] == 17 and baseline["fit_count"] == 100
                and baseline["samples_sha256"] == b0_files[result["path"] + "/samples.json"], "A nested baseline input changed")
require(remote["cumulative_fits"] == 62 and spec["expected_cumulative_fits"] == 62 and spec["planned_new_fits"] == 8,
        "Cumulative fit count differs")
require([row["stage_id"] for row in remote["completed_stages"]] == [row["stage_id"] for row in chain] + ["F1"]
        and remote["completed_stages"][:-1] == chain, "Completed stage chain differs")
for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses"):
    require(remote["completed_stages"][-1][key] == remote[key], "Embedded F1 summary differs")
require(remote["checkpoints"] == ledger["checkpoints"], "The standard checkpoint still requires I2 analysis")
next_spec = next(row for row in design["stages"] if row["stage_id"] == "I1_all_seeds")
require(next_spec["kind"] == "analysis" and next_spec["predecessor"] == "F1" and next_spec["planned_new_fits"] == 0
        and len(next_spec["source_run_keys"]) == 18 and next_spec["score_rules"] == ["native", "max", "top_0.01"]
        and next_spec["expected_rows"] == 54 and next_spec["expected_cumulative_fits"] == 62
        and next_spec["resources"]["gpus"] == 0, "Next approved CPU analysis differs")
helper = SOURCE.parent / "tc2_gpu_setup.ps1"
require(sha(helper) == ledger["external_helper_sha256"], "External helper changed")
command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{helper}" -Action RunExperiments -Stage I1_all_seeds'
for source, name in [(SOURCE / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
    (job_root / "setup_status.json", "remote_setup_status.json"), (job_root / "resources.json", "resources.json"),
    (job_root / "plan.json", "remote_plan.json"), (job_root / "result_summary.json", "result_summary.json"),
    (AUDIT / "setup_status.json", "previous_step7_status.json")]:
    with (HERE / name).open("xb") as stream:
        stream.write(collector._extended(source).read_bytes())
with (HERE / "archive_file_hashes.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(files, stream, indent=2)
    stream.write("\n")
locations = {key: str(SOURCE / "remote" / ("page_%03d" % page["page_number"]))
             for page in index["pages"] for key in page["result_ids"]}
now = datetime.now(timezone.utc).isoformat()
value = {"status": "passed", "stage_id": "F1", "job_id": "44217", "stage_complete": True, "step_7_complete": False,
    "accepted_at_utc": now, "slurm_state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:18:21",
    "node": "TC2N01", "slurm_max_rss_kib": 5263968, "source_directory": str(SOURCE), "index_sha256": INDEX_SHA,
    "index_verification": index_check, "collection_verification": collection, "pages_verified": 2,
    "unique_payload_files_verified": len(files), "results_verified": 8, "new_fits_verified": 8,
    "cumulative_formal_fits": 62, "phases_passed": 18, "predecessor": dependency,
    "design_sha256": remote["design_sha256"], "experiment_sources": remote["experiment_sources"],
    "protected_sources_checked": len(protected), "runtime": remote["runtime"], "resources": resources, "caches": caches,
    "independent_saved_maps_checked": 1676, "independent_score_vectors_checked": 80,
    "independent_image_rule_evaluations": 40, "maximum_independent_image_metric_absolute_error": metrics["maximum_absolute_error"],
    "nested_training_subsets": nesting, "all_eight_result_audits_newly_recomputed": True,
    "reports": {name: sha(HERE / name) for name in ("saved_arrays_verification.json", "independent_image_metrics.json",
        "archive_file_hashes.json", "check_saved_arrays.py", "independent_image_metrics_check.py")},
    "remote_status_sha256": sha(HERE / "remote_setup_status.json"), "result_page_locations": locations,
    "results": remote["results"], "core_checkpoint_complete": True, "standard_checkpoint_complete": False,
    "checkpoints": remote["checkpoints"],
    "remote_full_result_verification": "All eight original-resolution pixel-metric and full-cache saved-result verifications passed on TC2.",
    "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
    "weighted_native_score_limitation": "Eight weighted PatchCore native vectors were checked for FP32 dtype, finite values and shape; maps alone do not reconstruct nearest-neighbor support weights.",
    "next_stage": "I1_all_seeds", "next_stage_fits": 0, "next_stage_analysis_rows": 54, "next_user_terminal_command": command,
    "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
ledger["accepted_step_7_stages"].append({"stage_id": "F1", "job_id": "44217", "stage_complete": True,
    "verified_fits": 8, "record": "run/validation_tc2_gpu/step7_20261019/accepted_job_44217/verification.json",
    "record_sha256": sha(HERE / "verification.json"), "remote_status_sha256": value["remote_status_sha256"], "index_sha256": INDEX_SHA})
ledger.update(status="awaiting_I1_all_seeds_submission", remote_acceptance="B0_H1_H2_C1_I1_seed17_R0_C1R_C2_F1_accepted_remaining_stages_pending",
    recorded_at_utc=now, step_7_complete=False, verified_formal_fits=62, verified_new_fits=60, remaining_formal_fits=4,
    next_stage="I1_all_seeds", next_stage_new_fits=0, next_stage_pilot_verifications=0, next_stage_analysis_rows=54,
    next_user_terminal_command=command,
    next_acceptance="Verify the completed I1_all_seeds CPU analysis, all 54 rows and the returned collection before I2. The standard checkpoint remains incomplete until I2 passes.",
    next_action="Submit the approved I1_all_seeds CPU analysis from the user terminal and return its output for review.",
    latest_attempt={"job_id": "44217", "stage_id": "F1", "node": "TC2N01", "slurm_state": "COMPLETED", "exit_code": "0:0",
        "stage_complete": True, "verified_result_count": 8,
        "verification": "run/validation_tc2_gpu/step7_20261019/accepted_job_44217/verification.json"})
atomic_json(AUDIT / "setup_status.json", ledger)
print(json.dumps({key: value[key] for key in ("status", "stage_id", "stage_complete", "results_verified",
    "cumulative_formal_fits", "pages_verified", "unique_payload_files_verified", "next_stage", "next_stage_analysis_rows")}, indent=2))
