"""Preserve the failed job evidence and verify the narrow approved repair scope."""
from pathlib import Path
import hashlib
import json
import re

root = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
audit = root / "run/validation_tc2_gpu/step8_dependency_repair_20261019"
output = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_214652_c9d1a0af")
helper = output.parent / "tc2_gpu_setup.ps1"
extended = lambda path: Path("\\\\?\\"+str(path.absolute()))
sha = lambda path: hashlib.sha256(extended(path).read_bytes()).hexdigest().upper()
before = json.loads((audit / "before_scope.json").read_bytes())
index_path = output / "analysis-index.json"
expected_index = "237F94263B68FBE8E4F648D1712C2FF17BCE6261175D1CCF757C3CE758C67DFE"
assert sha(index_path) == expected_index
index = json.loads(index_path.read_bytes())
assert index["job_id"] == "44271" and index["partial"] is True and len(index["pages"]) == 1
rows = index["pages"][0]["files"]
assert len(rows) == 23
for page in index["pages"]:
    assert sha(output/page["name"]) == page["sha256"]
    assert (output/page["name"]).stat().st_size == page["bytes"]
    for row in page["files"]:
        path = output / "remote" / ("page_%03d" % page["page_number"]) / row["path"]
        assert sha(path) == row["sha256"] and extended(path).stat().st_size == row["size"]
record = output / "remote/page_001/run/validation_tc2_gpu/step8_job_44271"
state = json.loads(extended(record/"setup_status.json").read_bytes())
tests = json.loads(extended(record/"tests/test_report.json").read_bytes())
assert state["status"] == "failed" and state["step_8_complete"] is False
assert "collect_experiments_loco_tc2_gpu.py" in state["error"]
assert tests["status"] == "passed" and tests["tests_run"] == 29 and tests["full_plot_render_passed"] is True
assert tests["skipped"] == 0 and not tests["torch_imported"] and not tests["gpu_or_models_executed"]
assert all(sha(root/name) == fingerprint for name,fingerprint in state["sources"].items())
failure = {"status":"verified_failed_job","job_id":"44271","slurm_state":"FAILED","exit_code":"1:0",
    "elapsed":"00:00:23","node":"TC2N01","cpus":2,"requested_memory":"8G",
    "index_sha256":expected_index,"pages_verified":1,"payload_files_verified":23,
    "remote_full_tests_passed":29,"synthetic_plot_render_passed":True,"step_8_complete":False,
    "error":state["error"],"source_directory":str(output),"scientific_results_created":False,
    "actual_agent_tc2_connections":0,"actual_agent_slurm_submissions":0,"actual_agent_model_calls":0}
(audit/"job_44271_failure_verification.json").write_text(json.dumps(failure,indent=2)+"\n")
changed = [name for name,fingerprint in before["existing_files"].items() if sha(root/name) != fingerprint]
assert changed == ["README.md"], changed
assert all(sha(root/name) == fingerprint for name,fingerprint in before["analysis_sources"].items())
assert all(sha(root/name) == fingerprint for name,fingerprint in before["protected_sources"].items())
for name,expected in before["historical_run_metadata"].items():
    path = extended(root/"run"/name)
    assert path.is_file() and [path.stat().st_size,path.stat().st_mtime_ns] == expected,name
assert sha(root/"run/validation_tc2_gpu/step8_20261019/setup_status.json") == before["step8_status_sha256"]
chinese = lambda text: [line for line in text.splitlines() if re.search(r"[\u3400-\u9fff]",line)]
assert chinese((audit/"README.before.md").read_text(encoding="utf-8-sig")) == chinese((root/"README.md").read_text(encoding="utf-8-sig"))
old = (audit/"helper.before.ps1").read_text(encoding="utf-8-sig")
new = helper.read_text(encoding="utf-8-sig")
start = "($Action -eq 'RunExperiments') {"
end = "    if ($Action -in @('RunAnalysis','CollectAnalysis'"
assert old[old.index(start):old.index(end)] == new[new.index(start):new.index(end)]
for marker,last in (("$guard = @'","Log ('TC2 GPU: "),):
    assert old[old.index(marker):old.index(last)] == new[new.index(marker):new.index(last)]
old_analysis = old[old.index("($Action -eq 'RunAnalysis') {"):old.index("    } elseif ($Action -eq 'CollectAnalysis')")]
new_analysis = new[new.index("($Action -eq 'RunAnalysis') {"):new.index("    } elseif ($Action -eq 'CollectAnalysis')")]
new_analysis = new_analysis.replace("            $dependencyCheck = Get-AnalysisDependencyScript 'check'\n", "")
new_analysis = new_analysis.replace(' + $dependencyCheck + "`n"', '')
assert old_analysis == new_analysis,"Analysis modifications exceed the two approved preflight checks"
scope = {"status":"passed","existing_project_files_checked":len(before["existing_files"]),
    "project_source_files_modified":changed,"analysis_sources_unchanged":7,"protected_sources_unchanged":44,
    "historical_run_files_unchanged":len(before["historical_run_metadata"]),"existing_chinese_readme_unchanged":True,
    "existing_experiment_and_legacy_actions_unchanged":True,"existing_guard_and_queue_checks_unchanged":True,
    "analysis_changes":"Two read-only preflight checks only","step8_master_record_unchanged":True,
    "helper_sha256":sha(helper),"readme_sha256":sha(root/"README.md"),"step_8_complete":False}
(audit/"scope_validation.json").write_text(json.dumps(scope,indent=2)+"\n")
print(json.dumps({"status":"passed","job_44271_full_tests":29,"seven_analysis_files_unchanged":True,"historical_run_files":len(before["historical_run_metadata"])}))
