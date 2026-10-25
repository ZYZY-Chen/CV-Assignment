from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import tarfile

root=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code')
audit=root/'run/validation_tc2_gpu/step4_20261019'
returned=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_095830_c60eac52')
w=lambda path:Path('\\\\?\\'+str(path))
raw=lambda path:w(path).read_bytes()
sha=lambda path:hashlib.sha256(raw(path)).hexdigest().upper()
terminal=(returned/'terminal.txt').read_text(encoding='utf-8')
archive=returned/'remote-output.tar.gz'
expected,=set(re.findall(r'TC2_ARTIFACT_SHA256=([0-9a-fA-F]{64})',terminal))
assert sha(archive)==expected.upper()
assert re.search(r'^43968\s+\S+\s+COMPLETED\s+0:0\s',terminal,re.M)
remote=returned/'remote'
allowed=re.compile(r'^(?:run/(?:setup_tc2_gpu|validation_tc2_gpu|setup_v2|validation_v2)/|configs/tc2_(?:setup|gpu)\.json$|environment-tc2\.yml$|requirements-tc2-lock\.txt$)')
names=[]
with tarfile.open(archive,'r:gz') as handle:
    for item in handle.getmembers():
        name=item.name
        assert item.isfile() and not item.issym() and not item.islnk(),name
        assert not name.startswith('/') and '..' not in PurePosixPath(name).parts and '\\' not in name and ':' not in name and allowed.match(name),name
        assert name not in names,name
        names.append(name)
        assert handle.extractfile(item).read()==raw(remote/name),name
assert len(names)==150
long_remote=w(remote)
assert set(names)=={path.relative_to(long_remote).as_posix() for path in long_remote.rglob('*') if path.is_file()}
job='43968'
validation=remote/'run/validation_tc2_gpu'
job_dir=validation/f'step3_job_{job}'
stage=validation/'metrics_stage_20261019_095830_c60eac52'
status=json.loads((job_dir/'setup_status.json').read_text(encoding='utf-8'))
assert status['mode']=='full' and status['step_3_complete'] is True and status['status']=='passed'
assert (status['tests_run'],status['failures'],status['errors'],status['skipped'])==(24,0,0,0)
assert status['failure_details']==[] and status['reference']['cases']==81
assert status['reference']['max_auroc_abs_error']<1e-12 and status['reference']['max_ap_abs_error']<1e-12
assert status['runtime']['slurm_job_id']==job and status['runtime']['step_2_job_id']=='43950'
assert status['runtime']['device']=='cpu' and status['runtime']['gpu_requested'] is False
assert status['runtime']['protocol_sha256']==sha(root/'configs/protocol_v2.json')
assert status['runtime']['frozen_manifests_verified']==8
expected_sources={'src/metric_core.py','src/evaluate.py','src/data.py','tests/test_metrics_tc2_gpu.py','scripts/slurm/check_tc2_gpu_metrics.sh'}
assert set(status['source_hashes'])==expected_sources
assert all(sha(root/name)==digest for name,digest in status['source_hashes'].items())
rows=(stage/'metrics.sha256').read_text(encoding='utf-8').splitlines()
assert len(rows)==5
for row in rows:
    digest,name=row.split(None,1)
    assert digest.upper()==status['source_hashes'][name.strip()]
    assert raw(returned/'metrics_payload'/name.strip())==raw(root/name.strip())
assert raw(stage/'metrics.sha256')==raw(returned/'metrics_payload/metrics.sha256')
assert (stage/'job_id.txt').read_text().strip()==job
assert (validation/'last_check_metrics_job.txt').read_text().strip()==job
wrapper=root/'scripts/slurm/check_tc2_gpu_metrics.sh'
submitted=stage/'submission_lf.sh'
assert raw(submitted)==raw(wrapper).replace(b'\r\n',b'\n')
assert b'\r' not in raw(submitted)
submission_rows=(stage/'submission.sha256').read_text().splitlines()
assert len(submission_rows)==2
for line,expected_path,ending in zip(submission_rows,[wrapper,submitted],['/scripts/slurm/check_tc2_gpu_metrics.sh','/metrics_stage_20261019_095830_c60eac52/submission_lf.sh']):
    digest,recorded_path=line.split(None,1)
    assert digest.upper()==sha(expected_path) and recorded_path.endswith(ending)
