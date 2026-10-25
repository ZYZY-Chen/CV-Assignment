"""Verify the initial B0_LOCO snapshot using local evidence only."""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import sys

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
OUT = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_200541_29bea1c0")
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as c
from pilot_tc2_gpu import atomic_json

read = lambda p: json.loads(c._extended(p).read_text(encoding="utf-8"))
state_path = AUDIT / "setup_status.json"
old_bytes, old_sha, local = state_path.read_bytes(), c._sha(state_path), read(state_path)
assert not (HERE / "verification.json").exists()
assert len(local["accepted_step_7_stages"]) == 11
assert local["verified_formal_fits"] == 62 and local["verified_analysis_rows"] == 108
terminal = (OUT / "terminal.txt").read_text(encoding="utf-8-sig")
pinned = "45070E3D122A796CDF2C7D0C06590C10EFDEB0190D007D630F2A95FA02FD0C8C"
assert re.findall(r"EXPERIMENTS_INDEX_SHA256=([0-9A-F]{64})", terminal) == [pinned]
assert '"status": "published"' in terminal and '"stage_id": "B0_LOCO"' in terminal
assert re.search(r"^44235\s+ca6129_ex\+\s+RUNNING\s+0:0\s+00:00:45\s+TC2N01\s+2\s+24G", terminal, re.M)
index_path = OUT / "experiments-index.json"
index = read(index_path)
iv = c.verify_index(index_path, pinned, "44235")
for page in index["pages"]:
    archive = OUT / page["name"]
    assert archive.stat().st_size == page["bytes"] and c._sha(archive) == page["sha256"]
cv = c.verify_collection(index_path, OUT / "remote", "44235")
assert cv["status"] == iv["status"] == "verified" and cv["partial"]
assert not cv["stage_complete"] and not cv["step_7_complete"]
assert cv["stage_id"] == "B0_LOCO" and cv["result_count"] == cv["analysis_count"] == 0
remote = OUT / "remote/page_001/run/validation_tc2_gpu/step7_job_44235"
s, resources = read(remote / "setup_status.json"), read(remote / "resources.json")
design = read(ROOT / "configs/experiments_tc2_gpu.json")
spec = next(x for x in design["stages"] if x["stage_id"] == "B0_LOCO")
assert index["snapshot_status"] == s and s["status"] == "running" and s["job_id"] == "44235"
assert s["results"] == s["analyses"] == s["caches"] == s["phases"] == []
assert read(remote / "plan.json") == {"stage": spec, "design_sha256": local["design_sha256"]}
assert resources["requested"] == spec["resources"]
assert resources["slurm_environment"] == {
    "SLURM_JOB_ID": "44235", "SLURM_JOB_PARTITION": "MGPU-TC2", "SLURM_JOB_NODELIST": "TC2N01",
    "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_NODE": "24576", "SLURM_JOB_QOS": "normal"}
previous_runtime = read(AUDIT / "accepted_job_44217/remote_setup_status.json")["runtime"]
assert {k: v for k, v in s["runtime"].items() if k != "slurm_job_id"} == {
    k: v for k, v in previous_runtime.items() if k != "slurm_job_id"}
assert s["runtime"] == resources["runtime"] and s["runtime"]["slurm_job_id"] == "44235"
protected = {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **local["experiment_sources"]}
assert len(protected) == 44
for name, digest in protected.items():
    assert c._sha(ROOT / name) == digest, name
assert s["experiment_sources"] == local["experiment_sources"] == s["preflight"]["experiment_sources"]
for name, digest in local["experiment_sources"].items():
    assert c._sha(OUT / "experiments_payload" / name) == digest, name
assert s["submission"]["source_sha256"] == s["submission"]["submitted_sha256"] == local["experiment_sources"]["scripts/slurm/experiments_tc2_gpu.sh"]
assert c._sha(OUT.parent / "tc2_gpu_setup.ps1") == local["external_helper_sha256"]
assert c._sha(ROOT / "README.md") == "58872B230EE34B6711A424BB6120DEFDE41859C9AF6059E86D42081614FC32C3"
prior = local["accepted_step_7_stages"][-1]
predecessor = {"stage_id": "I2", "job_id": "44230", "status_sha256": prior["remote_status_sha256"]}
assert s["predecessor"] == s["preflight"]["predecessor"] == predecessor
chain = s["preflight"]["completed_stages"]
assert [x["stage_id"] for x in chain] == [x["stage_id"] for x in local["accepted_step_7_stages"]]
for accepted, embedded in zip(local["accepted_step_7_stages"], chain):
    record_path = ROOT / accepted["record"]
    raw = record_path.parent / "remote_setup_status.json"
    assert c._sha(record_path) == accepted["record_sha256"]
    assert c._sha(raw) == accepted["remote_status_sha256"] == embedded["status_sha256"]
    previous = read(raw)
    for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses"):
        assert embedded[key] == previous[key], (accepted["stage_id"], key)
