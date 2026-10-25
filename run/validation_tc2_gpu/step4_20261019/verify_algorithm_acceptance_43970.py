from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import tarfile

ROOT=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code')
AUDIT=ROOT/'run/validation_tc2_gpu/step4_20261019'
RETURNED=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_100241_1978a29d')
W=lambda path:Path('\\\\?\\'+str(path))
raw=lambda path:W(path).read_bytes()
sha=lambda path:hashlib.sha256(raw(path)).hexdigest().upper()
terminal=(RETURNED/'terminal.txt').read_text(encoding='utf-8')
archive=RETURNED/'remote-output.tar.gz'
expected,=set(re.findall(r'TC2_ARTIFACT_SHA256=([0-9a-fA-F]{64})',terminal))
assert sha(archive)==expected.upper()
assert re.search(r'^43970\s+\S+\s+COMPLETED\s+0:0\s',terminal,re.M)
remote=RETURNED/'remote'
allowed=re.compile(r'^(?:run/(?:setup_tc2_gpu|validation_tc2_gpu|setup_v2|validation_v2)/|configs/tc2_(?:setup|gpu)\.json$|environment-tc2\.yml$|requirements-tc2-lock\.txt$)')
archive_bytes={}
with tarfile.open(archive,'r:gz') as handle:
    for item in handle.getmembers():
        name=item.name
        assert item.isfile() and not item.issym() and not item.islnk(),name
        assert not name.startswith('/') and '..' not in PurePosixPath(name).parts and '\\' not in name and ':' not in name and allowed.match(name),name
        assert name not in archive_bytes,name
        data=handle.extractfile(item).read()
        assert data==raw(remote/name),name
        archive_bytes[name]=data
assert len(archive_bytes)==163
long_remote=W(remote)
assert set(archive_bytes)=={path.relative_to(long_remote).as_posix() for path in long_remote.rglob('*') if path.is_file()}
prior_archive=AUDIT/'metric_regression_job_43968/remote-output.tar.gz'
prior_count=0
with tarfile.open(prior_archive,'r:gz') as handle:
    for item in handle.getmembers():
        assert archive_bytes[item.name]==handle.extractfile(item).read(),item.name
        prior_count+=1
assert prior_count==150

job='43970'
validation=remote/'run/validation_tc2_gpu'
job_dir=validation/f'step4_job_{job}'
stage=validation/'algorithms_stage_20261019_100241_1978a29d'
status=json.loads((job_dir/'setup_status.json').read_text(encoding='utf-8'))
assert status['mode']=='full' and status['step_4_complete'] is True and status['status']=='passed'
for group,count in [('cpu',19),('gpu',2)]:
    result=status[group]
    assert (result['tests_run'],result['failures'],result['errors'],result['skipped'])==(count,0,0,0)
    assert result['passed'] is True and result['failure_details']==[]
    log=(job_dir/f'{group}_tests.txt').read_text(encoding='utf-8')
    assert len(re.findall(r'^test_.*\.\.\. ok$',log,re.M))==count
    assert f'Ran {count} tests' in log and re.search(r'^OK$',log,re.M)
runtime=status['runtime']
assert runtime['slurm_job_id']==job and runtime['metric_regression_job_id']=='43968' and runtime['step_2_job_id']=='43950'
assert runtime['gpu_requested'] is True and runtime['device']=='cuda' and runtime['gpu']=='NVIDIA A40'
assert runtime['matmul_tf32'] is False and runtime['cudnn_tf32'] is False and runtime['autocast_enabled'] is False
assert runtime['numpy']=='1.26.4' and runtime['torch']=='2.11.0+cu128' and runtime['cuda_build']=='12.8'
assert runtime['protocol_sha256']==sha(ROOT/'configs/protocol_v2.json') and runtime['frozen_manifests_verified']==8
sources=['src/padim_adapter.py','src/patchcore_adapter.py','src/sampling.py','src/scoring.py','src/anomaly_postprocess.py',
         'tests/test_algorithms_tc2_gpu.py','scripts/slurm/check_tc2_gpu_algorithms.sh','src/metric_core.py','src/evaluate.py','src/data.py','configs/tc2_gpu.json']
assert set(status['source_hashes'])==set(sources)
assert all(sha(ROOT/name)==digest for name,digest in status['source_hashes'].items())
rows=(stage/'algorithms.sha256').read_text(encoding='utf-8').splitlines()
assert len(rows)==11
for row in rows:
    digest,name=row.split(None,1); name=name.strip()
    assert digest.upper()==status['source_hashes'][name]
    assert raw(RETURNED/'algorithms_payload'/name)==raw(ROOT/name)
