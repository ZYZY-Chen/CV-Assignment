"""Record the approved collection-only supplement and preserve stage acceptance."""
from pathlib import Path
from datetime import datetime, timezone
import difflib
import hashlib
import json
import re
import sys

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
COURSE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS")
HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_loco_tc2_gpu as collector
from pilot_tc2_gpu import atomic_json

sha = collector._sha
read = lambda p: json.loads(collector._extended(p).read_text(encoding="utf-8-sig"))
before = read(HERE / "before_scope.json")
ledger_path = AUDIT / "setup_status.json"
ledger = read(ledger_path)
assert ledger_path.read_bytes() == (HERE / "previous_step7_status.json").read_bytes()
assert ledger["verified_formal_fits"] == 62 and ledger["verified_analysis_rows"] == 108
assert len(ledger["accepted_step_7_stages"]) == 11 and not ledger["step_7_complete"]
assert not (HERE / "verification.json").exists()
changed = []
for name, fingerprint in before["existing_project_files"].items():
    if sha(ROOT / name) != fingerprint:
        changed.append(name)
assert changed == ["README.md"], changed
existing = set(before["existing_project_files"])
current = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()
           and "run" not in p.relative_to(ROOT).parts and "__pycache__" not in p.parts
           and ".git" not in p.parts and p.suffix.lower() not in (".npy", ".npz")}
assert current - existing == {"scripts/collect_experiments_loco_tc2_gpu.py", "tests/test_collect_experiments_loco_tc2_gpu.py"}, current - existing
for name, metadata in before["historical_run_file_metadata"].items():
    stat = collector._extended(ROOT / "run" / name).stat()
    assert [stat.st_size, stat.st_mtime_ns] == metadata, name
old_readme = (HERE / "README.before.md").read_text(encoding="utf-8")
new_readme = (ROOT / "README.md").read_text(encoding="utf-8")
chinese_lines = lambda text: [line for line in text.splitlines() if re.search(r"[\u3400-\u9fff]", line)]
assert chinese_lines(old_readme) == chinese_lines(new_readme)
design = read(ROOT / "configs/experiments_tc2_gpu.json")
protected = {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **ledger["experiment_sources"]}
assert len(protected) == 44
for name, fingerprint in protected.items():
    assert sha(ROOT / name) == fingerprint, name
provenance = collector._collection_provenance()
assert provenance["collector_sha256"] == "09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967"
assert sha(ROOT / "tests/test_collect_experiments_loco_tc2_gpu.py") == "7FC31998DC2901B96F5C0420B41E6C12937EAB695FD932766DF37A7C21B9F222"
assert "torch" not in sys.modules and "numpy" not in sys.modules
compatibility = []
for accepted in ledger["accepted_step_7_stages"]:
    record_path = ROOT / accepted["record"]
    assert sha(record_path) == accepted["record_sha256"]
    raw_path = record_path.parent / "remote_setup_status.json"
    assert sha(raw_path) == accepted["remote_status_sha256"]
    if not accepted["verified_fits"]:
        continue
    record, raw = read(record_path), read(raw_path)
    hashes = read(record_path.parent / "archive_file_hashes.json")
    for result in raw["results"]:
        page = Path(record["result_page_locations"][result["run_key"]])
        files = {}
        for name in ("metrics.json", "samples.json", "config.yaml"):
            relative = result["path"] + "/" + name
            path = page / relative
            assert sha(path) == hashes[relative], relative
            files[name] = read(path)
        collector._validate_result_metrics(files["metrics.json"], files["config.yaml"], files["samples.json"])
        compatibility.append({"stage_id": accepted["stage_id"], "run_key": result["run_key"],
                              "metric_sha256": hashes[result["path"] + "/metrics.json"], "status": "passed"})
assert len(compatibility) == 62
test_text = (HERE / "loco_tests_final.txt").read_text(encoding="utf-8-sig")
assert "Ran 43 tests" in test_text and re.search(r"\nOK\s*$", test_text)
checks = {}
for name in ("local_transport_validation.json", "pilot_transport_validation.json", "experiments_transport_validation.json",
             "loco_transport_validation.json", "publish_guard_validation.json", "loco_bash_syntax_validation.json"):
    value = read(HERE / name)
    assert value["status"].lower() in ("passed", "pass"), name
    checks[name] = {"sha256": sha(HERE / name), "status": "passed"}
