from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,re,runpy,subprocess,tarfile
from urllib.parse import unquote
repo=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment');root=repo/'group_XX_code';audit=root/'run/validation_tc2_gpu/step5_20261019'
base=json.loads((audit/'baseline.json').read_text(encoding='utf-8'))
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest().upper()
changed=[]
for entry in base['files']:
    path=repo/entry['path'];assert path.is_file(),entry['path']
    if sha(path)!=entry['sha256']:changed.append(entry['path'])
assert sorted(changed)==sorted(base['allowed_existing_changes']),changed
old={entry['path'] for entry in base['files']};allowed={'group_XX_code/'+name for name in base['allowed_new_sources']};new=[];audit_count=0
for name in subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=repo).decode('utf-8').split('\0'):
    if not name or name in old:continue
    if name.startswith('group_XX_code/run/validation_tc2_gpu/step5_20261019/'):
        audit_count+=1;continue
    assert name in allowed,name;new.append(name)
assert set(new)==allowed
assert hashlib.sha256(subprocess.check_output(['git','ls-files','--stage','-z'],cwd=repo)).hexdigest().upper()==base['git_index_sha256']
subprocess.run(['git','diff','--check'],cwd=repo,capture_output=True,check=True)
ignore=(repo/'.gitignore').read_bytes();assert ignore.startswith((audit/'before/.gitignore').read_bytes())
assert subprocess.run(['git','check-ignore','--no-index','group_XX_code/run/tc2_gpu/feature_cache/example/layer1.npy'],cwd=repo,capture_output=True).returncode==0
readme=(root/'README.md').read_bytes();start=readme.index(b'## TC2 GPU workflow and step-5 acceptance\n');end=readme.index(('## '+''.join(chr(x) for x in (0x6570,0x636e,0x96c6))).encode('utf-8'),start)
assert readme[:start]+readme[end:]==(audit/'before/group_XX_code/README.md').read_bytes()
for name in base['allowed_new_sources']:
    text=(root/name).read_text(encoding='utf-8')
    assert not re.search(r'[\u3400-\u9fff]',text),name
    if name.endswith('.py'):ast.parse(text,filename=name)
for path in [root/'README.md',root/'docs/TC2_GPU_WORKFLOW.md']:
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#'):assert (path.parent/unquote(target.split('#')[0])).exists(),target
helper=Path(base['external_helper']);current=helper.read_bytes();changes=json.loads((audit/'workflow_helper_changes.json').read_text(encoding='utf-8'))
text=current.decode('utf-8-sig').replace('\r\n','\n');branch=changes['inserted_branch']
assert text.count(branch)==1
restored=text.replace(branch,'',1).replace("'CheckMetrics','CheckAlgorithms','CheckWorkflow')","'CheckMetrics','CheckAlgorithms')",1)
before=(audit/'tc2_gpu_setup.before.ps1').read_bytes();eol='\r\n' if before.count(b'\r\n')==before.count(b'\n') else '\n';bom=b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b''
assert bom+restored.replace('\n',eol).encode('utf-8')==before
assert sha(helper)==changes['after_sha256']
core=json.loads((audit/'local_core_02/setup_status.json').read_text(encoding='utf-8'))
assert core['status']=='passed' and core['core']['tests_run']==16 and core['core']['skipped']==0 and not core['step_5_complete']
assert all(sha(root/name)==digest for name,digest in core['source_hashes'].items())
guard=json.loads((audit/'local_full_guard/setup_status.json').read_text(encoding='utf-8'))
assert not guard['step_5_complete'] and 'Linux SLURM' in guard['error']
transport=json.loads((audit/'local_transport_validation.json').read_text(encoding='utf-8-sig'))
delivery=json.loads((audit/'delivery_validation.json').read_text(encoding='utf-8'))
assert transport['status']=='PASS' and transport['rendered_shell_commands']==19 and delivery['status']=='passed' and len(delivery['cases'])==11
pack=Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_111254_e84d6cf5')
assert 'LOCAL VALIDATION ONLY' in (pack/'terminal.txt').read_text(encoding='utf-8')
expected=runpy.run_path(str(root/'tests/test_workflow_tc2_gpu.py'))['payload_files']()
assert len(expected)==32
with tarfile.open(pack/'workflow-files.tar') as archive:
    members={entry.name.removeprefix('./'):entry for entry in archive.getmembers() if entry.isfile()}
    assert set(members)=={'workflow.sha256',*expected}
    rows=archive.extractfile(members['workflow.sha256']).read().decode('utf-8').splitlines();assert len(rows)==32
    for row in rows:
        digest,name=row.split(None,1);name=name.strip()
        assert hashlib.sha256(archive.extractfile(members[name]).read()).hexdigest().upper()==digest.upper()==sha(root/name),name
assert not (root/'run/tc2_gpu').exists()
step4=json.loads((root/'run/validation_tc2_gpu/step4_20261019/setup_status.json').read_text(encoding='utf-8'))
assert all(sha(root/name)==digest for name,digest in step4['source_hashes'].items())
scope={'status':'passed','preexisting_files_checked':len(base['files']),'preexisting_files_unchanged':len(base['files'])-len(changed),
       'changed_existing_files':sorted(changed),'new_source_files':sorted(new),'new_audit_files':audit_count,
       'readme_existing_bytes_and_chinese_preserved':True,'gitignore_append_only':True,'other_helper_bytes_preserved':True,
       'frozen_inputs_locks_historical_records_and_accepted_algorithms_unchanged':True,'git_index_unchanged':True,
       'git_diff_check_passed':True,'document_links_valid':True,'formal_output_directory_absent':True}
(audit/'scope_validation.json').write_text(json.dumps(scope,indent=2)+'\n',encoding='utf-8')
status={'status':'local_implementation_verified_awaiting_tc2_workflow_acceptance','step_5_complete':False,
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),'authorization':base['authorization'],
        'approved_design':'docs/TC2_GPU_WORKFLOW.md','scope':scope,'local_core':core['core'],
        'local_full_guard':{'status':'expected_refusal','error':guard['error']},'offline_transport':transport,
        'offline_delivery':delivery,'packaging_only':{'status':'passed','files':32,'terminal':str(pack/'terminal.txt'),'bundle_sha256':sha(pack/'workflow-files.tar')},
        'source_hashes':{name:sha(root/name) for name in expected if not name.startswith('docs/')},
        'documentation_hashes':{name:sha(root/name) for name in ['README.md','docs/TC2_GPU_WORKFLOW.md']},
        'external_helper':{'path':str(helper),'sha256':sha(helper)},'gpu_workflow_tests_pending':4,
        'required_unchanged_regressions':{'metric_tests':24,'algorithm_cpu_tests':19,'algorithm_gpu_tests':2},
        'remote_acceptance_received':False,'actual_tc2_connections':0,'actual_slurm_submissions':0,
        'local_generator_correction_record':'local_generation_note.json',
        'required_next_action':'Run CheckWorkflow in the local Windows terminal; return terminal.txt. Collect the same job if still queued/running.'}
(audit/'setup_status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':status['status'],'step_5_complete':False,'core_tests':16,'offline_delivery_cases':11,
                  'packaged_files':32,'scope':scope,'next_action':'CheckWorkflow'},indent=2))
