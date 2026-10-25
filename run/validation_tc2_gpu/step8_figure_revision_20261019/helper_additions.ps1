function Receive-FigureRevision([string]$figureJobId) {
    if ($figureJobId -notmatch '^[0-9]{1,12}$' -or $ValidateOnly -or $ExperimentStage -or $PreparationGpu -ne 0) { throw 'Figure collection requires one job ID and accepts no stage, GPU or ValidateOnly option.' }
    $collector = Join-Path $CodeRoot 'scripts/collect_figure_revision_tc2_gpu.py'
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf) -or -not (Test-Path -LiteralPath $collector -PathType Leaf)) { throw 'Figure collection requires the approved collector and an available Python executable.' }
    $collectorHash = (Get-FileHash -LiteralPath $collector -Algorithm SHA256).Hash.ToLowerInvariant()
    if (([IO.DriveInfo]::new([IO.Path]::GetPathRoot($localRoot))).AvailableFreeSpace -lt 2147483648) { throw 'Figure collection requires at least 2 GiB of local free space.' }
    $figureCollect = @'
job_id=__JOBID__
echo '[Personal queue]'
squeue --user=huajie001
echo "TC2_JOB_ID=$job_id"
sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList,AllocCPUS,ReqMem,MaxRSS,TotalCPU || true
for log in "$root/run/validation_tc2_gpu/slurm-$job_id.out" "$root/run/validation_tc2_gpu/slurm-$job_id.err"; do
    if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
