set -euo pipefail
[[ "$(id -un)" == huajie001 && "$HOME" == /home/mcaai/huajie001 ]] || { echo 'Unexpected remote identity or HOME.' >&2; exit 2; }
root=/home/mcaai/huajie001/ca6129_v2_setup
[[ ! -L "$root" && "$(readlink -m -- "$root")" == "$root" ]] || { echo 'Unexpected root or symbolic link.' >&2; exit 2; }
for relative in run run/setup_tc2_gpu run/validation_tc2_gpu run/setup_v2 run/validation_v2 configs scripts tmp _downloads _package_cache envs; do
    candidate="$root/$relative"
    [[ ! -L "$candidate" && "$(readlink -m -- "$candidate")" == "$candidate" ]] || { echo "Unsafe staging path: $relative" >&2; exit 2; }
done
setup_record() {
    local relative="$1"
    [[ "$relative" != /* && "$relative" != *..* && "$relative" != *\\* ]] || return 2
    if [[ -e "$root/run/setup_tc2_gpu/$relative" ]]; then
        printf '%s\n' "$root/run/setup_tc2_gpu/$relative"
    else
        printf '%s\n' "$root/run/setup_v2/$relative"
    fi
}
metric_source_is_accepted() {
    local relative="$1" current_hash="$2" expected
    case "$relative" in
        src/metric_core.py) expected=E3A444608FF1D5B3D489CECA981D9B480E48D7FA53DB41EA6C46D9888ACB5CCD ;;
        src/evaluate.py) expected=99852A3E9E7C99FBD872ED37EAF7C1527FFED970D99BBD08A1911310C93CA3C1 ;;
        *) return 1 ;;
    esac
    [[ "${current_hash^^}" == "$expected" ]]
}
if [[ -n "$(squeue --noheader --user=huajie001 --format=%i)" ]]; then
    echo 'A personal job is already queued or running. Collect it before submitting another setup job.' >&2
    exit 2
fi
cd -- "$root"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" 'ewogICJzY2hlbWFfdmVyc2lvbiI6ICIxLjAiLAogICJ3b3JrZmxvd19pZCI6ICJ0YzJfZ3B1IiwKICAicHJvdG9jb2xfc2hhMjU2IjogIjMwOThCNkE4NkRCQTY0RUU0MzlCRkU2MUM3QTRGQ0ZGQ0QwODIzNzFENUE4MEZGQkM3OTQwOTk3RUQ2QTFFRDEiLAogICJkYXRhc2V0IjogIm12dGVjX2FkIiwKICAiY2F0ZWdvcnkiOiAiYm90dGxlIiwKICAicnVuX3NlZWQiOiAxNywKICAibm9ybWFsX3RyYWluX24iOiAxMDAsCiAgInJ1bl9rZXlzIjogWwogICAgIkIwX212dGVjX2FkX2JvdHRsZV9wYWRpbV9zMTdfbjEwMF9CN0I4NkRCQjIwNDMiLAogICAgIkIwX212dGVjX2FkX2JvdHRsZV9wYXRjaGNvcmVfczE3X24xMDBfQkJDMkI4NUMyRkE4IgogIF0sCiAgImZpdHMiOiBbCiAgICB7CiAgICAgICJydW5fa2V5IjogIkIwX212dGVjX2FkX2JvdHRsZV9wYWRpbV9zMTdfbjEwMF9CN0I4NkRCQjIwNDMiLAogICAgICAiY29uZmlndXJhdGlvbiI6IHsKICAgICAgICAic3RhZ2UiOiAiQjAiLAogICAgICAgICJkYXRhc2V0IjogIm12dGVjX2FkIiwKICAgICAgICAiY2F0ZWdvcnkiOiAiYm90dGxlIiwKICAgICAgICAibWV0aG9kIjogInBhZGltIiwKICAgICAgICAicnVuX3NlZWQiOiAxNywKICAgICAgICAibm9ybWFsX3RyYWluX24iOiAxMDAsCiAgICAgICAgImV4ZWN1dGlvbiI6IHsKICAgICAgICAgICJzY2hlbWFfdmVyc2lvbiI6ICIxLjAiLAogICAgICAgICAgIndvcmtmbG93X2lkIjogInRjMl9ncHUiLAogICAgICAgICAgImV4dHJhY3Rpb25fYmF0Y2hfc2l6ZSI6IDEsCiAgICAgICAgICAicHJlZGljdGlvbl9iYXRjaF9zaXplIjogMSwKICAgICAgICAgICJ3b3JrZXJzIjogMCwKICAgICAgICAgICJjcHVfdGhyZWFkcyI6IDIsCiAgICAgICAgICAid2FybXVwX2l0ZXJhdGlvbnMiOiAyMCwKICAgICAgICAgICJwYWRpbV9wb3NpdGlvbl9jaHVua19zaXplIjogMjU2LAogICAgICAgICAgInBhdGNoY29yZV9xdWVyeV9jaHVua19zaXplIjogMTAyNCwKICAgICAgICAgICJwYXRjaGNvcmVfYmFua19jaHVua19zaXplIjogNDA5NiwKICAgICAgICAgICJwYXRjaGNvcmVfc2FtcGxpbmdfY2h1bmtfc2l6ZSI6IDE2Mzg0CiAgICAgICAgfSwKICAgICAgICAibGF5ZXJzIjogWwogICAgICAgICAgImxheWVyMSIsCiAgICAgICAgICAibGF5ZXIyIiwKICAgICAgICAgICJsYXllcjMiCiAgICAgICAgXSwKICAgICAgICAicGFkaW0iOiB7CiAgICAgICAgICAibl9kaW1zIjogMTAwLAogICAgICAgICAgImVwcyI6IDAuMDEsCiAgICAgICAgICAiZGltc19zZWVkIjogMTcKICAgICAgICB9CiAgICAgIH0KICAgIH0sCiAgICB7CiAgICAgICJydW5fa2V5IjogIkIwX212dGVjX2FkX2JvdHRsZV9wYXRjaGNvcmVfczE3X24xMDBfQkJDMkI4NUMyRkE4IiwKICAgICAgImNvbmZpZ3VyYXRpb24iOiB7CiAgICAgICAgInN0YWdlIjogIkIwIiwKICAgICAgICAiZGF0YXNldCI6ICJtdnRlY19hZCIsCiAgICAgICAgImNhdGVnb3J5IjogImJvdHRsZSIsCiAgICAgICAgIm1ldGhvZCI6ICJwYXRjaGNvcmUiLAogICAgICAgICJydW5fc2VlZCI6IDE3LAogICAgICAgICJub3JtYWxfdHJhaW5fbiI6IDEwMCwKICAgICAgICAiZXhlY3V0aW9uIjogewogICAgICAgICAgInNjaGVtYV92ZXJzaW9uIjogIjEuMCIsCiAgICAgICAgICAid29ya2Zsb3dfaWQiOiAidGMyX2dwdSIsCiAgICAgICAgICAiZXh0cmFjdGlvbl9iYXRjaF9zaXplIjogMSwKICAgICAgICAgICJwcmVkaWN0aW9uX2JhdGNoX3NpemUiOiAxLAogICAgICAgICAgIndvcmtlcnMiOiAwLAogICAgICAgICAgImNwdV90aHJlYWRzIjogMiwKICAgICAgICAgICJ3YXJtdXBfaXRlcmF0aW9ucyI6IDIwLAogICAgICAgICAgInBhZGltX3Bvc2l0aW9uX2NodW5rX3NpemUiOiAyNTYsCiAgICAgICAgICAicGF0Y2hjb3JlX3F1ZXJ5X2NodW5rX3NpemUiOiAxMDI0LAogICAgICAgICAgInBhdGNoY29yZV9iYW5rX2NodW5rX3NpemUiOiA0MDk2LAogICAgICAgICAgInBhdGNoY29yZV9zYW1wbGluZ19jaHVua19zaXplIjogMTYzODQKICAgICAgICB9LAogICAgICAgICJsYXllcnMiOiBbCiAgICAgICAgICAibGF5ZXIyIiwKICAgICAgICAgICJsYXllcjMiCiAgICAgICAgXSwKICAgICAgICAicGF0Y2hjb3JlIjogewogICAgICAgICAgImNvcmVzZXRfcmF0aW8iOiAwLjA1LAogICAgICAgICAgIm51bV9uZWlnaGJvcnMiOiA5LAogICAgICAgICAgInNhbXBsaW5nIjogImNvcmVzZXQiLAogICAgICAgICAgInNhbXBsaW5nX3NlZWQiOiAxNwogICAgICAgIH0KICAgICAgfQogICAgfQogIF0sCiAgImV4cGVjdGVkX2NvdW50cyI6IHsKICAgICJpbWFnZXMiOiAyOTIsCiAgICAiZml0X3Bvb2wiOiAxNjcsCiAgICAiZGV2IjogNDIsCiAgICAidGVzdCI6IDgzCiAgfSwKICAid29ya2Zsb3dfYWNjZXB0YW5jZV9qb2JfaWQiOiAiNDQwMTIiLAogICJ3b3JrZmxvd19zb3VyY2VfaGFzaGVzIjogewogICAgInNyYy90YzJfZ3B1X3Byb3RvY29sLnB5IjogIkRENjQ2RjI2RTYxQzg5QjYyMkQwRDJCMURFNTA0NjIzODNDRTIyRDJBRUY1QzdBQTc5RjNBRjVCOTlERTQ0QjYiLAogICAgInNyYy90YzJfZ3B1X2NhY2hlLnB5IjogIjg2N0MzMURGRDg3RTVCRkM2RUM0NzgzMTgzRDkyNzE5MkFCQkMyQTExNDA2MTBDNzlFNUE4RDg0MjY3NDI0OTUiLAogICAgInNyYy90YzJfZ3B1X3J1bm5lci5weSI6ICJDRURDNEVDRDU0M0RDMjVFRkE2RTQwMDNGMTU4OTU0Qzc3NUI4NDJCOThBMjYwOUJFOTQzOTI4QUE5MDA2MjhEIiwKICAgICJzY3JpcHRzL3J1bl90YzJfZ3B1LnB5IjogIjVGOTE5OUQ4MjBDQ0FEODBGMEM2MDY1RjYxMjc3NkUzNDY3QkRFNUY5NzhBQzI0MEIzNjBCNDJENkQzNkY5MjEiLAogICAgImNvbmZpZ3MvcnVudGltZV90YzJfZ3B1Lmpzb24iOiAiQjA1Nzc2NkFGREY0NzNBODlFNzQwMTZCMkY5REY2QjMxMTUxMEJBOEU0NDRENDJFRTE0QzA3NUJBRjA4QUVBQSIsCiAgICAidGVzdHMvdGVzdF93b3JrZmxvd190YzJfZ3B1LnB5IjogIjUxMzAxODREOUJENzY4NDBBRjFCRDhDQTIxN0MxODY0NjE4QjIyOEVEMTVCN0EyRjM3MkYwQjVFOTQ5NzM0Q0MiLAogICAgInNjcmlwdHMvc2x1cm0vY2hlY2tfdGMyX2dwdV93b3JrZmxvdy5zaCI6ICI4OTQwNjEyODQyQjkxRkQzNzA5RkQ2NDNFQjcyMDRBQjhCRkYyMzI0OUMxMzlFMEI0NDFCRUQ3MjAyQzhDMTZEIiwKICAgICJzcmMvcGFkaW1fYWRhcHRlci5weSI6ICI4MDNFMzBGMUFEMUY1OTFCREQyNkMwRDQ1OEQyNTJEMzk3NTc4RjhFNTM5ODQ4Njg1NURBQzAyNTdGNDQzQUIzIiwKICAgICJzcmMvcGF0Y2hjb3JlX2FkYXB0ZXIucHkiOiAiNDg3N0Q2NjYyNTE4MEJCMzYyNThFQTZCOTlERTk0MjdFNTQ1NzY0NjE0QUIwQ0IyNDVGNUZBRkM0NEVDMzA3RiIsCiAgICAic3JjL3NhbXBsaW5nLnB5IjogIkJFREIzMzA1N0JDN0U5MzgxMDhFNEI5QjE3N0VDREUxMjE0MThCMjREQzM0OENERjA3QUQwNEYzRjAyODRCNzkiLAogICAgInNyYy9zY29yaW5nLnB5IjogIkU4MzQ4NTUwRjBBNTVDQzhBMUVEQkI0QjEzMTBGQkU5ODU0OTNGMjJEQUU3MUI2QjU2MkYzNDcyMEMzRDRCMEIiLAogICAgInNyYy9hbm9tYWx5X3Bvc3Rwcm9jZXNzLnB5IjogIjRCRDlFOUJFM0NBRDdCOTBBMjRGN0RCRkFBQkRCNTVFQjQwM0M5NEJDRjRCNzcxRkY5RDczQTA2MzFCOUQ0QkQiLAogICAgInRlc3RzL3Rlc3RfYWxnb3JpdGhtc190YzJfZ3B1LnB5IjogIjUyMDBBQUUyNDBFNjREMjJDQUVDQ0JENDY2MTVEREUxMUY1MTE4OUM2MTI5MzgwNDZEQzJENEEwMDlFMTZFREYiLAogICAgInNjcmlwdHMvc2x1cm0vY2hlY2tfdGMyX2dwdV9hbGdvcml0aG1zLnNoIjogIjMyODc5QkNBMzE3QjQ0REQ3RjE5NjA4OEYyNzE4QjMxODg4ODlFNDdEMzRCMjNDOEEyNEQ2MDI0NzIwRThEQ0MiLAogICAgInNyYy9tZXRyaWNfY29yZS5weSI6ICJEMjE4QTQzODAzMURFNkIwQTgzQjE0OTUxMzU0Q0Q2NkE4NUVENjVGOTdGRkMyQ0ZCQUVGRjFENEZCOTFEQjc4IiwKICAgICJzcmMvZXZhbHVhdGUucHkiOiAiNERCMjQxM0NDNkFBRjQyMTBCMTQzMjg1RkU1RkQ3RkM2QThDMDhFOThDNjcwNzNFOUE5MkQzMTM1OUU2OEJDNiIsCiAgICAic3JjL2RhdGEucHkiOiAiOUE4MkQ1ODUyMDNCMzc2RjQxQzMyMDBBMzJENjk3MTI4OERENzBCNUM3RTcxMjEwRjNFMjFGOEM1QzFGMUY4OSIsCiAgICAiY29uZmlncy90YzJfZ3B1Lmpzb24iOiAiRUIyODk5QjJFNjg4ODIzMzg3NEM4RkE5N0IxMjQ3QUJEM0U2OEIzOTE1MzhDODZBMzYxMDU0MTA5MTdBMDBGMCIsCiAgICAidGVzdHMvdGVzdF9tZXRyaWNzX3RjMl9ncHUucHkiOiAiODBCNDg5QjgzOTkwREUyNUMyQkU0RjA1NUZBMzgyMjQ3RkQwQjkwOTFEMTk0NzY0RUMzQzAyREQzNzAzMTNGRCIsCiAgICAic2NyaXB0cy9zbHVybS9jaGVja190YzJfZ3B1X21ldHJpY3Muc2giOiAiOTNFNjQzMDkzNDgwODJFMUVCREVGMkIxNzA3QkE1QTFBNThFRjk1QzNFNkU1Mzk1QTgyMDkxOTFGQjBEMTUxOSIsCiAgICAiY29uZmlncy9wcm90b2NvbF92Mi5qc29uIjogIjMwOThCNkE4NkRCQTY0RUU0MzlCRkU2MUM3QTRGQ0ZGQ0QwODIzNzFENUE4MEZGQkM3OTQwOTk3RUQ2QTFFRDEiLAogICAgImVudmlyb25tZW50LXRjMi55bWwiOiAiNDdGMURBQTgzQTc0NDc0Mzk0NkM4M0U2REMxOTYzQjhGQTdFODM1QTRBMEY3MDEwQTNCMDUwMUVGNUEzREYzOCIsCiAgICAicmVxdWlyZW1lbnRzLXRjMi1sb2NrLnR4dCI6ICJGN0I4NDhGMTBGRkIzRjNDQ0VCNzA3NDUwQjJBNUZFNERDRDlBNkMzQjQ4OTk2M0E4OTMyMDk0RTAxNjg0MEI2IiwKICAgICJtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfYm90dGxlLmpzb24iOiAiMjkyMkZBNkU1MTNGOTgwQ0JERTUzQTMwM0Y4NkZFMTE2MDU4OERGN0VGQjA3OTZGNjg4OEM5NUQyQkFCNjE0MCIsCiAgICAibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX2NhYmxlLmpzb24iOiAiRTE4OEQwNUJEMjQ2QzI5NTAzQTM1REJBRjQ5REJDQzMyNkEzNTA3OUVDQzA3OTczQUUxQTdCQ0NGRDA4RkQ5NSIsCiAgICAibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX2NhcHN1bGUuanNvbiI6ICIwRTlGMUJGNTM2OERFMDNBMkE2QkU1N0NEOEIxM0Q4Q0U5RDQ4NERFM0EwNTYzNTIwNkM3RDhGQzI4RDFFMzY3IiwKICAgICJtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfc2NyZXcuanNvbiI6ICJFMjA5RjQ0MjlDNDA1NkVDRkE2RjJEQTgyRkFBOUI1QjNBRTQ5NUVCRkRCRjk0RDU4MDhDOTY3NkQ4QTk5RjlCIiwKICAgICJtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfdGlsZS5qc29uIjogIjJCNDI3NEZFNzZCQkNCQ0UzQjk2OENDQ0FBMEYzREFBNjE1MUZBRjlBQTYzNTg0NDVBQ0RBMUI1REZCRUU5NEMiLAogICAgIm1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF93b29kLmpzb24iOiAiNTc2NDYwMDdFQkFGRThGMDE1Rjk3NjE4NjE5N0E3QTA4RDMzOEVDQUVCNkJGOEI1RDM3NjRERTlBNDY4ODhBRSIsCiAgICAibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2xvY29fanVpY2VfYm90dGxlLmpzb24iOiAiRTU0QUIzRkEzNTRFMjU4RDU5MUY2QzUzQjM5NUVEOUVFRDI1NTE4Q0YyNUYwMzlGRUI4ODA0MEEyRUM0NkM4NiIsCiAgICAibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2xvY29fc2NyZXdfYmFnLmpzb24iOiAiN0MwMkVEMUNGMzNBRkQzNUY4QkVGQjczNDI1MjVGNTMyMjEzQ0M2ODRBREMzMzA0MTQ1MjJEQjUxQjFDNjZDQSIKICB9LAogICJyZXNvdXJjZXMiOiB7CiAgICAicGFydGl0aW9uIjogIk1HUFUtVEMyIiwKICAgICJxb3MiOiAibm9ybWFsIiwKICAgICJub2RlcyI6IDEsCiAgICAidGFza3MiOiAxLAogICAgImdwdXMiOiAxLAogICAgImNwdXNfcGVyX3Rhc2siOiAyLAogICAgIm1lbW9yeV9naWIiOiAyNCwKICAgICJ0aW1lX2xpbWl0IjogIjAyOjAwOjAwIgogIH0sCiAgIm1pbmltdW1fZnJlZV9ieXRlcyI6IDQyOTQ5NjcyOTYsCiAgIm1heGltdW1fZXhwb3J0X2J5dGVzIjogNTM2ODcwOTEyLAogICJleHBlY3RlZF9ncHUiOiAiTlZJRElBIEE0MCIsCiAgImV4cGVjdGVkX2RyaXZlciI6ICI1NzAuMTQ4LjA4IiwKICAiZXhwZWN0ZWRfY3VkYV9idWlsZCI6ICIxMi44Igp9Cg==' <<'PILOT_PREFLIGHT_PY'
import base64, hashlib, json, pathlib, shutil, sys
root = pathlib.Path(sys.argv[1])
config = json.loads(base64.b64decode(sys.argv[2], validate=True))
def safe(relative):
    p = pathlib.PurePosixPath(relative)
    if p.is_absolute() or not relative or str(p) != relative or '..' in p.parts or '\\' in relative or ':' in relative:
        raise RuntimeError('Unsafe preflight path')
    q = root / p
    if q.resolve() != q or any(a.is_symlink() for a in (q, *q.parents)) or not q.is_file():
        raise RuntimeError('Unsafe or missing preflight file: ' + relative)
    return q
def sha(relative):
    h = hashlib.sha256()
    with safe(relative).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest().upper()
expected = config['workflow_source_hashes']
if len(expected) != 31 or config['workflow_acceptance_job_id'] != '44012':
    raise RuntimeError('Pilot workflow acceptance identity differs')
pointer = safe('run/validation_tc2_gpu/last_check_workflow_job.txt').read_text().strip()
if pointer != '44012':
    raise RuntimeError('Workflow acceptance pointer differs')
record = json.loads(safe('run/validation_tc2_gpu/step5_job_44012/setup_status.json').read_text())
if record.get('mode') != 'full' or record.get('status') != 'passed' or record.get('step_5_complete') is not True:
    raise RuntimeError('Full workflow acceptance is required')
if record.get('source_hashes') != expected:
    raise RuntimeError('Workflow acceptance scientific fingerprints differ')
for name, value in expected.items():
    if sha(name) != value.upper():
        raise RuntimeError('Accepted scientific source differs: ' + name)
if sha('configs/tc2_setup.json') != 'EDF3D1D0380E0105A5173607CE360221FD43B059478915EEC0EC04ED9110F913':
    raise RuntimeError('Original remote compatibility configuration differs')
if sha('weights/resnet18-f37072fd.pth') != 'F37072FD47E89C5E827621C5BAFFA7500819F7896BBACEC160B1A16C560E07EC':
    raise RuntimeError('Accepted local weights differ')
if shutil.disk_usage(root).free < 4 * 1024 ** 3:
    raise RuntimeError('Pilot requires at least 4 GiB of remote free space')
print('Pilot head-node preflight passed: 31 accepted scientific sources; no model or GPU probe executed.')
PILOT_PREFLIGHT_PY
[[ ! -e "$root/_downloads/pilot-files-20261019_203535_2d8ae79b.tar" && ! -L "$root/_downloads/pilot-files-20261019_203535_2d8ae79b.tar" ]] || { echo 'Pilot upload target already exists; no overwrite.' >&2; exit 2; }
