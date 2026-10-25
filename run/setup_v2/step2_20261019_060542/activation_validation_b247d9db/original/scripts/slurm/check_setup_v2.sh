#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=ca6129_setup_v2
# Partition, QoS and absolute log paths must be supplied after account verification.
set -euo pipefail

if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    echo "Submit this script with sbatch; do not run it on the head node." >&2
    exit 2
fi
if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: check_setup_v2.sh /verified/conda/environment [environment|all]" >&2
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
if [[ "$HOME" != /home/mcaai/huajie001 || "$project_root" != "$HOME/ca6129_v2_setup" ]]; then
    echo "Submit from the verified personal ca6129_v2_setup directory." >&2
    exit 2
fi
cd -- "$project_root"
if [[ ! -f configs/protocol_v2.json || ! -f configs/tc2_setup.json ]]; then
    echo "The staging project must contain the frozen protocol and verified setup configuration." >&2
    exit 2
fi

if [[ -n "${TC2_ANACONDA_MODULE:-}" ]]; then
    module load "$TC2_ANACONDA_MODULE"
fi
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
python -B scripts/check_setup_v2.py \
    --mode "$check_mode" \
    --config configs/tc2_setup.json \
    --output-dir "run/setup_v2/job_${SLURM_JOB_ID}_${check_mode}"
