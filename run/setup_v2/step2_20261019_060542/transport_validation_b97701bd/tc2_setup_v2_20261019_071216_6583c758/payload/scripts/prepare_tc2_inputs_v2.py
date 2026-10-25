#!/usr/bin/env python3
"""Restore only approved TC2 inputs; never fit a model or replace a conflicting file."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import check_setup_v2 as audit


def inside(path, root):
    root = Path(root).resolve()
    path = Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Path is outside the approved root or is a symbolic link: ' + str(path))
    for parent in path.parents:
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError('Symbolic-link parent is not allowed: ' + str(parent))
    return path


def digest_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest().upper()


def member_paths(archive, category, destination):
    """Validate the entire member table before any extraction."""
    members = archive.getmembers()
    parts = []
    for member in members:
        raw = member.name
        path = PurePosixPath(raw)
        if path.is_absolute() or '..' in path.parts or '\\' in raw or ':' in raw:
            raise ValueError('Unsafe archive path: ' + raw)
        if not (member.isfile() or member.isdir()):
            raise ValueError('Archive links/devices are not accepted: ' + raw)
        if path.parts:
            parts.append((member, path.parts))
    strip_category = bool(parts) and all(item[0] == category for _, item in parts)
    seen = set()
    result = []
    for member, components in parts:
        relative = components[1:] if strip_category else components
        if not relative:
            if member.isfile():
                raise ValueError('File cannot be the category root')
            continue
        key = '/'.join(relative)
        if key in seen:
            raise ValueError('Duplicate archive member: ' + key)
        seen.add(key)
        target = inside(Path(destination).joinpath(*relative), destination)
        result.append((member, target, key))
    if not result:
        raise ValueError('Archive contains no category files')
    return result


def restore_archive(path, category, destination, expected, temp_root):
    destination = inside(destination, destination.parent)
    with tarfile.open(path, 'r:xz') as archive:
        entries = member_paths(archive, category, destination)
        found = {}
        # Verify all required content and existing-file conflicts before writing.
        for member, target, key in entries:
            if member.isdir():
                if target.exists() and not target.is_dir():
                    raise ValueError('Directory conflicts with existing file: ' + str(target))
                continue
            if target.exists() and not target.is_file():
                raise ValueError('File conflicts with existing directory: ' + str(target))
            with archive.extractfile(member) as stream:
                actual = digest_stream(stream)
            found[key] = actual
            if key in expected and actual != expected[key]:
                raise ValueError('Frozen manifest hash mismatch inside archive: ' + key)
            if target.exists() and audit.sha256(target) != actual:
                raise ValueError('Existing file differs; no overwrite: ' + str(target))
        missing = set(expected) - set(found)
        if missing:
            raise ValueError('Archive lacks frozen input files: ' + ', '.join(sorted(missing)[:5]))
        for member, target, _ in entries:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                # Publish without overwriting; clean up only our own temporary file.
                with tempfile.NamedTemporaryFile(dir=temp_root, prefix='extract_', delete=False) as pending:
                    temporary = Path(pending.name)
                    with archive.extractfile(member) as source:
                        shutil.copyfileobj(source, pending, length=1024 * 1024)
                try:
                    os.link(temporary, target)
                finally:
                    temporary.unlink()


def download(url, target, *, validate=None):
    """One attempt, HTTPS, retain partial files; resume only if the server agrees."""
    if urlsplit(url).scheme != 'https':
        raise ValueError('Only HTTPS official delivery is supported')
    target = Path(target)
    if target.is_symlink():
        raise ValueError('Download target is a symbolic link')
    if target.exists():
        if validate:
            validate(target)
        return dict(source=url, path=str(target), reused=True, size_bytes=target.stat().st_size,
                    sha256=audit.sha256(target))
    partial = target.with_name(target.name + '.part')
    if partial.is_symlink():
        raise ValueError('Partial download is a symbolic link')
    marker = partial.with_name(partial.name + '.source.txt')
    if marker.is_symlink():
        raise ValueError('Download source marker is a symbolic link')
    if partial.exists() and (not marker.exists() or marker.read_text() != url):
        raise ValueError('Partial download source is unknown or differs; inspect before resuming')
    if not marker.exists():
        with marker.open('x', encoding='utf-8') as stream:
            stream.write(url)
    elif marker.read_text() != url:
        raise ValueError('Existing source marker differs')
    offset = partial.stat().st_size if partial.exists() else 0
    request = Request(url, headers={'User-Agent': 'CA6129-academic-input-check/2.0'})
    if offset:
        request.add_header('Range', f'bytes={offset}-')
    with urlopen(request, timeout=60) as response:
        if urlsplit(response.geturl()).scheme != 'https':
            raise ValueError('Official delivery redirected to non-HTTPS')
        if offset and (response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
            raise RuntimeError('Server did not accept resume; partial retained without replacement')
        expected_length = response.headers.get('Content-Length')
        received = 0
        with partial.open('ab' if offset else 'xb') as stream:
            for block in iter(lambda: response.read(1024 * 1024), b''):
                stream.write(block)
                received += len(block)
        if expected_length is not None and received != int(expected_length):
            raise RuntimeError('Incomplete download; partial retained')
    if validate:
        validate(partial)
    # No overwrite even if another process created the target during transfer.
    os.link(partial, target)
    partial.unlink()
    return dict(source=url, path=str(target), reused=False, size_bytes=target.stat().st_size,
                sha256=audit.sha256(target))


def verify_weight(path, setup):
    record = audit.audit_weights(path, setup)
    if not record['ready']:
        raise ValueError('Weight did not pass the frozen hash-prefix check: ' + str(record))


def prepare(setup, manifests, out):
    root = audit.PROJECT.resolve()
    plan = setup['preparation']
    if not plan['approved'] or not setup['scope']['permit_dataset_or_weights_download']:
        raise RuntimeError('Input restoration is not approved')
    audit.require_verified_remote(setup)
    if Path(sys.prefix).resolve() != Path(plan['environment_prefix']).resolve():
        raise RuntimeError('Use the prepared dedicated environment')
    data_root = inside(Path(plan['datasets_root']), root)
    weight = inside(Path(plan['weights_path']), root)
    downloads = inside(root / '_downloads', root)
    temporary = inside(root / 'tmp', root)
    for directory in (data_root, weight.parent, downloads, temporary):
        directory.mkdir(parents=True, exist_ok=True)
    expected_rows = audit.required_files(manifests)
    transfers = []
    for manifest in manifests:
        key = manifest['dataset'] + '/' + manifest['category']
        prefix = key + '/'
        rows = [row for row in expected_rows if row['path'].startswith(prefix)]
        existing = [audit.inspect_file(data_root, row) for row in rows]
        conflicts = [row for row in existing if row['status'] not in ('match', 'missing')]
        if conflicts:
            raise ValueError('Existing inputs conflict with the frozen manifest: ' + str(conflicts[:2]))
        if all(row['status'] == 'match' for row in existing):
            transfers.append(dict(category=key, status='existing_frozen_inputs_match'))
            continue
        archive = downloads / (manifest['category'] + '.tar.xz')
        destination = inside(data_root / key, data_root)
        expected = {row['path'][len(prefix):]: row['expected_sha256'] for row in rows}
        def validate_archive(path):
            with tarfile.open(path, 'r:xz') as source:
                member_paths(source, manifest['category'], destination)
        print('Restoring ' + key + ' from official source; no third-party fallback.', flush=True)
        transfer = download(plan['archive_sources'][key], archive, validate=validate_archive)
        restore_archive(archive, manifest['category'], destination, expected, temporary)
        transfer.update(category=key, status='restored')
        transfers.append(transfer)
        audit.write_json(out / 'transfers.json', transfers)
    uploaded_weight = inside(downloads / weight.name, root)
    if not weight.exists() and uploaded_weight.exists():
        verify_weight(uploaded_weight, setup)
        os.link(uploaded_weight, weight)
        weight_transfer = dict(source=setup['expected_inputs']['weights_official_url'],
            path=str(weight), transfer_method='user_uploaded_official_file',
            size_bytes=weight.stat().st_size, sha256=audit.sha256(weight))
    else:
        weight_transfer = download(setup['expected_inputs']['weights_official_url'], weight,
                                   validate=lambda path: verify_weight(path, setup))
    transfers.append(dict(kind='weight', **weight_transfer))
    audit.write_json(out / 'transfers.json', transfers)
    data_audit = audit.audit_inputs(data_root, manifests, setup)
    weights = audit.audit_weights(weight, setup)
    audit.write_json(out / 'data_audit.json', data_audit)
    audit.write_json(out / 'weights_info.json', weights)
    if not data_audit['ready'] or not weights['ready']:
        raise RuntimeError('Restored inputs did not pass the complete frozen audit')
    setup['remote']['datasets_root'] = str(data_root)
    setup['remote']['weights_path'] = str(weight)
    audit.write_json(root / 'configs/tc2_setup.json', setup)
    return dict(ready=True, step_2_complete=False, input_counts=data_audit['counts'],
                weights_ready=weights['ready'], meaning='Inputs restored; final GPU acceptance remains required.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accept-license', action='store_true')
    args = parser.parse_args()
    audit.require_compute_job()
    if not args.accept_license:
        parser.error('Input restoration requires acceptance of CC BY-NC-SA 4.0')
    setup, _, manifests = audit.read_contract(audit.PROJECT / 'configs/tc2_setup.json')
    audit.require_verified_remote(setup)
    out = inside(audit.PROJECT / 'run/setup_v2' / ('job_' + os.environ['SLURM_JOB_ID'] + '_prepare_inputs'), audit.PROJECT)
    out.mkdir(parents=True, exist_ok=False)
    status = dict(ready=False, step_2_complete=False)
    try:
        status = prepare(setup, manifests, out)
    except Exception as error:
        status['error'] = type(error).__name__ + ': ' + str(error)
        print(status['error'], file=sys.stderr)
    audit.write_json(out / 'preparation_status.json', status)
    print(json.dumps(status, indent=2))
    return 0 if status['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