done
collector="$root/scripts/collect_figure_revision_tc2_gpu.py"
[[ -f "$collector" && ! -L "$collector" && "$(sha256sum "$collector" | cut -d' ' -f1)" == __COLLECTORHASH__ ]] || { echo 'Figure collector fingerprint differs; no export executed.' >&2; exit 2; }
directory="$root/tmp/figure-revision-$job_id-__RUNID__"
[[ ! -e "$directory" && ! -L "$directory" ]] || exit 2
export_json=$("$root/envs/ca6129-ad-v2/bin/python" -I -B "$collector" export --root "$root" --job-id "$job_id" --destination "$directory")
printf '%s' "$export_json" | "$root/envs/ca6129-ad-v2/bin/python" -I -B -c 'import json,re,sys; v=json.load(sys.stdin); assert v["job_id"]==sys.argv[1]; assert v["directory"]==sys.argv[2]; assert v["index_path"]==sys.argv[2]+"/index.json"; assert re.fullmatch("[0-9a-fA-F]{64}",v["index_sha256"]); assert v["page_count"]==1; print("FIGURE_INDEX_PATH="+v["index_path"]); print("FIGURE_INDEX_SHA256="+v["index_sha256"].upper()); print("FIGURE_PARTIAL="+str(v["partial"]))' "$job_id" "$directory"
'@
    $figureCollect = $figureCollect.Replace('__JOBID__',$figureJobId).Replace('__RUNID__',$runId).Replace('__COLLECTORHASH__',$collectorHash)
    $logStart = [IO.File]::ReadAllText($logPath).Length
    Ssh ($guard + "`n" + $figureCollect)
    $newLog = [IO.File]::ReadAllText($logPath).Substring($logStart)
    $paths = [regex]::Matches($newLog,'(?m)^FIGURE_INDEX_PATH=([^\r\n]+)\r?$')
    $hashes = [regex]::Matches($newLog,'(?m)^FIGURE_INDEX_SHA256=([0-9A-F]{64})\r?$')
    $remoteDirectory = $remoteRoot + '/tmp/figure-revision-' + $figureJobId + '-' + $runId
    if ($paths.Count -ne 1 -or $hashes.Count -ne 1 -or $paths[0].Groups[1].Value -cne ($remoteDirectory + '/index.json')) { throw 'Figure index metadata is missing, ambiguous or unexpected; no download attempted.' }
    $indexHash = $hashes[0].Groups[1].Value
    $indexPath = Join-Path $localRoot 'figure-revision-index.json'
    Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',($server + ':' + $remoteDirectory + '/index.json'),$indexPath)
    if ((Get-Item -LiteralPath $indexPath).Length -gt 8388608 -or (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash -cne $indexHash) { throw 'Figure index size or SHA256 differs.' }
    Native $PythonExecutable @('-I','-B',$collector,'verify-index','--index',$indexPath,'--sha256',$indexHash,'--job-id',$figureJobId)
    $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
    $pages = @($index.pages)
    if ($pages.Count -ne 1) { throw 'Figure collection requires exactly one bounded page.' }
    $page = $pages[0]
    if ($page.name -cne 'page_001.tar.gz' -or $page.page_number -ne 1 -or $page.sha256 -notmatch '^[0-9A-Fa-f]{64}$' -or [long]$page.bytes -le 0 -or [long]$page.bytes -gt 536870912) { throw 'Unsafe figure page metadata.' }
    $archivePath = Join-Path $localRoot 'page_001.tar.gz'
    if (Test-Path -LiteralPath $archivePath) { throw 'Figure archive already exists locally.' }
    Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',($server + ':' + $remoteDirectory + '/page_001.tar.gz'),$archivePath)
    if ((Get-Item -LiteralPath $archivePath).Length -ne [long]$page.bytes -or (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $page.sha256) { throw 'Figure page size or SHA256 differs; no extraction performed.' }
    $destination = Join-Path $localRoot 'remote'
    $null = New-Item -ItemType Directory -Path $destination
    Native $PythonExecutable @('-I','-B',$collector,'verify','--index',$indexPath,'--page-id','1','--archive',$archivePath,'--sha256',$page.sha256,'--job-id',$figureJobId,'--destination',(Join-Path $destination 'page_001'))
    Native $PythonExecutable @('-I','-B',$collector,'verify-collection','--index',$indexPath,'--directory',$destination,'--job-id',$figureJobId)
    Log ('Figure revision snapshot downloaded and verified. Index SHA256=' + $indexHash)
    Log 'A partial snapshot is not acceptance. Step 8 still requires a completed CPU job, exact data invariance and visual review of all 15 revised PNG/PDF pairs.'
}

function Run-FigureRevision {
    if ($JobId -or $ExperimentStage -or $PreparationGpu -ne 0) { throw 'RunFigureRevision accepts no job, stage or GPU option.' }
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw 'An available Python executable is required.' }
    $files = @('configs/figure_revision_tc2_gpu.json','scripts/revise_figures_tc2_gpu.py','scripts/collect_figure_revision_tc2_gpu.py','scripts/slurm/figure_revision_tc2_gpu.sh','tests/test_figure_revision_tc2_gpu.py','docs/TC2_GPU_FIGURE_REVISION.md')
    foreach ($relative in $files) { if (-not (Test-Path -LiteralPath (Join-Path $CodeRoot $relative) -PathType Leaf)) { throw ('Missing figure revision source: ' + $relative) } }
    $analysisInput = $InputDirectory
    if (-not $analysisInput) { $analysisInput = Join-Path $PSScriptRoot 'tc2_gpu_setup_20261019_220347_4dc4d911/remote/page_001/run/tc2_gpu/summaries/analysis/6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C' }
    $planPath = Join-Path $localRoot 'figure-revision-plan.json'
    Native $PythonExecutable @('-I','-B',(Join-Path $CodeRoot 'scripts/revise_figures_tc2_gpu.py'),'plan','--root',$CodeRoot,'--analysis-root',$analysisInput,'--output',$planPath)
    $planHash = (Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash
    $plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
    if ($plan.identity -notmatch '^[0-9A-F]{64}$' -or (@($plan.figure_revision_sources.PSObject.Properties.Name | Sort-Object) -join "`n") -cne (($files | Sort-Object) -join "`n")) { throw 'Figure plan source set differs from the approved six files.' }
    $payload = Join-Path $localRoot 'figure_revision_payload'
    $null = New-Item -ItemType Directory -Path $payload
    $hashLines = @()
    foreach ($relative in $files) {
        $target = Join-Path $payload $relative
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
        Copy-Item -LiteralPath (Join-Path $CodeRoot $relative) -Destination $target
        $fingerprint = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($fingerprint -cne $plan.figure_revision_sources.$relative) { throw ('Figure source changed after planning: ' + $relative) }
        $hashLines += $fingerprint.ToLowerInvariant() + '  ' + $relative
    }
    Copy-Item -LiteralPath $planPath -Destination (Join-Path $payload 'plan.json')
    if ((Get-FileHash -LiteralPath (Join-Path $payload 'plan.json') -Algorithm SHA256).Hash -cne $planHash) { throw 'Copied figure plan fingerprint differs.' }
    $hashLines += $planHash.ToLowerInvariant() + '  plan.json'
    [IO.File]::WriteAllText((Join-Path $payload 'figure_revision.sha256'),($hashLines -join "`n") + "`n",$utf8)
    $bundle = Join-Path $localRoot 'figure-revision-files.tar'
    Native $tar (@('-cf',$bundle,'-C',$payload,'--','figure_revision.sha256','plan.json') + $files)
    if ((Get-Item -LiteralPath $bundle).Length -gt 16777216) { throw 'Figure revision bundle exceeds 16 MiB.' }
    $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ValidateOnly) {
        $result = [ordered]@{status='validated_package';step_8_complete=$false;identity=$plan.identity;plan_sha256=$planHash;bundle_sha256=$bundleHash.ToUpperInvariant();sources=$files;actual_tc2_connections=0;actual_slurm_submissions=0}
        [IO.File]::WriteAllText((Join-Path $localRoot 'figure-revision-package-validation.json'),($result | ConvertTo-Json -Depth 5) + "`n",$utf8)
        Log 'Figure revision package verified locally. No remote action was performed.'
        return
    }
    $preflight = @'
upload="$root/_downloads/figure-revision-files-__RUNID__.tar"
[[ ! -e "$upload" && ! -L "$upload" ]] || { echo 'Figure upload target exists; no overwrite.' >&2; exit 2; }
pointer="$root/run/validation_tc2_gpu/last_figure_revision_job.txt"
[[ ! -e "$pointer" && ! -L "$pointer" ]] || { echo 'A figure revision submission is already recorded. Use CollectFigureRevision; no duplicate job.' >&2; exit 2; }
original="$root/run/tc2_gpu/summaries/analysis/6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C"
[[ -d "$original" && ! -L "$original" && "$(readlink -m -- "$original")" == "$original" && -f "$original/SUCCESS" && ! -L "$original/SUCCESS" ]] || exit 2
[[ -f "$original/artifacts.sha256" && ! -L "$original/artifacts.sha256" && "$(sha256sum "$original/artifacts.sha256" | cut -d' ' -f1)" == 1b5326ee8eb707e75bcd3f043b3479dcd8c6472ecb78fa770f0b2c618d5c33da ]] || exit 2
'@
    Ssh ($guard + "`n" + $noOtherJobs + "`n" + $preflight.Replace('__RUNID__',$runId))
    Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteRoot + '/_downloads/figure-revision-files-' + $runId + '.tar'))
    $figureStage = @'
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" __RUNID__ __BUNDLEHASH__ __PLANHASH__ <<'FIGURE_BOOTSTRAP_PY'
from pathlib import Path, PurePosixPath
import hashlib, json, os, re, stat, sys, tarfile
root,run_id,bundle_hash,plan_hash=Path(sys.argv[1]),*sys.argv[2:]
files={'configs/figure_revision_tc2_gpu.json','scripts/revise_figures_tc2_gpu.py','scripts/collect_figure_revision_tc2_gpu.py','scripts/slurm/figure_revision_tc2_gpu.sh','tests/test_figure_revision_tc2_gpu.py','docs/TC2_GPU_FIGURE_REVISION.md'}
sha=lambda data:hashlib.sha256(data).hexdigest().upper()
def safe(name):
    value=PurePosixPath(name)
    if value.is_absolute() or value.as_posix()!=name or any(p in ('','.','..') for p in name.split('/')) or '\\' in name or ':' in name:
        raise RuntimeError('Unsafe figure publication path')
    path=root/name
    if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
        raise RuntimeError('Linked figure publication path')
    if path.exists():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise RuntimeError('Nonregular figure publication path')
    return path
