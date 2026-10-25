#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --job-name=ca6129_metrics_v2
set -euo pipefail
[[ "${SLURM_JOB_ID:-}" =~ ^[0-9]+$ && -n "${SLURM_SUBMIT_DIR:-}" ]] || { echo 'Submit with sbatch.' >&2; exit 2; }
root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
[[ "$HOME" == /home/mcaai/huajie001 && "$root" == "$HOME/ca6129_v2_setup" ]] || exit 2
cd -- "$root"
[[ ! -L run/validation_v2 && "$(readlink -m run/validation_v2)" == "$root/run/validation_v2" ]] || exit 2
module load anaconda/25.5.1
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$root/envs/ca6129-ad-v2"
set -u
unset conda_hook
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
# All test tensors explicitly use CPU; no GPU allocation or probe is requested.
python -B tests/test_metrics_v2.py --mode full --output-dir "run/validation_v2/step3_job_${SLURM_JOB_ID}"
