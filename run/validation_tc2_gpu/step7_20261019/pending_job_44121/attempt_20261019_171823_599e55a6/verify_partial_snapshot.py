"""Verify a partial R0 collection without accepting the unfinished stage."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
ROOT = AUDIT.parents[2]
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_171823_599e55a6")
INDEX_SHA = "E1D2774213DD3218BCC2F96642F5E1E3C3064D7956E307543B0EAC8337B2C57E"
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
spec = next(row for row in design["stages"] if row["stage_id"] == "R0")
index_path = SOURCE / "experiments-index.json"
index_check = collector.verify_index(index_path, INDEX_SHA, "44121")
index = read(index_path)
for page in index["pages"]:
    archive = SOURCE / page["name"]
    require(sha(archive) == page["sha256"] and archive.stat().st_size == page["bytes"], "Archive bytes differ")
collection = collector.verify_collection(index_path, SOURCE / "remote", "44121")
require(collection["status"] == "verified" and collection["stage_id"] == "R0" and collection["partial"] is True
        and collection["stage_complete"] is False and collection["step_7_complete"] is False
        and collection["result_count"] == 14 and collection["analysis_count"] == 0 and collection["page_count"] == 4,
        "Partial collection scope differs")
page_root = SOURCE / "remote/page_001"
job_root = page_root / "run/validation_tc2_gpu/step7_job_44121"
remote, resources = read(job_root / "setup_status.json"), read(job_root / "resources.json")
require(remote["mode"] == "formal_experiment_stage" and remote["stage_id"] == "R0" and remote["job_id"] == "44121"
        and remote["status"] == "running" and remote["stage_complete"] is False and remote["step_7_complete"] is False,
        "Unexpected running stage state")
require([row["run_key"] for row in remote["results"]] == spec["run_keys"][:14]
        and all(row["run_status"] == "completed" and row["verified"] is True and row["accepted_pilot_reuse"] is False
                for row in remote["results"]) and remote["analyses"] == [], "Returned results differ from the planned prefix")
expected_phases = ["phase_%03d_extract" % number for number in range(1, 7)]
expected_phases += ["phase_%03d_%s" % (number, "run" if number % 2 else "verify") for number in range(7, 35)]
require([row["phase"] for row in remote["phases"]] == expected_phases
        and all(row["exit_code"] == 0 for row in remote["phases"]), "Completed phases differ")
require(ledger["verified_formal_fits"] == 22 and ledger["core_checkpoint_complete"] is True
        and [row["stage_id"] for row in ledger["accepted_step_7_stages"]] == ["B0", "H1", "H2", "C1", "I1_seed17"],
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
dependency = {"stage_id": "I1_seed17", "job_id": "44116",
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
        and remote["runtime"]["slurm_job_id"] == "44121"
        and resources["slurm_environment"] == {"SLURM_JOB_ID": "44121", "SLURM_JOB_PARTITION": "MGPU-TC2",
            "SLURM_JOB_NODELIST": "TC2N01", "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_NODE": "24576",
            "SLURM_JOB_QOS": "normal"}, "Actual resources or runtime differ")
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8-sig")
require(re.search(r"(?m)^44121\s+\S+\s+RUNNING\s+0:0\s+00:20:21\s+TC2N01\s+2\s+24G", terminal)
        and "Starting phase_035_run" in terminal, "Running SLURM snapshot is absent")
files = {}
for page in index["pages"]:
    directory = SOURCE / "remote" / ("page_%03d" % page["page_number"])
    for row in read(directory / "experiments_export_manifest.json")["files"]:
        require(row["path"] not in files or files[row["path"]] == row["sha256"], "Repeated metadata differs")
        files[row["path"]] = row["sha256"]
require(len(files) == 209, "Unexpected payload coverage")
b0 = read(AUDIT / "accepted_job_44053/remote_setup_status.json")
require(remote["caches"] == b0["caches"], "Cache identities differ from accepted B0")
caches = []
for row in remote["caches"]:
    meta_path = page_root / row["path"] / "metadata.json"
    metadata = read(meta_path)
    require(sha(meta_path) == row["metadata_sha256"]
            and all(layer["dtype"] == "float32" for layer in metadata["layers"].values()), "Cache metadata differs")
    caches.append({"category": row["identity"]["category"], "images": len(metadata["index"]),
                   "metadata_sha256": row["metadata_sha256"]})
require(len(caches) == 6 and sum(row["images"] for row in caches) == 2170, "Cache coverage differs")
arrays, metrics = read(HERE / "saved_arrays_verification.json"), read(HERE / "independent_image_metrics.json")
require(arrays["status"] == "passed" and arrays["job_id"] == "44121" and arrays["stage_id"] == "R0"
        and arrays["results_checked"] == 14 and arrays["maps_checked"] == 2432
        and arrays["index_sha256"] == INDEX_SHA and arrays["design_sha256"] == remote["design_sha256"]
        and arrays["audit_script_sha256"] == sha(HERE / "check_saved_arrays.py")
        and arrays["map_derived_score_vectors_checked"] == 128
        and arrays["weighted_patchcore_native_vectors_checked_for_finite_dtype_shape_only"] == 12, "Array audit differs")
require(metrics["status"] == "passed" and metrics["stage_id"] == "R0" and metrics["result_count"] == 14
        and metrics["rule_count"] == 70 and metrics["maximum_absolute_error"] <= 1e-12
        and metrics["job_id"] == "44121" and metrics["index_sha256"] == INDEX_SHA
        and metrics["design_sha256"] == remote["design_sha256"]
        and metrics["audit_script_sha256"] == sha(HERE / "independent_image_metrics_check.py"), "Metric audit differs")
previous_audit = HERE.parent / "attempt_20261019_171157_7b5e9e85"
previous_record = read(previous_audit / "verification.json")
require(previous_record["verification_status"] == "passed" and previous_record["stage_accepted"] is False,
        "Prior partial verification is unavailable")
for name, fingerprint in previous_record["reports"].items():
    require(sha(previous_audit / name) == fingerprint, "Prior partial evidence changed")
require(arrays["prior_report_sha256"] == sha(previous_audit / "saved_arrays_verification.json")
        and arrays["results_previous_array_audit_reused"] == 10 and arrays["results_array_values_rechecked"] == 4
        and metrics["prior_recomputation_reused_after_exact_hash_match"] == 10
        and metrics["newly_recomputed_from_final_snapshot"] == 4, "Partial audit reuse scope differs")
previous_arrays = read(previous_audit / "saved_arrays_verification.json")
previous_metrics = read(previous_audit / "independent_image_metrics.json")
for old in previous_arrays["results"]:
    current = next(row for row in arrays["results"] if row["result_identity_sha256"] == old["result_identity_sha256"])
    for key in ("run_key", "predictions_sha256", "samples_sha256", "configuration_file_sha256",
                "evidence_sha256", "artifact_manifest_sha256", "frozen_manifest_sha256", "cache_metadata_sha256"):
        require(current[key] == old[key], "A reused array input changed")
for old in previous_metrics["results"]:
    current = next(row for row in metrics["results"] if row["identity_sha256"] == old["identity_sha256"])
    require(current["artifact_hashes"] == old["artifact_hashes"], "A reused metric input changed")
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
helper = SOURCE.parent / "tc2_gpu_setup.ps1"
require(sha(helper) == ledger["external_helper_sha256"], "External helper changed")
command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{helper}" -Action CollectExperiments -JobId 44121'
for source, name in [(SOURCE / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
    (job_root / "setup_status.json", "remote_setup_status.json"), (job_root / "resources.json", "remote_resources.json"),
    (job_root / "plan.json", "remote_plan.json"), (AUDIT / "setup_status.json", "previous_step7_status.json")]:
    with (HERE / name).open("xb") as stream:
        stream.write(collector._extended(source).read_bytes())
with (HERE / "archive_file_hashes.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(files, stream, indent=2)
    stream.write("\n")
now = datetime.now(timezone.utc).isoformat()
value = {"verification_status": "passed", "stage_accepted": False, "step_7_complete": False,
    "job_id": "44121", "requested_stage": "R0", "checked_at_utc": now, "source_directory": str(SOURCE),
    "index_sha256": INDEX_SHA, "index_verification": index_check, "collection_verification": collection,
    "slurm_state_at_snapshot": "RUNNING", "slurm_elapsed_at_snapshot": "00:20:21", "node_at_snapshot": "TC2N01",
    "current_remote_state": "unknown", "phase_at_snapshot": "phase_035_run", "completed_phases": 34,
    "verified_stage_results": 14, "expected_stage_results": 24, "results": remote["results"],
    "previously_accepted_formal_fits": 22, "core_checkpoint_complete": True,
    "predecessor": dependency, "previous_stage_chain_matches_accepted_records": True,
    "protected_sources_checked": len(protected), "design_sha256": remote["design_sha256"],
    "runtime": remote["runtime"], "resources": resources, "cache_metadata_and_identity_checks": caches,
    "independent_saved_maps_checked": 2432, "independent_score_vectors_checked": 140,
    "independent_image_rule_evaluations": 70, "maximum_independent_image_metric_absolute_error": metrics["maximum_absolute_error"],
    "reports": {name: sha(HERE / name) for name in ("saved_arrays_verification.json", "independent_image_metrics.json",
        "archive_file_hashes.json", "check_saved_arrays.py", "independent_image_metrics_check.py")},
    "previous_partial_verification_sha256": sha(previous_audit / "verification.json"),
    "previous_result_audits_reused_after_exact_hash_match": 10,
    "new_result_audits_recomputed": 4,
    "remote_status_sha256": sha(HERE / "remote_setup_status.json"),
    "partial_evidence_reuse_policy": "Reuse a result audit only after all referenced input hashes exactly match a later verified snapshot; the R0 stage remains unaccepted.",
    "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
    "next_user_terminal_command": command, "actual_agent_tc2_connections": 0,
    "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
ledger.update(status="waiting_R0_job_44121", remote_acceptance="B0_H1_H2_C1_I1_seed17_accepted_R0_partial",
    recorded_at_utc=now, next_user_terminal_command=command,
    next_acceptance="Collect the existing R0 job 44121. Verify COMPLETED 0:0, all 24 results and every page before C1R. Fourteen checked partial results do not constitute stage acceptance.",
    next_action="Collect the existing running R0 job from the user terminal and return the generated terminal.txt path. Do not resubmit the job.",
    latest_attempt={"job_id": "44121", "stage_id": "R0", "slurm_state": "RUNNING", "node": "TC2N01",
        "elapsed_at_snapshot": "00:20:21", "stage_complete": False, "verified_result_count": 14,
        "expected_result_count": 24, "completed_cache_verifications": 6,
        "verification": (HERE / "verification.json").relative_to(ROOT).as_posix()})
atomic_json(AUDIT / "setup_status.json", ledger)
print(json.dumps({key: value[key] for key in ("verification_status", "stage_accepted", "job_id",
    "verified_stage_results", "expected_stage_results", "previously_accepted_formal_fits")}, indent=2))
