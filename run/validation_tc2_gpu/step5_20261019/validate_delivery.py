"""Offline rendered workflow publication, rejection and submission fixtures only."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import uuid

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASH=r'C:\Program Files\Git\bin\bash.exe'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
transport=json.loads((HERE/'local_transport_validation.json').read_text(encoding='utf-8-sig'))
commands=list(Path(transport['validation_root']).rglob('command_*.sh'))
assert len(commands)==19
for path in commands+[ROOT/'scripts/slurm/check_tc2_gpu_workflow.sh']:
    result=subprocess.run([BASH,'-n',str(path)],capture_output=True,text=True)
    assert result.returncode==0,(str(path),result.stderr)
command,=[path for path in commands if 'Thirty-two verified workflow files staged' in path.read_text(encoding='utf-8')]
rendered=command.read_text(encoding='utf-8')
lookup=re.search(r'(?ms)^setup_record\(\) \{.*?^\}',rendered).group()
start=rendered.index('cd -- "$root"\nworkflow_file_allowed()')
last='printf \'%s\\n\' "$job_id" > "$stage_record/job_id.txt"'
end=rendered.index(last,start)+len(last)
body=rendered[start:end]
payload=command.parent/'workflow_payload'
rows=[line.split(maxsplit=1) for line in (payload/'workflow.sha256').read_text(encoding='utf-8').splitlines()]
assert len(rows)==len({row[1] for row in rows})==32
for digest,name in rows:assert sha(ROOT/name)==digest==sha(payload/name),name
assert 'configs/tc2_setup.json' not in {name for _,name in rows}
bundle_name=re.search(r'workflow-files-[^/"\n]+\.tar',body).group()
weight_hash=re.search(r'sha256sum weights/resnet18-f37072fd.pth.*?== ([0-9a-f]{64})',body).group(1)
accepted=json.loads((ROOT/'run/validation_tc2_gpu/step4_20261019/setup_status.json').read_text(encoding='utf-8'))
compatibility=Path(accepted['accepted_algorithm_execution']['source_terminal']).parent/'remote/configs/tc2_setup.json'
assert sha(compatibility)=='edf3d1d0380e0105a5173607ce360221fd43b059478915eec0ec04ed9110f913'
metric=accepted['latest_metric_submission']
algorithm=accepted['accepted_algorithm_execution']
new=set(json.loads((HERE/'baseline.json').read_text(encoding='utf-8'))['allowed_new_sources'])
result_root=HERE/('delivery_'+uuid.uuid4().hex[:8]);result_root.mkdir()
cases=['absent','identical','unknown_source','missing_metric','failed_metric','failed_algorithm',
       'changed_accepted_hash','compatibility_changed','bad_weight_hash','bad_bundle','submission_failure']
results=[]
for case in cases:
    target=result_root/case
    for relative in ['tmp','_downloads','configs','weights','envs/ca6129-ad-v2/bin',
                     'run/setup_v2/job_43950_all','run/validation_tc2_gpu/step3_job_43968','run/validation_tc2_gpu/step4_job_43970']:
        (target/relative).mkdir(parents=True)
    executable=target/'envs/ca6129-ad-v2/bin/python';executable.write_text('#!/bin/sh\nexit 0\n',newline='\n')
    (target/'run/setup_v2/last_check_all_job.txt').write_text('43950\n')
    (target/'run/setup_v2/job_43950_all/setup_status.json').write_text('{"step_2_complete": true}\n')
    if case!='missing_metric':(target/'run/validation_tc2_gpu/last_check_metrics_job.txt').write_text('43968\n')
    (target/'run/validation_tc2_gpu/last_check_algorithms_job.txt').write_text('43970\n')
    pointer=target/'run/validation_tc2_gpu/last_check_workflow_job.txt';pointer.write_text('80000\n')
    m={'mode':'full','status':'passed','step_3_complete':case!='failed_metric','source_hashes':metric['source_hashes']}
    a={'mode':'full','status':'passed','step_4_complete':case!='failed_algorithm','source_hashes':dict(algorithm['source_hashes'])}
    if case=='changed_accepted_hash':a['source_hashes']['src/sampling.py']='0'*64
    (target/'run/validation_tc2_gpu/step3_job_43968/setup_status.json').write_text(json.dumps(m,indent=2)+'\n')
    (target/'run/validation_tc2_gpu/step4_job_43970/setup_status.json').write_text(json.dumps(a,indent=2)+'\n')
    shutil.copyfile(compatibility,target/'configs/tc2_setup.json')
    if case=='compatibility_changed':
        with (target/'configs/tc2_setup.json').open('ab') as stream:stream.write(b' ')
    (target/'weights/resnet18-f37072fd.pth').write_bytes(b'Offline placeholder; weight hash is stubbed, not verified here.\n')
    original={}
    for _,name in rows:
        if name not in new or case=='identical':
            path=target/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(payload/name,path)
    if case=='unknown_source':
        path=target/'src/tc2_gpu_runner.py';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'Unknown existing source. Preserve.\n')
    for path in target.rglob('*'):
        if path.is_file():original[path.relative_to(target).as_posix()]=(path.read_bytes(),path.stat().st_mtime_ns)
    bundle=target/'_downloads'/bundle_name;shutil.copyfile(command.parent/'workflow-files.tar',bundle)
    if case=='bad_bundle':
        with bundle.open('ab') as stream:stream.write(b'tampered')
    stub=r'''set -euo pipefail
root="$(pwd -P)"
chmod +x "$root/envs/ca6129-ad-v2/bin/python"
sha256sum() {
    if [[ "$#" == 1 && "$1" == weights/resnet18-f37072fd.pth ]]; then
        printf '%s  %s\n' "$STUB_WEIGHT_HASH" "$1"
    else command sha256sum "$@"; fi
}
sbatch() {
    printf 'stub\n' >> "$root/stub_calls.txt"
    printf '%s\0' "$@" > "$root/stub_arguments.bin"
    local script="${!#}"
    [[ "$script" == "$stage_record/submission_lf.sh" ]] || return 20
    if LC_ALL=C grep -q $'\r' "$script"; then return 21; fi
    bash -n "$script" || return 22
    if [[ "${STUB_FAIL:-0}" == 1 ]]; then return 17; fi
    printf '91235;offline\n'
}
'''
    settings='STUB_WEIGHT_HASH='+('0'*64 if case=='bad_weight_hash' else weight_hash)+'\n'
    if case=='submission_failure':settings+='STUB_FAIL=1\n'
    script=target/'exercise.sh';script.write_text(stub+settings+lookup+'\n'+body+'\n',encoding='utf-8',newline='\n')
    completed=subprocess.run([BASH,str(script)],cwd=target,capture_output=True,text=True)
    (target/'stdout.txt').write_text(completed.stdout,encoding='utf-8')
    (target/'stderr.txt').write_text(completed.stderr,encoding='utf-8')
    success=case in ('absent','identical')
    assert (completed.returncode==0)==success,(case,completed.stdout,completed.stderr)
    records=list((target/'run/validation_tc2_gpu').glob('workflow_stage_*'))
    if success or case=='submission_failure':
        stage,=records
        for digest,name in rows:assert sha(target/name)==digest,(case,name)
        wrapper=target/'scripts/slurm/check_tc2_gpu_workflow.sh'
        assert (stage/'submission_lf.sh').read_bytes()==wrapper.read_bytes().replace(b'\r\n',b'\n')
        assert len((stage/'submission.sha256').read_text().splitlines())==2
        assert (stage/'metric_regression_job.txt').read_text().strip()=='43968'
        assert (stage/'algorithm_acceptance_job.txt').read_text().strip()=='43970'
        if success:
            assert (stage/'job_id.txt').read_text().strip()=='91235'
            assert pointer.read_text().strip()=='91235'
        else:
            assert not (stage/'job_id.txt').exists()
    else:
        assert not records,case
        for name in new:
            if name not in original:assert not (target/name).exists(),(case,name)
    for name,(content,mtime) in original.items():
        if success and name=='run/validation_tc2_gpu/last_check_workflow_job.txt':continue
        assert (target/name).read_bytes()==content and (target/name).stat().st_mtime_ns==mtime,(case,name)
    calls=target/'stub_calls.txt';count=len(calls.read_text().splitlines()) if calls.exists() else 0
    assert count==(1 if success or case=='submission_failure' else 0),(case,count)
    results.append({'case':case,'status':'passed','stub_submissions':count,'exit_code':completed.returncode})

result={'status':'passed','rendered_shell_commands_parsed':19,'payload_files':32,'payload_hashes_match_current_sources':True,
        'cases':results,'readonly_compatibility_configuration_preserved':True,'existing_bytes_and_mtimes_preserved':True,
        'actual_weight_file_not_available_locally':True,'weight_hash_gate_tested_with_stub':True,
        'actual_tc2_connections':0,'actual_slurm_submissions':0,'result_root':str(result_root)}
(HERE/'delivery_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','cases_passed':len(results),'payload_files':32,'shell_commands_parsed':19,
                  'actual_tc2_connections':0,'actual_slurm_submissions':0},indent=2))
