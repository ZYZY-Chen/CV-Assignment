"""Insert only approved pilot actions; retain every preexisting helper byte."""
from pathlib import Path
import hashlib
import json

audit = Path(__file__).parent
target = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
before = (audit / "tc2_gpu_setup.before.ps1").read_bytes()
assert target.read_bytes() == before, "Helper changed after step-6 baseline"
functions = (audit / "pilot_helper_functions.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
branch = (audit / "pilot_helper_branch.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
old_set = b"'CheckAlgorithms','CheckWorkflow')]"
new_set = b"'CheckAlgorithms','CheckWorkflow','RunPilot','CollectPilot')]"
assert before.count(old_set) == 1
function_anchor = b"$guard = @'\r\n"
old_branch = b"    if ($Action -eq 'DownloadInputs') {\r\n"
assert before.count(function_anchor) == before.count(old_branch) == 1
after = before.replace(old_set, new_set).replace(function_anchor, functions + function_anchor).replace(old_branch, branch)
reverted = after.replace(new_set, old_set).replace(functions, b"").replace(branch, old_branch)
assert reverted == before
target.write_bytes(after)
result = {"status": "passed", "existing_helper_bytes_preserved": True,
          "allowed_validate_set_append": ["RunPilot", "CollectPilot"],
          "inserted_functions": ["Receive-Pilot"], "source": str(target),
          "before_sha256": hashlib.sha256(before).hexdigest().upper(),
          "after_sha256": hashlib.sha256(after).hexdigest().upper(),
          "function_template": "pilot_helper_functions.txt", "branch_template": "pilot_helper_branch.txt",
          "actual_tc2_connections": 0, "actual_slurm_submissions": 0}
(audit / "helper_changes.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
