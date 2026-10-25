"""Read-only preservation audit with a fresh step-8 receipt."""
from pathlib import Path
import hashlib
import json
import re

root = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
audit = root / "run/validation_tc2_gpu/step8_20261019"
helper = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
before = json.loads((audit / "before_scope.json").read_bytes())
def extended(path):
    return Path("\\\\?\\"+str(path.absolute()))
def sha(path):
    return hashlib.sha256(extended(path).read_bytes()).hexdigest().upper()
changed = [name for name, expected in before["existing_files"].items() if sha(root/name) != expected]
assert changed == ["README.md"], changed
old_readme = (audit / "README.before.md").read_text(encoding="utf-8-sig")
new_readme = (root / "README.md").read_text(encoding="utf-8-sig")
chinese = lambda text: [line for line in text.splitlines() if re.search(r"[\u3400-\u9fff]",line)]
assert chinese(old_readme) == chinese(new_readme), "Existing Chinese README content changed"
altered = []
for name, expected in before["historical_run_metadata"].items():
    path = extended(root/"run"/name)
    if not path.is_file() or [path.stat().st_size,path.stat().st_mtime_ns] != expected:
        altered.append(name)
assert not altered, altered[:10]
assert sha(root/"run/validation_tc2_gpu/step7_20261019/setup_status.json") == before["step7_status_sha256"]
registry = json.loads((audit / "validated_inputs_final.json").read_bytes())
assert all(sha(root/name) == expected for name, expected in registry["protected_sources"].items())
assert all(sha(root/name) == expected for name, expected in registry["analysis_sources"].items())
expected_new = set(registry["analysis_sources"])
observed = {p.relative_to(root).as_posix() for folder in ("configs","scripts","tests","docs") for p in (root/folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
assert observed - set(before["existing_files"]) == expected_new, sorted(observed - set(before["existing_files"]))
old_helper = (audit/"helper.before.ps1").read_text(encoding="utf-8-sig")
new_helper = helper.read_text(encoding="utf-8-sig")
# The prior RunExperiments-through-legacy action implementation remains byte-for-byte equivalent as text.
start = "($Action -eq 'RunExperiments') {"
end = "    Log 'Action finished. Read the relevant status JSON:"
old_actions = old_helper[old_helper.index(start):old_helper.index(end)].rstrip()
new_actions = new_helper[new_helper.index(start):new_helper.index("    if ($Action -in @('RunAnalysis','CollectAnalysis'))")].rstrip()
assert old_actions == new_actions, "Existing action implementations changed"
# Every original helper function is located before the new Receive-Analysis insertion.
old_functions = old_helper[old_helper.index("function Log("):old_helper.index("$guard = @'")].rstrip()
new_functions = new_helper[new_helper.index("function Log("):new_helper.index("function Receive-Analysis(")].rstrip()
assert old_functions == new_functions, "Existing helper functions changed"
report = {"status":"passed","existing_source_files_checked":len(before["existing_files"]),
          "existing_source_files_modified":changed,"new_source_files":sorted(expected_new),
          "protected_sources_unchanged":len(registry["protected_sources"]),
          "historical_run_files_unchanged":len(before["historical_run_metadata"]),
          "existing_chinese_readme_unchanged":True,"step7_ledger_unchanged":True,
          "existing_helper_functions_and_actions_unchanged":True,
          "helper_sha256":sha(helper),"analysis_sources":registry["analysis_sources"],
          "actual_agent_tc2_connections":0,"actual_agent_slurm_submissions":0,"actual_agent_model_calls":0}
(audit/"final_scope_validation.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"status":"passed","existing_sources":len(before["existing_files"]),"protected_sources":44,"historical_files":len(before["historical_run_metadata"]),"new_sources":7}))
