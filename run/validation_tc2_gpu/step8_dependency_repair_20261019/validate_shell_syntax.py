"""Parse new rendered shell commands only; never execute their contents."""
from pathlib import Path
import json
import subprocess

audit=Path(__file__).resolve().parent
report=json.loads((audit/'dependency_transport_validation.json').read_text(encoding='utf-8-sig'))
paths=sorted(Path(report['validation_root']).rglob('command_*.sh'))
assert paths,'No rendered commands found'
for path in paths:
    subprocess.run([r'C:\Program Files\Git\bin\bash.exe','-n',str(path).replace('\\','/')],check=True)
receipt={'status':'passed','scripts_checked':len(paths),'syntax_only':True,'actual_script_executions':0,
         'actual_tc2_connections':0,'actual_slurm_submissions':0}
(audit/'shell_syntax_validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
