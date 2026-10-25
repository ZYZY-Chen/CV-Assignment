#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=ca6129_hardware_v2
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo 'Submit with sbatch.' >&2; exit 2; }
[[ -n "${SLURM_SUBMIT_DIR:-}" ]] || { echo 'SLURM_SUBMIT_DIR is required.' >&2; exit 2; }
project_root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
[[ "$HOME" == /home/mcaai/huajie001 && "$project_root" == "$HOME/ca6129_v2_setup" ]] || exit 2
cd -- "$project_root"
module load anaconda/25.5.1
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
sys.path.insert(0, str(Path.cwd() / 'scripts'))
import check_setup_v2 as audit
audit.require_compute_job()
setup, _, _ = audit.read_contract('configs/tc2_setup.json')
if not setup.get('preparation', {}).get('approved'):
    raise RuntimeError('Supplementary preparation is not approved')
if os.environ.get('SLURM_JOB_PARTITION') != setup['remote']['partition']:
    raise RuntimeError('Unexpected SLURM partition')
out = Path('run/setup_v2') / ('job_' + os.environ['SLURM_JOB_ID'] + '_hardware')
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
