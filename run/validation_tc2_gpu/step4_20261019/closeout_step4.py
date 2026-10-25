from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import subprocess
from urllib.parse import unquote

root=Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code')
repo=root.parent
audit=root/'run/validation_tc2_gpu/step4_20261019'
record=audit/'final_closeout'
record.mkdir()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest().upper()
main_path=audit/'setup_status.json'
main=json.loads(main_path.read_text(encoding='utf-8'))
accepted=json.loads((audit/'algorithm_acceptance_job_43970/verification.json').read_text(encoding='utf-8'))
assert accepted['status']=='passed' and accepted['step_4_complete'] is True
assert all(sha(root/name)==digest for name,digest in accepted['source_hashes'].items())
for relative in ['README.md','docs/TC2_GPU_ALGORITHMS.md']:
    destination=record/'before'/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/relative,destination)
shutil.copyfile(main_path,record/'setup_status.before.json')

readme=root/'README.md'
data=readme.read_bytes()
old='Models, caches, and job execution will be corrected and validated under the approved designs of their respective later steps; independent acceptance of metric corrections was completed in step 3.'
new='Cache and runner/job integration remain for the approved later steps; independent acceptance of metric corrections and algorithm corrections was completed in steps 3 and 4.'
assert data.count(old.encode())==1
data=data.replace(old.encode(),new.encode())
old='Implementation is awaiting remote acceptance. The new [algorithm tests](tests/test_algorithms_tc2_gpu.py) contain 19 CPU tests and two GPU tests, including independent references and actual ResNet18 feature shapes generated synthetically. First pass `CheckMetrics`, then use the local helper\'s `CheckAlgorithms` action to submit the [GPU acceptance job](scripts/slurm/check_tc2_gpu_algorithms.sh). Only full-mode `step_4_complete=true` completes this step. No real-data fitting, cache generation, or formal experiment has been run. Records are kept under `run/validation_tc2_gpu/step4_20261019/` and job-specific directories.'
new='Step 4 completed on 2026-10-19. Current-naming metric regression job 43968 passed all 24 tests. Algorithm acceptance job 43970 on TC2N01 (NVIDIA A40) finished as COMPLETED / 0:0: all 19 CPU tests and two GPU tests passed, with full-mode `step_4_complete=true`. The [algorithm tests](tests/test_algorithms_tc2_gpu.py) cover independent references and actual ResNet18 feature shapes generated synthetically. All eleven source fingerprints and 163 returned files were verified. See the [step-4 acceptance record](run/validation_tc2_gpu/step4_20261019/setup_status.json) and [GPU acceptance entry point](scripts/slurm/check_tc2_gpu_algorithms.sh). No real-data fitting, cache generation, or formal experiment has been run.'
assert data.count(old.encode())==1
data=data.replace(old.encode(),new.encode())
readme.write_bytes(data)

doc=root/'docs/TC2_GPU_ALGORITHMS.md'
text=doc.read_text(encoding='utf-8')
replacements={
    'Current implementation and acceptance status will be recorded after actual checks.':'Final status and accepted source fingerprints are recorded in the acceptance sections below.',
    'Run the first command in the local Windows terminal and return its terminal.txt path for verification:':'The following commands document the accepted verification sequence. Both checks have now passed for the source fingerprints recorded below; use them only when a new verification is needed:',
    'The step remains incomplete until the current-naming metric regression and the full CPU/GPU algorithm job pass on TC2.':'Completion requires both the current-naming metric regression and the full CPU/GPU algorithm job to pass on TC2; the final acceptance below satisfies both conditions.',
    'Retry CheckMetrics using the command above; the previous rejected attempt provides no metric acceptance, and step_4_complete remains false.':'At this point in the recorded sequence, the next action was to retry CheckMetrics; the rejected attempt provided no metric acceptance. The successful retry and algorithm acceptance are recorded below.',
    'The prerequisite for CheckAlgorithms is satisfied. Step 4 remains incomplete pending its full 19-CPU-test and 2-GPU-test acceptance.':'This established the prerequisite for CheckAlgorithms. Full algorithm acceptance is recorded in the next section.'
}
for old,new in replacements.items():
    assert text.count(old)==1,old
    text=text.replace(old,new)
