"""Verify the completed C1 collection and bind independent acceptance evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT, AUDIT = HERE.parents[3], HERE.parent
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_164545_67ec5487")
INDEX_SHA = "5565885339EC2C84F2669F5569EFAE63CE2219A300ACBF5E435AF1E031761722"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as collector
from pilot_tc2_gpu import atomic_json

read = lambda path: json.loads(collector._extended(path).read_text(encoding="utf-8"))
sha = collector._sha


def require(condition, message):
    if not condition:
        raise ValueError(message)


design = read(ROOT / "configs/experiments_tc2_gpu.json")
local = read(AUDIT / "setup_status.json")
spec = next(row for row in design["stages"] if row["stage_id"] == "C1")
next_spec = next(row for row in design["stages"] if row["stage_id"] == "I1_seed17")
require([row["stage_id"] for row in local["accepted_step_7_stages"]] == ["B0", "H1", "H2"], "Unexpected prior local acceptance")
require(local["verified_formal_fits"] == 20 and local["step_7_complete"] is False, "Unexpected prior fit count")
index_path = SOURCE / "experiments-index.json"
index_check = collector.verify_index(index_path, INDEX_SHA, "44103")
index = read(index_path)
for page in index["pages"]:
    archive = SOURCE / page["name"]
    require(sha(archive) == page["sha256"] and archive.stat().st_size == page["bytes"], "Archive bytes differ from the pinned index")
collection = collector.verify_collection(index_path, SOURCE / "remote", "44103")
require(collection["stage_id"] == "C1" and collection["partial"] is False and collection["stage_complete"] is True
        and collection["step_7_complete"] is False and collection["result_count"] == 2
        and collection["analysis_count"] == 0 and collection["page_count"] == 2, "Incomplete C1 collection")
page_root = SOURCE / "remote/page_001"
job_root = page_root / "run/validation_tc2_gpu/step7_job_44103"
remote, resources = read(job_root / "setup_status.json"), read(job_root / "resources.json")
require(remote["mode"] == "formal_experiment_stage" and remote["stage_id"] == "C1" and remote["job_id"] == "44103"
        and remote["status"] == "passed" and remote["stage_complete"] is True and remote["step_7_complete"] is False
        and remote["cumulative_fits"] == 22, "Unexpected completed C1 state")
require([row["run_key"] for row in remote["results"]] == spec["run_keys"]
        and all(row["verified"] is True and row["run_status"] == "completed" and row["accepted_pilot_reuse"] is False
                for row in remote["results"]) and remote["analyses"] == [], "C1 results differ from the frozen plan")
require([row["phase"] for row in remote["phases"]] == [
    "phase_001_extract", "phase_002_extract", "phase_003_run",
    "phase_004_verify", "phase_005_run", "phase_006_verify"]
    and all(row["exit_code"] == 0 for row in remote["phases"]), "A C1 phase did not complete")
prior_path = AUDIT / "accepted_job_44086/remote_setup_status.json"
prior = read(prior_path)
dependency = {"stage_id": "H2", "job_id": "44086", "status_sha256": sha(prior_path)}
require(remote["predecessor"] == dependency == remote["preflight"]["predecessor"]
        and remote["preflight"]["status"] == "passed", "C1 predecessor differs")
require([row["stage_id"] for row in remote["completed_stages"]] == ["B0", "H1", "H2", "C1"], "Completed chain differs")
for embedded, accepted in zip(remote["completed_stages"][:-1], local["accepted_step_7_stages"]):
    accepted_path = ROOT / accepted["record"]
    raw_path = accepted_path.parent / "remote_setup_status.json"
    accepted_remote = read(raw_path)
    require(sha(accepted_path) == accepted["record_sha256"]
            and embedded["status_sha256"] == sha(raw_path) == accepted["remote_status_sha256"]
            and all(embedded[key] == accepted_remote[key] for key in
                    ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")),
            "An accepted predecessor changed")
for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses"):
    require(remote["completed_stages"][-1][key] == remote[key], "Embedded C1 summary differs")
require(remote["experiment_sources"] == local["experiment_sources"]
        and remote["design_sha256"] == sha(ROOT / "configs/experiments_tc2_gpu.json") == local["design_sha256"],
        "Experiment source identity differs")
source_record = read(job_root / "experiment_sources.json")
require(source_record["files"] == remote["experiment_sources"] and source_record["submission"] == remote["submission"],
        "Published source receipt differs")
require(remote["submission"]["source_sha256"] == remote["submission"]["submitted_sha256"]
        == local["experiment_sources"]["scripts/slurm/experiments_tc2_gpu.sh"], "Submitted script differs")
protected = {**remote["experiment_sources"], **design["scientific_source_hashes"], **design["pilot_source_hashes"]}
require(all(sha(ROOT / name) == digest for name, digest in protected.items()), "A protected source changed")
require(read(job_root / "plan.json") == {"stage": spec, "design_sha256": remote["design_sha256"]}, "Stage plan differs")
require(resources["requested"] == spec["resources"] and resources["runtime"] == remote["runtime"]
        and all(remote["runtime"][key] == expected for key, expected in design["expected_hardware"].items())
        and all(remote["runtime"][key] == expected for key, expected in prior["runtime"].items() if key != "slurm_job_id")
        and remote["runtime"]["slurm_job_id"] == "44103"
        and remote["runtime"]["tf32"] is False and remote["runtime"]["autocast"] is False
        and resources["slurm_environment"] == {"SLURM_JOB_ID": "44103", "SLURM_JOB_PARTITION": "MGPU-TC2",
            "SLURM_JOB_NODELIST": "TC2N01", "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_NODE": "24576",
            "SLURM_JOB_QOS": "normal"}, "Runtime or requested resources differ")
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8-sig")
require(re.search(r"(?m)^44103\s+\S+\s+COMPLETED\s+0:0\s+00:04:50\s+TC2N01\s+2\s+24G", terminal), "Successful SLURM completion is absent")
require(re.search(r"(?m)^44103\.batch\s+batch\s+COMPLETED\s+0:0\s+00:04:50\s+TC2N01\s+2\s+5151984K", terminal), "Batch resource record differs")
files, locations, total = {}, {}, 0
for page in index["pages"]:
    directory = SOURCE / "remote" / ("page_%03d" % page["page_number"])
    manifest = read(directory / "experiments_export_manifest.json")
    total += len(manifest["files"])
    for row in manifest["files"]:
        require(row["path"] not in files or files[row["path"]] == row["sha256"], "Repeated page metadata differs")
        files[row["path"]] = row["sha256"]
    for key in page["result_ids"]:
        locations[key] = str(directory)
caches = []
require(remote["caches"] == prior["caches"], "Reused cache identities differ")
for row in remote["caches"]:
    meta_path = page_root / row["path"] / "metadata.json"
    meta = read(meta_path)
    require(sha(meta_path) == row["metadata_sha256"] and set(meta["layers"]) == {"layer1", "layer2", "layer3"}
            and all(layer["dtype"] == "float32" for layer in meta["layers"].values()), "Cache metadata differs")
    caches.append({"category": row["identity"]["category"], "images": len(meta["index"]), "metadata_sha256": row["metadata_sha256"]})
require({row["category"] for row in caches} == {"cable", "screw"} and sum(row["images"] for row in caches) == 854, "Cache coverage differs")
arrays, metrics = read(HERE / "saved_arrays_verification.json"), read(HERE / "independent_image_metrics.json")
require(arrays["status"] == "passed" and arrays["job_id"] == "44103" and arrays["stage_id"] == "C1"
        and arrays["results_checked"] == 2 and arrays["maps_checked"] == 419
        and arrays["map_derived_score_vectors_checked"] == 16
        and arrays["weighted_patchcore_native_vectors_checked_for_finite_dtype_shape_only"] == 4
        and arrays["index_sha256"] == INDEX_SHA and arrays["design_sha256"] == remote["design_sha256"]
        and arrays["audit_script_sha256"] == sha(HERE / "check_saved_arrays.py"), "Independent saved-array evidence differs")
require(metrics["status"] == "passed" and metrics["stage_id"] == "C1" and metrics["result_count"] == 2
        and metrics["rule_count"] == 10 and metrics["maximum_absolute_error"] <= 1e-12
        and metrics["prediction_maps_loaded"] is False and metrics["torch_imported"] is False, "Independent metric checks did not pass")
lookup = {row["identity_sha256"]: row for row in remote["results"]}
require({row["result_identity_sha256"] for row in arrays["results"]} == set(lookup)
        == {row["identity_sha256"] for row in metrics["results"]}, "Independent result coverage differs")
cache_hashes = {row["category"]: row["metadata_sha256"] for row in caches}
for row in arrays["results"]:
    result = lookup[row["result_identity_sha256"]]
    require(row["run_key"] == result["run_key"] and row["configuration_matches_frozen_fit"] is True
            and row["cache_metadata_sha256"] == cache_hashes[result["category"]]
            and row["frozen_manifest_sha256"] == design["scientific_source_hashes"]["manifests/manifest_mvtec_ad_" + result["category"] + ".json"],
            "Array check input identity differs")
    for field, name in (("predictions_sha256", "predictions.npz"), ("samples_sha256", "samples.json"),
                        ("configuration_file_sha256", "config.yaml"), ("evidence_sha256", "evidence.json"),
                        ("artifact_manifest_sha256", "artifacts.sha256")):
        require(row[field] == files[result["path"] + "/" + name], "Array evidence refers to different bytes")
for row in metrics["results"]:
    result = lookup[row["identity_sha256"]]
    require(row["relative_path"] == result["path"] and row["max_abs_error"] <= 1e-12 and row["rule_count"] == 5,
            "Metric result identity or coverage differs")
    for name, fingerprint in row["artifact_hashes"].items():
        require(fingerprint == files[result["path"] + "/" + name], "Metric evidence refers to different bytes")
require(next_spec["kind"] == "analysis" and next_spec["planned_new_fits"] == 0
        and next_spec["expected_rows"] == 18 and next_spec["expected_cumulative_fits"] == 22
        and next_spec["resources"]["gpus"] == 0, "Next approved analysis differs")
require(all(row["complete"] is False for row in remote["checkpoints"]), "A later checkpoint was prematurely marked complete")
helper = SOURCE.parent / "tc2_gpu_setup.ps1"
require(sha(helper) == local["external_helper_sha256"], "External helper changed")
command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{helper}" -Action RunExperiments -Stage I1_seed17'
for source, name in [(SOURCE / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
                     (job_root / "setup_status.json", "remote_setup_status.json"), (job_root / "resources.json", "resources.json"),
                     (job_root / "result_summary.json", "result_summary.json"), (AUDIT / "setup_status.json", "previous_step7_status.json")]:
    with (HERE / name).open("xb") as stream:
        stream.write(collector._extended(source).read_bytes())
with (HERE / "archive_file_hashes.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(files, stream, indent=2)
    stream.write("\n")
now = datetime.now(timezone.utc).isoformat()
value = {"status": "passed", "stage_id": "C1", "job_id": "44103", "stage_complete": True, "step_7_complete": False,
    "accepted_at_utc": now, "slurm_state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:04:50",
    "node": "TC2N01", "slurm_max_rss_kib": 5151984, "source_directory": str(SOURCE), "index_sha256": INDEX_SHA,
    "index_verification": index_check, "collection_verification": collection, "pages_verified": 2,
    "total_page_payload_entries": total, "unique_payload_files_verified": len(files), "results_verified": 2,
    "new_fits_verified": 2, "cumulative_formal_fits": 22, "phases_passed": 6, "predecessor": dependency,
    "design_sha256": remote["design_sha256"], "experiment_sources": remote["experiment_sources"],
    "protected_sources_checked": len(protected), "runtime": remote["runtime"], "resources": resources, "caches": caches,
    "independent_saved_maps_checked": 419, "independent_score_vectors_checked": 20,
    "independent_image_rule_evaluations": 10, "maximum_independent_image_metric_absolute_error": metrics["maximum_absolute_error"],
    "remote_full_result_verification": "Both original-resolution pixel-metric and full-cache saved-result verifications passed on TC2.",
    "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
    "weighted_native_score_limitation": "Four weighted PatchCore native vectors were checked for FP32 dtype, finite values and shape; maps alone do not reconstruct nearest-neighbor support weights.",
    "reports": {name: sha(HERE / name) for name in ("saved_arrays_verification.json", "independent_image_metrics.json",
        "archive_file_hashes.json", "check_saved_arrays.py", "independent_image_metrics_check.py")},
    "remote_status_sha256": sha(HERE / "remote_setup_status.json"), "result_page_locations": locations,
    "results": remote["results"], "next_stage": "I1_seed17", "next_stage_fits": 0, "next_stage_analysis_rows": 18,
    "core_checkpoint_complete": False, "next_user_terminal_command": command,
    "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
local["accepted_step_7_stages"].append({"stage_id": "C1", "job_id": "44103", "stage_complete": True, "verified_fits": 2,
    "record": "run/validation_tc2_gpu/step7_20261019/accepted_job_44103/verification.json",
    "record_sha256": sha(HERE / "verification.json"), "remote_status_sha256": value["remote_status_sha256"], "index_sha256": INDEX_SHA})
local.update(status="awaiting_I1_seed17_submission", remote_acceptance="B0_H1_H2_C1_accepted_remaining_stages_pending",
    step_7_complete=False, recorded_at_utc=now, verified_formal_fits=22, verified_new_fits=20, remaining_formal_fits=44,
    next_stage="I1_seed17", next_stage_new_fits=0, next_stage_pilot_verifications=0, next_stage_analysis_rows=18,
    next_user_terminal_command=command,
    next_acceptance="Verify the completed I1_seed17 CPU analysis, all 18 rows and the returned collection. The core checkpoint remains incomplete until this analysis passes.",
    next_action="Submit the approved I1_seed17 CPU analysis from the user terminal and return its output for review.",
    latest_attempt={"job_id": "44103", "stage_id": "C1", "node": "TC2N01", "slurm_state": "COMPLETED",
        "exit_code": "0:0", "stage_complete": True, "verified_result_count": 2,
        "verification": "run/validation_tc2_gpu/step7_20261019/accepted_job_44103/verification.json"})
atomic_json(AUDIT / "setup_status.json", local)
print(json.dumps({key: value[key] for key in ("status", "stage_id", "stage_complete", "results_verified",
    "cumulative_formal_fits", "pages_verified", "unique_payload_files_verified", "next_stage", "next_stage_analysis_rows")}, indent=2))
