"""Finalize approved step-5 evidence after independent returned-artifact checks."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import unquote

REPO = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment")
ROOT = REPO / "group_XX_code"
AUDIT = ROOT / "run/validation_tc2_gpu/step5_20261019"
sys.path.insert(0, str(ROOT / "src"))
from tc2_gpu_protocol import sha

baseline = json.loads((AUDIT / "baseline.json").read_text())
accepted = json.loads((AUDIT / "accepted_job_44012/verification.json").read_text())
remote = json.loads((AUDIT / "accepted_job_44012/remote_setup_status.json").read_text())
assert accepted["status"] == "passed" and accepted["step_5_complete"] and remote["step_5_complete"]
changed = []
for item in baseline["files"]:
    path = REPO / item["path"]
    assert path.is_file(), item["path"]
    if sha(path) != item["sha256"]:
        changed.append(item["path"])
assert sorted(changed) == sorted(baseline["allowed_existing_changes"])
old = {item["path"] for item in baseline["files"]}
allowed = {"group_XX_code/" + name for name in baseline["allowed_new_sources"]}
new, audit_count = [], 0
for name in subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=REPO).decode('utf-8').split('\0'):
    if not name or name in old:
        continue
    if name.startswith('group_XX_code/run/validation_tc2_gpu/step5_20261019/'):
        audit_count += 1
        continue
    assert name in allowed, name
    new.append(name)
assert set(new) == allowed
index = hashlib.sha256(subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=REPO)).hexdigest().upper()
assert index == baseline['git_index_sha256']
subprocess.run(['git', 'diff', '--check'], cwd=REPO, capture_output=True, check=True)
assert (REPO / '.gitignore').read_bytes().startswith((AUDIT / 'before/.gitignore').read_bytes())
readme = (ROOT / 'README.md').read_bytes()
start = readme.index(b'## TC2 GPU workflow and step-5 acceptance\n')
end = readme.index(('## ' + ''.join(chr(x) for x in (0x6570, 0x636e, 0x96c6))).encode('utf-8'), start)
restored = readme[:start] + readme[end:]
before = (AUDIT / 'before/group_XX_code/README.md').read_bytes()
old_paragraph = next(p for p in before.splitlines() if p.startswith(b'Subsequent formal experiments use'))
new_paragraph = next(p for p in restored.splitlines() if p.startswith(b'Subsequent formal experiments use'))
assert all(byte < 128 for byte in old_paragraph + new_paragraph)
assert restored.replace(new_paragraph, old_paragraph, 1) == before
for name in baseline['allowed_new_sources']:
    text = (ROOT / name).read_text(encoding='utf-8')
    assert not re.search(r'[\u3400-\u9fff]', text), name
    if name.endswith('.py'):
        ast.parse(text, filename=name)
for file in [ROOT / 'README.md', ROOT / 'docs/TC2_GPU_WORKFLOW.md']:
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#'):
            assert (file.parent / unquote(target.split('#')[0])).exists(), target
helper_changes = json.loads((AUDIT / 'workflow_helper_changes.json').read_text())
helper = Path(baseline['external_helper'])
assert sha(helper) == helper_changes['after_sha256']
assert all(sha(ROOT / name) == value for name, value in remote['source_hashes'].items())
assert sha(ROOT / 'docs/TC2_GPU_WORKFLOW.md') != remote['payload_hashes']['docs/TC2_GPU_WORKFLOW.md']
assert not (ROOT / 'run/tc2_gpu').exists()
scope = {'status': 'passed', 'preexisting_files_checked': len(baseline['files']),
         'preexisting_files_unchanged': len(baseline['files']) - len(changed), 'changed_existing_files': sorted(changed),
         'new_source_files': sorted(new), 'new_audit_files_before_finalization': audit_count,
         'readme_existing_chinese_and_other_content_preserved': True,
         'readme_changes': 'Step-5 section and existing English overview status only.',
         'gitignore_append_only': True, 'external_helper_unchanged_since_offline_verification': True,
         'frozen_inputs_locks_historical_records_and_accepted_algorithms_unchanged': True,
         'accepted_scientific_source_hashes_unchanged': True, 'documentation_finalization_only_after_acceptance': True,
         'git_index_unchanged': True, 'git_diff_check_passed': True, 'document_links_valid': True,
         'formal_output_directory_absent': True}
status_path = AUDIT / 'setup_status.json'
previous_bytes = status_path.read_bytes()
status = json.loads(previous_bytes)
assert status['step_5_complete'] is False
backup = AUDIT / 'setup_status.before_remote_acceptance.json'
assert not backup.exists()
backup.write_bytes(previous_bytes)
status['local_scope'] = status['scope']
status.update(status='passed', step_5_complete=True, checked_at_utc=datetime.now(timezone.utc).isoformat(), scope=scope,
              remote_acceptance_received=True, gpu_workflow_tests_pending=0, accepted_workflow_execution=accepted,
              submitted_payload_hashes=remote['payload_hashes'],
              documentation_hashes={name: sha(ROOT / name) for name in ['README.md', 'docs/TC2_GPU_WORKFLOW.md']},
              completion_scope=accepted['completion_scope'],
              required_next_action='Await the user request for the step-6 design. Real-data extraction and pilots require separate design approval.')
status['connection_accounting'] = 'Zero TC2 connections/submissions by the assistant; the user submitted job 44012 and collected its records with the approved local helper.'
(AUDIT / 'final_scope_validation.json').write_text(json.dumps(scope, indent=2) + '\n', encoding='utf-8')
status_path.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
assert sha(helper) == status['external_helper']['sha256']
assert all(sha(ROOT / name) == value for name, value in status['source_hashes'].items())
print(json.dumps({'status': status['status'], 'step_5_complete': True, 'job_id': '44012', 'total_tests': 65,
                  'archive_files_verified': 421, 'source_fingerprints_verified': 31, 'scope': scope}, indent=2))
