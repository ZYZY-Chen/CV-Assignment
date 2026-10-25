#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --job-name=ca6129_prepare_tc2_gpu
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo 'Submit with sbatch.' >&2; exit 2; }
[[ $# == 1 && ( "$1" == environment || "$1" == inputs ) ]] || { echo 'Use environment or inputs.' >&2; exit 2; }
mode="$1"
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
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-2}" MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-2}"
export CONDA_PKGS_DIRS="$project_root/_package_cache/conda"
export CONDA_ENVS_PATH="$project_root/envs"
export PIP_CACHE_DIR="$project_root/_package_cache/pip"
export TMPDIR="$project_root/tmp"
for directory in "$CONDA_PKGS_DIRS" "$CONDA_ENVS_PATH" "$PIP_CACHE_DIR" "$TMPDIR" "$project_root/run/setup_tc2_gpu" "$project_root/configs"; do
    [[ ! -L "$directory" && "$(readlink -m -- "$directory")" == "$directory" ]] || { echo 'Unsafe preparation directory.' >&2; exit 2; }
done
[[ ! -L "$project_root/configs/tc2_gpu/setup.json" ]] || exit 2
mkdir -p -- "$CONDA_PKGS_DIRS" "$CONDA_ENVS_PATH" "$PIP_CACHE_DIR" "$TMPDIR"
if [[ "$mode" == environment ]]; then
    bash scripts/tc2_gpu/setup/prepare_environment.sh
else
    environment_prefix="$tc2_environment_prefix"
    [[ -x "$environment_prefix/bin/python" && ! -L "$environment_prefix" ]] || { echo 'Dedicated environment not ready.' >&2; exit 2; }
    # Shared activation hooks may legitimately read unset optional Qt variables.
    # Keep errexit/pipefail, and restore nounset before project code runs.
    set +u
    conda_hook="$(conda shell.bash hook)"
    eval "$conda_hook"
    conda activate "$environment_prefix"
    set -u
    unset conda_hook
    python -B scripts/tc2_gpu/setup/prepare_inputs.py --accept-license
fi