marker='## Approved implementation\n'
assert text.count(marker)==1
text=text.replace(marker,'## Current acceptance status\n\nStep 4 is complete. Current-naming metric regression job 43968 and full algorithm acceptance job 43970 both passed. The final [acceptance record](../run/validation_tc2_gpu/step4_20261019/setup_status.json) binds this result to the exact verified source fingerprints. Validation used synthetic features; runner/cache integration and real-data experiments remain separate later steps.\n\n'+marker)
text+='''
## Full algorithm acceptance completed

CheckAlgorithms job 43970 on TC2N01 completed as COMPLETED / 0:0 in fifteen seconds using the allocated NVIDIA A40. Full-mode step_4_complete=true was returned. All 19 CPU tests and both GPU tests passed with zero failures, errors, or skips. CPU/GPU numerical comparisons met the approved tolerances. The GPU checks covered all frozen PaDiM layer/dimension variants and both PatchCore sampling strategies at actual ResNet18 feature shapes generated synthetically. Arithmetic used FP32, with TF32 and autocast disabled as recorded by the acceptance runner.

Independent verification checked the output archive SHA256, all 163 extracted files, all eleven accepted source fingerprints against the current checkout, both submission fingerprints, unchanged resource directives, and the current metric and algorithm job pointers. All 150 files from the earlier metric archive were preserved byte-for-byte. Metric regression 43968, the eight frozen manifests, actual environment locks, and the workflow naming map were verified. Evidence is retained under run/validation_tc2_gpu/step4_20261019/algorithm_acceptance_job_43970/.

Step 4 is accepted for the recorded synthetic algorithm scope. No real-data fitting, feature cache generation, formal experiment, or report writing occurred. The legacy runner and FP16 cache path remain outside this acceptance. Step 5 requires its own design discussion and explicit execution confirmation before runner/cache integration changes.
'''
doc.write_text(text,encoding='utf-8',newline='\n')

baseline=json.loads((audit/'baseline.json').read_text(encoding='utf-8'))
changed=[]
for entry in baseline['files']:
    path=repo/entry['path']
    assert path.is_file(),entry['path']
    if sha(path)!=entry['sha256']:changed.append(entry['path'])
assert set(changed)==set(baseline['allowed_existing_changes']),changed
allowed_new={'group_XX_code/'+name for name in baseline['allowed_new_sources']}
visible=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=repo).decode('utf-8').split('\0')
old_names={entry['path'] for entry in baseline['files']}
new_sources=[]
for name in visible:
    if not name or name in old_names or name.startswith('group_XX_code/run/validation_tc2_gpu/step4_20261019/'):continue
    assert name in allowed_new,name
    new_sources.append(name)
assert set(new_sources)==allowed_new
index=hashlib.sha256(subprocess.check_output(['git','ls-files','--stage','-z'],cwd=repo)).hexdigest().upper()
assert index==baseline['git_staged_entries_sha256']
assert sha(Path(main['external_helper']['path']))==main['external_helper']['sha256']
assert all(sha(root/name)==digest for name,digest in accepted['source_hashes'].items())
original=(audit/'before/README.md').read_text(encoding='utf-8')
current=readme.read_text(encoding='utf-8')
cjk=lambda value:[line for line in value.splitlines() if re.search(r'[\u3400-\u9fff]',line)]
assert cjk(original)==cjk(current)
for document in [readme,doc]:
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)',document.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#'):
            assert (document.parent/unquote(target.split('#')[0])).exists(),target
assert not (root/'run/tc2_gpu').exists()
subprocess.run(['git','diff','--check'],cwd=repo,capture_output=True,check=True)
scope={'status':'passed','preexisting_files_checked':len(baseline['files']),
       'preexisting_files_unchanged':len(baseline['files'])-len(changed),
       'changed_existing_files':sorted(changed),'new_source_files':sorted(new_sources),
       'accepted_algorithm_source_hashes_unchanged':True,'frozen_inputs_and_historical_records_unchanged':True,
       'external_helper_unchanged_since_verified_supplement':True,'existing_readme_chinese_unchanged':True,
       'git_index_unchanged':True,'git_diff_check_passed':True,'document_links_valid':True,
       'formal_output_directory_absent':True}
(record/'scope_validation.json').write_text(json.dumps(scope,indent=2)+'\n',encoding='utf-8')
main.update(status='passed',step_4_complete=True,checked_at_utc=datetime.now(timezone.utc).isoformat(),
            completion_scope='Synthetic CPU/GPU algorithm corrections under the approved step-4 design and LF submission supplement.',
            remote_acceptance_received=True,remote_algorithm_acceptance_received=True,
            accepted_algorithm_execution=accepted,final_scope=scope,
            required_next_action='Step 4 is complete. Await the user request to start step 5 before its design discussion or execution.')
main['documentation_hashes']={name:sha(root/name) for name in ['README.md','docs/TC2_GPU_ALGORITHMS.md']}
main['submission_lf_supplement'].update(status='remote_metric_and_algorithm_submissions_verified',algorithm_job_id='43970')
main_path.write_text(json.dumps(main,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
(record/'final_fingerprints.json').write_text(json.dumps({'source_hashes':accepted['source_hashes'],
    'documentation_hashes':main['documentation_hashes'],'external_helper':main['external_helper'],
    'setup_status_sha256':sha(main_path)},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','step_4_complete':True,'metric_job':'43968','algorithm_job':'43970',
                  'cpu_tests':19,'gpu_tests':2,'scope':scope,'acceptance_record':str(main_path)},indent=2))
