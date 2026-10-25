"""Bind independent B0 checks to the collected bytes and record stage acceptance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
AUDIT = HERE.parent
read = lambda path: json.loads(path.read_text(encoding="utf-8"))
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
collection = read(HERE / "collection_verification.json")
arrays = read(HERE / "saved_arrays_verification.json")
metrics = read(HERE / "independent_image_metrics.json")
files = read(HERE / "archive_file_hashes.json")
remote = read(HERE / "remote_setup_status.json")
design = read(ROOT / "configs/experiments_tc2_gpu.json")
if (collection["verification_status"] != "passed" or collection["collection_verification"]["stage_complete"] is not True
        or arrays["status"] != "passed" or arrays["results_checked"] != 12 or arrays["maps_checked"] != 2022
        or arrays["index_sha256"] != collection["index_sha256"] or arrays["design_sha256"] != remote["design_sha256"]
        or arrays["audit_script_sha256"] != sha(HERE / "check_saved_arrays.py")
        or metrics["status"] != "passed" or metrics["result_count"] != 10 or metrics["rule_count"] != 50
        or metrics["maximum_absolute_error"] > 1e-12):
    raise ValueError("Every completed collection and independent check is required")
results = {row["identity_sha256"]: row for row in remote["results"]}
if {row["result_identity_sha256"] for row in arrays["results"]} != set(results):
    raise ValueError("Saved-array verification does not cover exactly the twelve B0 results")
cache_hashes = {row["identity"]["category"]: row["metadata_sha256"] for row in remote["caches"]}
for row in arrays["results"]:
    result = results[row["result_identity_sha256"]]
    if (row["run_key"] != result["run_key"] or row["configuration_matches_frozen_fit"] is not True
            or row["predictions_sha256"] != files[result["path"] + "/predictions.npz"]
            or row["samples_sha256"] != files[result["path"] + "/samples.json"]
            or row["cache_metadata_sha256"] != cache_hashes[result["category"]]
            or row["frozen_manifest_sha256"] != design["scientific_source_hashes"]["manifests/manifest_mvtec_ad_" + result["category"] + ".json"]):
        raise ValueError("Saved-array verification refers to different artifacts or inputs")
new_ids = {key for key, row in results.items() if not row["accepted_pilot_reuse"]}
if {row["identity_sha256"] for row in metrics["results"]} != new_ids:
    raise ValueError("Image-metric verification must cover all ten new result identities")
for row in metrics["results"]:
    result = results[row["identity_sha256"]]
    if row["relative_path"] != result["path"] or row["rule_count"] != 5 or row["max_abs_error"] > 1e-12:
        raise ValueError("Independent image-metric coverage differs")
    for name, fingerprint in row["artifact_hashes"].items():
        if fingerprint != files[result["path"] + "/" + name]:
            raise ValueError("Independent metric evidence refers to different collected bytes")
command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\Users\\mhjv_\\Desktop\\CharGPT projects\\CA6129 COMPUTER VISION & APPLICATIONS\\output\\tc2_gpu_setup.ps1" -Action RunExperiments -Stage H1'
value = {"status": "passed", "stage_id": "B0", "job_id": "44053", "stage_complete": True,
         "step_7_complete": False, "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
         "slurm_state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:17:55", "node": "TC2N01",
         "index_sha256": collection["index_sha256"], "design_sha256": remote["design_sha256"],
         "experiment_sources": remote["experiment_sources"], "remote_status_sha256": sha(HERE / "remote_setup_status.json"),
         "source_directory": collection["source_directory"], "pages_verified": 6, "unique_payload_files_verified": 180,
         "results_verified": 12, "new_fits_verified": 10, "pilot_results_reused": 2,
         "pilot_artifact_files_unchanged": 16, "cached_categories": 6, "cached_images": 2170,
         "independent_saved_maps_checked": 2022, "independent_score_vectors_checked": 120,
         "independent_image_metric_results_checked": 10, "independent_image_rule_evaluations": 50,
         "maximum_independent_image_metric_absolute_error": metrics["maximum_absolute_error"],
         "pixel_metric_validation": "Full original-mask metric reproduction passed remotely for all twelve saved results; raw masks and NPY caches were not downloaded.",
         "local_pixel_metrics_recomputed": False,
         "reports": {name: sha(HERE / name) for name in ("collection_verification.json", "archive_file_hashes.json", "saved_arrays_verification.json", "independent_image_metrics.json")},
         "result_page_locations": collection["result_page_locations"], "results": remote["results"],
         "next_stage": "H1", "next_stage_fits": 4, "next_user_terminal_command": command,
         "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
current_path = AUDIT / "setup_status.json"
state = read(current_path)
with (HERE / "previous_step7_status.json").open("xb") as stream:
    stream.write(current_path.read_bytes())
accepted = {"stage_id": "B0", "job_id": "44053", "stage_complete": True, "verified_fits": 12,
            "record": "run/validation_tc2_gpu/step7_20261019/accepted_job_44053/verification.json",
            "record_sha256": sha(HERE / "verification.json"), "remote_status_sha256": value["remote_status_sha256"],
            "index_sha256": value["index_sha256"]}
if state["accepted_step_7_stages"]:
    raise ValueError("Preserve existing stage acceptance records before updating the ledger")
state.update(status="awaiting_H1_submission", remote_acceptance="B0_accepted_remaining_stages_pending",
             step_7_complete=False, accepted_step_7_stages=[accepted], verified_formal_fits=12,
             verified_new_fits=10, remaining_formal_fits=54, next_stage="H1", next_stage_new_fits=4,
             next_stage_pilot_verifications=0, next_user_terminal_command=command,
             next_action="Submit the approved H1 stage from the user terminal, then return its collection output for review.",
             latest_attempt={"job_id": "44053", "stage_id": "B0", "node": "TC2N01", "slurm_state": "COMPLETED",
                             "exit_code": "0:0", "stage_complete": True, "verified_result_count": 12,
                             "verified_new_result_count": 10, "verification": accepted["record"]})
sys.path.insert(0, str(ROOT / "scripts"))
from pilot_tc2_gpu import atomic_json
atomic_json(current_path, state)
print(json.dumps({key: value[key] for key in ("status", "stage_id", "stage_complete", "step_7_complete", "results_verified", "new_fits_verified", "next_stage", "next_stage_fits")}, indent=2))
