from pathlib import Path
import ast
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import tarfile
from urllib.parse import unquote

repo = Path(r'C:\Users\mhjv_\PycharmProjects\6129_assignment')
root = repo / 'group_XX_code'
audit = root / 'run/validation_tc2_gpu/step4_20261019'
sha = lambda data: hashlib.sha256(data).hexdigest().upper()
base = json.loads((audit / 'baseline.json').read_text(encoding='utf-8'))
old = {entry['path']: entry for entry in base['files']}
changed = []
for name, entry in old.items():
    path = repo / name
    assert path.is_file(), f'Preexisting file removed: {name}'
    if sha(path.read_bytes()) != entry['sha256']:
        changed.append(name)
assert sorted(changed) == sorted(base['allowed_existing_changes']), changed
allowed_new = {'group_XX_code/' + name for name in base['allowed_new_sources']}
new_sources = []
audit_count = 0
visible = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=repo)
for name in visible.decode('utf-8').split('\0'):
    if not name:
        continue
    path = repo / name
    rel = path.relative_to(repo).as_posix()
    if rel.startswith('.git/') or rel in old:
        continue
    if rel.startswith('group_XX_code/run/validation_tc2_gpu/step4_20261019/'):
        audit_count += 1
        continue
    assert rel in allowed_new, f'Unexpected new file outside approved paths: {rel}'
    new_sources.append(rel)
assert set(new_sources) == allowed_new
entries = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=repo)
assert sha(entries) == base['git_staged_entries_sha256'], 'Git index changed'
subprocess.run(['git', 'diff', '--check'], cwd=repo, check=True, capture_output=True)
assert not (root / 'run/tc2_gpu').exists(), 'Unexpected formal output directory'
original = (audit / 'before/README.md').read_text(encoding='utf-8')
current = (root / 'README.md').read_text(encoding='utf-8')
cjk = lambda text: [line for line in text.splitlines() if re.search(r'[\u3400-\u9fff]', line)]
assert cjk(original) == cjk(current), 'Existing README Chinese changed'
for document in [root / 'README.md', root / 'docs/TC2_GPU_ALGORITHMS.md']:
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#'):
            assert (document.parent / unquote(target.split('#')[0])).exists(), target

sources = ['src/padim_adapter.py', 'src/patchcore_adapter.py', 'src/sampling.py', 'src/scoring.py',
           'src/anomaly_postprocess.py', 'tests/test_algorithms_tc2_gpu.py', 'scripts/slurm/check_tc2_gpu_algorithms.sh',
           'src/metric_core.py', 'src/evaluate.py', 'src/data.py', 'configs/tc2_gpu.json']
syntax = [name for name in sources if name.endswith('.py')] + ['tests/test_metrics_tc2_gpu.py']
for name in syntax:
    ast.parse((root / name).read_text(encoding='utf-8'), filename=name)
outputs = Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output')
packages = {}
for action, folder, bundle, manifest, expected_count in [
    ('CheckMetrics', 'tc2_gpu_setup_20261019_094832_7a78af8a', 'metrics-files.tar', 'metrics.sha256', 5),
    ('CheckAlgorithms', 'tc2_gpu_setup_20261019_094838_ae8ca7a9', 'algorithm-files.tar', 'algorithms.sha256', 11)]:
    directory = outputs / folder
    log = (directory / 'terminal.txt').read_text(encoding='utf-8')
    assert 'LOCAL VALIDATION ONLY' in log and 'no connection or submission' in log
    with tarfile.open(directory / bundle) as archive:
        members = {member.name.removeprefix('./'): member for member in archive.getmembers() if member.isfile()}
        checks = archive.extractfile(members[manifest]).read().decode('utf-8').splitlines()
        assert len(checks) == expected_count
        file_names = []
        for line in checks:
            digest, name = line.split(None, 1)
            name = name.strip().lstrip('*')
            data = archive.extractfile(members[name]).read()
            assert sha(data) == digest.upper() == sha((root / name).read_bytes()), name
            file_names.append(name)
        assert set(members) == {*file_names, manifest}
        if action == 'CheckAlgorithms':
            assert set(file_names) == set(sources)
    packages[action] = {'status': 'passed', 'files': expected_count, 'all_hashes_match_current_sources': True,
                        'terminal': str(directory / 'terminal.txt'), 'bundle_sha256': sha((directory / bundle).read_bytes()),
                        'actual_ssh_calls': 0, 'actual_slurm_submissions': 0}

reference = json.loads((audit / 'local_reference_checks.json').read_text())
transport = json.loads((audit / 'local_transport_validation.json').read_text())
delivery = json.loads((audit / 'delivery_validation.json').read_text())
assert reference['status'] == 'passed' and transport['status'] == 'PASS' and delivery['status'] == 'passed'
assert reference['python_syntax_files'] == len(syntax)
local_cpu = json.loads((audit / 'local_cpu_dependency_check/setup_status.json').read_text())
full_guard = json.loads((audit / 'local_full_guard_check/setup_status.json').read_text())
assert not local_cpu['step_4_complete'] and 'ModuleNotFoundError' in local_cpu['error']
assert not full_guard['step_4_complete'] and 'Linux SLURM' in full_guard['error']
scope = {'status': 'passed', 'preexisting_files_checked': len(old), 'preexisting_files_unchanged': len(old) - len(changed),
         'changed_existing_files': sorted(changed), 'new_source_files': sorted(new_sources),
         'new_audit_files': audit_count, 'git_index_unchanged': True, 'existing_readme_chinese_unchanged': True,
         'frozen_inputs_environment_locks_and_historical_records_unchanged': True,
         'formal_output_directory_absent': True, 'git_diff_check_passed': True, 'document_links_valid': True}
(audit / 'scope_validation.json').write_text(json.dumps(scope, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
status = {'status': 'local_implementation_verified_awaiting_tc2_metric_regression', 'step_4_complete': False,
          'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'approved_design': 'docs/TC2_GPU_ALGORITHMS.md',
          'user_confirmation': base['authorization'], 'scope': scope,
          'local_reference_checks': reference, 'local_transport_checks': transport, 'local_delivery_checks': delivery,
          'packaging_only_checks': packages,
          'local_algorithm_execution': {'status': 'not_run_missing_pytorch', 'error': local_cpu['error'],
                                        'dependencies_installed': False, 'cpu_tests_passed': False, 'gpu_tests_run': False},
          'local_full_guard_check': {'status': 'expected_refusal', 'error': full_guard['error']},
          'planned_remote_tests': {'cpu': 19, 'gpu': 2},
          'source_hashes': {name: sha((root / name).read_bytes()) for name in sources},
          'documentation_hashes': {name: sha((root / name).read_bytes()) for name in ['README.md', 'docs/TC2_GPU_ALGORITHMS.md']},
          'external_helper': {'path': base['external_helper'], 'sha256': sha(Path(base['external_helper']).read_bytes())},
          'required_next_action': 'Run CheckMetrics on TC2 and return terminal.txt; verify it before CheckAlgorithms.',
          'remote_acceptance_received': False, 'actual_ssh_calls': 0, 'actual_slurm_submissions': 0}
(audit / 'setup_status.json').write_text(json.dumps(status, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
print(json.dumps({'status': status['status'], 'step_4_complete': False, 'scope': scope,
                  'packaging': {key: value['status'] for key, value in packages.items()}}, indent=2))
