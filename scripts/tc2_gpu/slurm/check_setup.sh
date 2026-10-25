#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=ca6129_setup_tc2_gpu
# Partition, QoS and absolute log paths must be supplied after account verification.
set -euo pipefail

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    echo "Submit this script with sbatch; do not run it on the head node." >&2
    exit 2
fi
if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: check_tc2_gpu_setup.sh /verified/conda/environment [environment|all]" >&2
    exit 2
fi

environment_prefix="$1"
check_mode="${2:-environment}"
if [[ "$check_mode" != "environment" && "$check_mode" != "all" ]]; then
    echo "GPU job mode must be environment or all." >&2
    exit 2
fi
if [[ "$environment_prefix" != /* || ! -x "$environment_prefix/bin/python" ]]; then
    echo "Supply an existing absolute Conda environment prefix with a Python executable." >&2
    exit 2
fi

if [[ -z "${SLURM_SUBMIT_DIR:-}" ]]; then
    echo "SLURM_SUBMIT_DIR is required; submit from the verified staging directory." >&2
    exit 2
fi
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
if [[ "$environment_prefix" != "$tc2_environment_prefix" ]]; then
    echo "The supplied environment differs from the current deployment configuration." >&2
    exit 2
fi
cd -- "$project_root"
if [[ ! -f configs/tc2_gpu/protocol.json || ! -f configs/tc2_gpu/setup.json ]]; then
    echo "The staging project must contain the frozen protocol and verified setup configuration." >&2
    exit 2
fi

if [[ -n "${TC2_ANACONDA_MODULE:-}" && "$TC2_ANACONDA_MODULE" != "$tc2_anaconda_module" ]]; then
    echo "Module override differs from the current deployment configuration." >&2
    exit 2
fi
module load "$tc2_anaconda_module"
if ! command -v conda >/dev/null 2>&1; then
    echo "Load the verified Anaconda module, or set TC2_ANACONDA_MODULE to its verified name." >&2
    exit 2
fi
# Shared activation hooks may read unset optional Qt variables.
# Retain errexit/pipefail throughout activation, then restore nounset.
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$environment_prefix"
set -u
unset conda_hook

# Preserve SLURM CUDA_VISIBLE_DEVICES. Do not create or change a user environment.
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-2}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-2}"
python -B scripts/tc2_gpu/setup/check_setup.py \
    --mode "$check_mode" \
    --config configs/tc2_gpu/setup.json \
    --output-dir "run/setup_tc2_gpu/job_${SLURM_JOB_ID}_${check_mode}"