assert raw(stage/'algorithms.sha256')==raw(RETURNED/'algorithms_payload/algorithms.sha256')
assert (stage/'job_id.txt').read_text().strip()==job
assert (stage/'metric_regression_job.txt').read_text().strip()=='43968'
assert (validation/'last_check_algorithms_job.txt').read_text().strip()==job
assert (validation/'last_check_metrics_job.txt').read_text().strip()=='43968'
prior_status=validation/'step3_job_43968/setup_status.json'
prior_copy=AUDIT/'metric_regression_job_43968/remote/run/validation_tc2_gpu/step3_job_43968/setup_status.json'
assert raw(prior_status)==raw(prior_copy)
metrics=json.loads(prior_status.read_text(encoding='utf-8'))
assert metrics['status']=='passed' and metrics['step_3_complete'] is True and metrics['mode']=='full'
for name in ['src/metric_core.py','src/evaluate.py','src/data.py']:
    assert metrics['source_hashes'][name]==status['source_hashes'][name]
wrapper=ROOT/'scripts/slurm/check_tc2_gpu_algorithms.sh'
submitted=stage/'submission_lf.sh'
assert raw(submitted)==raw(wrapper).replace(b'\r\n',b'\n') and b'\r' not in raw(submitted)
submission_rows=(stage/'submission.sha256').read_text(encoding='utf-8').splitlines()
assert len(submission_rows)==2
for line,path,ending in zip(submission_rows,[wrapper,submitted],['/scripts/slurm/check_tc2_gpu_algorithms.sh','/algorithms_stage_20261019_100241_1978a29d/submission_lf.sh']):
    digest,recorded_path=line.split(None,1)
    assert digest.upper()==sha(path) and recorded_path.endswith(ending)
expected_directives=['--nodes=1','--ntasks=1','--gres=gpu:1','--cpus-per-task=2','--mem=8G','--time=00:15:00','--job-name=ca6129_algorithms_tc2_gpu']
assert [line[8:] for line in raw(submitted).decode('utf-8').splitlines() if line.startswith('#SBATCH ')]==expected_directives
assert raw(validation/f'slurm-{job}.err')==b''
protocol=json.loads((ROOT/'configs/protocol_v2.json').read_text(encoding='utf-8'))
assert all(sha(ROOT/entry['path'])==entry['file_sha256'] for entry in protocol['data']['frozen_manifests'])
assert raw(remote/'environment-tc2.yml')==raw(ROOT/'environment-tc2.yml')
assert raw(remote/'requirements-tc2-lock.txt')==raw(ROOT/'requirements-tc2-lock.txt')
assert raw(remote/'configs/tc2_gpu.json')==raw(ROOT/'configs/tc2_gpu.json')
main=json.loads((AUDIT/'setup_status.json').read_text(encoding='utf-8'))
assert main['source_hashes']==status['source_hashes']
assert sha(Path(main['external_helper']['path']))==main['external_helper']['sha256']
assert not (ROOT/'run/tc2_gpu').exists()

record=AUDIT/'algorithm_acceptance_job_43970'
record.mkdir(exist_ok=False)
shutil.copyfile(W(RETURNED/'terminal.txt'),W(record/'terminal.txt'))
shutil.copyfile(W(archive),W(record/'remote-output.tar.gz'))
selected=[Path(str(path).removeprefix('\\\\?\\')) for path in W(job_dir).rglob('*') if path.is_file()]
selected += [*stage.glob('*'),validation/f'slurm-{job}.out',validation/f'slurm-{job}.err',validation/'last_check_algorithms_job.txt']
for path in selected:
    assert W(path).is_file()
    destination=record/'remote'/path.relative_to(remote)
    W(destination.parent).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(W(path),W(destination))
verification={'status':'passed','checked_at_utc':datetime.now(timezone.utc).isoformat(),
              'action':'CheckAlgorithms','job_id':job,'scheduler_state':'COMPLETED','exit_code':'0:0','node':'TC2N01',
              'source_terminal':str(RETURNED/'terminal.txt'),'terminal_sha256':sha(RETURNED/'terminal.txt'),
              'archive_sha256':sha(archive),'archive_files_verified':len(archive_bytes),
              'prior_archive_files_preserved':prior_count,'source_hashes':status['source_hashes'],
              'source_fingerprints_match_current_checkout':True,'lf_submission_verified':True,
              'submission_resources_verified':{'gpu':1,'cpu':2,'memory_gib':8,'time_limit':'00:15:00'},
              'metric_regression_job_id':'43968','metric_regression_evidence_unchanged':True,
              'frozen_manifests_actual_environment_locks_and_naming_map_verified':True,
              'runtime':runtime,'cpu':status['cpu'],'gpu':status['gpu'],'step_4_complete':True,
              'scope':'Synthetic algorithm acceptance only; runner/cache integration and real-data experiments remain later steps.'}
(record/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','job_id':job,'step_4_complete':True,'archive_files_verified':len(archive_bytes),
                  'prior_archive_files_preserved':prior_count,'source_fingerprints_verified':len(sources),
                  'cpu_tests':status['cpu']['tests_run'],'gpu_tests':status['gpu']['tests_run'],'record':str(record/'verification.json')},indent=2))