archive=safe('_downloads/figure-revision-files-'+run_id+'.tar')
if archive.stat().st_size>16777216 or sha(archive.read_bytes()).lower()!=bundle_hash: raise RuntimeError('Figure bundle fingerprint differs')
data={}
with tarfile.open(archive,'r:') as stream:
    for member in stream:
        safe(member.name)
        if member.name not in files|{'plan.json','figure_revision.sha256'} or member.name in data or not member.isfile() or member.pax_headers or not 0<=member.size<=8388608:
            raise RuntimeError('Unexpected figure bundle member')
        value=stream.extractfile(member).read(member.size+1)
        if len(value)!=member.size: raise RuntimeError('Truncated figure bundle')
        data[member.name]=value
if set(data)!=files|{'plan.json','figure_revision.sha256'}: raise RuntimeError('Incomplete figure bundle')
observed={}
for line in data['figure_revision.sha256'].decode('utf-8').splitlines():
    fingerprint,name=line.split(None,1)
    if name not in files|{'plan.json'} or name in observed or not re.fullmatch('[a-f0-9]{64}',fingerprint) or sha(data[name]).lower()!=fingerprint:
        raise RuntimeError('Figure bundle checksum differs')
    observed[name]=fingerprint.upper()
if set(observed)!=files|{'plan.json'} or observed['plan.json']!=plan_hash: raise RuntimeError('Figure plan binding differs')
plan=json.loads(data['plan.json']); sources={name:observed[name] for name in files}
if plan['figure_revision_sources']!=sources or len(plan['preserved_sources'])!=51: raise RuntimeError('Figure plan binds other sources')
for name,fingerprint in plan['preserved_sources'].items():
    if sha(safe(name).read_bytes())!=fingerprint: raise RuntimeError('Frozen source changed: '+name)
