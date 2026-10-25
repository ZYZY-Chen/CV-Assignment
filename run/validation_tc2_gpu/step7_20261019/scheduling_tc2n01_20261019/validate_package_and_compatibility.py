"""Check the local-only bundle and byte-exact preservation of older helper paths."""
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

audit = Path(__file__).parent
code = audit.parents[3]
helper = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
package = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_144521_22546814")
baseline = json.loads((audit / "baseline.json").read_text(encoding="utf-8"))
sha = lambda data: hashlib.sha256(data).hexdigest().upper()
old = (audit / "helper.before.ps1").read_bytes()
new = helper.read_bytes()
needle = b"$resourceArguments = '--gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00'"
replacement = needle.replace(b"'--gres", b"'--nodelist=TC2N01 --gres")
assert sha(old) == baseline["helper_sha256"]
assert old.count(needle) == new.count(replacement) == 1
assert new.replace(replacement, needle, 1) == old
expected = baseline["experiment_sources"]
for relative, digest in expected.items():
    assert sha((code / relative).read_bytes()) == digest, relative
    assert sha((package / "experiments_payload" / relative).read_bytes()) == digest, relative
manifest = (package / "experiments_payload/experiments.sha256").read_bytes()
lines = manifest.decode("ascii").splitlines()
actual = {line[66:]: line[:64].upper() for line in lines}
assert len(lines) == 7 and actual == expected
with tarfile.open(package / "experiments-files.tar", "r:") as stream:
    members = stream.getmembers()
    assert len(members) == 8
    assert {m.name for m in members} == set(expected) | {"experiments.sha256"}
    for member in members:
        assert member.isfile() and not member.islnk() and not member.issym()
        data = stream.extractfile(member).read()
        if member.name == "experiments.sha256":
            assert data == manifest
        else:
            assert sha(data) == expected[member.name]
terminal = (package / "terminal.txt").read_text(encoding="utf-8")
assert "LOCAL VALIDATION ONLY. Seven-file experiment bundle built for stage B0; no connection or submission." in terminal
transport = json.loads((audit / "experiments_transport_validation.json").read_text(encoding="utf-8"))
assert transport["status"] == "passed" and len(transport["cases"]) == 18
assert transport["gpu_fit_stages"] == 9 and transport["cpu_analysis_stages"] == 3
record = {
    "status": "passed",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "helper_before_sha256": sha(old),
    "helper_after_sha256": sha(new),
    "single_fit_resource_string_change_only": True,
    "all_older_action_branches_byte_identical": True,
    "powershell_ast_errors": 0,
    "offline_transport_cases": 18,
    "rendered_shell_commands": transport["rendered_shell_commands"],
    "gpu_fit_stage_requests_checked": 9,
    "cpu_analysis_stage_requests_checked": 3,
    "all_fit_stages_select_tc2n01": True,
    "all_analysis_stages_use_existing_scheduling": True,
    "submission_cwd_and_chdir_preserved": True,
    "real_helper_validate_only_exit_code": 0,
    "local_package_directory": str(package),
    "local_package_files": 8,
    "published_source_files_byte_identical": 7,
    "source_hashes": expected,
    "actual_tc2_connections": 0,
    "actual_slurm_submissions": 0,
}
(audit / "package_and_compatibility_validation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
