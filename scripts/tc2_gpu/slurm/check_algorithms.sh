#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --job-name=ca6129_algorithms_tc2_gpu
set -euo pipefail
[[ "${SLURM_JOB_ID:-}" =~ ^[0-9]+$ && -n "${SLURM_SUBMIT_DIR:-}" ]] || { echo 'Submit with sbatch.' >&2; exit 2; }
root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
deployment_info="$("${TC2_BOOTSTRAP_PYTHON:-python3}" -B - "$root" "algorithms" <<'TC2_GPU_DEPLOYMENT_PY'
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
cd -- "$root"
[[ ! -L run/validation_tc2_gpu && "$(readlink -m run/validation_tc2_gpu)" == "$root/run/validation_tc2_gpu" ]] || exit 2
module load "$tc2_anaconda_module"
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$tc2_environment_prefix"
set -u
unset conda_hook
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
# Respect the scheduler's visible devices; the test requires one real CUDA GPU.
python -B tests/test_algorithms_tc2_gpu.py --mode full --output-dir "run/validation_tc2_gpu/step4_job_${SLURM_JOB_ID}"
