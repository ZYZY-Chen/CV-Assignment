"""Add only the approved experiment actions to the preserved PowerShell helper."""
import hashlib
import json
from pathlib import Path

AUDIT = Path(__file__).parent
HELPER = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1")
before = (AUDIT / "tc2_gpu_setup.before.ps1").read_bytes()
assert hashlib.sha256(before).hexdigest().upper() == "78F6AAA1940745C6014FDA780E8D50829EDE511463210FEE6F2A49934A9B04FC"

function = r'''
function Receive-Experiments([string]$experimentsJobId) {
    if ($experimentsJobId -notmatch '^[0-9]+$') { throw 'A numeric experiment job ID is required.' }
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw 'Supply -PythonExecutable with an available Python 3.10+ executable.' }
    $collector = Join-Path $CodeRoot 'scripts/collect_experiments_tc2_gpu.py'
    if (-not (Test-Path -LiteralPath $collector -PathType Leaf)) { throw 'The approved experiment collector is missing locally.' }
    $collectorHash = (Get-FileHash -LiteralPath $collector -Algorithm SHA256).Hash.ToLowerInvariant()
    $available = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($localRoot))).AvailableFreeSpace
    if ($available -lt 8589934592) { throw 'Experiment collection requires at least 8 GiB of local free space.' }
    $experimentsCollect = @'
job_id=__JOBID__
echo '[Personal queue]'
squeue --user=huajie001
echo "TC2_JOB_ID=$job_id"
sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList,AllocCPUS,ReqMem,MaxRSS,TotalCPU || true
for log in "$root/run/validation_tc2_gpu/slurm-$job_id.out" "$root/run/validation_tc2_gpu/slurm-$job_id.err"; do
    if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
done
collector="$root/scripts/collect_experiments_tc2_gpu.py"
[[ -f "$collector" && ! -L "$collector" && "$(sha256sum "$collector" | cut -d' ' -f1)" == __COLLECTORHASH__ ]] || { echo 'Experiment collector fingerprint differs; no export executed.' >&2; exit 2; }
directory="$root/tmp/experiments-$job_id-__RUNID__"
[[ ! -e "$directory" && ! -L "$directory" ]] || exit 2
export_json=$("$root/envs/ca6129-ad-v2/bin/python" -I -B "$collector" export --root "$root" --job-id "$job_id" --directory "$directory")
printf '%s' "$export_json" | "$root/envs/ca6129-ad-v2/bin/python" -I -B -c 'import json,re,sys; v=json.load(sys.stdin); assert v["job_id"] == sys.argv[1]; assert v["directory"] == sys.argv[2]; assert v["index_path"] == sys.argv[2]+"/index.json"; assert re.fullmatch("[0-9a-fA-F]{64}",v["index_sha256"]); assert 1 <= len(v["pages"]) <= 32; print("EXPERIMENTS_INDEX_PATH="+v["index_path"]); print("EXPERIMENTS_INDEX_SHA256="+v["index_sha256"].upper()); print("EXPERIMENTS_PAGE_COUNT="+str(len(v["pages"]))); print("EXPERIMENTS_PARTIAL="+str(v["partial"]))' "$job_id" "$directory"
'@
    $experimentsCollect = $experimentsCollect.Replace('__JOBID__',$experimentsJobId).Replace('__RUNID__',$runId).Replace('__COLLECTORHASH__',$collectorHash)
    $logStart = [IO.File]::ReadAllText($logPath).Length
    Ssh ($guard + "`n" + $experimentsCollect)
    $newLog = [IO.File]::ReadAllText($logPath).Substring($logStart)
    $pathMarkers = [regex]::Matches($newLog,'(?m)^EXPERIMENTS_INDEX_PATH=([^\r\n]+)\r?$')
    $hashMarkers = [regex]::Matches($newLog,'(?m)^EXPERIMENTS_INDEX_SHA256=([0-9A-F]{64})\r?$')
    $countMarkers = [regex]::Matches($newLog,'(?m)^EXPERIMENTS_PAGE_COUNT=([0-9]+)\r?$')
    if ($pathMarkers.Count -ne 1 -or $hashMarkers.Count -ne 1 -or $countMarkers.Count -ne 1) { throw 'Experiment export metadata is missing or ambiguous; no download attempted.' }
    $remoteDirectory = $remoteRoot + '/tmp/experiments-' + $experimentsJobId + '-' + $runId
    $expectedIndex = $remoteDirectory + '/index.json'
    if ($pathMarkers[0].Groups[1].Value -cne $expectedIndex) { throw 'Unexpected experiment index path; no download attempted.' }
    $pageCount = [int]$countMarkers[0].Groups[1].Value
    if ($pageCount -lt 1 -or $pageCount -gt 32) { throw 'Experiment page count exceeds the transfer bound.' }
    $indexHash = $hashMarkers[0].Groups[1].Value
    $indexPath = Join-Path $localRoot 'experiments-index.json'
    Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',($server + ':' + $expectedIndex),$indexPath)
    if ((Get-Item -LiteralPath $indexPath).Length -gt 4194304 -or (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash -cne $indexHash) { throw 'Experiment index SHA256 or size differs; no pages downloaded.' }
    Native $PythonExecutable @('-I','-B',$collector,'verify-index','--index',$indexPath,'--sha256',$indexHash,'--job-id',$experimentsJobId)
    $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
    $pages = @($index.pages)
    if ($pages.Count -ne $pageCount) { throw 'Verified experiment index page count differs.' }
    $destination = Join-Path $localRoot 'remote'
    $null = New-Item -ItemType Directory -Path $destination
    $number = 0
    foreach ($page in $pages) {
        $number += 1
        $name = 'page_{0:D3}.tar.gz' -f $number
        if ($page.name -cne $name -or $page.page_number -ne $number -or $page.sha256 -notmatch '^[0-9A-Fa-f]{64}$' -or [long]$page.bytes -le 0 -or [long]$page.bytes -gt 536870912) { throw 'Verified experiment page metadata differs from the bounded sequential layout.' }
        $archivePath = Join-Path $localRoot $name
        if (Test-Path -LiteralPath $archivePath) { throw 'Experiment page archive already exists locally.' }
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',($server + ':' + $remoteDirectory + '/' + $name),$archivePath)
        if ((Get-Item -LiteralPath $archivePath).Length -ne [long]$page.bytes -or (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $page.sha256) { throw 'Experiment page size or SHA256 differs; no extraction performed.' }
        Native $PythonExecutable @('-I','-B',$collector,'verify','--archive',$archivePath,'--sha256',$page.sha256,'--job-id',$experimentsJobId,'--destination',(Join-Path $destination ('page_{0:D3}' -f $number)),'--index',$indexPath)
    }
    Native $PythonExecutable @('-I','-B',$collector,'verify-collection','--index',$indexPath,'--directory',$destination,'--job-id',$experimentsJobId)
    Log ('All ' + $pageCount + ' experiment pages downloaded and independently verified. Index SHA256=' + $indexHash)
    Log 'A queued, running or partial snapshot is not acceptance. Verify the completed stage and all collection pages before the next stage.'
}
'''