assert len(read(HERE / "loco_transport_validation.json")["cases"]) == 12
assert len(read(HERE / "publish_guard_validation.json")["checks"]) == 6
assert read(HERE / "loco_bash_syntax_validation.json")["scripts_checked"] == 13
helper = COURSE / "output/tc2_gpu_setup.ps1"
helper_sha = sha(helper)
for old_path, new_path, name in ((HERE / "helper.before.ps1", helper, "helper.diff"),
                                (HERE / "README.before.md", ROOT / "README.md", "README.diff"),
                                (ROOT / "scripts/collect_experiments_tc2_gpu.py", ROOT / "scripts/collect_experiments_loco_tc2_gpu.py", "collector.diff")):
    difference = "".join(difflib.unified_diff(old_path.read_text(encoding="utf-8").splitlines(True),
                                            new_path.read_text(encoding="utf-8").splitlines(True), fromfile=old_path.name, tofile=new_path.name))
    with (HERE / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(difference)
with (HERE / "helper.tested.ps1").open("xb") as stream:
    stream.write(helper.read_bytes())
with (HERE / "existing_AD_compatibility.json").open("x", encoding="utf-8") as stream:
    json.dump({"status": "passed", "result_count": 62, "checks": compatibility}, stream, indent=2)
    stream.write("\n")
command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + str(helper) + '" -Action CollectExperiments -JobId 44235 -LocoCollection'
record = {"status": "passed", "scope": "Approved step-7 LOCO collection-only supplement",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(), "step_7_complete": False,
    "implementation_files": {name: sha(ROOT / name) for name in ("scripts/collect_experiments_loco_tc2_gpu.py", "tests/test_collect_experiments_loco_tc2_gpu.py", "README.md")},
    "external_helper_sha256": helper_sha, "previous_external_helper_sha256": before["helper_sha256"],
    "collector_provenance": provenance, "new_collector_tests": {"tests_run": 43, "failures": 0, "errors": 0, "skipped": 0,
        "source_sha256": sha(ROOT / "tests/test_collect_experiments_loco_tc2_gpu.py"), "console_sha256": sha(HERE / "loco_tests_final.txt")},
    "checks": checks, "existing_AD_results_compatible": 62,
    "existing_AD_compatibility_sha256": sha(HERE / "existing_AD_compatibility.json"),
    "protected_scientific_pilot_experiment_files_unchanged": 44,
    "frozen_seven_experiment_sources_unchanged": True,
    "historical_run_files_metadata_unchanged": len(before["historical_run_file_metadata"]),
    "accepted_stage_record_and_remote_status_hashes_unchanged": 11,
    "existing_Chinese_README_lines_unchanged": True,
    "accepted_formal_fits": 62, "accepted_analysis_rows": 108, "remaining_formal_fits": 4,
    "runtime_observation": "The latest remote snapshot showed job 44235 RUNNING at 00:20:44; current remote state is unknown.",
    "next_user_terminal_command": command,
    "next_acceptance": "Collect the existing job with the independent LOCO collector, verify all returned pages, saved arrays and pooled/group image metrics. Original-mask pixel metric reproduction remains remote evidence. All twelve local stage collections are required for step-7 completion.",
    "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "actual_agent_model_calls": 0,
    "report_writing_started": False}
with (HERE / "verification.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
ledger.update(status="awaiting_B0_LOCO_collection", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
    external_helper_sha256=helper_sha, next_user_terminal_command=command,
    next_action="Collect existing B0_LOCO job 44235 using -LocoCollection and return terminal.txt; do not refit or resubmit.",
    next_acceptance=record["next_acceptance"],
    loco_collection_supplement={"status": "passed", "record": (HERE / "verification.json").relative_to(ROOT).as_posix(),
        "record_sha256": sha(HERE / "verification.json"), "collector_provenance": provenance,
        "external_helper_sha256": helper_sha, "new_collector_tests": 43, "existing_AD_results_compatible": 62,
        "frozen_experiment_sources_unchanged": True, "remote_recollection_pending": True})
atomic_json(ledger_path, ledger)
assert not read(ledger_path)["step_7_complete"] and read(ledger_path)["verified_formal_fits"] == 62
print(json.dumps({"status": "passed", "collector_tests": 43, "existing_AD_results": 62,
    "historical_run_files_unchanged": len(before["historical_run_file_metadata"]),
    "verification": str(HERE / "verification.json"), "next_user_terminal_command": command}, indent=2))
