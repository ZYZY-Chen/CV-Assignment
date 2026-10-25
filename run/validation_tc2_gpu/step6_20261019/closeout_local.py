"""Verify approved step-6 local scope and delivery; never submit real work."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from urllib.parse import unquote

REPO = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment")
ROOT = REPO / "group_XX_code"
AUDIT = ROOT / "run/validation_tc2_gpu/step6_20261019"
PACK = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_134135_dcc0c587")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with Path("\\\\?\\" + str(path)).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


base = read(AUDIT / "baseline.json")
changed = []
for item in base["files"]:
    if sha(REPO / item["path"]) != item["sha256"]:
        changed.append(item["path"])
assert changed == base["allowed_existing_changes"], changed
old = {item["path"] for item in base["files"]}
allowed = {"group_XX_code/" + name for name in base["allowed_new_sources"]}
new, audit_count = [], 0
for name in subprocess.check_output(["git", "-c", "core.longpaths=true", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=REPO).decode("utf-8").split("\0"):
    if not name or name in old:
        continue
    if name.startswith("group_XX_code/run/validation_tc2_gpu/step6_20261019/"):
        audit_count += 1
        continue
    assert name in allowed, name
    new.append(name)
assert set(new) == allowed
index = hashlib.sha256(subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=REPO)).hexdigest().upper()
assert index == base["git_index_sha256"]
subprocess.run(["git", "diff", "--check"], cwd=REPO, capture_output=True, check=True)
readme = (ROOT / "README.md").read_bytes()
start = readme.index(b"## TC2 GPU real-data pilot and step-6 acceptance")
end = readme.index(("## " + "".join(chr(x) for x in (0x6570, 0x636e, 0x96c6))).encode("utf-8"), start)
assert readme[:start] + readme[end:] == (AUDIT / "README.before.md").read_bytes()
helper = Path(base["external_helper"])
before = (AUDIT / "tc2_gpu_setup.before.ps1").read_bytes()
current = helper.read_bytes()
functions = (AUDIT / "pilot_helper_functions.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
branch = (AUDIT / "pilot_helper_branch.txt").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
old_set = b"'CheckAlgorithms','CheckWorkflow')]"
new_set = b"'CheckAlgorithms','CheckWorkflow','RunPilot','CollectPilot')]"
assert current.count(functions) == current.count(branch) == 1
assert current.replace(new_set, old_set, 1).replace(functions, b"", 1).replace(branch, b"    if ($Action -eq 'DownloadInputs') {\r\n", 1) == before
assert sha(helper) == read(AUDIT / "helper_changes.json")["after_sha256"]
for name in base["allowed_new_sources"]:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert not re.search(r"[\u3400-\u9fff]", text), name
    if name.endswith(".py"):
        ast.parse(text, filename=name)
config = read(ROOT / "configs/pilot_tc2_gpu.json")
assert all(sha(ROOT / name) == value for name, value in config["workflow_source_hashes"].items())
local = read(AUDIT / "offline_tests_04/setup_status.json")
assert local["status"] == "passed" and local["tests_run"] == 28 and local["failures"] == local["errors"] == local["skipped"] == 0
assert not local["step_6_complete"]
assert all(sha(ROOT / name) == value for name, value in local["source_hashes"].items())
transport = read(AUDIT / "pilot_transport_validation.json")
legacy = read(AUDIT / "local_transport_validation.json")
bootstrap = read(AUDIT / "pilot_bootstrap_validation.json")
bash = read(AUDIT / "helper_bash_validation.json")
assert transport["status"] == bootstrap["status"] == bash["status"] == "passed"
assert len(transport["cases"]) == 6 and len(bootstrap["cases"]) == 9 and bash["scripts_parsed"] == 9
assert legacy["status"] == "PASS" and legacy["rendered_shell_commands"] == 19
with tarfile.open(PACK / "pilot-files.tar") as archive:
    members = {item.name.removeprefix("./"): item for item in archive.getmembers() if item.isfile()}
    assert set(members) == {"pilot.sha256", *base["allowed_new_sources"]}
    rows = archive.extractfile(members["pilot.sha256"]).read().decode("ascii").splitlines()
    assert len(rows) == 6
    for row in rows:
        value, name = row.split(None, 1)
        assert hashlib.sha256(archive.extractfile(members[name]).read()).hexdigest().upper() == value.upper() == sha(ROOT / name)
assert "LOCAL VALIDATION ONLY" in (PACK / "terminal.txt").read_text(encoding="utf-8")
guard = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/pilot_tc2_gpu.py"), "run", "--root", str(ROOT)], capture_output=True, text=True)
assert guard.returncode != 0 and "Real-data pilots require a Linux SLURM compute job" in guard.stderr
(AUDIT / "local_guard_terminal.txt").write_text(guard.stdout + guard.stderr, encoding="utf-8")
assert not (ROOT / "run/tc2_gpu").exists()
scope = {"status": "passed", "preexisting_files_checked": len(base["files"]),
         "preexisting_files_unchanged": len(base["files"]) - len(changed), "changed_existing_files": changed,
         "new_source_files": sorted(new), "new_audit_files_before_closeout": audit_count,
         "readme_existing_bytes_and_chinese_preserved": True, "other_helper_bytes_preserved": True,
         "accepted_scientific_sources_frozen_inputs_locks_and_historical_records_unchanged": True,
         "git_index_unchanged": True, "git_diff_check_passed": True, "formal_output_directory_absent_locally": True}
status = {"status": "local_implementation_verified_awaiting_tc2_real_data_pilot", "step_6_complete": False,
          "checked_at_utc": datetime.now(timezone.utc).isoformat(), "authorization": base["authorization"],
          "approved_design": "docs/TC2_GPU_PILOT.md", "scope": scope, "offline_tests": local,
          "new_transport": transport, "legacy_transport": legacy, "bootstrap": bootstrap, "bash_syntax": bash,
          "local_compute_guard": {"status": "expected_refusal", "exit_code": guard.returncode, "torch_imported": False},
          "packaging_only": {"status": "passed", "files": 6, "terminal": str(PACK / "terminal.txt"), "bundle_sha256": sha(PACK / "pilot-files.tar")},
          "source_hashes": {name: sha(ROOT / name) for name in base["allowed_new_sources"]},
          "accepted_workflow_source_hashes": config["workflow_source_hashes"],
          "external_helper": {"path": str(helper), "sha256": sha(helper)},
          "required_pilot": {"dataset": "mvtec_ad", "category": "bottle", "run_keys": config["run_keys"], "expected_counts": config["expected_counts"], "resources": config["resources"]},
          "remote_acceptance_received": False, "actual_model_calls": 0, "actual_tc2_connections": 0, "actual_slurm_submissions": 0,
          "required_next_action": "The user runs RunPilot in the local terminal and returns terminal.txt. Use CollectPilot for the same job when queued/running; do not resubmit."}
(AUDIT / "setup_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
for path in [ROOT / "README.md", ROOT / "docs/TC2_GPU_PILOT.md"]:
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        if "://" not in target and not target.startswith("#"):
            assert (path.parent / unquote(target.split("#")[0])).exists(), target
scope["document_links_valid"] = True
(AUDIT / "scope_validation.json").write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8")
(AUDIT / "setup_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": status["status"], "step_6_complete": False, "offline_tests": 28, "scope": scope,
                  "packaged_files": 6, "remote_job_submitted": False}, indent=2))
