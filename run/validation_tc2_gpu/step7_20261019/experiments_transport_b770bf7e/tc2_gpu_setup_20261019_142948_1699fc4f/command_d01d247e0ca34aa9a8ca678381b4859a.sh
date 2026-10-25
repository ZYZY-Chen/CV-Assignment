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
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" 'eyJhY2NlcHRlZF93b3JrZmxvd19qb2JfaWQiOiI0NDAxMiIsImFjY2VwdGVkX3BpbG90X2pvYl9pZCI6IjQ0MDI0Iiwic2NpZW50aWZpY19zb3VyY2VfaGFzaGVzIjp7InNyYy90YzJfZ3B1X3Byb3RvY29sLnB5IjoiREQ2NDZGMjZFNjFDODlCNjIyRDBEMkIxREU1MDQ2MjM4M0NFMjJEMkFFRjVDN0FBNzlGM0FGNUI5OURFNDRCNiIsInNyYy90YzJfZ3B1X2NhY2hlLnB5IjoiODY3QzMxREZEODdFNUJGQzZFQzQ3ODMxODNEOTI3MTkyQUJCQzJBMTE0MDYxMEM3OUU1QThEODQyNjc0MjQ5NSIsInNyYy90YzJfZ3B1X3J1bm5lci5weSI6IkNFREM0RUNENTQzREMyNUVGQTZFNDAwM0YxNTg5NTRDNzc1Qjg0MkI5OEEyNjA5QkU5NDM5MjhBQTkwMDYyOEQiLCJzY3JpcHRzL3J1bl90YzJfZ3B1LnB5IjoiNUY5MTk5RDgyMENDQUQ4MEYwQzYwNjVGNjEyNzc2RTM0NjdCREU1Rjk3OEFDMjQwQjM2MEI0MkQ2RDM2RjkyMSIsImNvbmZpZ3MvcnVudGltZV90YzJfZ3B1Lmpzb24iOiJCMDU3NzY2QUZERjQ3M0E4OUU3NDAxNkIyRjlERjZCMzExNTEwQkE4RTQ0NEQ0MkVFMTRDMDc1QkFGMDhBRUFBIiwidGVzdHMvdGVzdF93b3JrZmxvd190YzJfZ3B1LnB5IjoiNTEzMDE4NEQ5QkQ3Njg0MEFGMUJEOENBMjE3QzE4NjQ2MThCMjI4RUQxNUI3QTJGMzcyRjBCNUU5NDk3MzRDQyIsInNjcmlwdHMvc2x1cm0vY2hlY2tfdGMyX2dwdV93b3JrZmxvdy5zaCI6Ijg5NDA2MTI4NDJCOTFGRDM3MDlGRDY0M0VCNzIwNEFCOEJGRjIzMjQ5QzEzOUUwQjQ0MUJFRDcyMDJDOEMxNkQiLCJzcmMvcGFkaW1fYWRhcHRlci5weSI6IjgwM0UzMEYxQUQxRjU5MUJERDI2QzBENDU4RDI1MkQzOTc1NzhGOEU1Mzk4NDg2ODU1REFDMDI1N0Y0NDNBQjMiLCJzcmMvcGF0Y2hjb3JlX2FkYXB0ZXIucHkiOiI0ODc3RDY2NjI1MTgwQkIzNjI1OEVBNkI5OURFOTQyN0U1NDU3NjQ2MTRBQjBDQjI0NUY1RkFGQzQ0RUMzMDdGIiwic3JjL3NhbXBsaW5nLnB5IjoiQkVEQjMzMDU3QkM3RTkzODEwOEU0QjlCMTc3RUNERTEyMTQxOEIyNERDMzQ4Q0RGMDdBRDA0RjNGMDI4NEI3OSIsInNyYy9zY29yaW5nLnB5IjoiRTgzNDg1NTBGMEE1NUNDOEExRURCQjRCMTMxMEZCRTk4NTQ5M0YyMkRBRTcxQjZCNTYyRjM0NzIwQzNENEIwQiIsInNyYy9hbm9tYWx5X3Bvc3Rwcm9jZXNzLnB5IjoiNEJEOUU5QkUzQ0FEN0I5MEEyNEY3REJGQUFCREI1NUVCNDAzQzk0QkNGNEI3NzFGRjlENzNBMDYzMUI5RDRCRCIsInRlc3RzL3Rlc3RfYWxnb3JpdGhtc190YzJfZ3B1LnB5IjoiNTIwMEFBRTI0MEU2NEQyMkNBRUNDQkQ0NjYxNURERTExRjUxMTg5QzYxMjkzODA0NkRDMkQ0QTAwOUUxNkVERiIsInNjcmlwdHMvc2x1cm0vY2hlY2tfdGMyX2dwdV9hbGdvcml0aG1zLnNoIjoiMzI4NzlCQ0EzMTdCNDRERDdGMTk2MDg4RjI3MThCMzE4ODg4OUU0N0QzNEIyM0M4QTI0RDYwMjQ3MjBFOERDQyIsInNyYy9tZXRyaWNfY29yZS5weSI6IkQyMThBNDM4MDMxREU2QjBBODNCMTQ5NTEzNTRDRDY2QTg1RUQ2NUY5N0ZGQzJDRkJBRUZGMUQ0RkI5MURCNzgiLCJzcmMvZXZhbHVhdGUucHkiOiI0REIyNDEzQ0M2QUFGNDIxMEIxNDMyODVGRTVGRDdGQzZBOEMwOEU5OEM2NzA3M0U5QTkyRDMxMzU5RTY4QkM2Iiwic3JjL2RhdGEucHkiOiI5QTgyRDU4NTIwM0IzNzZGNDFDMzIwMEEzMkQ2OTcxMjg4REQ3MEI1QzdFNzEyMTBGM0UyMUY4QzVDMUYxRjg5IiwiY29uZmlncy90YzJfZ3B1Lmpzb24iOiJFQjI4OTlCMkU2ODg4MjMzODc0QzhGQTk3QjEyNDdBQkQzRTY4QjM5MTUzOEM4NkEzNjEwNTQxMDkxN0EwMEYwIiwidGVzdHMvdGVzdF9tZXRyaWNzX3RjMl9ncHUucHkiOiI4MEI0ODlCODM5OTBERTI1QzJCRTRGMDU1RkEzODIyNDdGRDBCOTA5MUQxOTQ3NjRFQzNDMDJERDM3MDMxM0ZEIiwic2NyaXB0cy9zbHVybS9jaGVja190YzJfZ3B1X21ldHJpY3Muc2giOiI5M0U2NDMwOTM0ODA4MkUxRUJERUYyQjE3MDdCQTVBMUE1OEVGOTVDM0U2RTUzOTVBODIwOTE5MUZCMEQxNTE5IiwiY29uZmlncy9wcm90b2NvbF92Mi5qc29uIjoiMzA5OEI2QTg2REJBNjRFRTQzOUJGRTYxQzdBNEZDRkZDRDA4MjM3MUQ1QTgwRkZCQzc5NDA5OTdFRDZBMUVEMSIsImVudmlyb25tZW50LXRjMi55bWwiOiI0N0YxREFBODNBNzQ0NzQzOTQ2QzgzRTZEQzE5NjNCOEZBN0U4MzVBNEEwRjcwMTBBM0IwNTAxRUY1QTNERjM4IiwicmVxdWlyZW1lbnRzLXRjMi1sb2NrLnR4dCI6IkY3Qjg0OEYxMEZGQjNGM0NDRUI3MDc0NTBCMkE1RkU0RENEOUE2QzNCNDg5OTYzQTg5MzIwOTRFMDE2ODQwQjYiLCJtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfYm90dGxlLmpzb24iOiIyOTIyRkE2RTUxM0Y5ODBDQkRFNTNBMzAzRjg2RkUxMTYwNTg4REY3RUZCMDc5NkY2ODg4Qzk1RDJCQUI2MTQwIiwibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX2NhYmxlLmpzb24iOiJFMTg4RDA1QkQyNDZDMjk1MDNBMzVEQkFGNDlEQkNDMzI2QTM1MDc5RUNDMDc5NzNBRTFBN0JDQ0ZEMDhGRDk1IiwibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX2NhcHN1bGUuanNvbiI6IjBFOUYxQkY1MzY4REUwM0EyQTZCRTU3Q0Q4QjEzRDhDRTlENDg0REUzQTA1NjM1MjA2QzdEOEZDMjhEMUUzNjciLCJtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfc2NyZXcuanNvbiI6IkUyMDlGNDQyOUM0MDU2RUNGQTZGMkRBODJGQUE5QjVCM0FFNDk1RUJGREJGOTRENTgwOEM5Njc2RDhBOTlGOUIiLCJtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfdGlsZS5qc29uIjoiMkI0Mjc0RkU3NkJCQ0JDRTNCOTY4Q0NDQUEwRjNEQUE2MTUxRkFGOUFBNjM1ODQ0NUFDREExQjVERkJFRTk0QyIsIm1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF93b29kLmpzb24iOiI1NzY0NjAwN0VCQUZFOEYwMTVGOTc2MTg2MTk3QTdBMDhEMzM4RUNBRUI2QkY4QjVEMzc2NERFOUE0Njg4OEFFIiwibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2xvY29fanVpY2VfYm90dGxlLmpzb24iOiJFNTRBQjNGQTM1NEUyNThENTkxRjZDNTNCMzk1RUQ5RUVEMjU1MThDRjI1RjAzOUZFQjg4MDQwQTJFQzQ2Qzg2IiwibWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2xvY29fc2NyZXdfYmFnLmpzb24iOiI3QzAyRUQxQ0YzM0FGRDM1RjhCRUZCNzM0MjUyNUY1MzIyMTNDQzY4NEFEQzMzMDQxNDUyMkRCNTFCMUM2NkNBIn0sInBpbG90X3NvdXJjZV9oYXNoZXMiOnsiY29uZmlncy9waWxvdF90YzJfZ3B1Lmpzb24iOiIwRTFFMjUxQzFGMDNCNzZENEFGOUU4QkNEMDlBODcyMDUzMUUwMEVDRTgwMTczQzUxN0I4NUExNkU5QTg4RjlDIiwic2NyaXB0cy9waWxvdF90YzJfZ3B1LnB5IjoiOTAxMEM1NkE2RjUyNzQ1RDIxQTU1MDI4NEQ3ODA3MDA3RkY3OEU4REE5QzE4RTc4NkVCQUUzMTBBOEJFNjI3NCIsInNjcmlwdHMvc2x1cm0vcGlsb3RfdGMyX2dwdS5zaCI6IkUyRENCRUNENDcwQzIwOUY3NEMzNTJGQTQzQjU2QTQ5MkU4QjA3MUMyQjhBMEUzQjg1RDVFMzM4ODQ1N0M5MzEiLCJzY3JpcHRzL2NvbGxlY3RfdGMyX2dwdV9waWxvdC5weSI6IkQ4RDNCMDcyQTZCNzY5RDgxMDIzQUMwQkUwNzcwQTI0Qzk5OUM4MjJCNUE2Mzg2OTk5MkJGRjA4NDg0OERBQzQiLCJ0ZXN0cy90ZXN0X3BpbG90X3RjMl9ncHUucHkiOiIwNzNENzZBODJGNzRBMTIzOTkyNzAyQUMwODBGRUM5RDFDQTAyMTU2MUM0MjJDN0UzOEFGOEVGMzAyNDI1NUYyIiwiZG9jcy9UQzJfR1BVX1BJTE9ULm1kIjoiOTU2OENDMzhFRjM0NENCN0UyRTNBREZBQzhEMTNENjlDMDhBMjM3MTk3MzhGRDFCMTFBQUZDQTI5NzUwQzkxNyJ9LCJzdGFnZXMiOlt7InN0YWdlX2lkIjoiQjAiLCJwcmVkZWNlc3NvciI6bnVsbH1dLCJkZXNpZ25fc2hhMjU2IjoiNjY5QUUwNTA0NEM5NDQxRkFDQzY1NzFGNEU1QUI1MTc2QkIwODI3NkRGNThDQTJCMEQ5NDFCNTE0QTU1RkI3NSJ9' 'B0' <<'EXPERIMENTS_PREFLIGHT_PY'
import base64, hashlib, json, pathlib, re, shutil, sys
root = pathlib.Path(sys.argv[1])
config = json.loads(base64.b64decode(sys.argv[2], validate=True))
stage_id = sys.argv[3]
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
def read(relative):
    return json.loads(safe(relative).read_text())
