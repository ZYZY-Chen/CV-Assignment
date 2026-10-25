"""Bind the completed CPU analysis to locally accepted source results and audits."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT, AUDIT = HERE.parents[3], HERE.parent
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_165134_fdee4ac2")
INDEX_SHA = "1181927A6ACFB91D2006683B28360D2428EBDCFEECDAC88863D108188DFEDA64"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as collector
from pilot_tc2_gpu import atomic_json

read = lambda path: json.loads(collector._extended(path).read_text(encoding="utf-8"))
sha = collector._sha
digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
    ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


local = read(AUDIT / "setup_status.json")
design = read(ROOT / "configs/experiments_tc2_gpu.json")
spec = next(row for row in design["stages"] if row["stage_id"] == "I1_seed17")
next_spec = next(row for row in design["stages"] if row["stage_id"] == "R0")
prior_names = ["B0", "H1", "H2", "C1"]
require([row["stage_id"] for row in local["accepted_step_7_stages"]] == prior_names
        and local["verified_formal_fits"] == 22 and local["step_7_complete"] is False, "Unexpected prior local acceptance")
index_path = SOURCE / "experiments-index.json"
index_check = collector.verify_index(index_path, INDEX_SHA, "44116")
index = read(index_path)
for page in index["pages"]:
    archive = SOURCE / page["name"]
    require(sha(archive) == page["sha256"] and archive.stat().st_size == page["bytes"], "Archive bytes differ")
collection = collector.verify_collection(index_path, SOURCE / "remote", "44116")
require(collection["stage_id"] == "I1_seed17" and collection["stage_complete"] is True
        and collection["partial"] is False and collection["step_7_complete"] is False
        and collection["result_count"] == 0 and collection["analysis_count"] == 1
        and collection["page_count"] == 1, "Analysis collection is incomplete")
page_root = SOURCE / "remote/page_001"
job_root = page_root / "run/validation_tc2_gpu/step7_job_44116"
remote, resources = read(job_root / "setup_status.json"), read(job_root / "resources.json")
require(remote["mode"] == "formal_experiment_stage" and remote["stage_id"] == "I1_seed17"
        and remote["job_id"] == "44116" and remote["status"] == "passed"
        and remote["stage_complete"] is True and remote["step_7_complete"] is False
        and remote["cumulative_fits"] == 22 and remote["results"] == [], "Unexpected analysis stage state")
require(len(remote["phases"]) == 1 and remote["phases"][0]["phase"] == "phase_001_analyze"
        and remote["phases"][0]["exit_code"] == 0, "CPU analysis phase did not pass")
require([row["stage_id"] for row in remote["completed_stages"]] == prior_names + ["I1_seed17"], "Completed chain differs")
for embedded, accepted in zip(remote["completed_stages"][:-1], local["accepted_step_7_stages"]):
    accepted_path = ROOT / accepted["record"]
    raw_path = accepted_path.parent / "remote_setup_status.json"
    previous = read(raw_path)
    require(sha(accepted_path) == accepted["record_sha256"]
            and sha(raw_path) == accepted["remote_status_sha256"] == embedded["status_sha256"]
            and all(embedded[key] == previous[key] for key in
                ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")),
            "A predecessor differs from local acceptance")
prior_path = AUDIT / "accepted_job_44103/remote_setup_status.json"
prior = read(prior_path)
dependency = {"stage_id": "C1", "job_id": "44103", "status_sha256": sha(prior_path)}
require(remote["predecessor"] == remote["preflight"]["predecessor"] == dependency
        and remote["preflight"]["status"] == "passed", "Predecessor differs")
for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses"):
    require(remote["completed_stages"][-1][key] == remote[key], "Embedded analysis summary differs")
require(remote["experiment_sources"] == local["experiment_sources"]
        and remote["design_sha256"] == sha(ROOT / "configs/experiments_tc2_gpu.json") == local["design_sha256"],
        "Source identity differs")
source_record = read(job_root / "experiment_sources.json")
require(source_record["files"] == remote["experiment_sources"] and source_record["submission"] == remote["submission"]
        and remote["submission"]["source_sha256"] == remote["submission"]["submitted_sha256"]
        == local["experiment_sources"]["scripts/slurm/experiments_tc2_gpu.sh"], "Publication receipt differs")
protected = {**remote["experiment_sources"], **design["scientific_source_hashes"], **design["pilot_source_hashes"]}
require(all(sha(ROOT / name) == value for name, value in protected.items()), "A protected source changed")
require(all(sha(SOURCE / "experiments_payload" / name) == value for name, value in remote["experiment_sources"].items()),
        "A published payload differs")
require(read(job_root / "plan.json") == {"stage": spec, "design_sha256": remote["design_sha256"]}, "Stage plan differs")
require(resources["requested"] == spec["resources"] and resources["runtime"] == remote["runtime"]
        and remote["runtime"]["device"] == "cpu" and remote["runtime"]["slurm_job_id"] == "44116"
        and remote["runtime"]["torch_imported"] is False and remote["runtime"]["software"] == prior["runtime"]["software"]
        and resources["slurm_environment"] == {"SLURM_JOB_ID": "44116", "SLURM_JOB_PARTITION": "MGPU-TC2",
            "SLURM_JOB_NODELIST": "TC2N02", "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_NODE": "8192",
            "SLURM_JOB_QOS": "normal"}, "CPU resources or runtime differ")
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8-sig")
require(re.search(r'\"status\": \"published\",\s*\"stage_id\": \"I1_seed17\",\s*\"files\": 7', terminal)
        and "TC2_JOB_ID=44116" in terminal
        and re.search(r"(?m)^44116\s+\S+\s+COMPLETED\s+0:0\s+00:00:20\s+TC2N02\s+2\s+8G", terminal),
        "Successful analysis submission and completion are absent")
manifest = read(page_root / "experiments_export_manifest.json")
files = {row["path"]: row["sha256"] for row in manifest["files"]}
require(len(files) == 36, "Unexpected analysis payload")
b0_root = AUDIT / "accepted_job_44053"
b0 = read(b0_root / "remote_setup_status.json")
b0_hashes = read(b0_root / "archive_file_hashes.json")
require(remote["caches"] == b0["caches"], "Analysis caches differ from accepted B0")
caches = []
for row in remote["caches"]:
    metadata_path = page_root / row["path"] / "metadata.json"
    metadata = read(metadata_path)
    require(sha(metadata_path) == row["metadata_sha256"]
            and all(layer["dtype"] == "float32" for layer in metadata["layers"].values()), "Cache metadata changed")
    caches.append({"category": row["identity"]["category"], "images": len(metadata["index"]),
                   "metadata_sha256": row["metadata_sha256"]})
require(len(caches) == 6 and sum(row["images"] for row in caches) == 2170, "Cache coverage differs")
sources_by_key = {row["run_key"]: row for row in b0["results"]}
require(read(job_root / "analysis_index.json")["results"] == [sources_by_key[key] for key in spec["source_run_keys"]],
        "Source result selection differs")
require(len(remote["analyses"]) == 1, "Unexpected analysis count")
record = remote["analyses"][0]
require(record["status"] == "passed" and record["stage"] == record["stage_id"] == "I1_seed17"
        and record["rows"] == 18 and record["source_run_keys"] == spec["source_run_keys"], "Analysis receipt differs")
analysis_root = page_root / record["path"]
analysis, evidence = read(analysis_root / "analysis.json"), read(analysis_root / "evidence.json")
identity = evidence["identity"]
require(digest(identity) == record["identity_sha256"] == analysis["identity_sha256"]
        and identity["rows_sha256"] == digest(analysis["rows"])
        and identity["protocol_sha256"] == design["protocol_sha256"]
        and identity["score_rules"] == analysis["score_rules"] == spec["score_rules"]
        and [row["run_key"] for row in identity["sources"]] == spec["source_run_keys"]
        and analysis["row_count"] == 18 and analysis["source_count"] == 6, "Analysis content identity differs")
for source in identity["sources"]:
    accepted = sources_by_key[source["run_key"]]
    require(source["path"] == accepted["path"] and source["identity_sha256"] == accepted["identity_sha256"]
            and source["artifacts_sha256"] == b0_hashes[source["path"] + "/artifacts.sha256"],
            "Analysis source identity changed")
    for name, value in source["artifact_hashes"].items():
        require(value == b0_hashes[source["path"] + "/" + name], "A source artifact differs from accepted B0 bytes")
analysis_hashes = {name: sha(analysis_root / name) for name in
    ("analysis.json", "analysis.csv", "evidence.json", "analysis.sha256", "SUCCESS")}
for name, value in analysis_hashes.items():
    require(value == files[record["path"] + "/" + name], "Analysis receipt refers to different bytes")
require(evidence["runtime"]["device"] == "cpu" and evidence["runtime"]["slurm_job_id"] == "44116"
        and evidence["runtime"]["torch_imported_by_analysis"] is False
        and evidence["runtime"]["map_arrays_loaded"] is False and evidence["runtime"]["feature_arrays_loaded"] is False
        and evidence["runtime"]["pixel_metrics_recomputed"] is False, "Analysis runtime scope differs")
expected_checkpoints = [
    {"checkpoint_id": "core", "after_stage": "I1_seed17", "expected_fits": 22, "complete": True},
    {"checkpoint_id": "standard", "after_stage": "I2", "expected_fits": 62, "complete": False},
    {"checkpoint_id": "full", "after_stage": "B0_LOCO", "expected_fits": 66, "complete": False}]
require(remote["checkpoints"] == expected_checkpoints, "Checkpoint state differs")
provenance = read(HERE / "analysis_provenance_verification.json")
metrics = read(HERE / "independent_analysis_metrics.json")
for report in (provenance, metrics):
    require(report["status"] == "passed" and report["stage_id"] == "I1_seed17"
            and report["analysis_identity_sha256"] == record["identity_sha256"]
            and report["source_count"] == 6 and report["row_count"] == 18, "Independent analysis evidence differs")
    require(report["analysis_artifact_hashes"] == analysis_hashes, "Independent artifact coverage differs")
    for name, value in report["analysis_artifact_hashes"].items():
        require(value == analysis_hashes[name], "Independent report refers to different analysis bytes")
    require([source["run_key"] for source in report["sources"]] == spec["source_run_keys"], "Independent source coverage differs")
    for source in report["sources"]:
        reference = next(row for row in identity["sources"] if row["run_key"] == source["run_key"])
        require(source["artifact_hashes"] == reference["artifact_hashes"], "Independent source bytes differ")
require(provenance["job_id"] == "44116" and provenance["index_sha256"] == INDEX_SHA
        and provenance["design_sha256"] == remote["design_sha256"]
        and provenance["remote_status_sha256"] == sha(job_root / "setup_status.json")
        and provenance["accepted_b0_verification_sha256"] == sha(b0_root / "verification.json")
        and provenance["audit_script_sha256"] == sha(HERE / "check_analysis_provenance.py")
        and all(provenance[key] is True for key in ("canonical_identity_passed", "completion_manifest_passed",
            "csv_json_exact_match", "row_order_and_uniqueness_passed", "source_artifacts_identical_to_accepted_b0")),
        "Provenance verification binding differs")
require(metrics["maximum_absolute_error"] <= 1e-12 and metrics["source_image_rules_checked"] == 18
        and metrics["csv_rows_checked"] == 18 and metrics["counts_checked"] is True
        and metrics["delta_vs_native_checked"] is True and metrics["source_id_and_hash_bindings_exact"] is True
        and metrics["source_acceptance_ledger"]["sha256"] == sha(b0_root / "verification.json")
        and metrics["prediction_maps_loaded"] is False and metrics["feature_arrays_loaded"] is False
        and metrics["torch_imported"] is False, "Independent analysis metric checks differ")
require(next_spec["kind"] == "fit" and next_spec["predecessor"] == "I1_seed17"
        and next_spec["planned_new_fits"] == 24 and len(next_spec["run_keys"]) == 24
        and next_spec["expected_cumulative_fits"] == 46, "Next approved stage differs")
helper = SOURCE.parent / "tc2_gpu_setup.ps1"
require(sha(helper) == local["external_helper_sha256"], "External helper changed")
command = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{helper}" -Action RunExperiments -Stage R0'
for source, name in [(SOURCE / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
    (job_root / "setup_status.json", "remote_setup_status.json"), (job_root / "resources.json", "resources.json"),
    (job_root / "analysis_index.json", "analysis_index.json"), (job_root / "result_summary.json", "result_summary.json"),
    (analysis_root / "analysis.json", "analysis.json"), (analysis_root / "analysis.csv", "analysis.csv"),
    (analysis_root / "evidence.json", "analysis_evidence.json"), (AUDIT / "setup_status.json", "previous_step7_status.json")]:
    with (HERE / name).open("xb") as stream:
        stream.write(collector._extended(source).read_bytes())
with (HERE / "archive_file_hashes.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(files, stream, indent=2)
    stream.write("\n")
now = datetime.now(timezone.utc).isoformat()
value = {"status": "passed", "stage_id": "I1_seed17", "job_id": "44116", "stage_complete": True, "step_7_complete": False,
    "accepted_at_utc": now, "slurm_state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:00:20",
    "node": "TC2N02", "source_directory": str(SOURCE), "index_sha256": INDEX_SHA,
    "index_verification": index_check, "collection_verification": collection,
    "pages_verified": 1, "unique_payload_files_verified": len(files), "results_verified": 0, "new_fits_verified": 0,
    "analyses_verified": 1, "analysis_rows_verified": 18, "analysis_source_results_verified": 6, "cumulative_formal_fits": 22,
    "phases_passed": 1, "predecessor": dependency, "design_sha256": remote["design_sha256"],
    "experiment_sources": remote["experiment_sources"], "protected_sources_checked": len(protected),
    "runtime": remote["runtime"], "resources": resources, "caches": caches, "analysis": record,
    "analysis_artifact_hashes": analysis_hashes, "maximum_independent_analysis_metric_absolute_error": metrics["maximum_absolute_error"],
    "reports": {name: sha(HERE / name) for name in ("analysis_provenance_verification.json", "independent_analysis_metrics.json",
        "archive_file_hashes.json", "check_analysis_provenance.py", "independent_analysis_check.py")},
    "remote_status_sha256": sha(HERE / "remote_setup_status.json"), "checkpoints": expected_checkpoints,
    "core_checkpoint_complete": True, "cache_npy_arrays_downloaded": False, "new_prediction_arrays_downloaded": False,
    "local_pixel_metrics_recomputed": False, "next_stage": "R0", "next_stage_fits": 24,
    "next_user_terminal_command": command, "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0,
    "implementation_files_modified": 0}
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
local["accepted_step_7_stages"].append({"stage_id": "I1_seed17", "job_id": "44116", "stage_complete": True,
    "verified_fits": 0, "verified_analysis_rows": 18,
    "record": "run/validation_tc2_gpu/step7_20261019/accepted_job_44116/verification.json",
    "record_sha256": sha(HERE / "verification.json"), "remote_status_sha256": value["remote_status_sha256"], "index_sha256": INDEX_SHA})
local.update(status="awaiting_R0_submission", remote_acceptance="B0_H1_H2_C1_I1_seed17_accepted_remaining_stages_pending",
    step_7_complete=False, recorded_at_utc=now, verified_formal_fits=22, verified_new_fits=20, remaining_formal_fits=44,
    verified_analysis_rows=18, core_checkpoint_complete=True, checkpoints=expected_checkpoints,
    next_stage="R0", next_stage_new_fits=24, next_stage_pilot_verifications=0, next_stage_analysis_rows=0,
    next_user_terminal_command=command, next_acceptance="Verify all 24 R0 fits and every returned collection page before proceeding to C1R.",
    next_action="Submit the approved R0 stage from the user terminal and return its output for review.",
    latest_attempt={"job_id": "44116", "stage_id": "I1_seed17", "node": "TC2N02", "slurm_state": "COMPLETED",
        "exit_code": "0:0", "stage_complete": True, "verified_result_count": 0, "verified_analysis_rows": 18,
        "verification": "run/validation_tc2_gpu/step7_20261019/accepted_job_44116/verification.json"})
atomic_json(AUDIT / "setup_status.json", local)
print(json.dumps({key: value[key] for key in ("status", "stage_id", "stage_complete", "analysis_rows_verified",
    "cumulative_formal_fits", "core_checkpoint_complete", "next_stage", "next_stage_fits")}, indent=2))
