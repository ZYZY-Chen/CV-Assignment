"""Verify the returned step-3 evidence without connecting to TC2 or running tests."""
import hashlib
import json
import re
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

AUDIT = Path(__file__).resolve().parent
CODE = AUDIT.parents[2]
REPO = CODE.parent
OUTPUT = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_setup_v2_20261019_083700_13089bef")
REMOTE = OUTPUT / "remote"
SNAPSHOT = AUDIT / "remote_job_43956/snapshot_20261019_083700_13089bef"
ARCHIVE_SHA256 = "E4D4112A233B39754EB10BC35E877F820379B00588BC525C3A8DBFCDF041515A"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def copy_exact(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert digest(target) == digest(source), f"Conflicting evidence: {target}"
    else:
        shutil.copy2(source, target)


archive = OUTPUT / "remote-output.tar.gz"
assert digest(archive) == ARCHIVE_SHA256
terminal = (OUTPUT / "terminal.txt").read_text(encoding="utf-8-sig")
assert f"SHA256={ARCHIVE_SHA256}" in terminal
assert re.search(r"^43956\s+\S+\s+COMPLETED\s+0:0\s+00:00:19\s+TC2N01\s*$", terminal, re.M)
members = []
with tarfile.open(archive) as bundle:
    for entry in bundle.getmembers():
        path = PurePosixPath(entry.name)
        assert entry.isfile() and not entry.issym() and not entry.islnk()
        assert not path.is_absolute() and ".." not in path.parts and "\\" not in entry.name
        assert path.parts[:2] in [("run", "setup_v2"), ("run", "validation_v2")] or entry.name in {
            "configs/tc2_setup.json", "environment-tc2.yml", "requirements-tc2-lock.txt"
        }
        assert entry.name not in members
        data = bundle.extractfile(entry).read()
        local = REMOTE.joinpath(*path.parts)
        assert local.is_file() and local.read_bytes() == data, entry.name
        members.append(entry.name)
assert len(members) == 100
assert {p.relative_to(REMOTE).as_posix() for p in REMOTE.rglob("*") if p.is_file()} == set(members)

status_path = REMOTE / "run/validation_v2/step3_job_43956/setup_status.json"
status = read_json(status_path)
assert status["mode"] == "full" and status["status"] == "passed" and status["step_3_complete"] is True
assert status["tests_run"] == 24 and status["failures"] == status["errors"] == status["skipped"] == 0
assert status["failure_details"] == []
assert status["reference"]["cases"] == 81
for key in ("max_auroc_abs_error", "max_ap_abs_error"):
    assert 0 <= status["reference"][key] <= 1e-12
runtime = status["runtime"]
assert runtime["slurm_job_id"] == "43956" and runtime["step_2_job_id"] == "43950"
assert runtime["device"] == "cpu" and runtime["gpu_requested"] is False
assert runtime["python"].startswith("3.10.22") and runtime["frozen_manifests_verified"] == 8
assert runtime["packages"] == {"numpy": "1.26.4", "scikit-learn": "1.7.2", "torch": "2.11.0+cu128", "torchvision": "0.26.0+cu128", "pillow": "12.3.0"}
protocol_path = CODE / "configs/protocol_v2.json"
assert digest(protocol_path) == runtime["protocol_sha256"] == "3098B6A86DBA64EE439BFE61C7A4FCFFCD082371D5A80FFBC7940997ED6A1ED1"
for manifest in read_json(protocol_path)["data"]["frozen_manifests"]:
    assert digest(CODE / manifest["path"]) == manifest["file_sha256"]
for path, expected in {
    "environment-tc2.yml": "47F1DAA83A744743946C83E6DC1963B8FA7E835A4A0F7010A3B0501EF5A3DF38",
    "requirements-tc2-lock.txt": "F7B848F10FFB3F3CCEB707450B2A5FE4DCD9A6C3B489963A8932094E016840B6",
}.items():
    assert digest(CODE / path) == expected == digest(REMOTE / path)
step2 = read_json(REMOTE / "run/setup_v2/job_43950_all/setup_status.json")
assert step2["mode"] == "all" and step2["step_2_complete"] is True
stage = REMOTE / "run/validation_v2/metrics_stage_20261019_083700_13089bef"
stage_hashes = {line.split(maxsplit=1)[1].strip(): line.split()[0].upper() for line in (stage / "metrics.sha256").read_text().splitlines()}
assert stage_hashes == status["source_hashes"]
assert len(stage_hashes) == 5
for path, expected in stage_hashes.items():
    assert digest(CODE / path) == expected == digest(OUTPUT / "metrics_payload" / path)
assert (stage / "metrics.sha256").read_bytes() == (OUTPUT / "metrics_payload/metrics.sha256").read_bytes()
assert (stage / "job_id.txt").read_text().strip() == "43956"
assert (REMOTE / "run/validation_v2/last_check_metrics_job.txt").read_text().strip() == "43956"
assert (REMOTE / "run/validation_v2/slurm-43956.err").stat().st_size == 0
test_log = (REMOTE / "run/validation_v2/slurm-43956.out").read_text()
assert "Ran 24 tests" in test_log and "\nOK\n" in test_log
wrapper = (CODE / "scripts/slurm/check_metrics_v2.sh").read_text()
assert "#SBATCH --cpus-per-task=2" in wrapper and "#SBATCH --mem=4G" in wrapper and "#SBATCH --time=00:15:00" in wrapper
assert not re.search(r"^#SBATCH.*(?:--gres|--gpus)", wrapper, re.M)

baseline = read_json(AUDIT / "baseline.json")
changed = []
by_hash = {}
for item in baseline["files"]:
    path = REPO / item["path"]
    assert path.is_file(), item["path"]
    actual = digest(path)
    by_hash.setdefault(actual, []).append(item["path"])
    if actual != item["sha256"]:
        changed.append(item["path"])
assert set(changed) == set(baseline["allowed_existing_changes"])
baseline_paths = {entry["path"] for entry in baseline["files"]}
added = []
for path in REPO.rglob("*"):
    if not path.is_file():
        continue
    relative = path.relative_to(REPO).as_posix()
    if any(relative == excluded or relative.startswith(excluded + "/") for excluded in baseline["excluded_directories"]):
        continue
    if "__pycache__" in path.parts:
        continue
    if relative not in baseline_paths:
        added.append(relative)
assert set(added) == {
    "group_XX_code/docs/METRICS_V2.md", "group_XX_code/src/metric_core.py",
    "group_XX_code/tests/test_metrics_v2.py", "group_XX_code/scripts/slurm/check_metrics_v2.sh",
}
legacy = read_json(CODE / "run/legacy_v1_inventory.json")
legacy_hash_fallbacks = []
for item in legacy["legacy_files"]:
    path = REPO / item["path"]
    if path.is_file():
        assert digest(path) == item["sha256"] and path.stat().st_size == item["size_bytes"]
    else:
        # Two legacy inventory filenames contain pre-existing replacement characters.
        matches = [name for name in by_hash.get(item["sha256"], []) if (REPO / name).stat().st_size == item["size_bytes"]]
        assert len(matches) == 1, item["path"]
        legacy_hash_fallbacks.append({"inventory_path": item["path"], "verified_path": matches[0]})
assert len(legacy["legacy_files"]) == 346 and not (CODE / "run/v2").exists()
assert digest(REPO / ".gitignore") == "EB51A534837CCC5EE368439B48FB56129B7AE505B7661527164B2DBCF7C56021"

copy_exact(OUTPUT / "terminal.txt", SNAPSHOT / "terminal.txt")
copy_exact(archive, SNAPSHOT / "remote-output.tar.gz")
for name in members:
    # Fixture PNGs remain in the verified archive; avoid Windows MAX_PATH in the nested audit copy.
    if (name.startswith("run/validation_v2/") and "/synthetic_fixtures/" not in name) or name == "run/setup_v2/job_43950_all/setup_status.json":
        copy_exact(REMOTE / name, SNAPSHOT / "remote" / name)
result = {
    "status": "passed", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    "step_3_complete": True, "source_output": str(OUTPUT), "snapshot": str(SNAPSHOT),
    "slurm": {"job_id": "43956", "state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:00:19", "node": "TC2N01", "device": "cpu", "gpu_requested": False, "stderr_bytes": 0},
    "archive": {"sha256": ARCHIVE_SHA256, "regular_files": len(members), "all_downloaded_bytes_match": True, "paths_and_member_types_verified": True},
    "acceptance": {"tests_run": 24, "failures": 0, "errors": 0, "skipped": 0, "reference": status["reference"], "absolute_error_tolerance": 1e-12},
    "source_hashes": status["source_hashes"], "local_payload_remote_source_hashes_match": True,
    "protocol_manifests_and_environment_locks_preserved": True, "step_2_all_job_43950_still_passed": True,
    "scope": {"baseline_files_verified": len(baseline["files"]), "modified_existing_files": sorted(changed), "added_source_files": sorted(added), "legacy_files_preserved": 346, "legacy_filename_hash_resolutions": legacy_hash_fallbacks, "user_gitignore_preserved": True, "formal_run_v2_not_created": True},
    "remote_commands_executed_by_this_verifier": False,
}
(AUDIT / "remote_job_43956/verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "archive_files": len(members), "tests": 24, "reference_cases": 81, "baseline_files": len(baseline["files"]), "verification": str(AUDIT / "remote_job_43956/verification.json")}, ensure_ascii=False))
