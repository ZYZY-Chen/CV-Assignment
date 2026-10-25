"""Local safety validation only: synthetic files, no network or GPU."""
from pathlib import Path
import ast
import hashlib
import io
import json
import sys
import tarfile
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_tc2_inputs_v2 as prep


def digest(data):
    return hashlib.sha256(data).hexdigest().upper()


def archive(path, entries):
    with tarfile.open(path, 'w:xz') as target:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            if kind == 'file':
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
            else:
                info.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE,
                             'device': tarfile.CHRTYPE}[kind]
                info.linkname = '../../outside'
                target.addfile(info)


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {'Content-Length': str(len(data))}

    def geturl(self):
        return 'https://download.pytorch.org/file'


def rejected(action):
    try:
        action()
    except (ValueError, RuntimeError):
        return
    raise AssertionError('Expected refusal')


def main():
    checks = []
    assert 'torch' not in sys.modules
    setup, _, manifests = prep.audit.read_contract(ROOT / 'configs/tc2_setup.json')
    assert len(prep.audit.required_files(manifests)) == 4669
    checks.append('Frozen protocol, eight manifests and 4669 input paths; no Torch import')
    parent = Path(__file__).parent.resolve()
    with tempfile.TemporaryDirectory(prefix='synthetic_inputs_', dir=parent) as temporary:
        base = Path(temporary).resolve()
        assert base.is_relative_to(parent)
        for label, prefix in [('bare', ''), ('prefixed', 'bottle/')]:
            tarpath = base / (label + '.tar.xz')
            destination = base / label
            stage = base / (label + '_tmp')
            stage.mkdir()
            archive(tarpath, [(prefix + 'train/good/a.png', b'first', 'file')])
            expected = {'train/good/a.png': digest(b'first')}
            prep.restore_archive(tarpath, 'bottle', destination, expected, stage)
            assert (destination / 'train/good/a.png').read_bytes() == b'first'
            prep.restore_archive(tarpath, 'bottle', destination, expected, stage)
        checks.append('Bare/prefixed archive layouts; identical-file reuse')
        cases = [('../escape', b'x', 'file'), ('/absolute', b'x', 'file'),
                 ('bottle/../../escape', b'x', 'file'), ('bottle/link', b'', 'symlink'),
                 ('bottle/hard', b'', 'hardlink'), ('bottle/device', b'', 'device'),
                 ('bottle/back\\slash', b'x', 'file')]
        for index, entry in enumerate(cases):
            tarpath = base / f'bad{index}.tar.xz'
            destination = base / f'bad{index}'
            archive(tarpath, [entry])
            rejected(lambda: prep.restore_archive(tarpath, 'bottle', destination, {}, base))
            assert not destination.exists()
        checks.append('Traversal, absolute paths, links, devices and backslashes refused before writes')
        tarpath = base / 'conflict.tar.xz'
        destination = base / 'conflict'
        destination.mkdir()
        (destination / 'existing').write_bytes(b'old')
        archive(tarpath, [('new', b'new', 'file'), ('existing', b'changed', 'file')])
        rejected(lambda: prep.restore_archive(tarpath, 'bottle', destination, {}, base))
        assert (destination / 'existing').read_bytes() == b'old'
        assert not (destination / 'new').exists()
        archive(tarpath, [('new', b'bad', 'file')])
        for expected in [{'new': digest(b'good')}, {'missing': digest(b'x')}]:
            rejected(lambda: prep.restore_archive(tarpath, 'bottle', destination, expected, base))
            assert not (destination / 'new').exists()
        checks.append('Conflicts, wrong frozen hashes and missing members preserve destination')
        target = base / 'weight.pth'
        def wrong_weight(path):
            raise ValueError('Synthetic wrong weight')
        with patch.object(prep, 'urlopen', return_value=Response(b'complete')):
            rejected(lambda: prep.download('https://download.pytorch.org/file', target, validate=wrong_weight))
        assert not target.exists() and target.with_name(target.name + '.part').read_bytes() == b'complete'
        with patch.object(prep, 'urlopen', return_value=Response(b'fresh')):
            rejected(lambda: prep.download('https://download.pytorch.org/file', target))
        assert target.with_name(target.name + '.part').read_bytes() == b'complete'
        with patch.object(prep, 'urlopen', return_value=Response(b'_end', 206, {'Content-Range': 'bytes 8-11/12', 'Content-Length': '4'})):
            prep.download('https://download.pytorch.org/file', target)
        assert target.read_bytes() == b'complete_end'
        with patch.object(prep, 'urlopen', side_effect=AssertionError('Unexpected network attempt')):
            assert prep.download('https://download.pytorch.org/file', target)['reused']
        checks.append('Wrong weight not published; refused resume retains bytes; valid resume/reuse works')
        rejected(lambda: prep.download('http://download.pytorch.org/file', base / 'insecure'))
        rejected(lambda: prep.audit.require_compute_job())
        checks.append('HTTP and local non-SLURM preparation rejected')
    for path in [ROOT / 'scripts/prepare_tc2_inputs_v2.py']:
        ast.parse(path.read_text(encoding='utf-8'))
    result = dict(status='PASS', checks=checks, remote_commands=False, gpu_tested=False,
                  data_downloaded=False, shared_environment_modified=False)
    (parent / 'local_preparation_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