for name in files:
    if name.endswith('.py'): compile(data[name],name,'exec')
    target=safe(name)
    if target.exists() and target.read_bytes()!=data[name]: raise RuntimeError('Conflicting figure source; no overwrite: '+name)
stage_name='run/validation_tc2_gpu/figure_revision_stage_'+run_id
input_name='run/validation_tc2_gpu/figure_revision_inputs_'+run_id
stage=root/stage_name; input_dir=root/input_name
for path in (stage,input_dir):
    if path.exists() or path.is_symlink() or path.resolve()!=path: raise RuntimeError('Figure stage exists or is linked')
for name in files:
    target=safe(name); target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with target.open('xb') as stream: stream.write(data[name]); stream.flush(); os.fsync(stream.fileno())
stage.mkdir(); input_dir.mkdir()
with (input_dir/'plan.json').open('xb') as stream: stream.write(data['plan.json'])
script=data['scripts/slurm/figure_revision_tc2_gpu.sh'].replace(b'\r\n',b'\n')
with (stage/'submission_lf.sh').open('xb') as stream: stream.write(script)
record={'status':'published','figure_revision_sources':sources,'plan_sha256':plan_hash,'submission_source_sha256':sources['scripts/slurm/figure_revision_tc2_gpu.sh'],'submission_sha256':sha(script)}
with (stage/'publication.json').open('x',encoding='utf-8') as stream: json.dump(record,stream,indent=2); stream.write('\n')
print(json.dumps(record),flush=True)
FIGURE_BOOTSTRAP_PY
"$root/envs/ca6129-ad-v2/bin/python" -I -B "$root/scripts/revise_figures_tc2_gpu.py" preflight --root "$root" --plan "$root/run/validation_tc2_gpu/figure_revision_inputs___RUNID__/plan.json"
cd -- "$root"
[[ "$(pwd -P)" == "$root" ]] || exit 2
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root/run/validation_tc2_gpu/last_figure_revision_job.txt" <<'FIGURE_CLAIM_PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
if path.is_symlink() or path.resolve()!=path: raise RuntimeError('Linked figure submission claim')
with path.open('x',encoding='ascii') as stream: stream.write('submission_pending\n')
FIGURE_CLAIM_PY
echo "Figure revision submission directory: $(pwd -P)"
job_id=$(sbatch --parsable --chdir="$root" --partition=MGPU-TC2 --qos=normal --nodes=1 --ntasks=1 --cpus-per-task=2 --mem=8G --time=00:15:00 --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" --export="ALL,TC2_FIGURE_PLAN=run/validation_tc2_gpu/figure_revision_inputs___RUNID__/plan.json,TC2_FIGURE_PLAN_SHA256=__PLANHASH__,TC2_FIGURE_STAGE=run/validation_tc2_gpu/figure_revision_stage___RUNID__" "$root/run/validation_tc2_gpu/figure_revision_stage___RUNID__/submission_lf.sh")
job_id="${job_id%%;*}"
[[ "$job_id" =~ ^[0-9]{1,12}$ ]] || exit 2
[[ -f "$root/run/validation_tc2_gpu/last_figure_revision_job.txt" && ! -L "$root/run/validation_tc2_gpu/last_figure_revision_job.txt" ]] || exit 2
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_figure_revision_job.txt"
'@
    $figureStage = $figureStage.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash).Replace('__PLANHASH__',$planHash)
    $logStart = [IO.File]::ReadAllText($logPath).Length
    Ssh ($guard + "`n" + $noOtherJobs + "`n" + $figureStage + "`n" + $wait)
    $submittedLog = [IO.File]::ReadAllText($logPath).Substring($logStart)
    $jobs = [regex]::Matches($submittedLog,'(?m)^TC2_JOB_ID=([0-9]+)\r?$')
    if ($jobs.Count -ne 1) { throw 'Figure submission ID is missing or ambiguous. Do not resubmit; inspect the submission record.' }
    Receive-FigureRevision $jobs[0].Groups[1].Value
}
