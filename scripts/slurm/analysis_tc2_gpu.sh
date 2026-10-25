#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --job-name=ca6129_analysis_tc2_gpu
set -euo pipefail
[[ "${SLURM_JOB_ID:-}" =~ ^[0-9]+$ && -n "${SLURM_SUBMIT_DIR:-}" ]] || exit 2
root="$(cd -- "$SLURM_SUBMIT_DIR" && pwd -P)"
[[ "$HOME" == /home/mcaai/huajie001 && "$root" == "$HOME/ca6129_v2_setup" ]] || exit 2
cd -- "$root"
[[ ! -L run/validation_tc2_gpu && "$(readlink -m run/validation_tc2_gpu)" == "$root/run/validation_tc2_gpu" ]] || exit 2
[[ "${TC2_ANALYSIS_INPUTS:-}" =~ ^run/validation_tc2_gpu/analysis_inputs_[0-9]{8}_[0-9]{6}_[a-f0-9]{8}/inputs.json$ ]] || exit 2
[[ "${TC2_ANALYSIS_INPUTS_SHA256:-}" =~ ^[A-F0-9]{64}$ ]] || exit 2
[[ ! -L "$root/$TC2_ANALYSIS_INPUTS" && "$(readlink -m -- "$root/$TC2_ANALYSIS_INPUTS")" == "$root/$TC2_ANALYSIS_INPUTS" ]] || exit 2
actual="$(sha256sum -- "$root/$TC2_ANALYSIS_INPUTS" | cut -d' ' -f1)"
[[ "${actual^^}" == "$TC2_ANALYSIS_INPUTS_SHA256" ]] || exit 2
[[ "${SLURM_CPUS_PER_TASK:-}" == 2 && "${SLURM_MEM_PER_NODE:-}" == 8192 ]] || exit 2
[[ -z "${SLURM_JOB_GPUS:-}" && -z "${SLURM_STEP_GPUS:-}" && "${SLURM_GPUS:-0}" == 0 ]] || exit 2
module load anaconda/25.5.1
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$root/envs/ca6129-ad-v2"
set -u
unset conda_hook
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export CUDA_VISIBLE_DEVICES=-1 MPLBACKEND=Agg
record="$root/run/validation_tc2_gpu/step8_job_$SLURM_JOB_ID"
[[ ! -e "$record" && ! -L "$record" ]] || exit 2
mkdir -- "$record"
finish_analysis_job() {
    code=$?
    if [[ "$code" != 0 ]]; then
        python -I -B - "$record/setup_status.json" "$code" <<'ANALYSIS_FAILED_STATE_PY'
from pathlib import Path
import json, os, sys
path, code = Path(sys.argv[1]), int(sys.argv[2])
if path.is_file() and not path.is_symlink():
    value = json.loads(path.read_bytes())
    if value.get('status') not in ('passed','failed'):
        value.update(status='failed',step_8_complete=False,error='Analysis job exited with code ' + str(code))
        temporary = path.with_name('.wrapper_failed_state.json')
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
ANALYSIS_FAILED_STATE_PY
    fi
}
trap finish_analysis_job EXIT
python -I -B - "$root" "$record" "$TC2_ANALYSIS_INPUTS" "$SLURM_JOB_ID" "${BASH_SOURCE[0]}" <<'ANALYSIS_INITIAL_STATE_PY'
from pathlib import Path
import hashlib, json, os, re, sys
root, record, relative, job = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
data = (root / relative).read_bytes()
inputs = json.loads(data)
with (record / 'inputs.json').open('xb') as stream:
    stream.write(data)
state = {'schema_version':'1.0','mode':'tc2_gpu_analysis','stage_id':'analysis','job_id':job,
         'status':'running','phase':'tests','step_8_complete':False,'analysis_path':None,
         'inputs_path':relative,'inputs_sha256':hashlib.sha256(data).hexdigest().upper(),
         'sources':inputs['analysis_sources'],'config_sha256':inputs['config_sha256'],
         'protocol_sha256':inputs['protocol_sha256'],'results_count':66,'analysis_rows':108}
with (record / 'setup_status.json').open('x',encoding='utf-8') as stream:
    json.dump(state,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
for name, expected in inputs['analysis_sources'].items():
    path = root / name
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest().upper() != expected:
        raise RuntimeError('Analysis source changed before testing: ' + name)
stage_relative = relative.rsplit('/',1)[0].replace('/analysis_inputs_','/analysis_stage_')
if os.environ.get('TC2_ANALYSIS_STAGE_DIR') != stage_relative or not re.fullmatch(r'run/validation_tc2_gpu/analysis_stage_[0-9]{8}_[0-9]{6}_[a-f0-9]{8}',stage_relative):
    raise RuntimeError('Analysis submission record path differs')
stage = root / stage_relative
if any(path.is_symlink() for path in (stage,*stage.parents)) or stage.resolve() != stage:
    raise RuntimeError('Linked analysis submission record')
publication_path, submission_path = stage/'publication.json', stage/'submission_lf.sh'
if publication_path.is_symlink() or submission_path.is_symlink():
    raise RuntimeError('Linked analysis publication metadata')
publication = json.loads(publication_path.read_bytes())
sha = lambda value: hashlib.sha256(value).hexdigest().upper()
if (publication.get('status') != 'published' or publication.get('analysis_sources') != inputs['analysis_sources']
        or publication.get('inputs_sha256') != state['inputs_sha256']
        or publication.get('submission_source_sha256') != inputs['analysis_sources']['scripts/slurm/analysis_tc2_gpu.sh']
        or publication.get('submission_sha256') != sha(submission_path.read_bytes())
        or publication.get('submission_sha256') != sha(Path(sys.argv[5]).read_bytes())):
    raise RuntimeError('Analysis submission snapshot differs')
state['publication'] = publication
with (record/'setup_status.json').open('w',encoding='utf-8') as stream:
    json.dump(state,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
ANALYSIS_INITIAL_STATE_PY
python -I -B -u tests/test_analysis_tc2_gpu.py --output-dir "$record/tests" --full > "$record/tests.stdout.txt" 2> "$record/tests.stderr.txt"
python -I -B -u scripts/analyze_results_tc2_gpu.py run --root "$root" --inputs "$root/$TC2_ANALYSIS_INPUTS" --job-id "$SLURM_JOB_ID"
