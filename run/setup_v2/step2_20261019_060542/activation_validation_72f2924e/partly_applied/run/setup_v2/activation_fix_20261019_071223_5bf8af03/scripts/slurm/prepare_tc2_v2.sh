#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --job-name=ca6129_prepare_v2
set -euo pipefail
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo 'Submit with sbatch.' >&2; exit 2; }
[[ $# == 1 && ( "$1" == environment || "$1" == inputs ) ]] || { echo 'Use environment or inputs.' >&2; exit 2; }
mode="$1"
[[ -n "${SLURM_SUBMIT_DIR:-}" ]] || { echo 'SLURM_SUBMIT_DIR is required.' >&2; exit 2; }
project_root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
[[ "$HOME" == /home/mcaai/huajie001 && "$project_root" == "$HOME/ca6129_v2_setup" ]] || exit 2
cd -- "$project_root"
module load anaconda/25.5.1
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-2}" MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-2}"
export CONDA_PKGS_DIRS="$project_root/_package_cache/conda"
export CONDA_ENVS_PATH="$project_root/envs"
export PIP_CACHE_DIR="$project_root/_package_cache/pip"
export TMPDIR="$project_root/tmp"
for directory in "$CONDA_PKGS_DIRS" "$CONDA_ENVS_PATH" "$PIP_CACHE_DIR" "$TMPDIR" "$project_root/run/setup_v2" "$project_root/configs"; do
    [[ ! -L "$directory" && "$(readlink -m -- "$directory")" == "$directory" ]] || { echo 'Unsafe preparation directory.' >&2; exit 2; }
done
[[ ! -L "$project_root/configs/tc2_setup.json" ]] || exit 2
mkdir -p -- "$CONDA_PKGS_DIRS" "$CONDA_ENVS_PATH" "$PIP_CACHE_DIR" "$TMPDIR"
if [[ "$mode" == environment ]]; then
    bash scripts/prepare_tc2_environment_v2.sh
else
    environment_prefix="$project_root/envs/ca6129-ad-v2"
    [[ -x "$environment_prefix/bin/python" && ! -L "$environment_prefix" ]] || { echo 'Dedicated environment not ready.' >&2; exit 2; }
    # Shared activation hooks may legitimately read unset optional Qt variables.
    # Keep errexit/pipefail, and restore nounset before project code runs.
    set +u
    conda_hook="$(conda shell.bash hook)"
    eval "$conda_hook"
    conda activate "$environment_prefix"
    set -u
    unset conda_hook
    python -B scripts/prepare_tc2_inputs_v2.py --accept-license
fi
