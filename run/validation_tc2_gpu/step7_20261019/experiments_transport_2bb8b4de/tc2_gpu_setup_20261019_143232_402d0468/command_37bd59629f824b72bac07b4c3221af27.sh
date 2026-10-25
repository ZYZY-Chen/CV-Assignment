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
archive="$root/_downloads/experiments-files-20261019_143232_402d0468.tar"
incoming="$root/tmp/experiments-files-20261019_143232_402d0468"
stage_record="$root/run/validation_tc2_gpu/experiments_stage_20261019_143232_402d0468"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" "$archive" "$incoming" '1fe3f393d6baf5197a29c22027695d044400eb012f0390c8559f091fd3754e1a' 'NjY5YWUwNTA0NGM5NDQxZmFjYzY1NzFmNGU1YWI1MTc2YmIwODI3NmRmNThjYTJiMGQ5NDFiNTE0YTU1ZmI3NSAgY29uZmlncy9leHBlcmltZW50c190YzJfZ3B1Lmpzb24KZjQ4OTZkODNkZWQ5ZWFhY2I3MmVkN2E3NWI2M2Y3NmNjMzUzOGU2MWQyZmI5MGE4OGNmMTk0NWQzNmQwY2JkYSAgc2NyaXB0cy9leHBlcmltZW50c190YzJfZ3B1LnB5CmQxNDEyZjY3NDNlY2I2NzA5ZWI4MmZmOTc4ZGY0ZDhjMzc2MDEzNzFiZTRlNzhjMjMyOWI5YWFkMWZmNjA5ZjYgIHNjcmlwdHMvYW5hbHl6ZV9zY29yZXNfdGMyX2dwdS5weQpjNGQxMmNmYmM4ZDdiMGY3OTlhZDUxZTA2ODI2MzE4YzhhMTcyMTA1MjZlYzYzZWQwNGNkNGZmM2FiMTMwODBlICBzY3JpcHRzL3NsdXJtL2V4cGVyaW1lbnRzX3RjMl9ncHUuc2gKYWM2MTc3MmY2NWM5ZjJjNDEyNDc2MWQyMzYxZTBhODVlOWY2NWRiY2Y0ZGY1YmFiM2U5MzliNTExMTQ2NjAxMCAgc2NyaXB0cy9jb2xsZWN0X2V4cGVyaW1lbnRzX3RjMl9ncHUucHkKMzcxMDcyOTE0ZmQ4M2YxZTRhODAzNTAxYTg2OTY1OTc3YmExMmMxNzk3ZWU0NGMxNzhkMGE4NDNmOGEyZmZlNSAgdGVzdHMvdGVzdF9leHBlcmltZW50c190YzJfZ3B1LnB5CmViZjdhZDIzNGEyMzQ2Mzc5Y2U1YjdiODBhNzY4MjZhNTY0ZjNlZDdmZjA4ZGViMTdjYTM2MmVjOWUyZmQ0N2EgIGRvY3MvVEMyX0dQVV9FWFBFUklNRU5UUy5tZAo=' <<'EXPERIMENTS_BOOTSTRAP_PY'
import base64, hashlib, io, pathlib, re, sys, tarfile
root, archive, incoming = map(pathlib.Path, sys.argv[1:4])
expected_manifest = base64.b64decode(sys.argv[5], validate=True)
allowed = {'configs/experiments_tc2_gpu.json', 'scripts/experiments_tc2_gpu.py', 'scripts/analyze_scores_tc2_gpu.py', 'scripts/slurm/experiments_tc2_gpu.sh', 'scripts/collect_experiments_tc2_gpu.py', 'tests/test_experiments_tc2_gpu.py', 'docs/TC2_GPU_EXPERIMENTS.md'}
for path in (root, archive, incoming, *incoming.parents, *archive.parents):
    if path.is_symlink() or path.resolve() != path:
        raise RuntimeError('Unsafe experiment bootstrap path')
if archive.stat().st_size > 16 * 1024 ** 2:
    raise RuntimeError('Experiment source archive exceeds 16 MiB')
data = archive.read_bytes()
if hashlib.sha256(data).hexdigest() != sys.argv[4]:
    raise RuntimeError('Experiment source archive SHA256 differs')
expected = {}
for line in expected_manifest.decode('ascii').splitlines():
    match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
    if not match or match[2] not in allowed or match[2] in expected:
        raise RuntimeError('Unexpected experiment source manifest entry')
    expected[match[2]] = match[1]
if set(expected) != allowed:
    raise RuntimeError('Experiment source manifest must contain exactly seven files')
with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as package:
    members = package.getmembers()
    if len(members) != 8 or {m.name for m in members} != allowed | {'experiments.sha256'} or sum(m.size for m in members) > 8 * 1024 ** 2:
        raise RuntimeError('Experiment source archive member set differs')
    if any(not m.isfile() or m.islnk() or m.issym() or m.size < 0 for m in members):
        raise RuntimeError('Experiment archive permits only regular files')
    contents = {m.name: package.extractfile(m).read() for m in members}
if contents['experiments.sha256'] != expected_manifest or any(hashlib.sha256(contents[name]).hexdigest() != value for name, value in expected.items()):
    raise RuntimeError('Experiment source bytes do not match the verified manifest')
incoming.mkdir()
for name, content in contents.items():
    target = incoming / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(content)
print('Seven experiment sources safely extracted after complete archive validation.')
EXPERIMENTS_BOOTSTRAP_PY
module load anaconda/25.5.1
set +u
conda_hook="$(conda shell.bash hook)"
eval "$conda_hook"
conda activate "$root/envs/ca6129-ad-v2"
set -u
unset conda_hook
"$root/envs/ca6129-ad-v2/bin/python" -I -B "$incoming/scripts/experiments_tc2_gpu.py" publish --root "$root" --incoming "$incoming" --stage 'I1_seed17' --record "$stage_record"
submission_source="$root/scripts/slurm/experiments_tc2_gpu.sh"
submission_script="$stage_record/submission_lf.sh"
submission_hashes="$stage_record/submission.sha256"
[[ -f "$submission_source" && ! -L "$submission_source" ]] || exit 2
[[ ! -e "$submission_script" && ! -L "$submission_script" && ! -e "$submission_hashes" && ! -L "$submission_hashes" ]] || exit 2
( set -o noclobber; sed 's/\r$//' "$submission_source" > "$submission_script" )
[[ -s "$submission_script" ]] || exit 2
if LC_ALL=C grep -q $'\r' "$submission_script"; then echo 'Experiment submission contains a carriage return.' >&2; exit 2; fi
bash -n "$submission_script"
( set -o noclobber; sha256sum -- "$submission_source" "$submission_script" > "$submission_hashes" )
cat -- "$submission_hashes"
cd -- "$root"
[[ "$(pwd -P)" == "$root" ]] || { echo 'Experiment submission directory differs from the verified project root.' >&2; exit 2; }
echo "Experiment submission directory: $(pwd -P)"
job_id=$(sbatch --chdir="$root" --parsable --partition=MGPU-TC2 --qos=normal --cpus-per-task=2 --mem=8G --time=00:15:00 --export="ALL,TC2_EXPERIMENT_STAGE_DIR=run/validation_tc2_gpu/experiments_stage_20261019_143232_402d0468,TC2_EXPERIMENT_STAGE=I1_seed17" --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_experiments_I1_seed17_job.txt"
echo "TC2_JOB_ID=$job_id"
for attempt in 1 2 3 4; do
    [[ -n "$(squeue --noheader --jobs="$job_id" --format=%i)" ]] || break
    sleep 10
done
