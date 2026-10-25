"""Offline checks of rendered tc2_gpu publication and old/new readiness lookup."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASH = r"C:\Program Files\Git\bin\bash.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bash(script, cwd=None):
    return subprocess.run([BASH, str(script)], cwd=cwd, capture_output=True, text=True)


transport = json.loads((HERE / "local_transport_validation.json").read_text(encoding="utf-8-sig"))
commands = list(Path(transport["validation_root"]).rglob("command_*.sh"))
assert len(commands) == 15
wrappers = list((ROOT / "scripts/slurm").glob("*tc2_gpu*.sh"))
wrappers += [ROOT / "scripts/prepare_tc2_gpu_environment.sh"]
for command in commands + wrappers:
    checked = subprocess.run([BASH, "-n", str(command)], capture_output=True, text=True)
    assert checked.returncode == 0, (str(command), checked.stderr)
wrapper = (ROOT / "scripts/slurm/check_tc2_gpu_metrics.sh").read_text()
assert "#SBATCH --cpus-per-task=2" in wrapper and "#SBATCH --mem=4G" in wrapper
assert "#SBATCH --time=00:15:00" in wrapper and "--gres" not in wrapper and "--gpus" not in wrapper
command, = [p for p in commands if "Five verified metric test files staged" in p.read_text()]
rendered = command.read_text()
accepted_function = re.search(r"(?ms)^metric_source_is_accepted\(\) \{.*?^\}", rendered).group()
record_function = re.search(r"(?ms)^setup_record\(\) \{.*?^\}", rendered).group()
start = re.search(r'(?m)^archive="\$root/_downloads/metrics-files-[^\n]+$', rendered).start()
end = rendered.index("job_id=$(sbatch", start)
publication = rendered[start:end]
submission = rendered[end:rendered.index("\n", end)]
assert "run/validation_tc2_gpu" in submission and "check_tc2_gpu_metrics.sh" in submission
assert "--gres" not in submission and "--gpus" not in submission
bundle_name = re.search(r'metrics-files-[^/"\n]+\.tar', publication).group()
payload = command.parent / "metrics_payload"
rows = [line.split() for line in (payload / "metrics.sha256").read_text().splitlines()]
assert {p for _, p in rows} == {
    "src/metric_core.py", "src/evaluate.py", "src/data.py",
    "tests/test_metrics_tc2_gpu.py", "scripts/slurm/check_tc2_gpu_metrics.sh",
}
result_root = HERE / ("delivery_" + uuid.uuid4().hex[:8])
result_root.mkdir()
cases = ["absent", "identical", "accepted_predecessors", "unknown_shared", "unknown_entry", "bad_bundle"]
for case in cases:
    target = result_root / case
    for directory in ("_downloads", "tmp", "run/validation_tc2_gpu", "scripts/slurm", "src", "tests"):
        (target / directory).mkdir(parents=True, exist_ok=True)
    (target / "_downloads" / bundle_name).write_bytes((command.parent / "metrics-files.tar").read_bytes())
    existing = {}
    if case in ("identical", "accepted_predecessors", "unknown_shared", "unknown_entry"):
        for _, relative in rows:
            data = (payload / relative).read_bytes()
            if case == "accepted_predecessors" and relative in ("src/metric_core.py", "src/evaluate.py"):
                data = (HERE / "before" / relative).read_bytes()
            if case == "unknown_shared" and relative == "src/metric_core.py":
                data = b"Unknown shared metric source. Preserve it.\n"
            if case == "unknown_entry" and relative == "scripts/slurm/check_tc2_gpu_metrics.sh":
                data = b"Unknown entry point. Preserve it.\n"
            file = target / relative
            file.write_bytes(data)
            existing[relative] = (data, file.stat().st_mtime_ns)
    if case == "bad_bundle":
        with (target / "_downloads" / bundle_name).open("ab") as stream:
            stream.write(b"tampered")
    script = target / "publication.sh"
    script.write_text('set -euo pipefail\nroot="$(pwd -P)"\n' + accepted_function + "\n" + publication, encoding="utf-8", newline="\n")
    completed = bash(script, target)
    records = list((target / "run/validation_tc2_gpu").iterdir())
    success = case in ("absent", "identical", "accepted_predecessors")
    assert (completed.returncode == 0) == success, (case, completed.stdout, completed.stderr)
    if success:
        record, = records
        for expected, relative in rows:
            assert sha(target / relative) == expected
        if case == "accepted_predecessors":
            for relative in ("src/metric_core.py", "src/evaluate.py"):
                assert (record / "source_originals" / relative).read_bytes() == existing[relative][0]
    else:
        assert not records, case
    for relative, (data, mtime) in existing.items():
        if success and case == "accepted_predecessors" and relative in ("src/metric_core.py", "src/evaluate.py"):
            continue
        assert (target / relative).read_bytes() == data
        assert (target / relative).stat().st_mtime_ns == mtime

# Exercise the actual Bash lookup for legacy-only and new-over-legacy readiness.
lookup_root = result_root / "readiness"
for directory in ("run/setup_v2", "run/setup_tc2_gpu"):
    (lookup_root / directory).mkdir(parents=True, exist_ok=True)
legacy = lookup_root / "run/setup_v2/last_check_all_job.txt"
current = lookup_root / "run/setup_tc2_gpu/last_check_all_job.txt"
legacy.write_text("43950\n")
lookup_script = lookup_root / "lookup.sh"
lookup_script.write_text('set -euo pipefail\nroot="$(pwd -P)"\n' + record_function + '\ncat "$(setup_record last_check_all_job.txt)"\n', encoding="utf-8", newline="\n")
assert bash(lookup_script, lookup_root).stdout.strip() == "43950"
current.write_text("new-record-is-not-valid\n")
assert bash(lookup_script, lookup_root).stdout.strip() == "new-record-is-not-valid"
assert legacy.read_text() == "43950\n"
result = {
    "status": "passed", "rendered_commands_parsed": 15, "shell_files_parsed": len(wrappers),
    "publication_cases": cases, "accepted_source_backups_verified": True,
    "unknown_source_conflicts_preserved": True, "five_approved_payload_files": True,
    "legacy_readiness_fallback_verified": True, "new_readiness_precedence_verified": True,
    "metric_job_gpus_requested": 0, "result_root": str(result_root),
    "actual_ssh_calls": 0, "actual_slurm_submissions": 0,
}
(HERE / "delivery_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
