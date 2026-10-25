#!/bin/bash
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo 'Environment preparation requires a SLURM job.' >&2; exit 2; }
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
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
out="$project_root/run/setup_tc2_gpu/job_${SLURM_JOB_ID}_prepare_environment"
[[ ! -L "$out" && "$(readlink -m -- "$out")" == "$out" ]] || { echo 'Unsafe output directory.' >&2; exit 2; }
mkdir -- "$out"
trap 'result=$?; if [[ $result != 0 ]]; then printf "Preparation stopped with exit code %s. Existing files were retained.\n" "$result" > "$out/FAILED.txt"; fi' EXIT
environment_prefix="$tc2_environment_prefix"
[[ ! -e "$environment_prefix" && ! -L "$environment_prefix" ]] || { echo 'Environment target already exists; inspect before any repair.' >&2; exit 2; }

# Metadata and package operations only. No Torch import or GPU workload here.
python -B - "$out" <<'PY'
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
from scripts.tc2_gpu.setup import check_setup as audit
audit.require_compute_job()
setup, _, _ = audit.read_contract('configs/tc2_gpu/setup.json')
if not setup['preparation']['approved'] or not setup['scope']['permit_package_install_or_upgrade']:
    raise RuntimeError('Package preparation not approved')
root = Path.cwd().resolve()
if root != Path(setup['remote']['setup_root']).resolve() or setup['preparation']['environment_prefix'] != str(Path(setup['remote']['conda_environment_prefix']).resolve()):
    raise RuntimeError('Unexpected preparation path')
if os.environ.get('SLURM_JOB_PARTITION') != setup['remote']['partition']:
    raise RuntimeError('Unexpected partition')
job_id = audit.setup_record('last_probe_job.txt').read_text().strip()
if not job_id.isdecimal():
    raise RuntimeError('Invalid hardware job ID')
hardware = json.loads(audit.setup_record(f'job_{job_id}_hardware/hardware.json').read_text())
if not hardware['ready'] or hardware['protocol_sha256'] != audit.EXPECTED_PROTOCOL_SHA256:
    raise RuntimeError('Hardware compatibility gate did not pass')
if audit.sha256(root / 'requirements-tc2_gpu-bootstrap.txt') != setup['preparation']['requirements_lock_sha256']:
    raise RuntimeError('Existing requirements lock fingerprint changed')
remaining = [line.strip() for line in (root / 'requirements-tc2_gpu-bootstrap.txt').read_text().splitlines()
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
sys.path.insert(0, str(Path.cwd()))
from scripts.tc2_gpu.setup import check_setup as audit
setup, _, _ = audit.read_contract('configs/tc2_gpu/setup.json')
if sys.version_info[:2] != (3, 10) or Path(sys.prefix).resolve() != Path(setup['preparation']['environment_prefix']).resolve():
    raise RuntimeError('Unexpected dedicated Python environment')
targets = {}
for line in Path('requirements-tc2_gpu-bootstrap.txt').read_text().splitlines():
    if line.strip() and not line.lstrip().startswith(('#', '--')):
        name, value = line.strip().split('==')
        targets[name] = value
targets.update(torch=setup['preparation']['torch'], torchvision=setup['preparation']['torchvision'])
versions = {name: metadata.version(name) for name in targets}
if versions != targets:
    raise RuntimeError('Installed top-level versions differ from approved targets: ' + str(versions))
setup['remote']['conda_environment_prefix'] = str(Path(sys.prefix).resolve())
setup['remote']['setup_root_created_or_inspected'] = True
audit.write_json(Path('configs/tc2_gpu/setup.json'), setup)
audit.write_json(Path(sys.argv[1]) / 'preparation_status.json', dict(ready=True,
    environment_prefix=sys.prefix, packages=versions, gpu_tested=False,
    meaning='Package setup completed; GPU environment acceptance remains required.'))
PY
