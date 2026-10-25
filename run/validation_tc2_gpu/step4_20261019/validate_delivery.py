"""Run rendered algorithm preflight/publication against local fixtures only."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASH = r"C:\Program Files\Git\bin\bash.exe"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


transport = json.loads((HERE / "local_transport_validation.json").read_text(encoding="utf-8-sig"))
commands = list(Path(transport["validation_root"]).rglob("command_*.sh"))
assert len(commands) == 17
for path in commands + [ROOT / "scripts/slurm/check_tc2_gpu_algorithms.sh"]:
    checked = subprocess.run([BASH, "-n", str(path)], capture_output=True, text=True)
    assert checked.returncode == 0, (str(path), checked.stderr)
command, = [p for p in commands if "Eleven verified algorithm files staged" in p.read_text()]
rendered = command.read_text()
lookup = re.search(r"(?ms)^setup_record\(\) \{.*?^\}", rendered).group()
start = re.search(r'(?m)^cd -- "\$root"\nall_job=', rendered).start()
end = rendered.index("echo 'Eleven verified algorithm files staged", start)
deployment = rendered[start:end]
submission = rendered[end:rendered.index("job_id=${job_id%%;*}", end)]
assert "--partition=MGPU-TC2" in submission and "--qos=normal" in submission
assert "check_tc2_gpu_algorithms.sh" in submission
wrapper = (ROOT / "scripts/slurm/check_tc2_gpu_algorithms.sh").read_text()
for flag in ("--gres=gpu:1", "--cpus-per-task=2", "--mem=8G", "--time=00:15:00"):
    assert flag in wrapper
payload = command.parent / "algorithms_payload"
rows = [line.split(maxsplit=1) for line in (payload / "algorithms.sha256").read_text().splitlines()]
names = {name for _, name in rows}
assert len(rows) == len(names) == 11
assert names == {"src/padim_adapter.py", "src/patchcore_adapter.py", "src/sampling.py", "src/scoring.py",
                 "src/anomaly_postprocess.py", "tests/test_algorithms_tc2_gpu.py", "scripts/slurm/check_tc2_gpu_algorithms.sh",
                 "src/metric_core.py", "src/evaluate.py", "src/data.py", "configs/tc2_gpu.json"}
for expected, relative in rows:
    assert sha(ROOT / relative) == expected == sha(payload / relative)
bundle_name = re.search(r'algorithm-files-[^/"\n]+\.tar', deployment).group()
protocol = json.loads((ROOT / "configs/protocol_v2.json").read_text())
frozen = ["configs/protocol_v2.json", "environment-tc2.yml", "requirements-tc2-lock.txt"]
frozen += [item["path"] for item in protocol["data"]["frozen_manifests"]]
dependencies = ["src/metric_core.py", "src/evaluate.py", "src/data.py"]
result_root = HERE / ("delivery_" + uuid.uuid4().hex[:8]); result_root.mkdir()
cases = ["absent_algorithms", "identical", "unknown_existing", "missing_metric", "failed_metric", "changed_dependency_hash", "bad_bundle"]
for case in cases:
    target = result_root / case
    for directory in ("_downloads", "tmp", "src", "configs", "scripts/slurm", "tests", "envs/ca6129-ad-v2/bin",
                      "run/setup_v2/job_43950_all", "run/validation_tc2_gpu/step3_job_12345"):
        (target / directory).mkdir(parents=True, exist_ok=True)
    executable = target / "envs/ca6129-ad-v2/bin/python"
    executable.write_text("#!/bin/sh\nexit 0\n", newline="\n")
    for relative in frozen:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    (target / "run/setup_v2/last_check_all_job.txt").write_text("43950\n")
    (target / "run/setup_v2/job_43950_all/setup_status.json").write_text('{"step_2_complete": true}\n')
    metric_pointer = target / "run/validation_tc2_gpu/last_check_metrics_job.txt"
    if case != "missing_metric":
        metric_pointer.write_text("12345\n")
    metric = {"mode": "full", "status": "passed", "step_3_complete": case != "failed_metric",
              "source_hashes": {name: sha(ROOT / name).upper() for name in dependencies}}
    if case == "changed_dependency_hash":
        metric["source_hashes"]["src/metric_core.py"] = "0" * 64
    (target / "run/validation_tc2_gpu/step3_job_12345/setup_status.json").write_text(json.dumps(metric, indent=2) + "\n")
    original = {}
    for _, relative in rows:
        if relative in dependencies or case in ("identical", "unknown_existing"):
            destination = target / relative
            destination.write_bytes((payload / relative).read_bytes())
            if case == "unknown_existing" and relative == "src/scoring.py":
                destination.write_bytes(b"Unknown existing scoring source. Preserve it.\n")
            original[relative] = (destination.read_bytes(), destination.stat().st_mtime_ns)
    bundle = target / "_downloads" / bundle_name
    bundle.write_bytes((command.parent / "algorithm-files.tar").read_bytes())
    if case == "bad_bundle":
        with bundle.open("ab") as stream:
            stream.write(b"tampered")
    script = target / "deployment.sh"
    script.write_text('set -euo pipefail\nroot="$(pwd -P)"\nchmod +x "$root/envs/ca6129-ad-v2/bin/python"\n' + lookup + "\n" + deployment,
                      encoding="utf-8", newline="\n")
    completed = subprocess.run([BASH, str(script)], cwd=target, capture_output=True, text=True)
    success = case in ("absent_algorithms", "identical")
    assert (completed.returncode == 0) == success, (case, completed.stdout, completed.stderr)
    records = list((target / "run/validation_tc2_gpu").glob("algorithms_stage_*"))
    if success:
        record, = records
        assert (record / "metric_regression_job.txt").read_text().strip() == "12345"
        assert (record / "algorithms.sha256").read_bytes() == (payload / "algorithms.sha256").read_bytes()
        for expected, relative in rows:
            assert sha(target / relative) == expected
    else:
        assert not records, case
        for relative in names - original.keys():
            assert not (target / relative).exists(), (case, relative)
    for relative, (data, mtime) in original.items():
        assert (target / relative).read_bytes() == data, (case, relative)
        assert (target / relative).stat().st_mtime_ns == mtime, (case, relative)

result = {"status": "passed", "rendered_shell_commands_parsed": 17, "algorithm_wrapper_parsed": True,
          "payload_files": 11, "all_payload_hashes_match_current_sources": True, "publication_cases": cases,
          "metric_regression_gate_verified": True, "readonly_dependency_hash_gate_verified": True,
          "unknown_sources_and_existing_bytes_preserved": True, "resources": {"gpus": 1, "cpus": 2, "memory_gib": 8, "time_limit": "00:15:00"},
          "result_root": str(result_root), "actual_ssh_calls": 0, "actual_slurm_submissions": 0}
(HERE / "delivery_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
