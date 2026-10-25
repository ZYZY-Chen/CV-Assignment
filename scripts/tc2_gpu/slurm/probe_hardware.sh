#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=ca6129_hardware_tc2_gpu
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo 'Submit with sbatch.' >&2; exit 2; }
[[ -n "${SLURM_SUBMIT_DIR:-}" ]] || { echo 'SLURM_SUBMIT_DIR is required.' >&2; exit 2; }
project_root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
deployment_info="$("${TC2_BOOTSTRAP_PYTHON:-python3}" -B - "$project_root" "setup" <<'TC2_GPU_DEPLOYMENT_PY'
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
import tc2_gpu_provenance as provenance
setup = provenance.read_current_config(root, "setup")
provenance.require_current_acceptance(root, sys.argv[2])
remote = setup["remote"]
required = ("home", "setup_root", "conda_environment_prefix", "anaconda_module")
if any(not isinstance(remote.get(key), str) or not remote[key] for key in required):
    raise RuntimeError("Complete the current TC2 GPU deployment configuration before using this wrapper")
home, configured, environment = (Path(remote[key]).resolve() for key in ("home", "setup_root", "conda_environment_prefix"))
if root != configured or configured == home or not configured.is_relative_to(home):
    raise RuntimeError("Submission root differs from the explicitly configured personal TC2 GPU root")
if not environment.is_relative_to(root / "envs"):
    raise RuntimeError("The configured environment must stay inside the project envs directory")
module = remote["anaconda_module"]
if any(character in module for character in ("\n", "\r", "\x00")):
    raise RuntimeError("Invalid configured Anaconda module")
print(environment)
print(module)
TC2_GPU_DEPLOYMENT_PY
)"
mapfile -t tc2_deployment <<< "$deployment_info"
[[ "${#tc2_deployment[@]}" == 2 ]] || { echo 'Incomplete current deployment values.' >&2; exit 2; }
tc2_environment_prefix="${tc2_deployment[0]}"
tc2_anaconda_module="${tc2_deployment[1]}"
cd -- "$project_root"
module load "$tc2_anaconda_module"
export PYTHONDONTWRITEBYTECODE=1
python -B - <<'PY'
import csv
import io
import json
import os
from pathlib import Path
import platform
import re
import sys
sys.path.insert(0, str(Path.cwd()))
from scripts.tc2_gpu.setup import check_setup as audit
audit.require_compute_job()
setup, _, _ = audit.read_contract('configs/tc2_gpu/setup.json')
if not setup.get('preparation', {}).get('approved'):
    raise RuntimeError('Supplementary preparation is not approved')
if os.environ.get('SLURM_JOB_PARTITION') != setup['remote']['partition']:
    raise RuntimeError('Unexpected SLURM partition')
out = Path('run/setup_tc2_gpu') / ('job_' + os.environ['SLURM_JOB_ID'] + '_hardware')
if out.resolve() != Path.cwd() / out:
    raise RuntimeError('Hardware output path traverses a symbolic link')
out.mkdir(parents=True, exist_ok=False)
smi = audit.command_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader,nounits'])
system = audit.command_output(['ldd', '--version'])
rows = list(csv.reader(io.StringIO(smi['stdout']))) if smi['returncode'] == 0 else []
gpus = [dict(model=row[0].strip(), driver=row[1].strip(), memory_mib=row[2].strip()) for row in rows if len(row) == 3]
libc = platform.libc_ver()
def version(text):
    return tuple(int(n) for n in re.findall(r'\d+', text))
checks = {
    'linux': platform.system() == 'Linux',
    'architecture': platform.machine() == setup['preparation']['architecture'],
    'glibc': libc[0] == 'glibc' and version(libc[1]) >= version(setup['preparation']['minimum_glibc']),
    'driver': bool(gpus) and all(version(g['driver']) >= version(setup['preparation']['minimum_driver']) for g in gpus),
    'nvidia_smi': smi['returncode'] == 0,
}
result = dict(checked_at_utc=audit.now_utc(), slurm_job_id=os.environ['SLURM_JOB_ID'],
              node=platform.node(), architecture=platform.machine(), libc=list(libc),
              visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'), gpus=gpus,
              nvidia_smi=smi, ldd=system, checks=checks, ready=all(checks.values()),
              protocol_sha256=audit.EXPECTED_PROTOCOL_SHA256,
              meaning='Conservative cu128 preparation gate; CUDA operations are not yet tested.')
audit.write_json(out / 'hardware.json', result)
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['ready'] else 2)
PY