assert s["preflight"]["status"] == "passed" and s["preflight"]["free_bytes"] >= design["minimum_free_remote_bytes"]
guard = []
for row in s["loco_original_dimensions"]:
    manifest_path = ROOT / "manifests" / ("manifest_mvtec_loco_" + row["category"] + ".json")
    manifest = read(manifest_path)
    assert c._sha(OUT / "remote/page_001/manifests" / manifest_path.name) == c._sha(manifest_path) == protected["manifests/" + manifest_path.name]
    assert len(row["unique_original_hw"]) == 1
    h, w = row["unique_original_hw"][0]
    ntest = len(manifest["test"]["good"]) + len(manifest["test"]["anomalies"])
    count = len(manifest["fit_pool"]) + len(manifest["dev"]) + ntest
    assert row["images"] == count and row["original_pixels"] == count * h * w
    assert row["test_original_pixels"] == ntest * h * w
    assert row["conservative_host_bytes"] == 4 * 1024**3 + 20 * row["test_original_pixels"] <= 24 * 1024**3
    guard.append({**row, "estimated_host_gib": row["conservative_host_bytes"] / 1024**3,
        "below_fixed_memory_budget": True, "frozen_manifest_sha256": c._sha(manifest_path),
        "original_dimensions_evidence": "Reported by the frozen remote input index; local raw images were not downloaded."})
assert [x["category"] for x in guard] == ["juice_bottle", "screw_bag"]
assert "Starting phase_001_extract" in terminal
command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + str(OUT.parent / "tc2_gpu_setup.ps1") + '" -Action CollectExperiments -JobId 44235'
record = {
    "verification_status": "passed", "stage_accepted": False, "step_7_complete": False,
    "job_id": "44235", "requested_stage": "B0_LOCO", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "source_directory": str(OUT), "index_sha256": pinned, "index_verification": iv,
    "collection_verification": cv, "archive_hash_and_size_checks": index["pages"],
    "slurm_state_at_snapshot": "RUNNING", "slurm_elapsed_at_snapshot": "00:00:45",
    "node_at_snapshot": "TC2N01", "phase_at_snapshot": "phase_001_extract", "current_remote_state": "unknown",
    "completed_phases": [], "verified_stage_results": 0, "expected_stage_results": 4,
    "runtime_and_resources_match_accepted_environment": True, "runtime": s["runtime"],
    "resources": resources["requested"], "protected_sources_checked": 44, "published_payload_sources_checked": 7,
    "predecessor": predecessor, "previous_stage_chain_matches_accepted_records": True,
    "loco_resource_guard_checks": guard, "remote_status_sha256": c._sha(remote / "setup_status.json"),
    "previously_accepted_formal_fits": 62, "verified_analysis_rows": 108,
    "core_checkpoint_complete": True, "standard_checkpoint_complete": True,
    "next_user_terminal_command": command, "actual_agent_tc2_connections": 0,
    "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0, "audit_script_sha256": c._sha(Path(__file__))}
for source, name in [(OUT / "terminal.txt", "terminal.txt"), (index_path, "experiments-index.json"),
                     (remote / "setup_status.json", "remote_setup_status.json"),
                     (remote / "resources.json", "remote_resources.json"), (remote / "plan.json", "remote_plan.json")]:
    with (HERE / name).open("xb") as f:
        f.write(c._extended(source).read_bytes())
with (HERE / "previous_step7_status.json").open("xb") as f:
    f.write(old_bytes)
with (HERE / "verification.json").open("x", encoding="utf-8", newline="\n") as f:
    json.dump(record, f, indent=2, ensure_ascii=True, allow_nan=False)
    f.write("\n")
assert c._sha(state_path) == old_sha
local.update(status="awaiting_B0_LOCO_collection", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
    next_user_terminal_command=command,
    next_action="Collect the existing B0_LOCO job 44235 from the user terminal and return its output; do not resubmit.",
    latest_attempt={"job_id": "44235", "stage_id": "B0_LOCO", "node": "TC2N01", "slurm_state": "RUNNING",
        "exit_code": "0:0", "stage_complete": False, "verified_result_count": 0, "expected_result_count": 4,
        "verification": (HERE / "verification.json").relative_to(ROOT).as_posix()})
atomic_json(state_path, local)
assert read(state_path)["verified_formal_fits"] == 62 and len(read(state_path)["accepted_step_7_stages"]) == 11
print(json.dumps({"status": "passed", "job_id": "44235", "partial": True, "result_count": 0,
    "accepted_fits": 62, "verification": str(HERE / "verification.json")}, indent=2))
