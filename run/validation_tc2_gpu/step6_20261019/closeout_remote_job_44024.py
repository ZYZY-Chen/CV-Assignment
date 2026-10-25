"""Finalize step-6 acceptance and verify only authorized changes remain."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
from urllib.parse import unquote

REPO = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment")
ROOT = REPO / "group_XX_code"
AUDIT = ROOT / "run/validation_tc2_gpu/step6_20261019"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    value = hashlib.sha256()
    with Path("\\\\?\\" + str(path)).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


base = read(AUDIT / "baseline.json")
report = read(AUDIT / "accepted_job_44024/verification.json")
remote = read(AUDIT / "accepted_job_44024/remote_setup_status.json")
assert report["step_6_complete"] and remote["step_6_complete"] and report["status"] == remote["status"] == "passed"
changed = [item["path"] for item in base["files"] if sha(REPO / item["path"]) != item["sha256"]]
assert changed == ["group_XX_code/README.md"]
old = {item["path"] for item in base["files"]}
allowed = {"group_XX_code/" + name for name in base["allowed_new_sources"]}
new = []
for name in subprocess.check_output(["git", "-c", "core.longpaths=true", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=REPO).decode("utf-8").split("\0"):
    if not name or name in old or name.startswith("group_XX_code/run/validation_tc2_gpu/step6_20261019/"):
        continue
    assert name in allowed, name
    new.append(name)
assert set(new) == allowed
index = hashlib.sha256(subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=REPO)).hexdigest().upper()
assert index == base["git_index_sha256"]
subprocess.run(["git", "diff", "--check"], cwd=REPO, capture_output=True, check=True)
current_readme = (ROOT / "README.md").read_bytes()
start = current_readme.index(b"## TC2 GPU real-data pilot and step-6 acceptance")
end = current_readme.index(("## " + "".join(chr(x) for x in (0x6570, 0x636e, 0x96c6))).encode("utf-8"), start)
restored = current_readme[:start] + current_readme[end:]
before_readme = (AUDIT / "README.before.md").read_bytes()
for prefix in (b"Subsequent formal experiments use", b"Formal outputs use run/tc2_gpu/"):
    old_line = next(line for line in before_readme.splitlines(keepends=True) if line.startswith(prefix))
    new_line = next(line for line in restored.splitlines(keepends=True) if line.startswith(prefix))
    assert all(value < 128 for value in old_line + new_line)
    restored = restored.replace(new_line, old_line, 1)
assert restored == before_readme
helper = Path(base["external_helper"])
helper_bytes = helper.read_bytes()
eol = b"\r\n"
fix = eol.join([b'cd -- "$root"', b'[[ "$(pwd -P)" == "$root" ]] || { echo \'Pilot submission directory differs from the verified project root.\' >&2; exit 2; }', b'echo "Pilot submission directory: $(pwd -P)"']) + eol
assert helper_bytes.count(fix) == 1
before_fix = helper_bytes.replace(fix, b"", 1).replace(b'job_id=$(sbatch --chdir="$root" --parsable', b'job_id=$(sbatch --parsable', 1)
assert hashlib.sha256(before_fix).hexdigest().upper() == "4389FAA10B4260585F32205E70ADDBE96A0CAFC67D9D2B8B6ADA8FF86E0B3B3B"
functions = (AUDIT / "pilot_helper_functions.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", eol)
branch = (AUDIT / "pilot_helper_branch.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", eol)
restored_helper = before_fix.replace(b"'CheckAlgorithms','CheckWorkflow','RunPilot','CollectPilot')]", b"'CheckAlgorithms','CheckWorkflow')]", 1).replace(functions, b"", 1).replace(branch, b"    if ($Action -eq 'DownloadInputs') {\r\n", 1)
assert restored_helper == (AUDIT / "tc2_gpu_setup.before.ps1").read_bytes()
assert all(sha(ROOT / name) == value for name, value in remote["pilot_sources"].items())
design = read(ROOT / "configs/pilot_tc2_gpu.json")
assert all(sha(ROOT / name) == value for name, value in design["workflow_source_hashes"].items())
assert not (ROOT / "run/tc2_gpu").exists()
for file in (ROOT / "README.md", ROOT / "docs/TC2_GPU_PILOT.md"):
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
        if "://" not in target and not target.startswith("#"):
            assert (file.parent / unquote(target.split("#")[0])).exists(), target
scope = {"status": "passed", "preexisting_files_checked": len(base["files"]), "preexisting_files_unchanged": len(base["files"]) - len(changed),
         "changed_existing_files": changed, "new_source_files": sorted(new), "existing_chinese_and_unrelated_readme_bytes_preserved": True,
         "accepted_scientific_sources_frozen_inputs_locks_and_historical_records_unchanged": True,
         "all_six_submitted_pilot_files_unchanged": True, "submitted_design_document_preserved": True,
         "helper_changes_limited_to_pilot_actions_and_approved_submission_directory_fix": True,
         "git_index_unchanged": True, "git_diff_check_passed": True, "document_links_valid": True, "formal_output_directory_absent_locally": True}
status_path = AUDIT / "setup_status.json"
before_status = status_path.read_bytes()
status = json.loads(before_status)
assert not status["step_6_complete"]
backup = AUDIT / "setup_status.before_remote_acceptance.json"
assert not backup.exists()
backup.write_bytes(before_status)
status["local_scope"] = status["scope"]
status.update(status="passed", step_6_complete=True, checked_at_utc=datetime.now(timezone.utc).isoformat(), scope=scope,
              remote_acceptance_received=True, accepted_pilot_execution=report, submitted_pilot_source_hashes=remote["pilot_sources"],
              completion_scope=report["completion_scope"], source_hashes=remote["pilot_sources"],
              external_helper={"path": str(helper), "sha256": sha(helper)}, readme_sha256=sha(ROOT / "README.md"),
              submission_directory_fix={"user_authorization": "User requested script-only directory repair, direct README correction, no additional regression tests, and a new terminal submission after verification.",
                                        "verified_submission_directory": "/home/mcaai/huajie001/ca6129_v2_setup", "remote_pilot_sources_changed": False},
              activity_counters_scope="Existing zero activity counters describe assistant execution only. The user submitted the accepted TC2 job and its two fits using the local terminal helper.",
              required_next_action="Await the user's next-step design request. Reuse these two validated B0 results when identities match; execute no remaining matrix entry without its approved design.")
(AUDIT / "final_scope_validation.json").write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8")
status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": status["status"], "step_6_complete": True, "job_id": "44024", "completed_fits": 2,
                  "remaining_fits": 64, "scope": scope}, indent=2))
