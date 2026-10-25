"""Offline source-recovery safety checks; no real dataset, SSH, SLURM or GPU."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_preparation import archive, digest, rejected, Response
import prepare_tc2_inputs_v2 as prep

BASH = r'C:\Program Files\Git\bin\bash.exe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    checks = []
    setup, _, manifests = prep.audit.read_contract(ROOT / 'configs/tc2_setup.json')
    mirror = prep.mirror_plan(setup)
    assert len(prep.audit.required_files(manifests)) == 4669
    assert set(setup['preparation']['archive_sources']) == {'mvtec_loco/juice_bottle', 'mvtec_loco/screw_bag'}
    assert 'torch' not in sys.modules
    for field, value in [('approved', False), ('revision', 'main'), ('sha256', '0' * 64),
                         ('url', 'https://unapproved.example/file'), ('categories', ['bottle'])]:
        changed = copy.deepcopy(setup)
        changed['preparation']['mvtec_ad_mirror'][field] = value
        rejected(lambda: prep.mirror_plan(changed))
    checks.append('Mirror version, URL, archive hash, size and categories pinned; frozen 4669 paths unchanged')

    with tempfile.TemporaryDirectory(prefix='source_validation_', dir=HERE) as name:
        base = Path(name)
        tarpath = base / 'full.tar.xz'
        valid = [('readme.txt', b'root metadata', 'file'),
                 ('bottle/train/good/a.png', b'bottle', 'file'),
                 ('cable/train/good/ignored.png', b'not selected', 'file'),
                 ('wood/test/defect/b.png', b'wood', 'file')]
        expected = {'bottle/train/good/a.png': digest(b'bottle'),
                    'wood/test/defect/b.png': digest(b'wood')}
        archive(tarpath, valid)
        destination = base / 'selected'
        prep.restore_mirror_archive(tarpath, ['bottle', 'wood'], destination, expected, base)
        assert {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()} == set(expected)
        prep.restore_mirror_archive(tarpath, ['bottle', 'wood'], destination, expected, base)
        checks.append('Full archive restores only selected categories; root metadata and other categories excluded; reuse works')

        bad_cases = [valid + [('carpet/../../escape', b'x', 'file')],
                     valid + [('carpet/link', b'', 'symlink')],
                     valid + [('carpet/device', b'', 'device')],
                     valid + [('bottle/train/good/a.png', b'duplicate', 'file')],
                     valid[:-1],
                     valid[:-1] + [('wood/test/defect/b.png', b'wrong', 'file')]]
        for index, entries in enumerate(bad_cases):
            archive(tarpath, entries)
            fresh = base / ('refused_' + str(index))
            rejected(lambda: prep.restore_mirror_archive(tarpath, ['bottle', 'wood'], fresh, expected, base))
            assert not fresh.exists()
        archive(tarpath, valid)
        (destination / 'wood/test/defect/b.png').write_bytes(b'existing conflict')
        (destination / 'bottle/train/good/a.png').unlink()
        rejected(lambda: prep.restore_mirror_archive(tarpath, ['bottle', 'wood'], destination, expected, base))
        assert not (destination / 'bottle/train/good/a.png').exists()
        assert (destination / 'wood/test/defect/b.png').read_bytes() == b'existing conflict'
        checks.append('Late unsafe/duplicate/missing/corrupt members and existing conflicts stop before extraction writes')

        target = base / 'pinned.tar.xz'
        pin = {'size_bytes': 4, 'sha256': digest(b'good')}
        with patch.object(prep, 'urlopen', return_value=Response(b'evil')):
            rejected(lambda: prep.download(mirror['url'], target, validate=lambda p: prep.verify_mirror(p, pin)))
        assert not target.exists() and target.with_name(target.name + '.part').read_bytes() == b'evil'
        checks.append('Mirror hash failure retains partial file and never publishes it')

        local = base / 'local_check/transfer'
        calls = []
        def fake_download(url, target, validate=None):
            calls.append((url, target.name))
            target.write_bytes(b'synthetic package')
            return dict(source=url, path=str(target), sha256=digest(b'synthetic package'))
        with patch.object(prep, 'download', side_effect=fake_download):
            result = prep.download_transfer(setup, local)
        assert result['ready'] and not result['step_2_complete'] and not result['extracted']
        assert [name for _, name in calls] == ['mvtec_anomaly_detection.tar.xz', 'juice_bottle.tar.xz', 'screw_bag.tar.xz', 'resnet18-f37072fd.pth']
        assert not (local / 'mvtec_ad').exists() and 'torch' not in sys.modules
        rejected(lambda: prep.download_transfer(setup, base / 'wrong_directory_name'))
        checks.append('Local fallback plans only four fixed packages, writes metadata, never extracts or imports Torch')

    transport = json.loads((HERE / 'local_transport_validation.json').read_text(encoding='utf-8-sig'))
    rendering_root = Path(transport['validation_root'])
    commands = list(rendering_root.rglob('command_*.sh'))
    assert len(commands) == 13
    for command in commands:
        parsed = subprocess.run([BASH, '-n', str(command)], capture_output=True)
        assert parsed.returncode == 0, (command, parsed.stderr)
    updates = [p for p in commands if 'Approved AD mirror and original official LOCO sources deployed' in p.read_text()]
    command, = updates
    body = command.read_text(encoding='utf-8')
    assert 'last_prepare_inputs_job.txt)" == 43944' in body
    assert 'squeue --noheader --user=huajie001' in body
    start = re.search(r'(?m)^archive="\$root/_downloads/input-sources-[^\n]+$', body).start()
    end = body.index('job_id=$(sbatch', start)
    publication = body[start:end]
    archive_name = re.search(r'input-sources-[^/"\n]+\.tar', publication).group()
    payload = command.parent / 'sources_payload'
    rows = [line.split() for line in (payload / 'sources.sha256').read_text().splitlines()]
    assert {row[2] for row in rows} == {'configs/tc2_setup.json', 'scripts/prepare_tc2_inputs_v2.py'}
    baseline = {'configs/tc2_setup.json': HERE / 'inputs_job_43944_official_404/configs/tc2_setup.json',
                'scripts/prepare_tc2_inputs_v2.py': HERE / 'source_update_baseline/scripts/prepare_tc2_inputs_v2.py'}
    old_config = json.loads(baseline['configs/tc2_setup.json'].read_text())
    new_config = json.loads((payload / 'configs/tc2_setup.json').read_text())
    source_keys = ['archive_sources', 'input_source_revision', 'mvtec_ad_mirror']
    for config in [old_config, new_config]:
        for key in source_keys:
            config['preparation'].pop(key, None)
    assert old_config == new_config
    checks.append('Candidate remote configuration changes only the three approved source fields')

    with tempfile.TemporaryDirectory(prefix='source_publication_', dir=HERE) as name:
        directory = Path(name)
        for scenario in ['original', 'conflict', 'partly_applied']:
            test_root = directory / scenario
            for child in ['_downloads', 'tmp', 'run/setup_v2', 'scripts', 'configs']:
                (test_root / child).mkdir(parents=True, exist_ok=True)
            (test_root / '_downloads' / archive_name).write_bytes((command.parent / 'input-sources.tar').read_bytes())
            before = {}
            for index, (old_hash, new_hash, relative) in enumerate(rows):
                original = baseline[relative].read_bytes()
                assert hashlib.sha256(original).hexdigest() == old_hash
                data = original
                if scenario == 'conflict' and index == 1:
                    data = b'Unknown user modification; preserve this.\n'
                elif scenario == 'partly_applied' and index == 0:
                    data = (payload / relative).read_bytes()
                (test_root / relative).write_bytes(data)
                before[relative] = data
            script = test_root / 'publication.sh'
            script.write_text('set -euo pipefail\nroot="$(pwd -P)"\n' + publication, encoding='utf-8', newline='\n')
            actual = subprocess.run([BASH, str(script)], cwd=test_root, capture_output=True, text=True)
            backups = list((test_root / 'run/setup_v2').iterdir())
            if scenario == 'conflict':
                assert actual.returncode != 0 and not backups
                for relative, data in before.items():
                    assert (test_root / relative).read_bytes() == data
            else:
                assert actual.returncode == 0, actual.stderr
                backup, = backups
                for _, new_hash, relative in rows:
                    assert sha(test_root / relative) == new_hash
                    assert (backup / relative).read_bytes() == before[relative]
        checks.append('Actual rendered publication backs up both files, supports partial application and preserves unknown conflicts')
    ast.parse((ROOT / 'scripts/prepare_tc2_inputs_v2.py').read_text(encoding='utf-8'))
    result = dict(status='PASS', checks=checks, rendered_shell_commands=13,
                  real_network_downloads=0, actual_ssh_calls=0, actual_slurm_submissions=0,
                  gpu_tested=False, step_2_complete=False)
    (HERE / 'local_source_validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
