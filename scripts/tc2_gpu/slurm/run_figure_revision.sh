#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --job-name=ca6129_figure_revision_tc2_gpu
set -euo pipefail
[[ "${SLURM_JOB_ID:-}" =~ ^[0-9]{1,12}$ && -n "${SLURM_SUBMIT_DIR:-}" ]] || exit 2
root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
deployment_info="$("${TC2_BOOTSTRAP_PYTHON:-python3}" -B - "$root" "figure_revision" <<'TC2_GPU_DEPLOYMENT_PY'
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
[[ "${TC2_FIGURE_PLAN:-}" =~ ^run/validation_tc2_gpu/figure_revision_inputs_[0-9]{8}_[0-9]{6}_[a-f0-9]{8}/plan.json$ ]] || exit 2
[[ "${TC2_FIGURE_PLAN_SHA256:-}" =~ ^[A-F0-9]{64}$ ]] || exit 2
[[ "${TC2_FIGURE_STAGE:-}" =~ ^run/validation_tc2_gpu/figure_revision_stage_[0-9]{8}_[0-9]{6}_[a-f0-9]{8}$ ]] || exit 2
for path in run/validation_tc2_gpu "$TC2_FIGURE_PLAN" "$TC2_FIGURE_STAGE"; do
    [[ ! -L "$root/$path" && "$(readlink -m -- "$root/$path")" == "$root/$path" ]] || exit 2
done
actual="$(sha256sum -- "$root/$TC2_FIGURE_PLAN" | cut -d' ' -f1)"
[[ "${actual^^}" == "$TC2_FIGURE_PLAN_SHA256" ]] || exit 2
[[ "${SLURM_CPUS_PER_TASK:-}" == 2 && "${SLURM_MEM_PER_NODE:-}" == 8192 ]] || exit 2
[[ -z "${SLURM_JOB_GPUS:-}" && -z "${SLURM_STEP_GPUS:-}" && "${SLURM_GPUS:-0}" == 0 ]] || exit 2
module load "$tc2_anaconda_module"
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$tc2_environment_prefix"
set -u
unset conda_hook
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export CUDA_VISIBLE_DEVICES=-1 MPLBACKEND=Agg
record="$root/run/validation_tc2_gpu/step8_figure_revision_job_$SLURM_JOB_ID"
[[ ! -e "$record" && ! -L "$record" ]] || exit 2
mkdir -- "$record"
finish_figure_job() {
    code=$?
    if [[ "$code" != 0 ]]; then
        python -I -B - "$record/state.json" "$code" <<'FIGURE_FAILED_PY'
from pathlib import Path
import json, os, sys
path, code = Path(sys.argv[1]), int(sys.argv[2])
if path.is_file() and not path.is_symlink():
    value = json.loads(path.read_bytes())
    value.update(status='failed',step_8_complete=False,error='Figure revision job exited with code '+str(code))
    temporary = path.with_name('.wrapper_failed_state.json')
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,path)
FIGURE_FAILED_PY
    fi
}
trap finish_figure_job EXIT
python -I -B - "$root" "$record" "$TC2_FIGURE_PLAN" "$TC2_FIGURE_STAGE" "$SLURM_JOB_ID" "${BASH_SOURCE[0]}" <<'FIGURE_INITIAL_PY'
from pathlib import Path
import hashlib, json, os, sys
root,record,relative,stage_name,job,script=Path(sys.argv[1]),Path(sys.argv[2]),*sys.argv[3:]
sha=lambda data:hashlib.sha256(data).hexdigest().upper()
data=(root/relative).read_bytes(); plan=json.loads(data)
stage=root/stage_name
for path in (stage,stage/'publication.json',stage/'submission_lf.sh'):
    if path.is_symlink() or path.resolve()!=path: raise RuntimeError('Linked figure publication record')
publication=json.loads((stage/'publication.json').read_bytes())
sources=plan['figure_revision_sources']
if (publication.get('status')!='published' or publication.get('figure_revision_sources')!=sources
        or publication.get('plan_sha256')!=sha(data)
        or publication.get('submission_source_sha256')!=sources['scripts/tc2_gpu/slurm/run_figure_revision.sh']
        or publication.get('submission_sha256')!=sha((stage/'submission_lf.sh').read_bytes())
        or publication.get('submission_sha256')!=sha(Path(script).read_bytes())):
    raise RuntimeError('Figure publication snapshot differs')
for name,fingerprint in sources.items():
    path=root/name
    if path.is_symlink() or path.resolve()!=path or sha(path.read_bytes())!=fingerprint:
        raise RuntimeError('Figure revision source differs before testing: '+name)
for name,value in (('plan.json',data),('publication.json',(stage/'publication.json').read_bytes())):
    with (record/name).open('xb') as stream: stream.write(value)
state={'schema_version':'1.0','job_id':job,'identity':plan['identity'],'status':'running',
       'phase':'tests','output_relative':None,'step_8_complete':False,'new_fits':0,'model_predict_calls':0}
with (record/'state.json').open('x',encoding='utf-8') as stream:
    json.dump(state,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
FIGURE_INITIAL_PY
python -I -B scripts/tc2_gpu/analysis/revise_figures.py preflight --root "$root" --plan "$root/$TC2_FIGURE_PLAN"
python -I -B -u tests/test_figure_revision_tc2_gpu.py --output-dir "$record/tests" --full > "$record/tests.stdout.txt" 2> "$record/tests.stderr.txt"
python -I -B -u scripts/tc2_gpu/analysis/revise_figures.py run --root "$root" --job-id "$SLURM_JOB_ID" --plan "$root/$TC2_FIGURE_PLAN"
