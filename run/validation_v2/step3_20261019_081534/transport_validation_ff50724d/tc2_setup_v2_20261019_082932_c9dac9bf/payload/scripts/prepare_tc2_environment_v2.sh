#!/bin/bash
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo 'Environment preparation requires a SLURM job.' >&2; exit 2; }
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
[[ "$HOME" == /home/mcaai/huajie001 && "$project_root" == "$HOME/ca6129_v2_setup" ]] || exit 2
cd -- "$project_root"
out="$project_root/run/setup_v2/job_${SLURM_JOB_ID}_prepare_environment"
[[ ! -L "$out" && "$(readlink -m -- "$out")" == "$out" ]] || { echo 'Unsafe output directory.' >&2; exit 2; }
mkdir -- "$out"
trap 'result=$?; if [[ $result != 0 ]]; then printf "Preparation stopped with exit code %s. Existing files were retained.\n" "$result" > "$out/FAILED.txt"; fi' EXIT
environment_prefix="$project_root/envs/ca6129-ad-v2"
[[ ! -e "$environment_prefix" && ! -L "$environment_prefix" ]] || { echo 'Environment target already exists; inspect before any repair.' >&2; exit 2; }

# Metadata and package operations only. No Torch import or GPU workload here.
python -B - "$out" <<'PY'
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / 'scripts'))
import check_setup_v2 as audit
audit.require_compute_job()
setup, _, _ = audit.read_contract('configs/tc2_setup.json')
if not setup['preparation']['approved'] or not setup['scope']['permit_package_install_or_upgrade']:
    raise RuntimeError('Package preparation not approved')
root = Path.cwd().resolve()
if root != Path(setup['remote']['setup_root']).resolve() or setup['preparation']['environment_prefix'] != str(root / 'envs/ca6129-ad-v2'):
    raise RuntimeError('Unexpected preparation path')
if os.environ.get('SLURM_JOB_PARTITION') != setup['remote']['partition']:
    raise RuntimeError('Unexpected partition')
job_id = (root / 'run/setup_v2/last_probe_job.txt').read_text().strip()
if not job_id.isdecimal():
    raise RuntimeError('Invalid hardware job ID')
hardware = json.loads((root / f'run/setup_v2/job_{job_id}_hardware/hardware.json').read_text())
if not hardware['ready'] or hardware['protocol_sha256'] != audit.EXPECTED_PROTOCOL_SHA256:
    raise RuntimeError('Hardware compatibility gate did not pass')
if audit.sha256(root / 'requirements-lock.txt') != setup['preparation']['requirements_lock_sha256']:
    raise RuntimeError('Existing requirements lock fingerprint changed')
remaining = [line.strip() for line in (root / 'requirements-lock.txt').read_text().splitlines()
             if line.strip() and not line.lstrip().startswith(('#', '--', 'torch==', 'torchvision=='))]
out = Path(sys.argv[1])
(out / 'remaining-requirements.txt').write_text('\n'.join(remaining) + '\n')
audit.write_json(out / 'preflight.json', dict(ready=True, hardware_job_id=job_id,
    environment_prefix=setup['preparation']['environment_prefix'], protocol_sha256=audit.EXPECTED_PROTOCOL_SHA256))
PY

# Limit caches and temporary files to the approved staging directory.
export CONDA_PKGS_DIRS="$project_root/_package_cache/conda" CONDA_ENVS_PATH="$project_root/envs"
export PIP_CACHE_DIR="$project_root/_package_cache/pip" TMPDIR="$project_root/tmp"
export PIP_CONFIG_FILE=/dev/null PIP_NO_INPUT=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
unset PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_FIND_LINKS PIP_TRUSTED_HOST
mkdir -p -- "$CONDA_PKGS_DIRS" "$CONDA_ENVS_PATH" "$PIP_CACHE_DIR" "$TMPDIR"
conda create --dry-run --json --prefix "$environment_prefix" --override-channels -c conda-forge python=3.10 'pip>=24' > "$out/conda-plan.json"
conda create --yes --prefix "$environment_prefix" --override-channels -c conda-forge python=3.10 'pip>=24'
py="$environment_prefix/bin/python"
"$py" -B -m pip install --dry-run --report "$out/torch-plan.json" --index-url https://download.pytorch.org/whl/cu128 'torch==2.11.0+cu128' 'torchvision==0.26.0+cu128'
"$py" -B -m pip install --index-url https://download.pytorch.org/whl/cu128 'torch==2.11.0+cu128' 'torchvision==0.26.0+cu128'
"$py" -B -m pip install --dry-run --report "$out/dependencies-plan.json" --index-url https://pypi.org/simple -r "$out/remaining-requirements.txt"
"$py" -B -m pip install --index-url https://pypi.org/simple -r "$out/remaining-requirements.txt"
"$py" -B -m pip check
"$py" -B - "$out" <<'PY'
from importlib import metadata
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / 'scripts'))
import check_setup_v2 as audit
setup, _, _ = audit.read_contract('configs/tc2_setup.json')
if sys.version_info[:2] != (3, 10) or Path(sys.prefix).resolve() != Path(setup['preparation']['environment_prefix']).resolve():
    raise RuntimeError('Unexpected dedicated Python environment')
targets = {}
for line in Path('requirements-lock.txt').read_text().splitlines():
    if line.strip() and not line.lstrip().startswith(('#', '--')):
        name, value = line.strip().split('==')
        targets[name] = value
targets.update(torch=setup['preparation']['torch'], torchvision=setup['preparation']['torchvision'])
versions = {name: metadata.version(name) for name in targets}
if versions != targets:
    raise RuntimeError('Installed top-level versions differ from approved targets: ' + str(versions))
setup['remote']['conda_environment_prefix'] = str(Path(sys.prefix).resolve())
setup['remote']['setup_root_created_or_inspected'] = True
audit.write_json(Path('configs/tc2_setup.json'), setup)
audit.write_json(Path(sys.argv[1]) / 'preparation_status.json', dict(ready=True,
    environment_prefix=sys.prefix, packages=versions, gpu_tested=False,
    meaning='Package setup completed; GPU environment acceptance remains required.'))
PY
