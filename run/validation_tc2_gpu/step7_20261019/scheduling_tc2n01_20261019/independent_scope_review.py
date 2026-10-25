"""Read-only implementation review for the approved TC2N01 scheduling supplement."""
from __future__ import annotations

import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
AUDIT = ROOT / "run/validation_tc2_gpu/step7_20261019/scheduling_tc2n01_20261019"


def long(path: Path) -> Path:
    return Path("\\\\?\\" + str(path.absolute()))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with long(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict:
    return json.loads(long(path).read_text(encoding="utf-8-sig"))


baseline = read_json(AUDIT / "baseline.json")
helper = Path(baseline["helper_path"])
before_helper = long(AUDIT / "helper.before.ps1").read_bytes()
after_helper = long(helper).read_bytes()
old_argument = b"$resourceArguments = '--gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00'"
new_argument = b"$resourceArguments = '--nodelist=TC2N01 --gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00'"
assert before_helper.count(old_argument) == 1
assert after_helper.count(new_argument) == 1
assert after_helper.count(b"--nodelist=TC2N01") == 1
assert after_helper.replace(new_argument, old_argument, 1) == before_helper
assert sha(AUDIT / "helper.before.ps1") == baseline["helper_sha256"]
helper_text = after_helper.decode("utf-8-sig")
fit_start = helper_text.index("        if ($fit) {")
cpu_start = helper_text.index("        } else {", fit_start)
assert new_argument.decode() in helper_text[fit_start:cpu_start]
assert "--nodelist" not in helper_text[cpu_start:helper_text.index("        $payload =", cpu_start)]

before_readme_bytes = long(AUDIT / "README.before.md").read_bytes()
after_readme_bytes = long(ROOT / "README.md").read_bytes()
assert sha(AUDIT / "README.before.md") == baseline["readme_sha256"]
old_sentence = (
    "Fitting stages request one GPU, two CPUs, 24 GiB and two hours; "
    "analysis stages request no GPU, two CPUs, 8 GiB and fifteen minutes."
).encode()
new_sentence = (
    "Fitting stages request TC2N01 with one GPU, two CPUs, 24 GiB and two hours; "
    "analysis stages use partition scheduling with no GPU, two CPUs, 8 GiB and fifteen minutes. "
    "Actual fitting hardware must match NVIDIA A40, driver 570.148.08 and CUDA build 12.8."
).encode()
assert before_readme_bytes.count(old_sentence) == 1
assert after_readme_bytes.count(new_sentence) == 1
assert after_readme_bytes.replace(new_sentence, old_sentence, 1) == before_readme_bytes
before_readme = before_readme_bytes.decode("utf-8-sig")
after_readme = after_readme_bytes.decode("utf-8-sig")
chinese = lambda text: "".join(char for char in text if "\u3400" <= char <= "\u9fff")
assert chinese(before_readme) == chinese(after_readme)
added = [line[1:] for line in difflib.unified_diff(before_readme.splitlines(), after_readme.splitlines()) if line.startswith("+") and not line.startswith("+++")]
assert len(added) == 1
assert not any(word in added[0].lower() for word in ("44047", "tc2n03", "failed", "failure", "supplement"))

actual_sources = {relative: sha(ROOT / relative) for relative in baseline["protected_sources"]}
assert actual_sources == baseline["protected_sources"]
status_before = read_json(AUDIT / "step7_status.before.json")
assert {relative: actual_sources[relative] for relative in baseline["experiment_sources"]} == status_before["experiment_sources"]
design = read_json(ROOT / "configs/experiments_tc2_gpu.json")
accepted = {**design["scientific_source_hashes"], **design["pilot_source_hashes"]}
assert len(accepted) == 37
assert {relative: actual_sources[relative] for relative in accepted} == accepted

preserved = {}
for path_key, files_key in (("failed_output_path", "failed_output_files"), ("failed_archive_path", "failed_archive_files")):
    original_root = Path(baseline[path_key])
    expected = baseline[files_key]
    actual = {relative: sha(original_root / relative) for relative in expected}
    assert actual == expected
    preserved[path_key] = {"path": str(original_root), "file_count": len(actual), "sha256": actual}

report = {
    "status": "passed",
    "reviewer": "independent_scope_review",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "approved_scope": baseline["approved_scope"],
    "helper_sha256": sha(helper),
    "helper_previous_sha256": baseline["helper_sha256"],
    "helper_byte_reversal": "Exact original bytes restored by removing the single fit-branch --nodelist=TC2N01 addition.",
    "cpu_and_legacy_branches": "Byte-for-byte unchanged.",
    "readme_sha256": sha(ROOT / "README.md"),
    "readme_byte_reversal": "Exact original bytes restored by replacing the one final-usage sentence.",
    "readme_existing_chinese": "unchanged",
    "readme_failure_history_added": False,
    "published_experiment_sources_unchanged": 7,
    "accepted_scientific_and_pilot_sources_unchanged": 37,
    "protected_source_sha256": actual_sources,
    "preserved_original_failure_material": preserved,
    "scope_caveat": "This checks the approved implementation bytes and preserved evidence. It makes no remote hardware, scheduling, or experiment-acceptance claim.",
    "actual_agent_network_connections": 0,
    "actual_agent_jobs_submitted": 0,
    "actual_agent_model_calls": 0,
}
destination = AUDIT / "independent_scope_review.json"
with long(destination).open("x", encoding="utf-8", newline="\n") as handle:
    json.dump(report, handle, indent=2, ensure_ascii=False)
    handle.write("\n")
print(json.dumps({"status": "passed", "report": str(destination), "report_sha256": sha(destination), "sources": len(actual_sources), "preserved_original_files": sum(item["file_count"] for item in preserved.values())}, indent=2))
