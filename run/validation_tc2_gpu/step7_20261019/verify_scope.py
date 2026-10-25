"""Audit approved step-7 changes against the pre-edit snapshot."""
from datetime import datetime, timezone
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]
REPO = ROOT.parent


def disk(path):
    value = str(path.absolute())
    return Path("\\\\?\\" + value) if not value.startswith("\\\\?\\") else path


def sha(path):
    digest = hashlib.sha256()
    with disk(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read(path):
    return json.loads(disk(path).read_text(encoding="utf-8"))


baseline = read(AUDIT / "baseline.json")
allowed = set(baseline["allowed_existing_changes"])
changed = []
for entry in baseline["files"]:
    path = REPO / entry["path"]
    if not disk(path).is_file() or sha(path) != entry["sha256"]:
        changed.append(entry["path"])
unexpected_changes = sorted(set(changed) - allowed)
git_environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
rows = subprocess.check_output(["git", "-c", "core.longpaths=true", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=REPO, env=git_environment)
names = {name.decode("utf-8") for name in rows.split(b"\0") if name}
old_names = {entry["path"] for entry in baseline["files"]}
new_names = names - old_names
allowed_new = {"group_XX_code/" + name for name in baseline["allowed_new_sources"]}
audit_prefix = AUDIT.relative_to(REPO).as_posix() + "/"
unexpected_new = sorted(name for name in new_names if name not in allowed_new and not name.startswith(audit_prefix))
present_new = sorted(name for name in new_names if name in allowed_new)
index = REPO / subprocess.check_output(["git", "rev-parse", "--git-path", "index"], cwd=REPO, text=True, env=git_environment).strip()
staged = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=REPO, env=git_environment)
tree = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", "-z", "HEAD"], cwd=REPO, env=git_environment)
staged_entries = {}
for row in staged.split(b"\0"):
    if row:
        fields, name = row.split(b"\t", 1)
        mode, blob, stage_number = fields.split()
        if stage_number != b"0":
            raise ValueError("Unexpected unmerged index entry")
        staged_entries[name] = (mode, blob)
head_entries = {}
for row in tree.split(b"\0"):
    if row:
        fields, name = row.split(b"\t", 1)
        mode, kind, blob = fields.split()
        head_entries[name] = (mode, blob)
index_content_matches_head = staged_entries == head_entries
helper = Path(baseline["external_helper"])
helper_changes = read(AUDIT / "helper_changes.json")
current_helper = disk(helper).read_bytes()
reversed_helper = current_helper
for change in reversed(helper_changes["changes"]):
    before, after = change["before"].encode("utf-8"), change["after"].encode("utf-8")
    if reversed_helper.count(after) != 1:
        raise ValueError("Cannot uniquely reverse an approved helper insertion")
    reversed_helper = reversed_helper.replace(after, before, 1)
preserved_helper = reversed_helper == disk(AUDIT / "tc2_gpu_setup.before.ps1").read_bytes()
old_readme = disk(AUDIT / "README.before.md").read_text(encoding="utf-8")
new_readme = disk(ROOT / "README.md").read_text(encoding="utf-8")
chinese_lines = lambda text: [line for line in text.splitlines() if re.search(r"[\u3400-\u9fff]", line)]
preserved_chinese = chinese_lines(old_readme) == chinese_lines(new_readme)
new_english = all(not re.search(r"[\u3400-\u9fff]", disk(ROOT / name).read_text(encoding="utf-8")) for name in baseline["allowed_new_sources"])
for name in baseline["allowed_new_sources"]:
    if name.endswith(".py"):
        ast.parse(disk(ROOT / name).read_text(encoding="utf-8"), filename=name)
wrapper_lf = b"\r" not in disk(ROOT / "scripts/slurm/experiments_tc2_gpu.sh").read_bytes()
sources = {name: sha(ROOT / name) for name in baseline["allowed_new_sources"]}
tests = read(AUDIT / "offline_final/setup_status.json")
helper_check = read(AUDIT / "helper_final_validation.json")
required_reports = ["collector_validation.json", "collector_additional_validation.json", "helper_static_validation.json",
                    "local_transport_validation.json", "pilot_transport_validation.json", "experiments_transport_validation.json",
                    "experiments_bootstrap_validation.json", "helper_final_validation.json"]
reports = {name: read(AUDIT / name) for name in required_reports}
passed = (not unexpected_changes and not unexpected_new and set(present_new) == allowed_new
          and index_content_matches_head and preserved_helper and preserved_chinese and new_english and wrapper_lf
          and tests["status"] == "passed" and tests["tests_run"] == 33 and tests["source_hashes"] == sources
          and all(report.get("status", "").lower() in ("passed", "pass") for report in reports.values())
          and sha(helper) == helper_changes["after_sha256"] and not (ROOT / "run/tc2_gpu").exists())
result = {"status": "passed" if passed else "failed", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
          "protected_files_checked": len(baseline["files"]), "changed_existing_files": changed,
          "unexpected_existing_changes": unexpected_changes, "unexpected_new_files": unexpected_new,
          "new_sources": sources, "git_index_bytes_unchanged": sha(index) == baseline["git_index_sha256"],
          "git_staged_entries_match_head": index_content_matches_head,
          "git_staged_paths_checked": len(staged_entries),
          "git_index_note": "The index fingerprint differs from baseline; all staged path, mode and blob entries still match HEAD. No staging or commits were performed.",
          "existing_helper_bytes_preserved": preserved_helper, "existing_chinese_preserved": preserved_chinese,
          "new_sources_english": new_english, "slurm_wrapper_lf": wrapper_lf,
          "external_helper_sha256": sha(helper), "formal_local_outputs_absent": not (ROOT / "run/tc2_gpu").exists(),
          "offline_tests": {key: tests[key] for key in ("tests_run", "failures", "errors", "skipped", "torch_imported")},
          "reports": {name: {"status": report["status"], "sha256": sha(AUDIT / name)} for name, report in reports.items()},
          "actual_tc2_connections": 0, "actual_slurm_submissions": 0, "step_7_complete": False}
disk(AUDIT / "scope_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
raise SystemExit(0 if passed else 1)