branch = r'''    if ($Action -eq 'RunExperiments') {
        if (-not $Stage) { throw 'RunExperiments requires an explicit -Stage from the frozen stage list.' }
        $files = @('configs/experiments_tc2_gpu.json','scripts/experiments_tc2_gpu.py','scripts/analyze_scores_tc2_gpu.py','scripts/slurm/experiments_tc2_gpu.sh','scripts/collect_experiments_tc2_gpu.py','tests/test_experiments_tc2_gpu.py','docs/TC2_GPU_EXPERIMENTS.md')
        $configPath = Join-Path $CodeRoot 'configs/experiments_tc2_gpu.json'
        $design = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        $scientific = @($design.scientific_source_hashes.PSObject.Properties)
        $pilot = @($design.pilot_source_hashes.PSObject.Properties)
        if ($design.accepted_workflow_job_id -ne '44012' -or $design.accepted_pilot_job_id -ne '44024' -or $scientific.Count -ne 31 -or $pilot.Count -ne 6) { throw 'Experiments must bind workflow job 44012, pilot job 44024 and their complete source fingerprints.' }
        foreach ($entry in ($scientific + $pilot)) {
            if ($entry.Name -match '(^/|\\|:|(^|/)\.\.(/|$))' -or $entry.Value -notmatch '^[0-9A-Fa-f]{64}$') { throw 'Unsafe accepted-source entry in experiment configuration.' }
            if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot $entry.Name) -Algorithm SHA256).Hash -ne $entry.Value) { throw ('Accepted scientific or pilot source changed: ' + $entry.Name) }
        }
        $stages = @($design.stages | Where-Object { $_.stage_id -ceq $Stage })
        if ($stages.Count -ne 1) { throw 'The requested stage must occur exactly once in the frozen experiment configuration.' }
        $selected = $stages[0]
        $resource = $selected.resources
        $fit = $selected.kind -ceq 'fit'
        if (($selected.kind -cne 'fit' -and $selected.kind -cne 'analysis') -or $resource.partition -cne 'MGPU-TC2' -or $resource.qos -cne 'normal' -or $resource.nodes -ne 1 -or $resource.tasks -ne 1 -or $resource.cpus_per_task -ne 2) { throw 'Experiment stage resource identity differs.' }
        if ($fit) {
            if ($resource.gpus -ne 1 -or $resource.memory_gib -ne 24 -or $resource.time_limit -cne '02:00:00') { throw 'Fit stages require exactly one GPU, two CPUs, 24 GiB and two hours.' }
            $resourceArguments = '--gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00'
        } else {
            if ($resource.gpus -ne 0 -or $resource.memory_gib -ne 8 -or $resource.time_limit -cne '00:15:00') { throw 'Analysis stages require zero GPUs, two CPUs, 8 GiB and fifteen minutes.' }
            $resourceArguments = '--cpus-per-task=2 --mem=8G --time=00:15:00'
        }
        $payload = Join-Path $localRoot 'experiments_payload'
        $hashLines = @()
        foreach ($relative in $files) {
            $target = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
            Copy-Item -LiteralPath (Join-Path $CodeRoot $relative) -Destination $target
            $hashLines += (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative
        }
        $manifestText = ($hashLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'experiments.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'experiments-files.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','experiments.sha256') + $files)
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log ('LOCAL VALIDATION ONLY. Seven-file experiment bundle built for stage ' + $Stage + '; no connection or submission.'); exit 0 }
        $headDesign = [ordered]@{ accepted_workflow_job_id=$design.accepted_workflow_job_id; accepted_pilot_job_id=$design.accepted_pilot_job_id; scientific_source_hashes=$design.scientific_source_hashes; pilot_source_hashes=$design.pilot_source_hashes; stages=@([ordered]@{stage_id=$selected.stage_id; predecessor=$selected.predecessor}); design_sha256=(Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash }
        $configEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($headDesign | ConvertTo-Json -Depth 8 -Compress)))
        $experimentsPreflight = @'
cd -- "$root"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" '__CONFIG__' '__STAGE__' <<'EXPERIMENTS_PREFLIGHT_PY'
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
[[ ! -e "$root/_downloads/experiments-files-__RUNID__.tar" && ! -L "$root/_downloads/experiments-files-__RUNID__.tar" ]] || { echo 'Experiment upload target already exists; no overwrite.' >&2; exit 2; }
'@
        $experimentsPreflight = $experimentsPreflight.Replace('__CONFIG__',$configEncoded).Replace('__STAGE__',$Stage).Replace('__RUNID__',$runId)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $experimentsPreflight)
        $remoteBundle = $remoteRoot + '/_downloads/experiments-files-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $experimentsStage = @'
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
'@
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $experimentsStage = $experimentsStage.Replace('__RUNID__',$runId).Replace('__STAGE__',$Stage).Replace('__RESOURCES__',$resourceArguments).Replace('__BUNDLEHASH__',$bundleHash).Replace('__MANIFEST__',$manifestEncoded)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $experimentsStage + "`n" + $wait)
        $submittedLog = [IO.File]::ReadAllText($logPath)
        $jobMarkers = [regex]::Matches($submittedLog,'(?m)^TC2_JOB_ID=([0-9]+)\r?$')
        if ($jobMarkers.Count -ne 1) { throw 'Experiment submission ID is missing or ambiguous; inspect the terminal before collecting.' }
        Receive-Experiments $jobMarkers[0].Groups[1].Value
        Log 'Experiment stage submission complete. Do not resubmit a queued or running job; use CollectExperiments with the printed job ID.'
    } elseif ($Action -eq 'CollectExperiments') {
        if ($ValidateOnly) { throw 'CollectExperiments requires a real read-only collection; use RunExperiments -Stage B0 -ValidateOnly for offline packaging.' }
        if (-not $JobId) { throw 'CollectExperiments requires -JobId from the experiment submission output.' }
        Receive-Experiments $JobId
    } elseif ($Action -eq 'RunPilot') {'''

