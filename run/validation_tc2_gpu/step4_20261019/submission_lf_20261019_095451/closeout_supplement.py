from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import tarfile

root=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code')
audit=root/'run/validation_tc2_gpu/step4_20261019'
record=Path((audit/'active_submission_lf_record.txt').read_text(encoding='utf-8').strip())
checkpoint=json.loads((record/'baseline.json').read_text(encoding='utf-8'))
helper=Path(checkpoint['helper'])
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest().upper()
changes=json.loads((record/'implementation_changes.json').read_text(encoding='utf-8'))
current=helper.read_bytes()
assert sha(helper)==changes['after_sha256']
restored=current
for change in reversed(changes['changes']):
    new=change['new'].encode('utf-8')
    old=change['old'].encode('utf-8')
    if new not in restored: new=new.replace(b'\n',b'\r\n')
    assert restored.count(new)==1
    restored=restored.replace(new,old)
assert restored==(record/'tc2_gpu_setup.before.ps1').read_bytes()
assert all(sha(root/name)==digest for name,digest in checkpoint['protected_files'].items())
index=hashlib.sha256(subprocess.check_output(['git','ls-files','--stage','-z'],cwd=root.parent)).hexdigest().upper()
assert index==checkpoint['git_index_sha256']
initial=json.loads((audit/'baseline.json').read_text(encoding='utf-8'))
changed=[]
for entry in initial['files']:
    path=root.parent/entry['path']
    assert path.is_file(),entry['path']
    if sha(path)!=entry['sha256']:changed.append(entry['path'])
assert set(changed)==set(initial['allowed_existing_changes']),changed
subprocess.run(['git','diff','--check'],cwd=root.parent,capture_output=True,check=True)
failed_attempt=json.loads((audit/'metric_submission_20261019_095048/verification.json').read_text(encoding='utf-8'))
assert sha(Path(failed_attempt['source_terminal']))==failed_attempt['terminal_sha256']
assert sha(audit/'metric_submission_20261019_095048/terminal.txt')==failed_attempt['terminal_sha256']
assert not (root/'run/tc2_gpu').exists()

outputs=helper.parent
packaging={}
for action,folder,bundle,manifest,count in [
    ('CheckMetrics','tc2_gpu_setup_20261019_095723_b437fb0d','metrics-files.tar','metrics.sha256',5),
    ('CheckAlgorithms','tc2_gpu_setup_20261019_095724_f033567a','algorithm-files.tar','algorithms.sha256',11)]:
    directory=outputs/folder
    log=(directory/'terminal.txt').read_text(encoding='utf-8')
    assert 'LOCAL VALIDATION ONLY' in log
    with tarfile.open(directory/bundle) as archive:
        members={entry.name.removeprefix('./'):entry for entry in archive.getmembers() if entry.isfile()}
        rows=archive.extractfile(members[manifest]).read().decode('utf-8').splitlines()
        assert len(rows)==count
        names=[]
        for row in rows:
            digest,name=row.split(None,1)
            name=name.strip().lstrip('*')
            data=archive.extractfile(members[name]).read()
            assert hashlib.sha256(data).hexdigest().upper()==digest.upper()==sha(root/name)
            names.append(name)
        assert set(members)=={manifest,*names}
    packaging[action]={'status':'passed','files':count,'all_payload_bytes_and_hashes_match_sources':True,
                       'terminal':str(directory/'terminal.txt'),'bundle_sha256':sha(directory/bundle)}
transport=json.loads((record/'local_transport_validation.json').read_text(encoding='utf-8-sig'))
lf=json.loads((record/'lf_submission_validation.json').read_text(encoding='utf-8'))
assert transport['status']=='PASS' and lf['status']=='passed' and len(lf['submission_cases'])==16
new_source_hashes={name:sha(root/name) for name in checkpoint['protected_files']}

with (root/'docs/TC2_GPU_ALGORITHMS.md').open('a',encoding='utf-8',newline='\n') as stream:
    stream.write('''
The approved supplement is implemented and verified locally. Both helper blocks now create submission_lf.sh and submission.sha256 in their fresh attempt directories, preserve the verified original source, validate the copy before submission, and keep existing scheduler options. The actual rendered blocks passed sixteen offline fixtures across the two actions: LF, CRLF, existing copy, existing hash record, unsupported internal carriage return, invalid syntax, simulated submission failure, and invalid returned job ID. Failed cases preserved existing file bytes, modification times, and job pointers. Successful cases verified both fingerprints, the exact LF conversion, and unchanged resource directives.

All seventeen rendered commands passed Bash syntax checks. Output archive round trips and corrupt-hash/path rejection passed again. Real CheckMetrics and CheckAlgorithms packaging-only executions passed with five and eleven unchanged payload files, respectively, under local output records tc2_gpu_setup_20261019_095723_b437fb0d and tc2_gpu_setup_20261019_095724_f033567a. These checks made no network connection and submitted no actual job.

The supplement changed only the two authorized helper submission blocks and this document, plus new audit records. Both original SLURM wrappers, all algorithm/metric sources and tests, frozen files, dependency locks, prior terminal output, and the Git index were verified unchanged. New supplement evidence is recorded under run/validation_tc2_gpu/step4_20261019/submission_lf_20261019_095451/. Retry CheckMetrics using the command above; the previous rejected attempt provides no metric acceptance, and step_4_complete remains false.
''')

scope={'status':'passed','helper_changes_limited_to_two_submission_blocks':True,
       'all_other_helper_bytes_unchanged':True,'protected_files_checked':len(checkpoint['protected_files']),
       'protected_files_unchanged':True,'initial_files_checked':len(initial['files']),
       'initial_change_scope_unchanged':True,'prior_terminal_bytes_unchanged':True,
       'git_index_unchanged':True,'git_diff_check_passed':True,'formal_output_directory_absent':True}
status={'status':'local_supplement_verified_awaiting_tc2_metric_retry','step_4_complete':False,
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'authorization':checkpoint['authorization'],
        'scope':scope,'source_hashes':new_source_hashes,'helper_sha256':sha(helper),
        'design_document_sha256':sha(root/'docs/TC2_GPU_ALGORITHMS.md'),
        'offline_transport_checks':transport,'lf_submission_checks':lf,'packaging_only_checks':packaging,
        'actual_ssh_calls':0,'actual_slurm_submissions':0,
        'required_next_action':'Retry CheckMetrics and return terminal.txt; verify full metric acceptance before CheckAlgorithms.'}
(record/'setup_status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
main_path=audit/'setup_status.json'
main=json.loads(main_path.read_text(encoding='utf-8'))
main.update(status='local_supplement_verified_awaiting_tc2_metric_retry',step_4_complete=False,
            required_next_action=status['required_next_action'])
main['submission_lf_supplement']={'status':status['status'],'record':str(record/'setup_status.json'),
                                  'offline_cases_passed':16,'scope':scope,'helper_sha256':sha(helper)}
main['external_helper']['sha256']=sha(helper)
main['documentation_hashes']['docs/TC2_GPU_ALGORITHMS.md']=sha(root/'docs/TC2_GPU_ALGORITHMS.md')
main_path.write_text(json.dumps(main,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
print(json.dumps({'status':status['status'],'step_4_complete':False,'scope':scope,
                  'packaging':{key:value['status'] for key,value in packaging.items()},
                  'record':str(record/'setup_status.json')},indent=2))
