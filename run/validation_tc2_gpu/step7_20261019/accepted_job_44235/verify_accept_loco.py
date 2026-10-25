"""Accept the final LOCO collection and the complete twelve-stage experiment chain."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
OUT = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_205219_dee60b36")
HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
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
pinned = "DA890F4A554ED43009D7AA903A81A809FC5A009DB277234B800A342CA3B9D857"
assert re.findall(r"EXPERIMENTS_INDEX_SHA256=([0-9A-F]{64})", terminal) == [pinned]
assert re.search(r"^44235\s+ca6129_ex\+\s+COMPLETED\s+0:0\s+00:45:10\s+TC2N01\s+2\s+24G", terminal, re.M)
index_path = OUT / "experiments-index.json"
index = read(index_path)
iv = c.verify_index(index_path, pinned, "44235")
assert index["collector_provenance"] == c._collection_provenance()
assert iv["page_count"] == 2 and not iv["partial"] and iv["remote_stage_complete"]
for page in index["pages"]:
    path = OUT / page["name"]
    assert path.stat().st_size == page["bytes"] and c._sha(path) == page["sha256"]
cv = c.verify_collection(index_path, OUT / "remote", "44235")
assert cv["status"] == "verified" and cv["result_count"] == 4 and not cv["partial"]
assert cv["stage_complete"] and cv["step_7_complete"]
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
assert index["snapshot_status"] == s and s["status"] == "passed" and s["job_id"] == "44235"
assert s["stage_complete"] and s["step_7_complete"] and not s["analyses"]
design = read(ROOT / "configs/experiments_tc2_gpu.json")
spec = next(x for x in design["stages"] if x["stage_id"] == "B0_LOCO")
fits = {x["run_key"]: x["configuration"] for x in design["fits"]}
assert [row["run_key"] for row in s["results"]] == spec["run_keys"]
assert set(locations) == set(spec["run_keys"])
assert all(row["verified"] and row["run_status"] == "completed" and not row["accepted_pilot_reuse"] for row in s["results"])
assert read(remote / "plan.json") == {"stage": spec, "design_sha256": local["design_sha256"]}
assert resources["requested"] == spec["resources"]
previous_resources = read(AUDIT / "pending_job_44235/attempt_20261019_200541_29bea1c0/remote_resources.json")
for key in ("requested", "runtime", "slurm_environment"):
    assert resources[key] == previous_resources[key], key
assert s["runtime"] == resources["runtime"]
assert set(resources) == {"requested", "runtime", "slurm_environment", "child_peak_rss_kib", "free_bytes_after"}
assert type(resources["child_peak_rss_kib"]) is int and 0 < resources["child_peak_rss_kib"] <= spec["resources"]["memory_gib"] * 1024**2
assert type(resources["free_bytes_after"]) is int and resources["free_bytes_after"] >= design["minimum_free_remote_bytes"]
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
assert len(s["phases"]) == 10 and all(row["exit_code"] == 0 for row in s["phases"])
assert [row["phase"] for row in s["phases"]] == ["phase_001_extract", "phase_002_extract", "phase_003_run", "phase_004_verify", "phase_005_run", "phase_006_verify", "phase_007_run", "phase_008_verify", "phase_009_run", "phase_010_verify"]
assert re.search(r"^44235\.batch\s+batch\s+COMPLETED\s+0:0\s+00:45:10\s+TC2N01\s+2\s+12778560K", terminal, re.M)
assert s["loco_original_dimensions"] == read(AUDIT / "pending_job_44235/attempt_20261019_200541_29bea1c0/remote_setup_status.json")["loco_original_dimensions"]
metric = read(HERE / "independent_image_metrics.json")
arrays = read(HERE / "saved_arrays_verification.json")
for report, script in ((metric, "independent_image_metrics_check.py"), (arrays, "check_saved_arrays.py")):
    assert report["status"] == "passed" and report["job_id"] == "44235" and report["stage_id"] == "B0_LOCO"
    assert report["index_sha256"] == pinned and report["design_sha256"] == local["design_sha256"]
    assert report["audit_script_sha256"] == c._sha(HERE / script)
assert metric["result_count"] == arrays["results_checked"] == 4
assert metric["scope_rule_evaluations"] == 60 and metric["maximum_absolute_error"] <= 1e-12
assert metric["collector_provenance"] == provenance and not metric["pixel_metrics_recomputed"]
assert metric["remote_stage_complete"] and not metric["stage_acceptance_granted_by_this_audit"]
assert arrays["maps_checked"] == 1570 and arrays["map_derived_score_vectors_checked"] == 36
assert arrays["weighted_patchcore_native_vectors_checked_for_finite_dtype_shape_only"] == 4
assert arrays["cache_image_positions_checked"] == 1480 and not arrays["snapshot_partial"]
assert arrays["stage_complete"] and not arrays["stage_accepted"]
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

# The final remote record must cover the entire frozen experiment matrix.
assert [row["stage_id"] for row in s["completed_stages"]] == local["stages"]
assert s["completed_stages"][:-1] == chain
assert s["completed_stages"][-1] == {key: s[key] for key in ("stage_id", "job_id", "design_sha256", "results", "analyses", "status", "stage_complete")}
all_results = [result for stage in s["completed_stages"] for result in stage["results"]]
assert len(all_results) == len({row["run_key"] for row in all_results}) == 66
assert {row["run_key"] for row in all_results} == set(fits)
assert all(row["verified"] for row in all_results)
assert sum(row["accepted_pilot_reuse"] for row in all_results) == 2
assert sum(not row["accepted_pilot_reuse"] for row in all_results) == 64
assert s["cumulative_fits"] == design["expected_total_fits"] == 66
assert sum(item["rows"] for stage in s["completed_stages"] for item in stage["analyses"]) == 108
assert s["checkpoints"] == [{**row, "complete": True} for row in local["checkpoints"]]
assert all(row["complete"] for row in s["checkpoints"])
assert read(remote / "result_summary.json")["results"] == s["results"]

# Earlier independent calculations may be reused only for identical result inputs.
partial = AUDIT / "pending_job_44235/attempt_20261019_204442_691c27e1"
partial_record = read(partial / "verification.json")
for name in ("independent_image_metrics.json", "saved_arrays_verification.json", "independent_image_metrics_check.py", "check_saved_arrays.py"):
    assert c._sha(partial / name) == partial_record["reports"][name]
assert metric["prior_recomputation_reused_after_exact_hash_match"] == 3 and metric["newly_recomputed_from_snapshot"] == 1
assert arrays["results_previous_array_audit_reused"] == 3 and arrays["results_array_values_rechecked"] == 1
assert arrays["prior_report_sha256"] == c._sha(partial / "saved_arrays_verification.json")
for row in metric["results"]:
    if row.get("prior_evidence"):
        assert row["prior_evidence"]["sha256"] == c._sha(partial / "independent_image_metrics.json")
assert len(files) == 72
reports = {name: c._sha(HERE / name) for name in ("independent_image_metrics.json", "saved_arrays_verification.json", "independent_image_metrics_check.py", "check_saved_arrays.py")}

# Update only the already-approved README completion status; preserve old bytes.
readme_path = ROOT / "README.md"
readme_before = readme_path.read_bytes()
readme = readme_before.decode("utf-8")
old_paragraph = "Eleven stages through I2 have passed independent local acceptance: 62 of 66 fits and 108 saved-score analysis rows are verified. The core and standard checkpoints are complete. B0_LOCO job 44235 was submitted for the remaining four fits; its complete returned results still require acceptance."
new_paragraph = "Step 7 completed on 2026-10-19: all twelve stages passed independent local acceptance, covering 66 fits (64 new fits and two accepted pilot results reused) and 108 saved-score analysis rows. The core, standard and full checkpoints are complete. Final B0_LOCO job 44235 on TC2N01 finished as COMPLETED / 0:0 in 00:45:10; both returned pages, all four results, saved arrays and pooled/logical/structural image metrics passed verification. See the [final step-7 record](run/validation_tc2_gpu/step7_20261019/setup_status.json) and [LOCO acceptance](run/validation_tc2_gpu/step7_20261019/accepted_job_44235/verification.json). Original-mask pixel metrics were reproduced on TC2; local verification uses saved arrays, image scores and hash-bound cache metadata."
assert readme.count(old_paragraph) == 1
readme = readme.replace(old_paragraph, new_paragraph)
old_sentence = "Use the external helper with `-Action CollectExperiments -JobId 44235 -LocoCollection` to collect the existing job."
new_sentence = "The accepted LOCO collection used the external helper with `-Action CollectExperiments -JobId 44235 -LocoCollection`. Job 44235 needs no resubmission or further collection."
assert readme.count(old_sentence) == 1
readme = readme.replace(old_sentence, new_sentence)
assert [line for line in readme.splitlines() if re.search(r"[\u3400-\u9fff]", line)] == [line for line in readme_before.decode("utf-8").splitlines() if re.search(r"[\u3400-\u9fff]", line)]
with (HERE / "README.before_completion.md").open("xb") as stream:
    stream.write(readme_before)
readme_path.write_bytes(readme.encode("utf-8"))

record = {"status": "passed", "stage_id": "B0_LOCO", "job_id": "44235", "stage_complete": True,
    "step_7_complete": True, "accepted_at_utc": datetime.now(timezone.utc).isoformat(),
    "slurm_state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:45:10", "node": "TC2N01",
    "slurm_max_rss_kib": 12778560, "slurm_max_rss_gib": 12778560 / 1024**2,
    "child_peak_rss_kib": resources["child_peak_rss_kib"], "free_bytes_after": resources["free_bytes_after"],
    "source_directory": str(OUT), "index_sha256": pinned, "index_verification": iv, "collection_verification": cv,
    "archive_hash_and_size_checks": index["pages"], "pages_verified": 2, "unique_payload_files_verified": len(files),
    "results_verified": 4, "new_fits_verified": 4, "cumulative_formal_fits": 66,
    "total_new_fits_verified": 64, "accepted_pilot_fits_reused": 2, "verified_analysis_rows": 108,
    "phases_passed": 10, "predecessor": predecessor, "design_sha256": local["design_sha256"],
    "experiment_sources": s["experiment_sources"], "protected_sources_checked": 44,
    "collector_provenance": provenance, "runtime": s["runtime"], "resources": resources["requested"], "caches": s["caches"],
    "cache_image_positions_checked": 1480, "independent_saved_maps_checked": 1570,
    "independent_score_vectors_checked": 40, "independent_image_rule_evaluations": 20,
    "independent_image_scope_rule_evaluations": 60, "maximum_independent_image_metric_absolute_error": metric["maximum_absolute_error"],
    "previous_result_checks_reused_after_exact_hash_match": 3, "new_result_checks_recomputed": 1,
    "reports": reports, "remote_status_sha256": c._sha(remote / "setup_status.json"),
    "result_page_locations": locations, "results": s["results"], "all_twelve_stage_collections_verified": True,
    "previous_stage_record_and_raw_status_hashes_unchanged": 11, "all_66_unique_frozen_run_keys_verified": True,
    "core_checkpoint_complete": True, "standard_checkpoint_complete": True, "full_checkpoint_complete": True,
    "checkpoints": s["checkpoints"], "remote_full_result_verification": True,
    "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
    "weighted_native_score_limitation": "Four PatchCore native vectors were checked for finite FP32 shape only; reconstruction requires nearest-neighbor support beyond saved maps.",
    "README_before_completion_sha256": c._sha(HERE / "README.before_completion.md"), "README_completion_sha256": c._sha(readme_path),
    "existing_Chinese_README_content_preserved": True, "implementation_files_modified": ["README.md completion status only"],
    "next_stage": None, "next_user_terminal_command": None,
    "completion_boundary": "Step 7 is complete. Resource comparisons, aggregate statistics, figures, failure-case presentation and report writing remain later work; no later step was started.",
    "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "actual_agent_model_calls": 0}
for source, name in ((OUT / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
                     (remote / "setup_status.json", "remote_setup_status.json"), (remote / "resources.json", "resources.json"),
                     (remote / "plan.json", "remote_plan.json"), (remote / "result_summary.json", "result_summary.json"),
                     (OUT / "loco-collection-provenance.json", "loco-collection-provenance.json")):
    with (HERE / name).open("xb") as stream:
        stream.write(c._extended(source).read_bytes())
with (HERE / "previous_step7_status.json").open("xb") as stream:
    stream.write(old_bytes)
for name, value in (("archive_file_hashes.json", files), ("verification.json", record)):
    with (HERE / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
assert c._sha(state_path) == old_sha
local["accepted_step_7_stages"].append({"stage_id": "B0_LOCO", "job_id": "44235", "stage_complete": True,
    "verified_fits": 4, "record": (HERE / "verification.json").relative_to(ROOT).as_posix(),
    "record_sha256": c._sha(HERE / "verification.json"), "remote_status_sha256": record["remote_status_sha256"], "index_sha256": pinned})
local.update(status="passed", recorded_at_utc=datetime.now(timezone.utc).isoformat(), step_7_complete=True,
    remote_acceptance="all_twelve_stages_accepted", verified_formal_fits=66, verified_new_fits=64,
    remaining_formal_fits=0, verified_analysis_rows=108, core_checkpoint_complete=True,
    standard_checkpoint_complete=True, full_checkpoint_complete=True, checkpoints=s["checkpoints"],
    all_twelve_stage_collections_verified=True, next_stage=None, next_stage_new_fits=0, next_stage_pilot_verifications=0,
    next_stage_analysis_rows=0, next_user_terminal_command=None,
    next_acceptance="None for step 7; all twelve returned stage collections passed.",
    next_action="Step 7 is complete. Await the user's request to discuss the next numbered step; do not start report writing.",
    completion_README_sha256=c._sha(readme_path),
    latest_attempt={"job_id": "44235", "stage_id": "B0_LOCO", "node": "TC2N01", "slurm_state": "COMPLETED",
        "exit_code": "0:0", "elapsed": "00:45:10", "stage_complete": True, "verified_result_count": 4,
        "verification": (HERE / "verification.json").relative_to(ROOT).as_posix()})
local["loco_collection_supplement"].update(remote_recollection_pending=False, remote_full_collection_accepted=True,
    accepted_collection_record=(HERE / "verification.json").relative_to(ROOT).as_posix())
atomic_json(state_path, local)
final = read(state_path)
assert final["step_7_complete"] and len(final["accepted_step_7_stages"]) == 12
assert sum(row["verified_fits"] for row in final["accepted_step_7_stages"]) == 66
assert sum(row.get("verified_analysis_rows", 0) for row in final["accepted_step_7_stages"]) == 108
for accepted in final["accepted_step_7_stages"]:
    assert c._sha(ROOT / accepted["record"]) == accepted["record_sha256"]
print(json.dumps({"status": "passed", "step_7_complete": True, "accepted_stages": 12,
    "formal_fits": 66, "new_fits": 64, "reused_pilot_fits": 2, "analysis_rows": 108,
    "LOCO_elapsed": "00:45:10", "verification": str(HERE / "verification.json")}, indent=2))
