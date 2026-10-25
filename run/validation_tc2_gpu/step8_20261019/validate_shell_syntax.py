"""Syntax-check rendered scripts without executing them or connecting anywhere."""
from pathlib import Path
import json
import subprocess

audit = Path(__file__).resolve().parent
paths = [audit.parents[2] / "scripts/slurm/analysis_tc2_gpu.sh"]
for name in ("local_transport_validation.json", "pilot_transport_validation.json", "experiments_transport_validation.json", "loco_transport_validation.json", "analysis_transport_validation.json"):
    report = json.loads((audit / name).read_text(encoding="utf-8-sig"))
    paths.extend(Path(report["validation_root"]).rglob("command_*.sh"))
assert len(paths) > 80, len(paths)
for path in paths:
    subprocess.run([r"C:\Program Files\Git\bin\bash.exe", "-n", str(path).replace("\\", "/")], check=True)
report = {"status":"passed","scripts_checked":len(paths),"syntax_only":True,
          "actual_script_executions":0,"actual_tc2_connections":0,"actual_slurm_submissions":0}
(audit / "shell_syntax_validation.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report))
