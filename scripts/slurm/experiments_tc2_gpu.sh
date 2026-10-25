#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --job-name=ca6129_experiments_tc2_gpu
set -euo pipefail
[[ "${SLURM_JOB_ID:-}" =~ ^[0-9]+$ && -n "${SLURM_SUBMIT_DIR:-}" ]] || exit 2
root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
[[ "$HOME" == /home/mcaai/huajie001 && "$root" == "$HOME/ca6129_v2_setup" ]] || exit 2
cd -- "$root"
[[ ! -L run/validation_tc2_gpu && "$(readlink -m run/validation_tc2_gpu)" == "$root/run/validation_tc2_gpu" ]] || exit 2
[[ -n "${TC2_EXPERIMENT_STAGE_DIR:-}" && -n "${TC2_EXPERIMENT_STAGE:-}" ]] || exit 2
module load anaconda/25.5.1
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$root/envs/ca6129-ad-v2"
set -u
unset conda_hook
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -B -u scripts/experiments_tc2_gpu.py run --root "$root" --stage "$TC2_EXPERIMENT_STAGE"
