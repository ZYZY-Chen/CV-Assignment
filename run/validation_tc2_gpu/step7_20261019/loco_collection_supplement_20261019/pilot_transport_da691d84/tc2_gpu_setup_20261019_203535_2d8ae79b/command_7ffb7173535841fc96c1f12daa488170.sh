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
archive="$root/_downloads/pilot-files-20261019_203535_2d8ae79b.tar"
incoming="$root/tmp/pilot-files-20261019_203535_2d8ae79b"
stage_record="$root/run/validation_tc2_gpu/pilot_stage_20261019_203535_2d8ae79b"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" "$archive" "$incoming" 'a890d97bd0e03188a6062d1f53edef9dece6f687cefa40f05d0c6572f27203ef' 'MGUxZTI1MWMxZjAzYjc2ZDRhZjllOGJjZDA5YTg3MjA1MzFlMDBlY2U4MDE3M2M1MTdiODVhMTZlOWE4OGY5YyAgY29uZmlncy9waWxvdF90YzJfZ3B1Lmpzb24KOTAxMGM1NmE2ZjUyNzQ1ZDIxYTU1MDI4NGQ3ODA3MDA3ZmY3OGU4ZGE5YzE4ZTc4NmViYWUzMTBhOGJlNjI3NCAgc2NyaXB0cy9waWxvdF90YzJfZ3B1LnB5CmUyZGNiZWNkNDcwYzIwOWY3NGMzNTJmYTQzYjU2YTQ5MmU4YjA3MWMyYjhhMGUzYjg1ZDVlMzM4ODQ1N2M5MzEgIHNjcmlwdHMvc2x1cm0vcGlsb3RfdGMyX2dwdS5zaApkOGQzYjA3MmE2Yjc2OWQ4MTAyM2FjMGJlMDc3MGEyNGM5OTljODIyYjVhNjM4Njk5OTJiZmYwODQ4NDhkYWM0ICBzY3JpcHRzL2NvbGxlY3RfdGMyX2dwdV9waWxvdC5weQowNzNkNzZhODJmNzRhMTIzOTkyNzAyYWMwODBmZWM5ZDFjYTAyMTU2MWM0MjJjN2UzOGFmOGVmMzAyNDI1NWYyICB0ZXN0cy90ZXN0X3BpbG90X3RjMl9ncHUucHkKOTU2OGNjMzhlZjM0NGNiN2UyZTNhZGZhYzhkMTNkNjljMDhhMjM3MTk3MzhmZDFiMTFhYWZjYTI5NzUwYzkxNyAgZG9jcy9UQzJfR1BVX1BJTE9ULm1kCg==' <<'PILOT_BOOTSTRAP_PY'
import base64, hashlib, io, os, pathlib, re, sys, tarfile
root, archive, incoming = map(pathlib.Path, sys.argv[1:4])
expected_manifest = base64.b64decode(sys.argv[5], validate=True)
allowed = {'configs/pilot_tc2_gpu.json', 'scripts/pilot_tc2_gpu.py', 'scripts/slurm/pilot_tc2_gpu.sh', 'scripts/collect_tc2_gpu_pilot.py', 'tests/test_pilot_tc2_gpu.py', 'docs/TC2_GPU_PILOT.md'}
for path in (root, archive, incoming, *incoming.parents, *archive.parents):
    if path.is_symlink() or path.resolve() != path:
        raise RuntimeError('Unsafe bootstrap path')
if archive.stat().st_size > 16 * 1024 ** 2:
    raise RuntimeError('Pilot source archive exceeds 16 MiB')
data = archive.read_bytes()
if hashlib.sha256(data).hexdigest() != sys.argv[4]:
    raise RuntimeError('Pilot source archive SHA256 differs')
expected = {}
for line in expected_manifest.decode('ascii').splitlines():
    match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
    if not match or match[2] not in allowed or match[2] in expected:
        raise RuntimeError('Unexpected pilot source manifest entry')
    expected[match[2]] = match[1]
if set(expected) != allowed:
    raise RuntimeError('Pilot source manifest must contain exactly six files')
with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as package:
    members = package.getmembers()
    if len(members) != 7 or {m.name for m in members} != allowed | {'pilot.sha256'} or sum(m.size for m in members) > 8 * 1024 ** 2:
        raise RuntimeError('Pilot source archive member set differs')
    if any(not m.isfile() or m.islnk() or m.issym() or m.size < 0 for m in members):
        raise RuntimeError('Pilot archive permits only regular files')
    contents = {m.name: package.extractfile(m).read() for m in members}
if contents['pilot.sha256'] != expected_manifest or any(hashlib.sha256(contents[name]).hexdigest() != value for name, value in expected.items()):
    raise RuntimeError('Pilot source bytes do not match the verified manifest')
incoming.mkdir()
for name, content in contents.items():
    target = incoming / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(content)
print('Six pilot sources safely extracted after complete archive validation.')
PILOT_BOOTSTRAP_PY
"$root/envs/ca6129-ad-v2/bin/python" -I -B "$incoming/scripts/pilot_tc2_gpu.py" publish --root "$root" --incoming "$incoming" --stage "$stage_record"
submission_source="$root/scripts/slurm/pilot_tc2_gpu.sh"
submission_script="$stage_record/submission_lf.sh"
submission_hashes="$stage_record/submission.sha256"
[[ -f "$submission_source" && ! -L "$submission_source" ]] || exit 2
[[ ! -e "$submission_script" && ! -L "$submission_script" && ! -e "$submission_hashes" && ! -L "$submission_hashes" ]] || exit 2
( set -o noclobber; sed 's/\r$//' "$submission_source" > "$submission_script" )
[[ -s "$submission_script" ]] || exit 2
if LC_ALL=C grep -q $'\r' "$submission_script"; then echo 'Pilot submission contains a carriage return.' >&2; exit 2; fi
bash -n "$submission_script"
( set -o noclobber; sha256sum -- "$submission_source" "$submission_script" > "$submission_hashes" )
cat -- "$submission_hashes"
cd -- "$root"
[[ "$(pwd -P)" == "$root" ]] || { echo 'Pilot submission directory differs from the verified project root.' >&2; exit 2; }
echo "Pilot submission directory: $(pwd -P)"
job_id=$(sbatch --chdir="$root" --parsable --partition=MGPU-TC2 --qos=normal --gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00 --export="ALL,TC2_PILOT_STAGE=run/validation_tc2_gpu/pilot_stage_20261019_203535_2d8ae79b" --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_pilot_job.txt"
echo "TC2_JOB_ID=$job_id"
for attempt in 1 2 3 4; do
    [[ -n "$(squeue --noheader --jobs="$job_id" --format=%i)" ]] || break
    sleep 10
done
