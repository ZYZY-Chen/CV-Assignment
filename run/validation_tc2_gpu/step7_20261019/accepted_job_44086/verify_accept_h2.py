"""Verify the completed H2 collection and bind independent acceptance evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT, AUDIT = HERE.parents[3], HERE.parent
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_161703_e990a53d")
INDEX_SHA = "294759842B70011859B5C9C9CF771CB5AFB708DE695A766735882C737737F59D"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as collector
from pilot_tc2_gpu import atomic_json

read = lambda path: json.loads(collector._extended(path).read_text(encoding="utf-8"))
sha = collector._sha
design = read(ROOT / "configs/experiments_tc2_gpu.json")
local = read(AUDIT / "setup_status.json")
spec = next(value for value in design["stages"] if value["stage_id"] == "H2")
index_path = SOURCE / "experiments-index.json"
index_check = collector.verify_index(index_path, INDEX_SHA, "44086")
index = read(index_path)
for page in index["pages"]:
    archive = SOURCE / page["name"]
    if sha(archive) != page["sha256"] or archive.stat().st_size != page["bytes"]:
        raise ValueError("Archive bytes differ from the pinned index")
collection = collector.verify_collection(index_path, SOURCE / "remote", "44086")
page_root = SOURCE / "remote/page_001"
record_root = page_root / "run/validation_tc2_gpu/step7_job_44086"
remote, resources = read(record_root / "setup_status.json"), read(record_root / "resources.json")
prior_path = AUDIT / "accepted_job_44075/remote_setup_status.json"
prior = read(prior_path)
dependency = {"stage_id": "H1", "job_id": "44075", "status_sha256": sha(prior_path)}
if (remote["status"] != "passed" or remote["stage_complete"] is not True or remote["step_7_complete"] is not False
        or remote["stage_id"] != "H2" or remote["job_id"] != "44086" or remote["cumulative_fits"] != 20
        or remote["predecessor"] != dependency or remote["preflight"]["predecessor"] != dependency
        or [value["stage_id"] for value in remote["completed_stages"]] != ["B0", "H1", "H2"]
        or [value["run_key"] for value in remote["results"]] != spec["run_keys"]
        or len(remote["phases"]) != 10 or any(value["exit_code"] != 0 for value in remote["phases"])
        or any(value["run_status"] != "completed" or value["verified"] is not True for value in remote["results"])):
    raise ValueError("The completed H2 record differs from the approved plan")
completed_prior = remote["completed_stages"][1]
if completed_prior["status_sha256"] != sha(prior_path) or any(completed_prior[key] != prior[key] for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")):
    raise ValueError("H2 does not bind the exact accepted H1 stage")
for stage_name, accepted_job in (("B0", "44053"), ("H1", "44075")):
    accepted_path = AUDIT / ("accepted_job_" + accepted_job) / "remote_setup_status.json"
    accepted_record = read(accepted_path)
    embedded = next(row for row in remote["completed_stages"] if row["stage_id"] == stage_name)
    if embedded["status_sha256"] != sha(accepted_path) or any(embedded[key] != accepted_record[key] for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")):
        raise ValueError("The complete predecessor chain differs from local acceptance")
if (collection["partial"] is not False or collection["stage_complete"] is not True or collection["result_count"] != 4
        or collection["page_count"] != 2 or remote["experiment_sources"] != local["experiment_sources"]
        or remote["design_sha256"] != sha(ROOT / "configs/experiments_tc2_gpu.json")):
    raise ValueError("Collection completeness or source identity differs")
protected = {**remote["experiment_sources"], **design["scientific_source_hashes"], **design["pilot_source_hashes"]}
if any(sha(ROOT / name) != fingerprint for name, fingerprint in protected.items()):
    raise ValueError("Protected sources changed")
if (resources["requested"] != spec["resources"] or resources["runtime"] != remote["runtime"]
        or any(remote["runtime"][key] != expected for key, expected in design["expected_hardware"].items())
        or remote["runtime"]["software"] != prior["runtime"]["software"]
        or remote["runtime"]["tf32"] is not False or remote["runtime"]["autocast"] is not False
        or resources["slurm_environment"]["SLURM_JOB_NODELIST"] != "TC2N01"
        or resources["slurm_environment"]["SLURM_CPUS_PER_TASK"] != "2"
        or resources["slurm_environment"]["SLURM_MEM_PER_NODE"] != "24576"):
    raise ValueError("Actual resources, hardware or software differ")
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8")
if not re.search(r"(?m)^44086\s+\S+\s+COMPLETED\s+0:0\s+00:12:35\s+TC2N01\s+2\s+24G", terminal):
    raise ValueError("Successful SLURM completion is not established")
files, locations, total = {}, {}, 0
for page in index["pages"]:
    directory = SOURCE / "remote" / ("page_%03d" % page["page_number"])
    manifest = read(directory / "experiments_export_manifest.json")
    total += len(manifest["files"])
    for row in manifest["files"]:
        if row["path"] in files and files[row["path"]] != row["sha256"]:
            raise ValueError("Repeated metadata differs between pages")
        files[row["path"]] = row["sha256"]
    for key in page["result_ids"]:
        locations[key] = str(directory)
caches = []
prior_caches = {row["identity"]["category"]: row for row in prior["caches"]}
for row in remote["caches"]:
    category = row["identity"]["category"]
    meta = read(page_root / row["path"] / "metadata.json")
    if row != prior_caches[category] or set(meta["layers"]) != {"layer1", "layer2", "layer3"} or any(value["dtype"] != "float32" for value in meta["layers"].values()):
        raise ValueError("Reused cache identity or FP32 format differs")
    caches.append({"category": category, "images": len(meta["index"]), "metadata_sha256": row["metadata_sha256"]})
if {row["category"] for row in caches} != {"cable", "screw"} or sum(row["images"] for row in caches) != 854:
    raise ValueError("The two required category caches are incomplete")
arrays, metrics = read(HERE / "saved_arrays_verification.json"), read(HERE / "independent_image_metrics.json")
if (arrays["status"] != "passed" or arrays["results_checked"] != 4 or arrays["maps_checked"] != 838
        or arrays["index_sha256"] != INDEX_SHA or arrays["design_sha256"] != remote["design_sha256"]
        or arrays["audit_script_sha256"] != sha(HERE / "check_saved_arrays.py")
        or metrics["status"] != "passed" or metrics["result_count"] != 4 or metrics["rule_count"] != 20
        or metrics["maximum_absolute_error"] > 1e-12):
    raise ValueError("Independent saved-array and image-metric checks must pass")
lookup = {row["identity_sha256"]: row for row in remote["results"]}
if {row["result_identity_sha256"] for row in arrays["results"]} != set(lookup) or {row["identity_sha256"] for row in metrics["results"]} != set(lookup):
    raise ValueError("Independent checks do not cover the four exact H2 identities")
cache_hashes = {row["category"]: row["metadata_sha256"] for row in caches}
for row in arrays["results"]:
    result = lookup[row["result_identity_sha256"]]
    if (row["run_key"] != result["run_key"] or row["configuration_matches_frozen_fit"] is not True
            or row["predictions_sha256"] != files[result["path"] + "/predictions.npz"]
            or row["samples_sha256"] != files[result["path"] + "/samples.json"]
            or row["cache_metadata_sha256"] != cache_hashes[result["category"]]
            or row["frozen_manifest_sha256"] != design["scientific_source_hashes"]["manifests/manifest_mvtec_ad_" + result["category"] + ".json"]):
        raise ValueError("Array check refers to different collected bytes or inputs")
for row in metrics["results"]:
    result = lookup[row["identity_sha256"]]
    if row["relative_path"] != result["path"] or row["max_abs_error"] > 1e-12 or row["rule_count"] != 5:
        raise ValueError("Image-metric identity or coverage differs")
    for name, fingerprint in row["artifact_hashes"].items():
        if fingerprint != files[result["path"] + "/" + name]:
            raise ValueError("Image-metric evidence refers to different artifact bytes")
command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\Users\\mhjv_\\Desktop\\CharGPT projects\\CA6129 COMPUTER VISION & APPLICATIONS\\output\\tc2_gpu_setup.ps1" -Action RunExperiments -Stage C1'
for original, target in (("terminal.txt", "terminal.txt"), ("experiments-index.json", "experiments-index.json")):
    with (HERE / target).open("xb") as stream:
        stream.write((SOURCE / original).read_bytes())
for original, target in (("setup_status.json", "remote_setup_status.json"), ("resources.json", "resources.json"), ("result_summary.json", "result_summary.json")):
    with (HERE / target).open("xb") as stream:
        stream.write((record_root / original).read_bytes())
with (HERE / "archive_file_hashes.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(files, stream, indent=2)
    stream.write("\n")
value = {"status": "passed", "stage_id": "H2", "job_id": "44086", "stage_complete": True, "step_7_complete": False,
         "accepted_at_utc": datetime.now(timezone.utc).isoformat(), "slurm_state": "COMPLETED", "exit_code": "0:0",
         "elapsed": "00:12:35", "node": "TC2N01", "slurm_max_rss_kib": 5275916,
         "source_directory": str(SOURCE), "index_sha256": INDEX_SHA, "index_verification": index_check,
         "collection_verification": collection, "pages_verified": 2, "total_page_payload_entries": total,
         "unique_payload_files_verified": len(files), "results_verified": 4, "new_fits_verified": 4,
         "cumulative_formal_fits": 20, "phases_passed": 10, "predecessor": dependency,
         "design_sha256": remote["design_sha256"], "experiment_sources": remote["experiment_sources"],
         "protected_sources_checked": len(protected), "runtime": remote["runtime"], "resources": resources, "caches": caches,
         "independent_saved_maps_checked": 838, "independent_score_vectors_checked": 40,
         "independent_image_rule_evaluations": 20, "maximum_independent_image_metric_absolute_error": metrics["maximum_absolute_error"],
         "remote_full_result_verification": "All four original-resolution pixel-metric and full-cache saved-result verifications passed on TC2.",
         "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
         "reports": {name: sha(HERE / name) for name in ("saved_arrays_verification.json", "independent_image_metrics.json", "archive_file_hashes.json")},
         "remote_status_sha256": sha(HERE / "remote_setup_status.json"), "result_page_locations": locations,
         "results": remote["results"], "next_stage": "C1", "next_stage_fits": 2, "next_user_terminal_command": command,
         "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, indent=2)
    stream.write("\n")
if [row["stage_id"] for row in local["accepted_step_7_stages"]] != ["B0", "H1"]:
    raise ValueError("Preserve existing acceptance stages before updating the ledger")
with (HERE / "previous_step7_status.json").open("xb") as stream:
    stream.write((AUDIT / "setup_status.json").read_bytes())
local["accepted_step_7_stages"].append({"stage_id": "H2", "job_id": "44086", "stage_complete": True, "verified_fits": 4,
    "record": "run/validation_tc2_gpu/step7_20261019/accepted_job_44086/verification.json", "record_sha256": sha(HERE / "verification.json"),
    "remote_status_sha256": value["remote_status_sha256"], "index_sha256": INDEX_SHA})
local.update(status="awaiting_C1_submission", remote_acceptance="B0_H1_H2_accepted_remaining_stages_pending", step_7_complete=False,
             verified_formal_fits=20, verified_new_fits=18, remaining_formal_fits=46, next_stage="C1", next_stage_new_fits=2,
             next_stage_pilot_verifications=0, next_user_terminal_command=command,
             next_action="Submit the approved C1 stage from the user terminal and return its output for review.",
             latest_attempt={"job_id": "44086", "stage_id": "H2", "node": "TC2N01", "slurm_state": "COMPLETED", "exit_code": "0:0",
                             "stage_complete": True, "verified_result_count": 4, "verification": "run/validation_tc2_gpu/step7_20261019/accepted_job_44086/verification.json"})
atomic_json(AUDIT / "setup_status.json", local)
print(json.dumps({key: value[key] for key in ("status", "stage_id", "stage_complete", "results_verified", "cumulative_formal_fits", "pages_verified", "unique_payload_files_verified", "next_stage")}, indent=2))