scientific, pilot = config['scientific_source_hashes'], config['pilot_source_hashes']
if len(scientific) != 31 or len(pilot) != 6 or config['accepted_workflow_job_id'] != '44012' or config['accepted_pilot_job_id'] != '44024':
    raise RuntimeError('Experiment acceptance identities differ')
if safe('run/validation_tc2_gpu/last_check_workflow_job.txt').read_text().strip() != '44012':
    raise RuntimeError('Latest workflow acceptance pointer differs')
workflow = read('run/validation_tc2_gpu/step5_job_44012/setup_status.json')
if workflow.get('mode') != 'full' or workflow.get('status') != 'passed' or workflow.get('step_5_complete') is not True or workflow.get('source_hashes') != scientific:
    raise RuntimeError('Full accepted workflow is required')
if safe('run/validation_tc2_gpu/last_pilot_job.txt').read_text().strip() != '44024':
    raise RuntimeError('Latest pilot acceptance pointer differs')
accepted = read('run/validation_tc2_gpu/step6_job_44024/setup_status.json')
if accepted.get('mode') != 'real_data_pilot' or accepted.get('status') != 'passed' or accepted.get('step_6_complete') is not True or accepted.get('pilot_sources') != pilot:
    raise RuntimeError('Full accepted real-data pilot is required')
