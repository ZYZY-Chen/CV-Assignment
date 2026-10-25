"""Exercise the actual rendered LF submission blocks with a local sbatch stub."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASH = r'C:\Program Files\Git\bin\bash.exe'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
transport = json.loads((HERE/'local_transport_validation.json').read_text(encoding='utf-8-sig'))
commands = list(Path(transport['validation_root']).rglob('command_*.sh'))
assert len(commands) == 17
for path in commands:
    parsed = subprocess.run([BASH,'-n',str(path)],capture_output=True,text=True)
    assert parsed.returncode == 0, (str(path),parsed.stderr)

specs = {
    'CheckMetrics':('Five verified metric test files staged','check_tc2_gpu_metrics.sh','last_check_metrics_job.txt',
                    ['--nodes=1','--ntasks=1','--cpus-per-task=2','--mem=4G','--time=00:15:00','--job-name=ca6129_metrics_tc2_gpu']),
    'CheckAlgorithms':('Eleven verified algorithm files staged','check_tc2_gpu_algorithms.sh','last_check_algorithms_job.txt',
                       ['--nodes=1','--ntasks=1','--gres=gpu:1','--cpus-per-task=2','--mem=8G','--time=00:15:00','--job-name=ca6129_algorithms_tc2_gpu'])
}
cases = ['lf','crlf','existing_copy','existing_hashes','bare_cr','invalid_syntax','sbatch_failure','invalid_job_id']
results=[]
stub=r'''set -euo pipefail
root="$(pwd -P)"
stage_record="$root/run/validation_tc2_gpu/fixture_stage"
sbatch() {
    printf 'stub invocation\n' >> "$root/stub_calls.txt"
    printf '%s\0' "$@" > "$root/stub_arguments.bin"
    local script="${!#}"
    [[ "$script" == "$stage_record/submission_lf.sh" && -s "$script" ]] || return 20
    [[ "$(head -n 1 -- "$script")" == '#!/bin/bash' ]] || return 21
    if LC_ALL=C grep -q $'\r' "$script"; then return 22; fi
    bash -n "$script" || return 23
    if [[ "${STUB_FAIL:-0}" == 1 ]]; then echo 'Simulated sbatch rejection.' >&2; return 17; fi
    printf '%s\n' "${STUB_JOB_ID:-91234;offline}"
}
'''
for action,(marker,wrapper,pointer,directives) in specs.items():
    command, = [path for path in commands if marker in path.read_text(encoding='utf-8')]
    rendered=command.read_text(encoding='utf-8')
    start=rendered.index('# Preserve the verified source; submit a separately recorded LF-only copy.')
    final='printf \'%s\\n\' "$job_id" > "$stage_record/job_id.txt"'
    end=rendered.index(final,start)+len(final)
    block=rendered[start:end]
    assert 'scripts/slurm/'+wrapper in block and 'sbatch ' in block
    assert not any(token in block for token in ('ssh ','scp ','squeue ','sleep '))
    original=(ROOT/'scripts/slurm'/wrapper).read_bytes()
    lf=original.replace(b'\r\n',b'\n')
    expected_directives=[line[len('#SBATCH '):] for line in lf.decode('utf-8').splitlines() if line.startswith('#SBATCH ')]
    assert expected_directives == directives, (action,expected_directives)
    for case in cases:
        target=HERE/'submission_fixtures'/action/case
        stage=target/'run/validation_tc2_gpu/fixture_stage'
        stage.mkdir(parents=True)
        source=target/'scripts/slurm'/wrapper
        source.parent.mkdir(parents=True)
        data=lf.replace(b'\n',b'\r\n') if case=='crlf' else lf
        if case=='bare_cr':
            data+=b'echo unsupported\rvalue\n'
        if case=='invalid_syntax':
            data+=b'if\n'
        source.write_bytes(data)
        pointer_path=target/'run/validation_tc2_gpu'/pointer
        pointer_path.write_bytes(b'80000\n')
        if case=='existing_copy':
            (stage/'submission_lf.sh').write_bytes(b'Existing submission copy: preserve.\n')
        if case=='existing_hashes':
            (stage/'submission.sha256').write_bytes(b'Existing fingerprints: preserve.\n')
        protected=[source,pointer_path]+list(stage.glob('*'))
        before={str(path):(path.read_bytes(),path.stat().st_mtime_ns) for path in protected}
        config=''
        if case=='sbatch_failure': config='STUB_FAIL=1\n'
        if case=='invalid_job_id': config="STUB_JOB_ID='invalid-job'\n"
        script=target/'exercise.sh'
        script.write_text(stub+config+block+'\n',encoding='utf-8',newline='\n')
        completed=subprocess.run([BASH,str(script)],cwd=target,capture_output=True,text=True)
        (target/'stdout.txt').write_text(completed.stdout,encoding='utf-8')
        (target/'stderr.txt').write_text(completed.stderr,encoding='utf-8')
        success=case in ('lf','crlf')
        assert (completed.returncode==0)==success,(action,case,completed.stdout,completed.stderr)
        for path,(content,mtime) in before.items():
            if success and Path(path)==pointer_path: continue
            assert Path(path).read_bytes()==content,(action,case,path,'bytes changed')
            assert Path(path).stat().st_mtime_ns==mtime,(action,case,path,'mtime changed')
        calls=target/'stub_calls.txt'
        count=len(calls.read_text().splitlines()) if calls.exists() else 0
        expected_calls=1 if case in ('lf','crlf','sbatch_failure','invalid_job_id') else 0
        assert count==expected_calls,(action,case,count)
        if success:
            submitted=stage/'submission_lf.sh'
            assert submitted.read_bytes()==lf and b'\r' not in submitted.read_bytes()
            rows=(stage/'submission.sha256').read_text(encoding='utf-8').splitlines()
            assert len(rows)==2
            for line,path in zip(rows,[source,submitted]):
                digest,recorded_path=line.split(None,1)
                assert digest==sha(path),(action,case,path)
                assert recorded_path.endswith('/scripts/slurm/'+wrapper) or recorded_path.endswith('/fixture_stage/submission_lf.sh')
            assert (stage/'job_id.txt').read_bytes()==b'91234\n'
            assert pointer_path.read_bytes()==b'91234\n'
            argv=[value.decode('utf-8') for value in (target/'stub_arguments.bin').read_bytes().split(b'\0') if value]
            assert len(argv)==6 and argv[:3]==['--parsable','--partition=MGPU-TC2','--qos=normal'],argv
            assert argv[3].endswith('/run/validation_tc2_gpu/slurm-%j.out') and argv[3].startswith('--output=')
            assert argv[4].endswith('/run/validation_tc2_gpu/slurm-%j.err') and argv[4].startswith('--error=')
            assert argv[5].endswith('/fixture_stage/submission_lf.sh')
            actual_directives=[line[len('#SBATCH '):] for line in submitted.read_text(encoding='utf-8').splitlines() if line.startswith('#SBATCH ')]
            assert actual_directives==directives
            normalized=subprocess.run([BASH,'-c','sha256sum --check "$1"','offline',str(stage/'submission.sha256')],cwd=target,capture_output=True,text=True)
            assert normalized.returncode==0,(action,case,normalized.stderr)
        else:
            assert not (stage/'job_id.txt').exists(),(action,case)
        results.append({'action':action,'case':case,'status':'passed','stub_calls':count,'exit_code':completed.returncode})

result={'status':'passed','checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'rendered_commands_syntax_checked':len(commands),'submission_cases':results,
        'source_bytes_and_mtimes_preserved':True,'line_endings_only_conversion':True,
        'source_and_copy_fingerprints_verified':True,'resources_and_options_unchanged':True,
        'conflicts_refused_before_stub_submission':True,'failed_submission_preserves_job_pointers':True,
        'actual_ssh_calls':0,'actual_slurm_submissions':0}
(HERE/'lf_submission_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':result['status'],'submission_cases_passed':len(results),
                  'rendered_commands_syntax_checked':len(commands),'actual_ssh_calls':0,'actual_slurm_submissions':0},indent=2))
