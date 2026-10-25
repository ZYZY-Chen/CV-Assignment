"""Verify three returned LOCO results without accepting the unfinished stage."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
OUT = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_204442_691c27e1")
HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_loco_tc2_gpu as c
from pilot_tc2_gpu import atomic_json

read = lambda p: json.loads(c._extended(p).read_text(encoding="utf-8"))
state_path = AUDIT / "setup_status.json"
old_bytes, old_sha, local = state_path.read_bytes(), c._sha(state_path), read(state_path)
assert not (HERE / "verification.json").exists()
assert len(local["accepted_step_7_stages"]) == 11 and local["verified_formal_fits"] == 62
assert local["verified_analysis_rows"] == 108 and not local["step_7_complete"]
terminal = (OUT / "terminal.txt").read_text(encoding="utf-8-sig")
pinned = "C89F4E77B61756F7F397613A0CBD614AC99BB562BC45FE0745EB85BC79186DE9"
assert re.findall(r"EXPERIMENTS_INDEX_SHA256=([0-9A-F]{64})", terminal) == [pinned]
assert re.search(r"^44235\s+ca6129_ex\+\s+RUNNING\s+0:0\s+00:38:50\s+TC2N01\s+2\s+24G", terminal, re.M)
index_path = OUT / "experiments-index.json"
index = read(index_path)
iv = c.verify_index(index_path, pinned, "44235")
assert index["collector_provenance"] == c._collection_provenance()
assert iv["page_count"] == 2 and iv["partial"] and not iv["remote_stage_complete"]
for page in index["pages"]:
    path = OUT / page["name"]
    assert path.stat().st_size == page["bytes"] and c._sha(path) == page["sha256"]
cv = c.verify_collection(index_path, OUT / "remote", "44235")
assert cv["status"] == "verified" and cv["result_count"] == 3 and cv["partial"]
assert not cv["stage_complete"] and not cv["step_7_complete"]
files, locations = {}, {}
for page in index["pages"]:
    directory = OUT / "remote" / ("page_" + f"{page['page_number']:03d}")
    manifest = read(directory / "experiments_export_manifest.json")
    for row in manifest["files"]:
        previous = files.setdefault(row["path"], row["sha256"])
        assert previous == row["sha256"]
    for key in page["result_ids"]:
        assert key not in locations
        locations[key] = str(directory)
remote = OUT / "remote/page_001/run/validation_tc2_gpu/step7_job_44235"
s, resources = read(remote / "setup_status.json"), read(remote / "resources.json")
assert index["snapshot_status"] == s and s["status"] == "running" and s["job_id"] == "44235"
assert not s["stage_complete"] and not s["step_7_complete"] and not s["analyses"]
design = read(ROOT / "configs/experiments_tc2_gpu.json")
spec = next(x for x in design["stages"] if x["stage_id"] == "B0_LOCO")
fits = {x["run_key"]: x["configuration"] for x in design["fits"]}
assert [row["run_key"] for row in s["results"]] == spec["run_keys"][:3]
assert set(locations) == set(spec["run_keys"][:3])
assert all(row["verified"] and row["run_status"] == "completed" and not row["accepted_pilot_reuse"] for row in s["results"])
assert read(remote / "plan.json") == {"stage": spec, "design_sha256": local["design_sha256"]}
assert resources["requested"] == spec["resources"]
previous_resources = read(HERE.parent / "attempt_20261019_200541_29bea1c0/remote_resources.json")
assert resources == previous_resources and s["runtime"] == resources["runtime"]
assert resources["slurm_environment"]["SLURM_JOB_NODELIST"] == "TC2N01"
protected = {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **local["experiment_sources"]}
assert len(protected) == 44
for name, fingerprint in protected.items():
    assert c._sha(ROOT / name) == fingerprint, name
assert s["experiment_sources"] == s["preflight"]["experiment_sources"] == local["experiment_sources"]
supplement = local["loco_collection_supplement"]
supplement_path = ROOT / supplement["record"]
assert c._sha(supplement_path) == supplement["record_sha256"]
supplement_record = read(supplement_path)
for name, fingerprint in supplement_record["implementation_files"].items():
    assert c._sha(ROOT / name) == fingerprint
assert c._sha(OUT.parent / "tc2_gpu_setup.ps1") == local["external_helper_sha256"] == supplement_record["external_helper_sha256"]
transport = read(OUT / "loco-collection-provenance.json")
provenance = index["collector_provenance"]
assert transport["job_id"] == "44235" and transport["stage_id"] == "B0_LOCO"
assert transport["collector_sha256"] == provenance["collector_sha256"] and transport["base_collector_sha256"] == provenance["base_collector_sha256"]
assert transport["remote_collector"] == "scripts/collect_experiments_loco_tc2_gpu_" + provenance["collector_sha256"][:16].lower() + ".py"
for marker in ("LOCO_COLLECTION_BASE_SHA256=" + provenance["base_collector_sha256"],
               "LOCO_COLLECTION_COLLECTOR_SHA256=" + provenance["collector_sha256"],
               "LOCO_COLLECTION_REMOTE_COLLECTOR_SHA256=" + provenance["collector_sha256"]):
    assert terminal.count(marker) == 1
prior = local["accepted_step_7_stages"][-1]
predecessor = {"stage_id": "I2", "job_id": "44230", "status_sha256": prior["remote_status_sha256"]}
assert s["predecessor"] == s["preflight"]["predecessor"] == predecessor
chain = s["preflight"]["completed_stages"]
assert [x["stage_id"] for x in chain] == [x["stage_id"] for x in local["accepted_step_7_stages"]]
for accepted, embedded in zip(local["accepted_step_7_stages"], chain):
    path = ROOT / accepted["record"]
    raw = path.parent / "remote_setup_status.json"
    assert c._sha(path) == accepted["record_sha256"]
    assert c._sha(raw) == accepted["remote_status_sha256"] == embedded["status_sha256"]
    previous = read(raw)
    for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses"):
        assert embedded[key] == previous[key], (accepted["stage_id"], key)
assert s["preflight"]["status"] == "passed" and s["preflight"]["free_bytes"] >= design["minimum_free_remote_bytes"]
assert len(s["phases"]) == 8 and all(row["exit_code"] == 0 for row in s["phases"])
assert [row["phase"] for row in s["phases"]] == ["phase_001_extract", "phase_002_extract", "phase_003_run", "phase_004_verify", "phase_005_run", "phase_006_verify", "phase_007_run", "phase_008_verify"]
assert "Starting phase_009_run" in terminal
assert s["loco_original_dimensions"] == read(HERE.parent / "attempt_20261019_200541_29bea1c0/remote_setup_status.json")["loco_original_dimensions"]
metric = read(HERE / "independent_image_metrics.json")
arrays = read(HERE / "saved_arrays_verification.json")
for report, script in ((metric, "independent_image_metrics_check.py"), (arrays, "check_saved_arrays.py")):
    assert report["status"] == "passed" and report["job_id"] == "44235" and report["stage_id"] == "B0_LOCO"
    assert report["index_sha256"] == pinned and report["design_sha256"] == local["design_sha256"]
    assert report["audit_script_sha256"] == c._sha(HERE / script)
assert metric["result_count"] == arrays["results_checked"] == 3
assert metric["scope_rule_evaluations"] == 45 and metric["maximum_absolute_error"] <= 1e-12
assert metric["collector_provenance"] == provenance and not metric["pixel_metrics_recomputed"]
assert not metric["remote_stage_complete"] and not metric["stage_acceptance_granted_by_this_audit"]
assert arrays["maps_checked"] == 1169 and arrays["map_derived_score_vectors_checked"] == 28
assert arrays["weighted_patchcore_native_vectors_checked_for_finite_dtype_shape_only"] == 2
assert arrays["cache_image_positions_checked"] == 1480 and arrays["snapshot_partial"]
assert not arrays["stage_complete"] and not arrays["stage_accepted"]
assert arrays["collection_derivative_sha256"] == provenance["collector_sha256"]
by_id = {row["identity_sha256"]: row for row in s["results"]}
assert {row["identity_sha256"] for row in metric["results"]} == set(by_id)
assert {row["result_identity_sha256"] for row in arrays["results"]} == set(by_id)
for row in metric["results"]:
    result = by_id[row["identity_sha256"]]
    assert row["run_key_fields"] == fits[result["run_key"]] and row["relative_path"] == result["path"]
    for name, fingerprint in row["artifact_hashes"].items():
        assert fingerprint == files[result["path"] + "/" + name]
for row in arrays["results"]:
    result = by_id[row["result_identity_sha256"]]
    assert row["run_key"] == result["run_key"] and row["frozen_configuration"] == fits[row["run_key"]]
    for key, name in (("predictions_sha256", "predictions.npz"), ("samples_sha256", "samples.json"),
                      ("configuration_file_sha256", "config.yaml"), ("evidence_sha256", "evidence.json"),
                      ("artifact_manifest_sha256", "artifacts.sha256")):
        assert row[key] == files[result["path"] + "/" + name]
    category = result["category"]
    assert row["frozen_manifest_sha256"] == protected["manifests/manifest_mvtec_loco_" + category + ".json"]
    cache = next(x for x in s["caches"] if x["identity"]["category"] == category)
    assert row["cache_metadata_sha256"] == cache["metadata_sha256"] == files[cache["path"] + "/metadata.json"]
command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + str(OUT.parent / "tc2_gpu_setup.ps1") + '" -Action CollectExperiments -JobId 44235 -LocoCollection'
reports = {name: c._sha(HERE / name) for name in ("independent_image_metrics.json", "saved_arrays_verification.json", "independent_image_metrics_check.py", "check_saved_arrays.py")}
record = {"verification_status": "passed", "stage_accepted": False, "stage_complete": False,
    "step_7_complete": False, "job_id": "44235", "requested_stage": "B0_LOCO",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(), "source_directory": str(OUT),
    "index_sha256": pinned, "index_verification": iv, "collection_verification": cv,
    "archive_hash_and_size_checks": index["pages"], "unique_payload_files_verified": len(files),
    "slurm_state_at_snapshot": "RUNNING", "slurm_elapsed_at_snapshot": "00:38:50", "node_at_snapshot": "TC2N01",
    "phase_at_snapshot": "phase_009_run", "current_remote_state": "unknown", "completed_phases": s["phases"],
    "verified_stage_results": 3, "expected_stage_results": 4, "runtime_and_resources_match_accepted_environment": True,
    "runtime": s["runtime"], "resources": resources["requested"], "protected_sources_checked": 44,
    "collector_provenance": provenance, "predecessor": predecessor, "previous_stage_chain_matches_accepted_records": True,
    "caches": s["caches"], "cache_image_positions_checked": 1480, "reports": reports,
    "independent_saved_maps_checked": 1169, "independent_score_vectors_checked": 30,
    "independent_image_scope_rule_evaluations": 45, "maximum_independent_image_metric_absolute_error": metric["maximum_absolute_error"],
    "remote_status_sha256": c._sha(remote / "setup_status.json"), "result_page_locations": locations,
    "previously_accepted_formal_fits": 62, "verified_analysis_rows": 108, "core_checkpoint_complete": True,
    "standard_checkpoint_complete": True, "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
    "weighted_native_score_limitation": "Two PatchCore native vectors were checked for finite FP32 shape only; reconstruction requires nearest-neighbor support beyond saved maps.",
    "next_user_terminal_command": command, "actual_agent_tc2_connections": 0,
    "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
for source, name in ((OUT / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
                     (remote / "setup_status.json", "remote_setup_status.json"), (remote / "resources.json", "remote_resources.json"),
                     (remote / "plan.json", "remote_plan.json"), (OUT / "loco-collection-provenance.json", "loco-collection-provenance.json")):
    with (HERE / name).open("xb") as stream:
        stream.write(c._extended(source).read_bytes())
with (HERE / "previous_step7_status.json").open("xb") as stream:
    stream.write(old_bytes)
for name, value in (("archive_file_hashes.json", files), ("verification.json", record)):
    with (HERE / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
assert c._sha(state_path) == old_sha
local.update(status="awaiting_B0_LOCO_collection", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
    next_user_terminal_command=command, next_action="Collect the existing B0_LOCO job 44235 with -LocoCollection; three partial results passed but stage completion is still pending.",
    latest_attempt={"job_id": "44235", "stage_id": "B0_LOCO", "node": "TC2N01", "slurm_state": "RUNNING",
        "slurm_elapsed_at_snapshot": "00:38:50", "stage_complete": False, "partial": True,
        "verified_result_count": 3, "expected_result_count": 4, "collection_status": "verified_partial",
        "verification": (HERE / "verification.json").relative_to(ROOT).as_posix()})
atomic_json(state_path, local)
assert read(state_path)["verified_formal_fits"] == 62 and len(read(state_path)["accepted_step_7_stages"]) == 11
print(json.dumps({"status": "passed", "stage_accepted": False, "partial_results_verified": 3,
                  "maps_checked": 1169, "image_scope_rule_evaluations": 45, "accepted_fits": 62,
                  "next_user_terminal_command": command}, indent=2))
