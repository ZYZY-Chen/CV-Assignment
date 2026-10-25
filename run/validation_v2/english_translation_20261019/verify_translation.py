"""Verify the user-authorized documentation translation without running experiments."""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

AUDIT = Path(__file__).resolve().parent
CODE = AUDIT.parents[2]
REPO = CODE.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


baseline = read_json(AUDIT / "baseline.json")
changed = []
for record in baseline["files"]:
    path = REPO / record["path"]
    assert path.is_file(), record["path"]
    if digest(path) != record["sha256"]:
        changed.append(record["path"])
assert set(changed) == set(baseline["allowed_existing_changes"])
before_paths = {record["path"] for record in baseline["files"]}
for path in REPO.rglob("*"):
    if not path.is_file() or any(part in path.parts for part in (".git", ".idea", "__pycache__")):
        continue
    relative = path.relative_to(REPO).as_posix()
    if not path.is_relative_to(AUDIT):
        assert relative in before_paths, relative
for record in baseline["external_protected_files"]:
    assert digest(Path(record["path"])) == record["sha256"], record["path"]

han = re.compile(r"[\u3400-\u9fff]")
head_readme = (AUDIT / "readme_head.txt").read_text(encoding="utf-8")
before_readme = (AUDIT / "before_4.md").read_text(encoding="utf-8-sig")
current_readme = (CODE / "README.md").read_text(encoding="utf-8")
original_chinese = Counter(line for line in head_readme.splitlines() if han.search(line))
retained_chinese = Counter(line for line in before_readme.splitlines() if han.search(line)) & original_chinese
assert Counter(line for line in current_readme.splitlines() if han.search(line)) == retained_chinese

documents = [
    (1, "docs/EXPERIMENT_PROTOCOL_V2.md"),
    (2, "docs/TC2_SETUP_V2.md"),
    (3, "docs/METRICS_V2.md"),
    (4, "README.md"),
]
document_checks = []
for index, relative in documents:
    old = (AUDIT / f"before_{index}.md").read_text(encoding="utf-8-sig")
    path = CODE / relative
    new = path.read_text(encoding="utf-8")
    assert len(old.splitlines()) == len(new.splitlines()), relative
    if index != 4:
        assert not han.search(new), relative
    for pattern in (
        r"\b[0-9A-Fa-f]{40,64}\b",
        r"https?://[^\s)\]>`]+",
        r"\b439\d{2}\b",
        r"\d+(?:\.\d+)+(?:[eE][+-]?\d+)?(?:\+cu\d+)?",
    ):
        assert Counter(re.findall(pattern, old)) == Counter(re.findall(pattern, new)), (relative, pattern)
    # Preserve all original inline tokens except translated placeholders and notation.
    def literals(text):
        return Counter(value for value in re.findall(r"(?<!`)`([^`\n]+)`(?!`)", text) if not re.search(r"[\u3400-\u9fff\u00d7\u3001\u2192]", value))
    assert not (literals(old) - literals(new)), relative
    before_fences = re.findall(r"^```[^\n]*\n(.*?)^```", old, re.M | re.S)
    after_fences = re.findall(r"^```[^\n]*\n(.*?)^```", new, re.M | re.S)
    assert len(before_fences) == len(after_fences), relative
    for before, after in zip(before_fences, after_fences):
        if before != after:
            assert relative == "docs/TC2_SETUP_V2.md"
            assert before.startswith("python -B scripts/check_setup_v2.py --mode inputs --datasets-root <")
            assert after == "python -B scripts/check_setup_v2.py --mode inputs --datasets-root <verified-data-root> --output-dir run/setup_v2/<new-check-id>\n"
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", new):
        if not target.startswith(("http://", "https://")):
            assert (path.parent / target).is_file(), (relative, target)
    document_checks.append({"path": relative, "sha256": digest(path), "lines": len(new.splitlines()), "hashes_urls_jobs_versions_and_links_verified": True})

source_paths = [
    "src/metric_core.py", "src/evaluate.py", "tests/test_metrics_v2.py",
    "scripts/check_setup_v2.py", "scripts/prepare_tc2_inputs_v2.py",
    "scripts/prepare_tc2_environment_v2.sh", "scripts/slurm/check_setup_v2.sh",
    "scripts/slurm/check_metrics_v2.sh", "scripts/slurm/probe_hardware_v2.sh",
    "scripts/slurm/prepare_tc2_v2.sh",
]
for relative in source_paths:
    assert not han.search((CODE / relative).read_text(encoding="utf-8-sig")), relative
step3_path = CODE / "run/validation_v2/step3_20261019_081534/setup_status.json"
step3 = read_json(step3_path)
before_step3 = read_json(AUDIT / "before_5.json")
assert step3["step_3_complete"] is True
assert not han.search(step3["required_user_action"]["next_stage"])
for key in ("local_core", "remote_full_acceptance", "scope_verification", "completion_summary"):
    assert step3[key] == before_step3[key], key
for fingerprint in step3["implementation_fingerprints"]:
    path = Path(fingerprint["path"])
    if not path.is_absolute():
        path = CODE / path
    assert digest(path) == fingerprint["sha256"], fingerprint["path"]
assert read_json(CODE / "run/setup_v2/step2_20261019_060542/setup_status.json")["step_2_complete"] is True
assert not (CODE / "run/v2").exists()

result = {
    "status": "passed",
    "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "English translations of step-1-3 authored documentation and one status prompt; raw logs excluded by the user.",
    "modified_existing_files": sorted(changed),
    "baseline_files_checked": len(baseline["files"]),
    "protected_external_files_checked": len(baseline["external_protected_files"]),
    "pre_existing_chinese_readme_lines_preserved": sum(retained_chinese.values()),
    "remaining_chinese_in_active_step_1_3_prose": 0,
    "source_files_already_in_english": source_paths,
    "all_executable_source_and_raw_logs_unchanged": True,
    "protocol_manifests_dependency_locks_and_v1_files_unchanged": True,
    "documents": document_checks,
    "historical_acceptance_results_preserved": True,
    "historical_fingerprint_policy": "Historical baselines retain acceptance-time documentation hashes. This audit records the separately authorized translations and current document hashes.",
    "remote_commands_or_experiments_executed": False,
    "new_files_scope": "Translation audit directory only; backups are intentionally preserved in their original language.",
}
(AUDIT / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: result[key] for key in ("status", "baseline_files_checked", "protected_external_files_checked", "pre_existing_chinese_readme_lines_preserved", "remaining_chinese_in_active_step_1_3_prose", "modified_existing_files")}, ensure_ascii=False))
