"""Offline Bash/publication checks using the actual rendered PowerShell commands."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tarfile
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASH = r'C:\Program Files\Git\bin\bash.exe'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    transport = json.loads((HERE/'local_transport_validation.json').read_text(encoding='utf-8-sig'))
    commands = list(Path(transport['validation_root']).rglob('command_*.sh'))
    assert len(commands) == 15
    for command in commands + [ROOT/'scripts/slurm/check_metrics_v2.sh']:
        checked = subprocess.run([BASH,'-n',str(command)],capture_output=True)
        assert checked.returncode == 0,(str(command),checked.stderr)
    wrapper=(ROOT/'scripts/slurm/check_metrics_v2.sh').read_text(encoding='utf-8')
    assert '#SBATCH --cpus-per-task=2' in wrapper and '#SBATCH --mem=4G' in wrapper
    assert '#SBATCH --time=00:15:00' in wrapper and '--gres' not in wrapper and '--gpus' not in wrapper
    selected=[p for p in commands if 'Five verified metric test files staged' in p.read_text(encoding='utf-8')]
    command,=selected
    text=command.read_text(encoding='utf-8')
    assert 'step_2_complete' in text and 'squeue --noheader --user=huajie001' in text
    assert 'sha256sum --check -' in text
    start=re.search(r'(?m)^archive="\$root/_downloads/metrics-files-[^\n]+$',text).start()
    end=text.index('job_id=$(sbatch',start)
    publication=text[start:end]
    submission=text[end:text.index('\n',end)]
    assert '--partition=MGPU-TC2' in submission and '--qos=normal' in submission
    assert '--gres' not in submission and '--gpus' not in submission
    archive_name=re.search(r'metrics-files-[^/"\n]+\.tar',publication).group()
    bundle=command.parent/'metrics-files.tar'
    rows=[line.split() for line in (command.parent/'metrics_payload/metrics.sha256').read_text().splitlines()]
    names={r[1] for r in rows}
    assert names=={'src/metric_core.py','src/evaluate.py','src/data.py','tests/test_metrics_v2.py','scripts/slurm/check_metrics_v2.sh'}
    baseline=json.loads((HERE/'baseline.json').read_text(encoding='utf-8'))
    data_hash=next(r['sha256'] for r in baseline['files'] if r['path']=='group_XX_code/src/data.py')
    assert next(h for h,p in rows if p=='src/data.py').upper()==data_hash
    result_root=HERE/('delivery_validation_'+uuid.uuid4().hex[:8])
    assert result_root.resolve().is_relative_to(HERE)
    result_root.mkdir()
    for scenario in ['absent','identical','conflict','bad_bundle']:
        target=result_root/scenario
        for relative in ['_downloads','tmp','run/validation_v2','scripts/slurm','src','tests']:
            (target/relative).mkdir(parents=True,exist_ok=True)
        (target/'_downloads'/archive_name).write_bytes(bundle.read_bytes())
        before={}
        if scenario in ['identical','conflict']:
            for index,(h,relative) in enumerate(rows):
                data=(command.parent/'metrics_payload'/relative).read_bytes()
                if scenario=='conflict' and index==len(rows)-1:data=b'Unknown existing source. Preserve it.\n'
                file=target/relative
                file.write_bytes(data)
                before[relative]=(data,file.stat().st_mtime_ns)
        if scenario=='bad_bundle':
            with (target/'_downloads'/archive_name).open('ab') as stream:stream.write(b'tampered')
        script=target/'publication.sh'
        script.write_text('set -euo pipefail\nroot="$(pwd -P)"\n'+publication,encoding='utf-8',newline='\n')
        completed=subprocess.run([BASH,str(script)],cwd=target,capture_output=True,text=True)
        records=list((target/'run/validation_v2').iterdir())
        if scenario in ['conflict','bad_bundle']:
            assert completed.returncode != 0 and not records,(scenario,completed.stdout,completed.stderr)
            if scenario=='bad_bundle':assert not any((target/relative).exists() for _,relative in rows)
        else:
            assert completed.returncode==0,(scenario,completed.stdout,completed.stderr)
            record,=records
            assert (record/'metrics.sha256').read_bytes()==(command.parent/'metrics_payload/metrics.sha256').read_bytes()
            for h,relative in rows:assert digest(target/relative)==h
        for relative,(data,mtime) in before.items():
            assert (target/relative).read_bytes()==data and (target/relative).stat().st_mtime_ns==mtime
    result={'status':'PASS','rendered_commands_parsed':15,'cpu_wrapper_parsed':True,
            'only_five_approved_files':True,'unchanged_data_dependency_hash_verified':True,
            'cpu_request_verified':{'cpus':2,'memory_gib':4,'time_limit':'00:15:00','gpus':0},
            'publication_cases':['absent','identical','conflict','bad_bundle'],
            'result_directory':str(result_root),'actual_ssh_calls':0,'actual_slurm_submissions':0}
    (HERE/'local_delivery_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