for name, value in {**scientific, **pilot}.items():
    if sha(name) != value.upper():
        raise RuntimeError('Accepted scientific or pilot source differs: ' + name)
if sha('configs/tc2_setup.json') != 'EDF3D1D0380E0105A5173607CE360221FD43B059478915EEC0EC04ED9110F913':
    raise RuntimeError('Original remote compatibility configuration differs')
if sha('weights/resnet18-f37072fd.pth') != 'F37072FD47E89C5E827621C5BAFFA7500819F7896BBACEC160B1A16C560E07EC':
    raise RuntimeError('Accepted local weights differ')
if shutil.disk_usage(root).free < 20 * 1024 ** 3:
    raise RuntimeError('Experiments require at least 20 GiB of remote free space')
stages = [s for s in config['stages'] if s['stage_id'] == stage_id]
if len(stages) != 1:
    raise RuntimeError('Requested experiment stage is ambiguous')
predecessor = stages[0]['predecessor']
if predecessor:
    pointer = safe('run/validation_tc2_gpu/last_experiments_' + predecessor + '_job.txt').read_text().strip()
    if not re.fullmatch('[0-9]+', pointer):
        raise RuntimeError('Invalid latest predecessor job pointer')
    prior = read('run/validation_tc2_gpu/step7_job_' + pointer + '/setup_status.json')
    if prior.get('mode') != 'formal_experiment_stage' or prior.get('stage_id') != predecessor or prior.get('job_id') != pointer or prior.get('status') != 'passed' or prior.get('stage_complete') is not True or prior.get('design_sha256') != config['design_sha256']:
        raise RuntimeError('Latest predecessor stage is not complete; no earlier-success fallback')
print('Experiment head-node preflight passed: 31 scientific and six pilot sources; no model or GPU probe executed.')
EXPERIMENTS_PREFLIGHT_PY
[[ ! -e "$root/_downloads/experiments-files-20261019_142948_1699fc4f.tar" && ! -L "$root/_downloads/experiments-files-20261019_142948_1699fc4f.tar" ]] || { echo 'Experiment upload target already exists; no overwrite.' >&2; exit 2; }
