cd -- "$root"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" '__CONFIG__' '__STAGE__' <<'EXPERIMENTS_PREFLIGHT_PY'
import base64, hashlib, json, pathlib, re, shutil, sys
root = pathlib.Path(sys.argv[1])
config = json.loads(base64.b64decode(sys.argv[2], validate=True))
stage_id = sys.argv[3]
def safe(relative):
    p = pathlib.PurePosixPath(relative)
    if p.is_absolute() or not relative or str(p) != relative or '..' in p.parts or '\\' in relative or ':' in relative:
        raise RuntimeError('Unsafe preflight path')
    q = root / p
    if q.resolve() != q or any(a.is_symlink() for a in (q, *q.parents)) or not q.is_file():
        raise RuntimeError('Unsafe or missing preflight file: ' + relative)
    return q
def sha(relative):
    h = hashlib.sha256()
    with safe(relative).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest().upper()
def read(relative):
    return json.loads(safe(relative).read_text())
scientific, pilot = config['scientific_source_hashes'], config['pilot_source_hashes']
if len(scientific) != 31 or len(pilot) != 6 or config['accepted_workflow_job_id'] != '44012' or config['accepted_pilot_job_id'] != '44024':
    raise RuntimeError('Experiment acceptance identities differ')
if safe('run/validation_tc2_gpu/last_check_workflow_job.txt').read_text().strip() != '44012':
    raise RuntimeError('Latest workflow acceptance pointer differs')
workflow = read('run/validation_tc2_gpu/step5_job_44012/setup_status.json')
if workflow.get('mode') != 'full' or workflow.get('status') != 'passed' or workflow.get('step_5_complete') is not True or workflow.get('source_hashes') != scientific:
    raise RuntimeError('Full accepted workflow is required')
if safe('run/validation_tc2_gpu/last_pilot_job.txt').read_text().strip() != '44024':
    raise RuntimeError('Latest pilot acceptance pointer differs')
accepted = read('run/validation_tc2_gpu/step6_job_44024/setup_status.json')
if accepted.get('mode') != 'real_data_pilot' or accepted.get('status') != 'passed' or accepted.get('step_6_complete') is not True or accepted.get('pilot_sources') != pilot:
    raise RuntimeError('Full accepted real-data pilot is required')
for name, value in {**scientific, **pilot}.items():
    if sha(name) != value.upper():
        raise RuntimeError('Accepted scientific or pilot source differs: ' + name)
if sha('configs/tc2_setup.json') != 'EDF3D1D0380E0105A5173607CE360221FD43B059478915EEC0EC04ED9110F913':
    raise RuntimeError('Original remote compatibility configuration differs')
if sha('weights/resnet18-f37072fd.pth') != 'F37072FD47E89C5E827621C5BAFFA7500819F7896BBACEC160B1A16C560E07EC':
    raise RuntimeError('Accepted local weights differ')
if shutil.disk_usage(root).free < 20 * 1024 ** 3:
    raise RuntimeError('Experiments require at least 20 GiB of remote free space')
stages = [s for s in config['stages'] if s['stage_id'] == stage_id]
if len(stages) != 1:
    raise RuntimeError('Requested experiment stage is ambiguous')
predecessor = stages[0]['predecessor']
if predecessor:
    pointer = safe('run/validation_tc2_gpu/last_experiments_' + predecessor + '_job.txt').read_text().strip()
    if not re.fullmatch('[0-9]+', pointer):
        raise RuntimeError('Invalid latest predecessor job pointer')
    prior = read('run/validation_tc2_gpu/step7_job_' + pointer + '/setup_status.json')
    if prior.get('mode') != 'formal_experiment_stage' or prior.get('stage_id') != predecessor or prior.get('job_id') != pointer or prior.get('status') != 'passed' or prior.get('stage_complete') is not True or prior.get('design_sha256') != config['design_sha256']:
        raise RuntimeError('Latest predecessor stage is not complete; no earlier-success fallback')
print('Experiment head-node preflight passed: 31 scientific and six pilot sources; no model or GPU probe executed.')
EXPERIMENTS_PREFLIGHT_PY
[[ ! -e "$root/_downloads/experiments-files-__RUNID__.tar" && ! -L "$root/_downloads/experiments-files-__RUNID__.tar" ]] || { echo 'Experiment upload target already exists; no overwrite.' >&2; exit 2; }
