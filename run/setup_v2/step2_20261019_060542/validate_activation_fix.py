"""Offline activation regression and guarded two-file publication tests."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASH = r'C:\Program Files\Git\bin\bash.exe'
ORIGINAL = Path(r'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_setup_v2_20261019_065131_7cb9d616\payload')


def run(script, directory, name):
    path = directory / name
    path.write_text(script, encoding='utf-8', newline='\n')
    environment = dict(os.environ)
    environment.pop('QT_XCB_GL_INTEGRATION', None)
    return subprocess.run([BASH, str(path)], cwd=directory, env=environment,
                          capture_output=True, text=True, encoding='utf-8', errors='replace')


def fixture(block, mode):
    return r'''set -euo pipefail
unset QT_XCB_GL_INTEGRATION
environment_prefix=/synthetic/ca6129
conda() {
    if [[ "$1 $2" == 'shell.bash hook' ]]; then
        if [[ '__MODE__' == hook_failure ]]; then return 71; fi
        printf '%s\n' 'optional_qt_value="$QT_XCB_GL_INTEGRATION"'
    elif [[ "$1" == activate ]]; then
        if [[ '__MODE__' == activate_failure ]]; then return 72; fi
        optional_activate_value="$QT_XCB_GL_INTEGRATION"
    else
        return 80
    fi
}
'''.replace('__MODE__', mode) + block + r'''
[[ "$-" == *u* && "$-" == *e* ]] || exit 97
set -o | grep -Eq '^pipefail[[:space:]]+on$'
if (printf '%s' "$UNDEFINED_AFTER_ACTIVATION" >/dev/null) 2>/dev/null; then exit 98; fi
echo POST_ACTIVATION_REACHED
'''


def main():
    directory = HERE / ('activation_validation_' + uuid.uuid4().hex[:8])
    assert directory.resolve().is_relative_to(HERE.resolve())
    directory.mkdir()
    tested = []
    for name in ['prepare_tc2_v2.sh', 'check_setup_v2.sh']:
        text = (ROOT / 'scripts/slurm' / name).read_text(encoding='utf-8')
        start = text.index('set +u\n')
        end = text.index('unset conda_hook', start) + len('unset conda_hook')
        fixed = text[start:end]
        old = 'eval "$(conda shell.bash hook)"\nconda activate "$environment_prefix"'
        original = run(fixture(old, 'success'), directory, 'old_' + name)
        assert original.returncode != 0 and 'QT_XCB_GL_INTEGRATION' in original.stderr
        for mode, expected in [('success', 0), ('hook_failure', 71), ('activate_failure', 72)]:
            result = run(fixture(fixed, mode), directory, mode + '_' + name)
            assert result.returncode == expected, (name, mode, result.returncode, result.stderr)
            assert ('POST_ACTIVATION_REACHED' in result.stdout) == (mode == 'success')
        tested.append(name + ': reproduces old failure; fixed activation restores strict flags and propagates failures')
    transport = json.loads((HERE / 'local_transport_validation.json').read_text(encoding='utf-8'))
    rendering_root = Path(transport['validation_root'])
    commands = list(rendering_root.rglob('command_*.sh'))
    assert len(commands) == transport['rendered_shell_commands']
    for command in commands:
        result = subprocess.run([BASH, '-n', str(command)], capture_output=True)
        assert result.returncode == 0, str(command)
    actual = [path for path in commands if 'Two activation entry points updated' in path.read_text(encoding='utf-8')]
    assert len(actual) == 1
    text = actual[0].read_text(encoding='utf-8')
    start = re.search(r'(?m)^archive="\$root/_downloads/activation-fix-[^\n]+$', text).start()
    end = text.index('job_id=$(sbatch', start)
    publication = text[start:end]
    archive_name = re.search(r'activation-fix-[^/"\n]+\.tar', publication).group()
    payload_root = actual[0].parent / 'activation_payload'
    source_archive = actual[0].parent / 'activation-fix.tar'
    rows = [line.split() for line in (payload_root / 'activation.sha256').read_text().splitlines()]
    assert len(rows) == 2
    for scenario in ['original', 'conflict', 'partly_applied']:
        test_root = directory / scenario
        for child in ['_downloads', 'tmp', 'run/setup_v2', 'scripts/slurm']:
            (test_root / child).mkdir(parents=True, exist_ok=True)
        (test_root / '_downloads' / archive_name).write_bytes(source_archive.read_bytes())
        before = {}
        for index, (old_hash, new_hash, relative) in enumerate(rows):
            original = (ORIGINAL / relative).read_bytes()
            assert hashlib.sha256(original).hexdigest() == old_hash
            data = original
            if scenario == 'conflict' and index == 1:
                data = b'Unrecognized existing user script; preserve it.\n'
            elif scenario == 'partly_applied' and index == 0:
                data = (payload_root / relative).read_bytes()
            (test_root / relative).write_bytes(data)
            before[relative] = data
        script = 'set -euo pipefail\nroot="$(pwd -P)"\n' + publication
        result = run(script, test_root, 'publish_fixture.sh')
        if scenario == 'conflict':
            assert result.returncode != 0
            for relative, data in before.items():
                assert (test_root / relative).read_bytes() == data
            assert not list((test_root / 'run/setup_v2').iterdir())
        else:
            assert result.returncode == 0, (scenario, result.stderr)
            backup, = (test_root / 'run/setup_v2').iterdir()
            for _, new_hash, relative in rows:
                assert hashlib.sha256((test_root / relative).read_bytes()).hexdigest() == new_hash
                assert (backup / relative).read_bytes() == before[relative]
        tested.append('Guarded publication: ' + scenario)
    result = dict(status='PASS', validation_root=str(directory), checks=tested,
                  rendered_shell_commands_parsed=len(commands), actual_ssh_calls=0,
                  actual_conda_calls=0, actual_slurm_submissions=0)
    (HERE / 'local_activation_fix_validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