log=(validation/f'slurm-{job}.out').read_text(encoding='utf-8')
assert len(re.findall(r'^test_.*\.\.\. ok$',log,re.M))==24
assert 'Ran 24 tests' in log and re.search(r'^OK$',log,re.M)
assert raw(validation/f'slurm-{job}.err')==b''
protocol=json.loads((root/'configs/protocol_v2.json').read_text(encoding='utf-8'))
assert all(sha(root/entry['path'])==entry['file_sha256'] for entry in protocol['data']['frozen_manifests'])
assert raw(remote/'environment-tc2.yml')==raw(root/'environment-tc2.yml')
assert raw(remote/'requirements-tc2-lock.txt')==raw(root/'requirements-tc2-lock.txt')
main_path=audit/'setup_status.json'
main=json.loads(main_path.read_text(encoding='utf-8'))
assert all(sha(root/name)==digest for name,digest in main['source_hashes'].items())
assert sha(Path(main['external_helper']['path']))==main['external_helper']['sha256']

record=audit/'metric_regression_job_43968'
record.mkdir(exist_ok=False)
shutil.copyfile(w(returned/'terminal.txt'),w(record/'terminal.txt'))
shutil.copyfile(w(archive),w(record/'remote-output.tar.gz'))
selected=[job_dir/'setup_status.json',*stage.glob('*'),validation/f'slurm-{job}.out',validation/f'slurm-{job}.err',validation/'last_check_metrics_job.txt']
for path in selected:
    assert w(path).is_file()
    destination=record/'remote'/path.relative_to(remote)
    w(destination.parent).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(w(path),w(destination))
verification={'status':'passed','checked_at_utc':datetime.now(timezone.utc).isoformat(),
              'action':'CheckMetrics','job_id':job,'scheduler_state':'COMPLETED','exit_code':'0:0','node':'TC2N01',
              'source_terminal':str(returned/'terminal.txt'),'terminal_sha256':sha(returned/'terminal.txt'),
              'archive_sha256':sha(archive),'archive_files_verified':len(names),
              'tests_run':24,'failures':0,'errors':0,'skipped':0,'reference':status['reference'],
              'source_hashes':status['source_hashes'],'source_fingerprints_match_current_checkout':True,
              'lf_submission_differs_only_by_line_endings':True,'both_submission_fingerprints_verified':True,
              'current_metric_job_pointer_verified':True,'frozen_manifests_and_actual_environment_locks_verified':True,
              'algorithm_sources_and_helper_unchanged':True,'step_4_complete':False,
              'required_next_action':'Run CheckAlgorithms; return its terminal.txt and verify all CPU/GPU results.'}
(record/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
with (root/'docs/TC2_GPU_ALGORITHMS.md').open('a',encoding='utf-8',newline='\n') as stream:
    stream.write('''
## Current-naming metric regression accepted

After the approved LF submission repair, CheckMetrics job 43968 on TC2N01 completed as COMPLETED / 0:0 in sixteen seconds. All 24 tests passed with zero failures, errors, or skips, and full-mode step_3_complete=true. Across 81 scikit-learn references, maximum AUROC/AP absolute errors were 1.11e-16 / 2.22e-16, below 1e-12.

The returned archive SHA256 and all 150 extracted files were independently verified. All five accepted source hashes match the current checkout. The submitted LF wrapper differs from the original only by CRLF-to-LF conversion, both recorded fingerprints match, the current metric-job pointer identifies 43968, and the frozen manifests and actual environment locks remain unchanged. Evidence is retained under run/validation_tc2_gpu/step4_20261019/metric_regression_job_43968/. The prerequisite for CheckAlgorithms is satisfied. Step 4 remains incomplete pending its full 19-CPU-test and 2-GPU-test acceptance.
''')
history=main.setdefault('metric_submission_history',[])
prior=main.get('latest_metric_submission')
if prior and prior not in history:history.append(prior)
history.append(verification)
main.update(status='metric_regression_verified_awaiting_tc2_algorithm_acceptance',step_4_complete=False,
            required_next_action=verification['required_next_action'],latest_metric_submission=verification,
            remote_metric_regression_received=True,remote_algorithm_acceptance_received=False)
main['submission_lf_supplement'].update(status='remote_metric_submission_verified',metric_job_id=job)
main['documentation_hashes']['docs/TC2_GPU_ALGORITHMS.md']=sha(root/'docs/TC2_GPU_ALGORITHMS.md')
main_path.write_text(json.dumps(main,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
print(json.dumps(verification,indent=2))
