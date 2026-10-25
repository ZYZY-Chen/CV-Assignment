archive="$root/_downloads/experiments-files-__RUNID__.tar"
incoming="$root/tmp/experiments-files-__RUNID__"
stage_record="$root/run/validation_tc2_gpu/experiments_stage___RUNID__"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" "$archive" "$incoming" '__BUNDLEHASH__' '__MANIFEST__' <<'EXPERIMENTS_BOOTSTRAP_PY'
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
"$root/envs/ca6129-ad-v2/bin/python" -I -B "$incoming/scripts/experiments_tc2_gpu.py" publish --root "$root" --incoming "$incoming" --stage '__STAGE__' --record "$stage_record"
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
job_id=$(sbatch --chdir="$root" --parsable --partition=MGPU-TC2 --qos=normal __RESOURCES__ --export="ALL,TC2_EXPERIMENT_STAGE_DIR=run/validation_tc2_gpu/experiments_stage___RUNID__,TC2_EXPERIMENT_STAGE=__STAGE__" --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_experiments___STAGE___job.txt"