newline = "\r\n" if b"\r\n" in before else "\n"
text = before.decode("utf-8")
replacements = [
    ("'RunPilot','CollectPilot')]", "'RunPilot','CollectPilot','RunExperiments','CollectExperiments')]"),
    ("    [ValidatePattern('^[0-9]*$')][string]$JobId = '',", "    [ValidatePattern('^[0-9]*$')][string]$JobId = ''," + newline + "    [Alias('Stage')][ValidateSet('B0','H1','H2','C1','I1_seed17','R0','C1R','C2','F1','I1_all_seeds','I2','B0_LOCO')][string]$ExperimentStage = '',"),
    ("$guard = @'", function.replace("\n", newline) + newline + "$guard = @'"),
    ("    if ($Action -eq 'RunPilot') {", branch.replace("$Stage", "$ExperimentStage").replace("\n", newline)),
]
for old, new in replacements:
    assert text.count(old) == 1, old
    text = text.replace(old, new, 1)
after = text.encode("utf-8")
current = HELPER.read_bytes()
previous_record = AUDIT / "helper_changes.json"
known = json.loads(previous_record.read_text()) if previous_record.exists() else {}
if current != before and hashlib.sha256(current).hexdigest().upper() != known.get("after_sha256"):
    raise RuntimeError("Helper differs from the baseline or known additive revision; refuse overwrite")
HELPER.write_bytes(after)
reverse = text
for old, new in reversed(replacements):
    assert reverse.count(new) == 1
    reverse = reverse.replace(new, old, 1)
assert reverse.encode("utf-8") == before
(AUDIT / "helper_changes.json").write_text(json.dumps({
    "before_sha256": hashlib.sha256(before).hexdigest().upper(),
    "after_sha256": hashlib.sha256(after).hexdigest().upper(),
    "all_preexisting_bytes_preserved": True,
    "changes": [{"before": old, "after": new} for old, new in replacements],
    "actual_tc2_connections": 0,
    "actual_slurm_submissions": 0,
}, indent=2) + "\n", encoding="utf-8")
print("Approved experiment helper additions applied; all old bytes reversible exactly.")
