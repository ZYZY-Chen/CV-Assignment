[CmdletBinding()]
param(
    [ValidateSet('Probe','PrepareEnvironment','PrepareInputs','CheckEnvironment','CheckAll','Collect','UploadInputs','RepairActivation','UpdateInputSources','DownloadInputs','CheckMetrics','CheckAlgorithms','CheckWorkflow','RunPilot','CollectPilot','RunExperiments','CollectExperiments')]
    [string]$Action = 'Probe',
    [ValidatePattern('^[0-9]*$')][string]$JobId = '',
    [Alias('Stage')][ValidateSet('B0','H1','H2','C1','I1_seed17','R0','C1R','C2','F1','I1_all_seeds','I2','B0_LOCO')][string]$ExperimentStage = '',
    [ValidateSet(0,1)][int]$PreparationGpu = 0,
    [string]$InputDirectory = '',
    [string]$CodeRoot = 'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code',
    [string]$PythonExecutable = 'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
    [switch]$LocoCollection,
    [switch]$ValidateOnly
)
# Passwords are read only by OpenSSH in this terminal, never by this script.
# Default action: stage the approved files and submit a hardware-only SLURM job.
$ErrorActionPreference = 'Stop'
$server = 'huajie001@10.96.189.12'
$remoteRoot = '/home/mcaai/huajie001/ca6129_v2_setup'
$ssh = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scp = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$tar = Join-Path $env:WINDIR 'System32\tar.exe'
foreach ($program in @($ssh,$scp,$tar)) { if (-not (Test-Path -LiteralPath $program -PathType Leaf)) { throw ('Missing executable: ' + $program) } }
$CodeRoot = (Resolve-Path -LiteralPath $CodeRoot).Path
$runId = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyyMMdd_HHmmss') + '_' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$localRoot = Join-Path $PSScriptRoot ('tc2_gpu_setup_' + $runId)
$null = New-Item -ItemType Directory -Path $localRoot
$logPath = Join-Path $localRoot 'terminal.txt'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$script:artifactText = $null
$script:artifactHash = ''
function Log([string]$value) {
    [IO.File]::AppendAllText($logPath, $value + [Environment]::NewLine, $utf8)
    Write-Host $value
}
function Native([string]$program, [string[]]$nativeArguments) {
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $program @nativeArguments 2>&1 | ForEach-Object { Log ([string]$_) }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($code -ne 0) { throw ('Command failed with exit code ' + $code) }
}
function Receive-Archive {
    if ($null -eq $script:artifactText) { return }
    $archivePath = Join-Path $localRoot 'remote-output.tar.gz'
    [IO.File]::WriteAllBytes($archivePath, [Convert]::FromBase64String($script:artifactText.ToString()))
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $script:artifactHash) { throw 'Downloaded output archive hash mismatch.' }
    $members = @(& $tar -tzf $archivePath)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read output archive.' }
    foreach ($member in $members) {
        if ($member -match '(^/|\\|:|(^|/)\.\.(/|$))' -or $member -notmatch '^(run/setup_tc2_gpu/|run/validation_tc2_gpu/|run/setup_v2/|run/validation_v2/|configs/tc2_gpu\.json$|configs/tc2_setup\.json$|environment-tc2\.yml$|requirements-tc2-lock\.txt$)') {
            throw ('Unexpected output archive member: ' + $member)
        }
    }
    $destination = Join-Path $localRoot 'remote'
    $null = New-Item -ItemType Directory -Path $destination
    Native $tar @('-xzf',$archivePath,'-C',$destination)
    Log ('Downloaded ' + $members.Count + ' output files. SHA256=' + $script:artifactHash)
    Log ('Remote records: ' + $destination)
    $script:artifactText = $null
}
function Ssh([string]$remoteScript) {
    $script:artifactText = $null
    $script:artifactHash = ''
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript.Replace("`r",'') + "`n"))
    $command = "printf '%s' '" + $encoded + "' | base64 -d | bash -l -s"
    if ($command.Length -gt 26000) { throw 'Remote command too long; no connection attempted.' }
    $arguments = @('-T','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','-o','NumberOfPasswordPrompts=1','-o','StrictHostKeyChecking=yes','-p','22',$server,$command)
    Log 'SSH: enter the password in this terminal when requested.'
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $inArtifact = $false
    & $ssh @arguments 2>&1 | ForEach-Object {
        $line = [string]$_
        if ($line -eq '__TC2_ARTIFACT_BEGIN__') {
            $inArtifact = $true
            $script:artifactText = New-Object Text.StringBuilder
        } elseif ($line -eq '__TC2_ARTIFACT_END__') {
            $inArtifact = $false
        } elseif ($inArtifact) {
            if ($line -notmatch '^[A-Za-z0-9+/=]+$') { throw 'Invalid output archive stream.' }
            $null = $script:artifactText.Append($line)
            if ($script:artifactText.Length -gt 90000000) { throw 'Output archive exceeds the transfer limit.' }
        } else {
            if ($line -match '^TC2_ARTIFACT_SHA256=([0-9a-fA-F]{64})$') { $script:artifactHash = $Matches[1].ToUpperInvariant() }
            Log $line
        }
    }
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    Log ('SSH exit code: ' + $exitCode)
    if ($inArtifact) { throw 'Output archive stream was interrupted; no extraction performed.' }
    Receive-Archive
    if ($exitCode -ne 0) { throw 'Remote command failed; see terminal.txt. No next stage was submitted.' }
}

function Receive-Pilot([string]$pilotJobId) {
    if ($pilotJobId -notmatch '^[0-9]+$') { throw 'A numeric pilot job ID is required.' }
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw 'Supply -PythonExecutable with an available Python 3.10+ executable.' }
    $collector = Join-Path $CodeRoot 'scripts/collect_tc2_gpu_pilot.py'
    if (-not (Test-Path -LiteralPath $collector -PathType Leaf)) { throw 'The approved pilot collector is missing locally.' }
    $collectorHash = (Get-FileHash -LiteralPath $collector -Algorithm SHA256).Hash.ToLowerInvariant()
    $available = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($localRoot))).AvailableFreeSpace
    if ($available -lt 2147483648) { throw 'Pilot collection requires at least 2 GiB of local free space.' }
    $pilotCollect = @'
job_id=__JOBID__
echo '[Personal queue]'
squeue --user=huajie001
echo "TC2_JOB_ID=$job_id"
sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList,AllocCPUS,ReqMem,MaxRSS,TotalCPU || true
for log in "$root/run/validation_tc2_gpu/slurm-$job_id.out" "$root/run/validation_tc2_gpu/slurm-$job_id.err"; do
    if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
done
collector="$root/scripts/collect_tc2_gpu_pilot.py"
[[ -f "$collector" && ! -L "$collector" && "$(sha256sum "$collector" | cut -d' ' -f1)" == __COLLECTORHASH__ ]] || { echo 'Pilot collector fingerprint differs; no export executed.' >&2; exit 2; }
archive="$root/tmp/pilot-$job_id-__RUNID__.tar.gz"
[[ ! -e "$archive" && ! -L "$archive" ]] || exit 2
export_json=$("$root/envs/ca6129-ad-v2/bin/python" -I -B "$collector" export --root "$root" --job-id "$job_id" --archive "$archive")
printf '%s' "$export_json" | "$root/envs/ca6129-ad-v2/bin/python" -I -B -c 'import json,re,sys; v=json.load(sys.stdin); assert v["job_id"] == sys.argv[1]; assert v["archive"] == sys.argv[2]; assert re.fullmatch("[0-9a-fA-F]{64}",v["sha256"]); assert type(v["bytes"]) is int and 0 < v["bytes"] <= 536870912; print("PILOT_EXPORT_PATH="+v["archive"]); print("PILOT_EXPORT_SHA256="+v["sha256"].upper()); print("PILOT_EXPORT_BYTES="+str(v["bytes"])); print("PILOT_STATUS="+str(v.get("pilot_status","unknown")))' "$job_id" "$archive"
'@
    $pilotCollect = $pilotCollect.Replace('__JOBID__',$pilotJobId).Replace('__RUNID__',$runId).Replace('__COLLECTORHASH__',$collectorHash)
    $logStart = [IO.File]::ReadAllText($logPath).Length
    Ssh ($guard + "`n" + $pilotCollect)
    $newLog = [IO.File]::ReadAllText($logPath).Substring($logStart)
    $pathMarkers = [regex]::Matches($newLog,'(?m)^PILOT_EXPORT_PATH=([^\r\n]+)\r?$')
    $hashMarkers = [regex]::Matches($newLog,'(?m)^PILOT_EXPORT_SHA256=([0-9A-F]{64})\r?$')
    $sizeMarkers = [regex]::Matches($newLog,'(?m)^PILOT_EXPORT_BYTES=([0-9]+)\r?$')
    if ($pathMarkers.Count -ne 1 -or $hashMarkers.Count -ne 1 -or $sizeMarkers.Count -ne 1) { throw 'Pilot export metadata is missing or ambiguous; no download attempted.' }
    $expectedRemote = $remoteRoot + '/tmp/pilot-' + $pilotJobId + '-' + $runId + '.tar.gz'
    if ($pathMarkers[0].Groups[1].Value -cne $expectedRemote) { throw 'Unexpected pilot export path; no download attempted.' }
    $exportBytes = [long]$sizeMarkers[0].Groups[1].Value
    if ($exportBytes -le 0 -or $exportBytes -gt 536870912) { throw 'Pilot output archive exceeds its transfer bound.' }
    $exportHash = $hashMarkers[0].Groups[1].Value
    $archivePath = Join-Path $localRoot 'pilot-output.tar.gz'
    if (Test-Path -LiteralPath $archivePath) { throw 'Pilot output archive already exists locally.' }
    Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',($server + ':' + $expectedRemote),$archivePath)
    if ((Get-Item -LiteralPath $archivePath).Length -ne $exportBytes -or (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -cne $exportHash) { throw 'Pilot output archive size or SHA256 differs; no extraction performed.' }
    Native $PythonExecutable @('-I','-B',$collector,'verify','--archive',$archivePath,'--sha256',$exportHash,'--job-id',$pilotJobId,'--destination',(Join-Path $localRoot 'remote'))
    Log ('Pilot snapshot downloaded and verified. SHA256=' + $exportHash)
    Log 'A partial snapshot is not acceptance. Step 6 requires a completed job, verified cache and two verified formal results.'
}


function Receive-Experiments([string]$experimentsJobId) {
    if ($experimentsJobId -notmatch '^[0-9]+$') { throw 'A numeric experiment job ID is required.' }
    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw 'Supply -PythonExecutable with an available Python 3.10+ executable.' }
    $collector = Join-Path $CodeRoot 'scripts/collect_experiments_tc2_gpu.py'
    if (-not (Test-Path -LiteralPath $collector -PathType Leaf)) { throw 'The approved experiment collector is missing locally.' }
    $collectorName = 'collect_experiments_tc2_gpu.py'
    $locoPublish = ''
    if ($LocoCollection) {
        $baseHash = 'AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010'
        if ((Get-FileHash -LiteralPath $collector -Algorithm SHA256).Hash -cne $baseHash) { throw 'The frozen experiment collector differs; no LOCO upload attempted.' }
        $collector = Join-Path $CodeRoot 'scripts/collect_experiments_loco_tc2_gpu.py'
        if (-not (Test-Path -LiteralPath $collector -PathType Leaf)) { throw 'The independent LOCO collector is missing locally.' }
    }
    $collectorHash = (Get-FileHash -LiteralPath $collector -Algorithm SHA256).Hash.ToLowerInvariant()
    $available = ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($localRoot))).AvailableFreeSpace
    if ($available -lt 8589934592) { throw 'Experiment collection requires at least 8 GiB of local free space.' }
    if ($LocoCollection) {
        $collectorName = 'collect_experiments_loco_tc2_gpu_' + $collectorHash.Substring(0,16) + '.py'
        $provenance = [ordered]@{schema_version='1.0'; stage_id='B0_LOCO'; job_id=$experimentsJobId; base_collector='scripts/collect_experiments_tc2_gpu.py'; base_collector_sha256=$baseHash; collector='scripts/collect_experiments_loco_tc2_gpu.py'; collector_sha256=$collectorHash.ToUpperInvariant(); remote_collector=('scripts/' + $collectorName); scope='Collection only; existing experiment sources and saved results remain unchanged.'}
        [IO.File]::WriteAllText((Join-Path $localRoot 'loco-collection-provenance.json'),($provenance | ConvertTo-Json -Depth 4) + "`n",$utf8)
        Log ('LOCO_COLLECTION_BASE_SHA256=' + $baseHash)
        Log ('LOCO_COLLECTION_COLLECTOR_SHA256=' + $collectorHash.ToUpperInvariant())
        $uploadCheck = @'
upload="$root/_downloads/loco-collector-__RUNID__.py"
[[ ! -e "$upload" && ! -L "$upload" ]] || { echo 'LOCO upload target already exists; no overwrite.' >&2; exit 2; }
'@
        Ssh ($guard + "`n" + $uploadCheck.Replace('__RUNID__',$runId))
        $remoteUpload = $remoteRoot + '/_downloads/loco-collector-' + $runId + '.py'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$collector,($server + ':' + $remoteUpload))
        $locoPublish = @'
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" __RUNID__ __COLLECTORHASH__ __BASEHASH__ <<'LOCO_COLLECTION_PUBLISH_PY'
from pathlib import Path
import hashlib, os, sys
root, run_id, expected, base_expected = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
base = root / 'scripts/collect_experiments_tc2_gpu.py'
incoming = root / '_downloads' / ('loco-collector-' + run_id + '.py')
target = root / 'scripts' / ('collect_experiments_loco_tc2_gpu_' + expected[:16] + '.py')
if base.is_symlink() or not base.is_file() or hashlib.sha256(base.read_bytes()).hexdigest().upper() != base_expected:
    raise RuntimeError('Frozen base collector differs; no compatibility collector published')
if incoming.is_symlink() or not incoming.is_file() or incoming.stat().st_size > 262144:
    raise RuntimeError('Unsafe or oversized LOCO collector upload')
data = incoming.read_bytes()
if hashlib.sha256(data).hexdigest() != expected:
    raise RuntimeError('Uploaded LOCO collector fingerprint differs')
compile(data, str(target), 'exec')
if target.is_symlink():
    raise RuntimeError('LOCO collector target is a symbolic link')
if target.exists():
    if not target.is_file() or target.read_bytes() != data:
        raise RuntimeError('Existing LOCO collector differs; no overwrite')
else:
    with target.open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
print('LOCO_COLLECTION_REMOTE_COLLECTOR_SHA256=' + expected.upper(), flush=True)
LOCO_COLLECTION_PUBLISH_PY
'@
        $locoPublish = $locoPublish.Replace('__RUNID__',$runId).Replace('__COLLECTORHASH__',$collectorHash).Replace('__BASEHASH__',$baseHash)
    }
    $experimentsCollect = @'
job_id=__JOBID__
echo '[Personal queue]'
squeue --user=huajie001
echo "TC2_JOB_ID=$job_id"
sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList,AllocCPUS,ReqMem,MaxRSS,TotalCPU || true
for log in "$root/run/validation_tc2_gpu/slurm-$job_id.out" "$root/run/validation_tc2_gpu/slurm-$job_id.err"; do
    if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
done
collector="$root/scripts/__COLLECTORNAME__"
[[ -f "$collector" && ! -L "$collector" && "$(sha256sum "$collector" | cut -d' ' -f1)" == __COLLECTORHASH__ ]] || { echo 'Experiment collector fingerprint differs; no export executed.' >&2; exit 2; }
directory="$root/tmp/experiments-$job_id-__RUNID__"
[[ ! -e "$directory" && ! -L "$directory" ]] || exit 2
export_json=$("$root/envs/ca6129-ad-v2/bin/python" -I -B "$collector" export --root "$root" --job-id "$job_id" --directory "$directory" __COLLECTIONSTAGE__)
printf '%s' "$export_json" | "$root/envs/ca6129-ad-v2/bin/python" -I -B -c 'import json,re,sys; v=json.load(sys.stdin); assert v["job_id"] == sys.argv[1]; assert v["directory"] == sys.argv[2]; assert v["index_path"] == sys.argv[2]+"/index.json"; assert re.fullmatch("[0-9a-fA-F]{64}",v["index_sha256"]); assert 1 <= len(v["pages"]) <= 32; print("EXPERIMENTS_INDEX_PATH="+v["index_path"]); print("EXPERIMENTS_INDEX_SHA256="+v["index_sha256"].upper()); print("EXPERIMENTS_PAGE_COUNT="+str(len(v["pages"]))); print("EXPERIMENTS_PARTIAL="+str(v["partial"]))' "$job_id" "$directory"
'@
    $collectionStage = if ($LocoCollection) { '--stage B0_LOCO' } else { '' }
    $experimentsCollect = $experimentsCollect.Replace('__JOBID__',$experimentsJobId).Replace('__RUNID__',$runId).Replace('__COLLECTORHASH__',$collectorHash).Replace('__COLLECTORNAME__',$collectorName).Replace('__COLLECTIONSTAGE__',$collectionStage)
    $logStart = [IO.File]::ReadAllText($logPath).Length
    Ssh ($guard + "`n" + $locoPublish + "`n" + $experimentsCollect)
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

$guard = @'
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
'@
$noOtherJobs = @'
if [[ -n "$(squeue --noheader --user=huajie001 --format=%i)" ]]; then
    echo 'A personal job is already queued or running. Collect it before submitting another setup job.' >&2
    exit 2
fi
'@
$collect = @'
echo '[Personal queue]'
squeue --user=huajie001
if [[ -n "${job_id:-}" ]]; then
    echo "TC2_JOB_ID=$job_id"
    sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList || true
    for log_root in "$root/run/setup_tc2_gpu" "$root/run/validation_tc2_gpu" "$root/run/setup_v2" "$root/run/validation_v2"; do
        for log in "$log_root/slurm-$job_id.out" "$log_root/slurm-$job_id.err"; do
            if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
        done
    done
fi
cd -- "$root"
archive="$root/tmp/collect___RUNID__.tar.gz"
list="$root/tmp/collect___RUNID__.list"
[[ ! -e "$archive" && ! -e "$list" ]] || exit 2
: > "$list"
for record_root in run/setup_tc2_gpu run/validation_tc2_gpu run/setup_v2 run/validation_v2; do
    if [[ -d "$record_root" ]]; then find "$record_root" -type f -print0 >> "$list"; fi
done
for extra in configs/tc2_setup.json configs/tc2_gpu.json environment-tc2.yml requirements-tc2-lock.txt; do
    if [[ -f "$extra" && ! -L "$extra" ]]; then printf '%s\0' "$extra" >> "$list"; fi
done
set +e
tar --null --verbatim-files-from --hard-dereference -czf "$archive" -T "$list"
tar_code=$?
set -e
[[ "$tar_code" -le 1 ]] || exit "$tar_code"
[[ "$(stat -c %s -- "$archive")" -le 67108864 ]] || { echo 'Output archive exceeds 64 MiB.' >&2; exit 2; }
echo "TC2_ARTIFACT_SHA256=$(sha256sum "$archive" | cut -d' ' -f1)"
echo __TC2_ARTIFACT_BEGIN__
base64 -w 76 -- "$archive"
echo __TC2_ARTIFACT_END__
'@
$collect = $collect.Replace('__RUNID__',$runId)
$wait = @'
echo "TC2_JOB_ID=$job_id"
for attempt in 1 2 3 4; do
    [[ -n "$(squeue --noheader --jobs="$job_id" --format=%i)" ]] || break
    sleep 10
done
'@
Log ('TC2 GPU: ' + $Action)
Log ('Local output: ' + $localRoot)
Log 'A submitted or running job is not a passed check. Passwords are not stored.'
try {
    if ($LocoCollection -and $Action -ne 'CollectExperiments') { throw '-LocoCollection is valid only with -Action CollectExperiments.' }
    if ($Action -eq 'RunExperiments') {
        if (-not $ExperimentStage) { throw 'RunExperiments requires an explicit -Stage from the frozen stage list.' }
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
        $stages = @($design.stages | Where-Object { $_.stage_id -ceq $ExperimentStage })
        if ($stages.Count -ne 1) { throw 'The requested stage must occur exactly once in the frozen experiment configuration.' }
        $selected = $stages[0]
        $resource = $selected.resources
        $fit = $selected.kind -ceq 'fit'
        if (($selected.kind -cne 'fit' -and $selected.kind -cne 'analysis') -or $resource.partition -cne 'MGPU-TC2' -or $resource.qos -cne 'normal' -or $resource.nodes -ne 1 -or $resource.tasks -ne 1 -or $resource.cpus_per_task -ne 2) { throw 'Experiment stage resource identity differs.' }
        if ($fit) {
            if ($resource.gpus -ne 1 -or $resource.memory_gib -ne 24 -or $resource.time_limit -cne '02:00:00') { throw 'Fit stages require exactly one GPU, two CPUs, 24 GiB and two hours.' }
            $resourceArguments = '--nodelist=TC2N01 --gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00'
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
        if ($ValidateOnly) { Log ('LOCAL VALIDATION ONLY. Seven-file experiment bundle built for stage ' + $ExperimentStage + '; no connection or submission.'); exit 0 }
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
        $experimentsPreflight = $experimentsPreflight.Replace('__CONFIG__',$configEncoded).Replace('__STAGE__',$ExperimentStage).Replace('__RUNID__',$runId)
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
        $experimentsStage = $experimentsStage.Replace('__RUNID__',$runId).Replace('__STAGE__',$ExperimentStage).Replace('__RESOURCES__',$resourceArguments).Replace('__BUNDLEHASH__',$bundleHash).Replace('__MANIFEST__',$manifestEncoded)
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
    } elseif ($Action -eq 'RunPilot') {
        $files = @('configs/pilot_tc2_gpu.json','scripts/pilot_tc2_gpu.py','scripts/slurm/pilot_tc2_gpu.sh','scripts/collect_tc2_gpu_pilot.py','tests/test_pilot_tc2_gpu.py','docs/TC2_GPU_PILOT.md')
        $pilotConfigPath = Join-Path $CodeRoot 'configs/pilot_tc2_gpu.json'
        $pilotConfig = Get-Content -LiteralPath $pilotConfigPath -Raw | ConvertFrom-Json
        $sourceProperties = @($pilotConfig.workflow_source_hashes.PSObject.Properties)
        if ($pilotConfig.workflow_acceptance_job_id -ne '44012' -or $sourceProperties.Count -ne 31) { throw 'The pilot must bind the 31 scientific sources accepted in workflow job 44012.' }
        foreach ($entry in $sourceProperties) {
            if ($entry.Name -match '(^/|\\|:|(^|/)\.\.(/|$))' -or $entry.Value -notmatch '^[0-9A-Fa-f]{64}$') { throw 'Unsafe accepted-source entry in pilot configuration.' }
            if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot $entry.Name) -Algorithm SHA256).Hash -ne $entry.Value) { throw ('Accepted scientific source changed: ' + $entry.Name) }
        }
        $payload = Join-Path $localRoot 'pilot_payload'
        $hashLines = @()
        foreach ($relative in $files) {
            $target = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
            Copy-Item -LiteralPath (Join-Path $CodeRoot $relative) -Destination $target
            $hashLines += (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative
        }
        $manifestText = ($hashLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'pilot.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'pilot-files.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','pilot.sha256') + $files)
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. Six-file pilot bundle built; no connection or submission.'; exit 0 }
        $configEncoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pilotConfigPath))
        $pilotPreflight = @'
cd -- "$root"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" '__CONFIG__' <<'PILOT_PREFLIGHT_PY'
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
[[ ! -e "$root/_downloads/pilot-files-__RUNID__.tar" && ! -L "$root/_downloads/pilot-files-__RUNID__.tar" ]] || { echo 'Pilot upload target already exists; no overwrite.' >&2; exit 2; }
'@
        $pilotPreflight = $pilotPreflight.Replace('__CONFIG__',$configEncoded).Replace('__RUNID__',$runId)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $pilotPreflight)
        $remoteBundle = $remoteRoot + '/_downloads/pilot-files-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $pilotStage = @'
archive="$root/_downloads/pilot-files-__RUNID__.tar"
incoming="$root/tmp/pilot-files-__RUNID__"
stage_record="$root/run/validation_tc2_gpu/pilot_stage___RUNID__"
"$root/envs/ca6129-ad-v2/bin/python" -I -B - "$root" "$archive" "$incoming" '__BUNDLEHASH__' '__MANIFEST__' <<'PILOT_BOOTSTRAP_PY'
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
job_id=$(sbatch --chdir="$root" --parsable --partition=MGPU-TC2 --qos=normal --gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00 --export="ALL,TC2_PILOT_STAGE=run/validation_tc2_gpu/pilot_stage___RUNID__" --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_pilot_job.txt"
'@
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $pilotStage = $pilotStage.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash).Replace('__MANIFEST__',$manifestEncoded)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $pilotStage + "`n" + $wait)
        $submittedLog = [IO.File]::ReadAllText($logPath)
        $jobMarkers = [regex]::Matches($submittedLog,'(?m)^TC2_JOB_ID=([0-9]+)\r?$')
        if ($jobMarkers.Count -ne 1) { throw 'Pilot submission ID is missing or ambiguous; inspect the terminal before collecting.' }
        Receive-Pilot $jobMarkers[0].Groups[1].Value
        Log 'Real-data pilot submission complete. Do not resubmit a queued or running job; use CollectPilot with the printed job ID.'
    } elseif ($Action -eq 'CollectPilot') {
        if ($ValidateOnly) { throw 'CollectPilot requires a real read-only collection; use RunPilot -ValidateOnly for offline packaging.' }
        if (-not $JobId) { throw 'CollectPilot requires -JobId from the RunPilot submission output.' }
        Receive-Pilot $JobId
    } elseif ($Action -eq 'DownloadInputs') {
        $transferDirectory = if ($InputDirectory) { [IO.Path]::GetFullPath($InputDirectory) } else { Join-Path $CodeRoot ('run/setup_tc2_gpu/input_transfer_' + $runId + '/transfer') }
        if ($ValidateOnly) { Log ('LOCAL VALIDATION ONLY. Planned transfer directory: ' + $transferDirectory); exit 0 }
        if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw 'Supply -PythonExecutable with an available Python 3.10+ executable.' }
        Log ('Local package directory: ' + $transferDirectory)
        Native $PythonExecutable @('-B',(Join-Path $CodeRoot 'scripts/prepare_tc2_gpu_inputs.py'),'--accept-license','--download-only','--transfer-dir',$transferDirectory)
        Log 'Packages downloaded locally only. Frozen input acceptance and GPU checks remain pending.'
    } elseif ($Action -eq 'CheckMetrics') {
        $files = @('src/metric_core.py','src/evaluate.py','src/data.py','tests/test_metrics_tc2_gpu.py','scripts/slurm/check_tc2_gpu_metrics.sh')
        $config = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_setup.json') -Raw | ConvertFrom-Json
        if (-not $config.final_acceptance.step_2_complete) { throw 'Step 2 must be verified before metric acceptance.' }
        $protocol = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/protocol_v2.json') -Raw | ConvertFrom-Json
        $frozenRows = @($config.protocol_sha256.ToLowerInvariant() + '  configs/protocol_v2.json')
        foreach ($manifest in $protocol.data.frozen_manifests) { $frozenRows += $manifest.file_sha256.ToLowerInvariant() + '  ' + $manifest.path }
        foreach ($name in @('environment-tc2.yml','requirements-tc2-lock.txt')) { $frozenRows += $config.final_acceptance.export_hashes.$name.ToLowerInvariant() + '  ' + $name }
        foreach ($row in $frozenRows) {
            $parts = $row -split '\s+',2
            if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot $parts[1]) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $parts[0]) { throw ('Frozen input or actual environment lock differs: ' + $parts[1]) }
        }
        $payload = Join-Path $localRoot 'metrics_payload'
        $hashLines = @()
        foreach ($relative in $files) {
            $target = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
            Copy-Item -LiteralPath (Join-Path $CodeRoot $relative) -Destination $target
            $hashLines += (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative
        }
        $manifestText = ($hashLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'metrics.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'metrics-files.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','metrics.sha256') + $files)
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. Five-file metrics bundle built; no connection or submission.'; exit 0 }
        $metricsPreflight = @'
cd -- "$root"
all_job=$(cat "$(setup_record "last_check_all_job.txt")")
[[ "$all_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"step_2_complete": true' "$(setup_record "job_${all_job}_all/setup_status.json")" || { echo 'Step 2 all-mode acceptance has not passed.' >&2; exit 2; }
printf '%s' '__FROZEN__' | base64 -d | sha256sum --check -
printf '%s' '__MANIFEST__' | base64 -d | while read -r hash relative; do
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py|tests/test_metrics_tc2_gpu.py|scripts/slurm/check_tc2_gpu_metrics.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" ]] || exit 2
        current_hash=$(sha256sum "$target" | cut -d' ' -f1)
        [[ "$current_hash" == "$hash" ]] || metric_source_is_accepted "$relative" "$current_hash" || { echo "Unknown metric source; no overwrite: $relative" >&2; exit 2; }
    fi
done
'@
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $frozenEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($frozenRows -join "`n") + "`n"))
        $metricsPreflight = $metricsPreflight.Replace('__MANIFEST__',$manifestEncoded).Replace('__FROZEN__',$frozenEncoded)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $metricsPreflight)
        $remoteBundle = $remoteRoot + '/_downloads/metrics-files-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $metricsStage = @'
archive="$root/_downloads/metrics-files-__RUNID__.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == __BUNDLEHASH__ ]] || { echo 'Metric bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/metrics-files-__RUNID__"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check metrics.sha256 )
while read -r hash relative; do
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py|tests/test_metrics_tc2_gpu.py|scripts/slurm/check_tc2_gpu_metrics.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" ]] || exit 2
        current_hash=$(sha256sum "$target" | cut -d' ' -f1)
        [[ "$current_hash" == "$hash" ]] || metric_source_is_accepted "$relative" "$current_hash" || { echo "Unknown metric source; no overwrite: $relative" >&2; exit 2; }
    fi
done < "$incoming/metrics.sha256"
mkdir -p -- "$root/run/validation_tc2_gpu"
stage_record="$root/run/validation_tc2_gpu/metrics_stage___RUNID__"
mkdir -- "$stage_record"
cp -- "$incoming/metrics.sha256" "$stage_record/metrics.sha256"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then
        cp --no-clobber -- "$incoming/$relative" "$target"
    elif [[ "$(sha256sum "$target" | cut -d' ' -f1)" != "$hash" ]]; then
        current_hash=$(sha256sum "$target" | cut -d' ' -f1)
        metric_source_is_accepted "$relative" "$current_hash" || exit 2
        mkdir -p -- "$stage_record/source_originals/$(dirname -- "$relative")"
        cp -p -- "$target" "$stage_record/source_originals/$relative"
        cp -- "$incoming/$relative" "$target"
    fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/metrics.sha256"
echo 'Five verified metric test files staged; requesting CPU-only acceptance.'
# Preserve the verified source; submit a separately recorded LF-only copy.
submission_source="$root/scripts/slurm/check_tc2_gpu_metrics.sh"
submission_script="$stage_record/submission_lf.sh"
submission_hashes="$stage_record/submission.sha256"
[[ -f "$submission_source" && ! -L "$submission_source" ]] || exit 2
[[ ! -e "$submission_script" && ! -L "$submission_script" && ! -e "$submission_hashes" && ! -L "$submission_hashes" ]] || exit 2
( set -o noclobber; sed 's/\r$//' "$submission_source" > "$submission_script" )
[[ -s "$submission_script" ]] || exit 2
if LC_ALL=C grep -q $'\r' "$submission_script"; then
    echo 'Submission script contains an unsupported carriage return.' >&2
    exit 2
fi
bash -n "$submission_script"
( set -o noclobber; sha256sum -- "$submission_source" "$submission_script" > "$submission_hashes" )
echo "LF submission script: $submission_script"
cat -- "$submission_hashes"
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_check_metrics_job.txt"
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
'@
        $metricsStage = $metricsStage.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $metricsPreflight + "`n" + $metricsStage + "`n" + $wait + "`n" + $collect)
    } elseif ($Action -eq 'CheckAlgorithms') {
        $files = @('src/padim_adapter.py','src/patchcore_adapter.py','src/sampling.py','src/scoring.py','src/anomaly_postprocess.py','tests/test_algorithms_tc2_gpu.py','scripts/slurm/check_tc2_gpu_algorithms.sh','src/metric_core.py','src/evaluate.py','src/data.py','configs/tc2_gpu.json')
        $config = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_setup.json') -Raw | ConvertFrom-Json
        $naming = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_gpu.json') -Raw | ConvertFrom-Json
        if (-not $config.final_acceptance.step_2_complete -or $naming.workflow_id -ne 'tc2_gpu' -or $naming.frozen_protocol.sha256 -ne $config.protocol_sha256) { throw 'Verified setup or protocol naming map differs.' }
        $protocol = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/protocol_v2.json') -Raw | ConvertFrom-Json
        $frozenRows = @($config.protocol_sha256.ToLowerInvariant() + '  configs/protocol_v2.json')
        foreach ($manifest in $protocol.data.frozen_manifests) { $frozenRows += $manifest.file_sha256.ToLowerInvariant() + '  ' + $manifest.path }
        foreach ($name in @('environment-tc2.yml','requirements-tc2-lock.txt')) { $frozenRows += $config.final_acceptance.export_hashes.$name.ToLowerInvariant() + '  ' + $name }
        foreach ($row in $frozenRows) {
            $parts = $row -split '\s+',2
            if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot $parts[1]) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $parts[0]) { throw ('Frozen file differs: ' + $parts[1]) }
        }
        $payload = Join-Path $localRoot 'algorithms_payload'
        $hashLines = @()
        foreach ($relative in $files) {
            $target = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
            Copy-Item -LiteralPath (Join-Path $CodeRoot $relative) -Destination $target
            $hashLines += (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative
        }
        $manifestText = ($hashLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'algorithms.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'algorithm-files.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','algorithms.sha256') + $files)
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. Eleven-file algorithm bundle built; no connection or submission.'; exit 0 }
        $algorithmPreflight = @'
cd -- "$root"
all_job=$(cat "$(setup_record last_check_all_job.txt)")
[[ "$all_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"step_2_complete": true' "$(setup_record "job_${all_job}_all/setup_status.json")" || exit 2
metric_job=$(cat run/validation_tc2_gpu/last_check_metrics_job.txt)
[[ "$metric_job" =~ ^[0-9]+$ ]] || exit 2
metric_status="$root/run/validation_tc2_gpu/step3_job_${metric_job}/setup_status.json"
[[ -f "$metric_status" && ! -L "$metric_status" ]] || exit 2
grep -Eq '"step_3_complete": true' "$metric_status" || { echo 'Run CheckMetrics and verify its full acceptance before CheckAlgorithms.' >&2; exit 2; }
grep -Eq '"mode": "full"' "$metric_status" || exit 2
grep -Eq '"status": "passed"' "$metric_status" || exit 2
printf '%s' '__FROZEN__' | base64 -d | sha256sum --check -
printf '%s' '__MANIFEST__' | base64 -d | while read -r hash relative; do
    case "$relative" in src/padim_adapter.py|src/patchcore_adapter.py|src/sampling.py|src/scoring.py|src/anomaly_postprocess.py|tests/test_algorithms_tc2_gpu.py|scripts/slurm/check_tc2_gpu_algorithms.sh|src/metric_core.py|src/evaluate.py|src/data.py|configs/tc2_gpu.json) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py)
        [[ -f "$target" ]] || exit 2
        grep -Fiq "\"$relative\": \"$hash\"" "$metric_status" || { echo "Read-only metric dependency changed: $relative" >&2; exit 2; } ;;
    esac
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Existing algorithm source differs; no overwrite: $relative" >&2; exit 2; }
    fi
done
'@
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $frozenEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($frozenRows -join "`n") + "`n"))
        $algorithmPreflight = $algorithmPreflight.Replace('__MANIFEST__',$manifestEncoded).Replace('__FROZEN__',$frozenEncoded)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $algorithmPreflight)
        $remoteBundle = $remoteRoot + '/_downloads/algorithm-files-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $algorithmStage = @'
archive="$root/_downloads/algorithm-files-__RUNID__.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == __BUNDLEHASH__ ]] || { echo 'Algorithm bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/algorithm-files-__RUNID__"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check algorithms.sha256 )
while read -r hash relative; do
    case "$relative" in src/padim_adapter.py|src/patchcore_adapter.py|src/sampling.py|src/scoring.py|src/anomaly_postprocess.py|tests/test_algorithms_tc2_gpu.py|scripts/slurm/check_tc2_gpu_algorithms.sh|src/metric_core.py|src/evaluate.py|src/data.py|configs/tc2_gpu.json) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Unknown algorithm source; no overwrite: $relative" >&2; exit 2; }
    fi
done < "$incoming/algorithms.sha256"
mkdir -p -- "$root/run/validation_tc2_gpu"
stage_record="$root/run/validation_tc2_gpu/algorithms_stage___RUNID__"
mkdir -- "$stage_record"
cp -- "$incoming/algorithms.sha256" "$stage_record/algorithms.sha256"
printf '%s\n' "$metric_job" > "$stage_record/metric_regression_job.txt"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then cp --no-clobber -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/algorithms.sha256"
echo 'Eleven verified algorithm files staged; requesting one GPU for synthetic acceptance.'
# Preserve the verified source; submit a separately recorded LF-only copy.
submission_source="$root/scripts/slurm/check_tc2_gpu_algorithms.sh"
submission_script="$stage_record/submission_lf.sh"
submission_hashes="$stage_record/submission.sha256"
[[ -f "$submission_source" && ! -L "$submission_source" ]] || exit 2
[[ ! -e "$submission_script" && ! -L "$submission_script" && ! -e "$submission_hashes" && ! -L "$submission_hashes" ]] || exit 2
( set -o noclobber; sed 's/\r$//' "$submission_source" > "$submission_script" )
[[ -s "$submission_script" ]] || exit 2
if LC_ALL=C grep -q $'\r' "$submission_script"; then
    echo 'Submission script contains an unsupported carriage return.' >&2
    exit 2
fi
bash -n "$submission_script"
( set -o noclobber; sha256sum -- "$submission_source" "$submission_script" > "$submission_hashes" )
echo "LF submission script: $submission_script"
cat -- "$submission_hashes"
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_check_algorithms_job.txt"
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
'@
        $algorithmStage = $algorithmStage.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $algorithmPreflight + "`n" + $algorithmStage + "`n" + $wait + "`n" + $collect)
    } elseif ($Action -eq 'CheckWorkflow') {
        $files = @('src/tc2_gpu_protocol.py','src/tc2_gpu_cache.py','src/tc2_gpu_runner.py','scripts/run_tc2_gpu.py','configs/runtime_tc2_gpu.json','tests/test_workflow_tc2_gpu.py','scripts/slurm/check_tc2_gpu_workflow.sh','docs/TC2_GPU_WORKFLOW.md','src/padim_adapter.py','src/patchcore_adapter.py','src/sampling.py','src/scoring.py','src/anomaly_postprocess.py','tests/test_algorithms_tc2_gpu.py','scripts/slurm/check_tc2_gpu_algorithms.sh','src/metric_core.py','src/evaluate.py','src/data.py','configs/tc2_gpu.json','tests/test_metrics_tc2_gpu.py','scripts/slurm/check_tc2_gpu_metrics.sh','configs/protocol_v2.json','environment-tc2.yml','requirements-tc2-lock.txt','manifests/manifest_mvtec_ad_bottle.json','manifests/manifest_mvtec_ad_cable.json','manifests/manifest_mvtec_ad_capsule.json','manifests/manifest_mvtec_ad_screw.json','manifests/manifest_mvtec_ad_tile.json','manifests/manifest_mvtec_ad_wood.json','manifests/manifest_mvtec_loco_juice_bottle.json','manifests/manifest_mvtec_loco_screw_bag.json')
        $config = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_setup.json') -Raw | ConvertFrom-Json
        $naming = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_gpu.json') -Raw | ConvertFrom-Json
        $protocol = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/protocol_v2.json') -Raw | ConvertFrom-Json
        if (-not $config.final_acceptance.step_2_complete -or $naming.workflow_id -ne 'tc2_gpu' -or $naming.frozen_protocol.sha256 -ne $config.protocol_sha256) { throw 'Verified setup or naming map differs.' }
        $frozenRows = @($config.protocol_sha256.ToLowerInvariant() + '  configs/protocol_v2.json')
        foreach ($entry in $protocol.data.frozen_manifests) { $frozenRows += $entry.file_sha256.ToLowerInvariant() + '  ' + $entry.path }
        foreach ($name in @('environment-tc2.yml','requirements-tc2-lock.txt')) { $frozenRows += $config.final_acceptance.export_hashes.$name.ToLowerInvariant() + '  ' + $name }
        foreach ($row in $frozenRows) {
            $parts = $row -split '\s+',2
            if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot $parts[1]) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $parts[0]) { throw ('Frozen input or actual environment lock differs: ' + $parts[1]) }
        }
        $payload = Join-Path $localRoot 'workflow_payload'
        $hashLines = @()
        foreach ($relative in $files) {
            $target = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
            Copy-Item -LiteralPath (Join-Path $CodeRoot $relative) -Destination $target
            $hashLines += (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative
        }
        $manifestText = ($hashLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'workflow.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'workflow-files.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','workflow.sha256') + $files)
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. Thirty-two-file workflow bundle built; no connection or submission.'; exit 0 }
        $workflowPreflight = @'
cd -- "$root"
workflow_file_allowed() {
    case "$1" in src/tc2_gpu_protocol.py|src/tc2_gpu_cache.py|src/tc2_gpu_runner.py|scripts/run_tc2_gpu.py|configs/runtime_tc2_gpu.json|tests/test_workflow_tc2_gpu.py|scripts/slurm/check_tc2_gpu_workflow.sh|docs/TC2_GPU_WORKFLOW.md|src/padim_adapter.py|src/patchcore_adapter.py|src/sampling.py|src/scoring.py|src/anomaly_postprocess.py|tests/test_algorithms_tc2_gpu.py|scripts/slurm/check_tc2_gpu_algorithms.sh|src/metric_core.py|src/evaluate.py|src/data.py|configs/tc2_gpu.json|tests/test_metrics_tc2_gpu.py|scripts/slurm/check_tc2_gpu_metrics.sh|configs/protocol_v2.json|environment-tc2.yml|requirements-tc2-lock.txt|manifests/manifest_mvtec_ad_bottle.json|manifests/manifest_mvtec_ad_cable.json|manifests/manifest_mvtec_ad_capsule.json|manifests/manifest_mvtec_ad_screw.json|manifests/manifest_mvtec_ad_tile.json|manifests/manifest_mvtec_ad_wood.json|manifests/manifest_mvtec_loco_juice_bottle.json|manifests/manifest_mvtec_loco_screw_bag.json) return 0 ;; *) return 1 ;; esac
}
all_job=$(cat "$(setup_record last_check_all_job.txt)")
[[ "$all_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"step_2_complete": true' "$(setup_record "job_${all_job}_all/setup_status.json")" || exit 2
metric_job=$(cat run/validation_tc2_gpu/last_check_metrics_job.txt)
algorithm_job=$(cat run/validation_tc2_gpu/last_check_algorithms_job.txt)
[[ "$metric_job" =~ ^[0-9]+$ && "$algorithm_job" =~ ^[0-9]+$ ]] || exit 2
metric_status="$root/run/validation_tc2_gpu/step3_job_${metric_job}/setup_status.json"
algorithm_status="$root/run/validation_tc2_gpu/step4_job_${algorithm_job}/setup_status.json"
for status in "$metric_status" "$algorithm_status"; do
    [[ -f "$status" && ! -L "$status" ]] || exit 2
    grep -Eq '"mode": "full"' "$status" || exit 2
    grep -Eq '"status": "passed"' "$status" || exit 2
done
grep -Eq '"step_3_complete": true' "$metric_status" || exit 2
grep -Eq '"step_4_complete": true' "$algorithm_status" || exit 2
printf '%s' '__FROZEN__' | base64 -d | sha256sum --check -
# Preserve the original remote compatibility snapshot; never upload the local summary.
[[ "$(sha256sum configs/tc2_setup.json | cut -d' ' -f1)" == edf3d1d0380e0105a5173607ce360221fd43b059478915eec0ec04ed9110f913 ]] || { echo 'Unknown remote compatibility configuration; no overwrite.' >&2; exit 2; }
[[ "$(sha256sum weights/resnet18-f37072fd.pth | cut -d' ' -f1)" == __WEIGHTHASH__ ]] || exit 2
printf '%s' '__MANIFEST__' | base64 -d | while read -r hash relative; do
    workflow_file_allowed "$relative" || exit 2
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    case "$relative" in
        src/metric_core.py|src/evaluate.py|src/data.py|tests/test_metrics_tc2_gpu.py|scripts/slurm/check_tc2_gpu_metrics.sh)
            [[ -f "$target" ]] && grep -Fiq "\"$relative\": \"$hash\"" "$metric_status" || exit 2 ;;
        src/padim_adapter.py|src/patchcore_adapter.py|src/sampling.py|src/scoring.py|src/anomaly_postprocess.py|tests/test_algorithms_tc2_gpu.py|scripts/slurm/check_tc2_gpu_algorithms.sh|configs/tc2_gpu.json)
            [[ -f "$target" ]] && grep -Fiq "\"$relative\": \"$hash\"" "$algorithm_status" || exit 2 ;;
    esac
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Unknown workflow source; no overwrite: $relative" >&2; exit 2; }
    fi
done
'@
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $frozenEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($frozenRows -join "`n") + "`n"))
        $workflowPreflight = $workflowPreflight.Replace('__MANIFEST__',$manifestEncoded).Replace('__FROZEN__',$frozenEncoded).Replace('__WEIGHTHASH__',$config.final_acceptance.weights_sha256.ToLowerInvariant())
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $workflowPreflight)
        $remoteBundle = $remoteRoot + '/_downloads/workflow-files-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $workflowStage = @'
archive="$root/_downloads/workflow-files-__RUNID__.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == __BUNDLEHASH__ ]] || { echo 'Workflow bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/workflow-files-__RUNID__"
mkdir -- "$incoming"
members=$(tar -tf "$archive")
while IFS= read -r relative; do
    [[ "$relative" == workflow.sha256 ]] || workflow_file_allowed "$relative" || exit 2
done <<< "$members"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check workflow.sha256 )
while read -r hash relative; do
    workflow_file_allowed "$relative" || exit 2
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
    fi
done < "$incoming/workflow.sha256"
stage_record="$root/run/validation_tc2_gpu/workflow_stage___RUNID__"
mkdir -- "$stage_record"
cp -- "$incoming/workflow.sha256" "$stage_record/workflow.sha256"
printf '%s\n' "$metric_job" > "$stage_record/metric_regression_job.txt"
printf '%s\n' "$algorithm_job" > "$stage_record/algorithm_acceptance_job.txt"
sha256sum -- configs/tc2_setup.json > "$stage_record/compatibility_configuration.sha256"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then cp --no-clobber -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/workflow.sha256"
echo 'Thirty-two verified workflow files staged; requesting synthetic GPU acceptance.'
# Preserve the verified source; submit a separately recorded LF-only copy.
submission_source="$root/scripts/slurm/check_tc2_gpu_workflow.sh"
submission_script="$stage_record/submission_lf.sh"
submission_hashes="$stage_record/submission.sha256"
[[ -f "$submission_source" && ! -L "$submission_source" ]] || exit 2
[[ ! -e "$submission_script" && ! -L "$submission_script" && ! -e "$submission_hashes" && ! -L "$submission_hashes" ]] || exit 2
( set -o noclobber; sed 's/\r$//' "$submission_source" > "$submission_script" )
[[ -s "$submission_script" ]] || exit 2
if LC_ALL=C grep -q $'\r' "$submission_script"; then
    echo 'Submission script contains an unsupported carriage return.' >&2
    exit 2
fi
bash -n "$submission_script"
( set -o noclobber; sha256sum -- "$submission_source" "$submission_script" > "$submission_hashes" )
echo "LF submission script: $submission_script"
cat -- "$submission_hashes"
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_check_workflow_job.txt"
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
'@
        $workflowStage = $workflowStage.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $workflowPreflight + "`n" + $workflowStage + "`n" + $wait + "`n" + $collect)
        Log 'Workflow completion requires full-mode step_5_complete=true and independent verification of returned artifacts.'
    } elseif ($Action -eq 'Probe') {
        $files = @('configs/protocol_v2.json','configs/tc2_gpu.json','configs/tc2_setup.json','requirements-lock.txt','scripts/check_tc2_gpu_setup.py','scripts/prepare_tc2_gpu_environment.sh','scripts/prepare_tc2_gpu_inputs.py','scripts/slurm/check_tc2_gpu_setup.sh','scripts/slurm/probe_tc2_gpu_hardware.sh','scripts/slurm/prepare_tc2_gpu.sh')
        $protocol = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/protocol_v2.json') -Raw | ConvertFrom-Json
        $config = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_setup.json') -Raw | ConvertFrom-Json
        if (-not $config.preparation.approved -or -not $config.scope.permit_package_install_or_upgrade -or -not $config.scope.permit_dataset_or_weights_download) { throw 'Supplementary approval is missing.' }
        if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot 'configs/protocol_v2.json') -Algorithm SHA256).Hash -ne $config.protocol_sha256) { throw 'Frozen protocol hash mismatch.' }
        if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot 'requirements-lock.txt') -Algorithm SHA256).Hash -ne $config.preparation.requirements_lock_sha256) { throw 'Existing dependency lock hash mismatch.' }
        foreach ($manifest in $protocol.data.frozen_manifests) {
            if ((Get-FileHash -LiteralPath (Join-Path $CodeRoot $manifest.path) -Algorithm SHA256).Hash -ne $manifest.file_sha256) { throw ('Frozen manifest mismatch: ' + $manifest.path) }
            $files += $manifest.path
        }
        $payload = Join-Path $localRoot 'payload'
        $null = New-Item -ItemType Directory -Path $payload
        $hashLines = @()
        foreach ($relative in $files) {
            $source = Join-Path $CodeRoot $relative
            $destination = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force
            Copy-Item -LiteralPath $source -Destination $destination
            $hashLines += (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative
        }
        [IO.File]::WriteAllText((Join-Path $payload 'payload.sha256'), ($hashLines -join "`n") + "`n", $utf8)
        $bundle = Join-Path $localRoot 'setup-files.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','payload.sha256') + $files)
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        Log ('Prepared ' + $files.Count + ' approved files; bundle SHA256=' + $bundleHash)
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. No network connection or remote action.'; exit 0 }
        $preflight = @'
if [[ -e "$root" ]]; then
    [[ -d "$root" && "$(stat -c %u -- "$root")" == "$(id -u)" ]] || exit 2
    echo '[Existing staging entries]'
    find "$root" -mindepth 1 -maxdepth 2 -print
fi
echo '[Quota and shared filesystem]'
if command -v quota >/dev/null 2>&1; then quota -s || true; else echo 'Personal quota command unavailable; quota remains unknown.'; fi
df -h "$HOME"
for directory in "$root" "$root/run" "$root/run/setup_tc2_gpu" "$root/_downloads" "$root/tmp"; do
    [[ ! -L "$directory" ]] || exit 2
    mkdir -p -- "$directory"
done
'@
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $preflight)
        $remoteBundle = $remoteRoot + '/_downloads/setup-files-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $stage = @'
cd -- "$root"
archive="$root/_downloads/setup-files-__RUNID__.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == __BUNDLEHASH__ ]] || { echo 'Upload hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/stage-__RUNID__"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check payload.sha256 )
while read -r hash relative; do
    [[ "$relative" != /* && "$relative" != *..* && "$relative" != *\\* ]] || exit 2
    target="$root/$relative"
    [[ "$(readlink -m -- "$target")" == "$target" && ! -L "$target" ]] || exit 2
    if [[ -e "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" != "$hash" ]]; then
        echo "Existing staging file differs; no overwrite: $relative" >&2
        exit 2
    fi
done < "$incoming/payload.sha256"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then cp --no-clobber -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/payload.sha256"
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/setup_tc2_gpu/slurm-%j.out" --error="$root/run/setup_tc2_gpu/slurm-%j.err" scripts/slurm/probe_tc2_gpu_hardware.sh)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_tc2_gpu/last_probe_job.txt
'@
        $stage = $stage.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $stage + "`n" + $wait + "`n" + $collect)
    } elseif ($Action -eq 'UpdateInputSources') {
        # Preserve every remote setting except the explicitly approved source fields.
        $auditRoot = Join-Path $CodeRoot 'run/setup_v2/step2_20261019_060542'
        $baselineConfig = Join-Path $auditRoot 'inputs_job_43944_official_404/configs/tc2_setup.json'
        $baselineScript = Join-Path $auditRoot 'source_update_baseline/scripts/prepare_tc2_inputs_v2.py'
        $oldHashes = [ordered]@{
            'configs/tc2_setup.json' = 'f94b7108fd8b2f9ef9af6dd439e63219c3a3110cdad8f99c9c9d02fbec739405'
            'scripts/prepare_tc2_gpu_inputs.py' = 'da82f88f0665ab655677cd9cb07125752a0f609807a47f52c3aa1e209dc54e38'
        }
        if ((Get-FileHash -LiteralPath $baselineConfig -Algorithm SHA256).Hash.ToLowerInvariant() -ne $oldHashes['configs/tc2_setup.json'] -or
            (Get-FileHash -LiteralPath $baselineScript -Algorithm SHA256).Hash.ToLowerInvariant() -ne $oldHashes['scripts/prepare_tc2_gpu_inputs.py']) { throw 'Known source-update baseline differs.' }
        $candidate = Get-Content -LiteralPath $baselineConfig -Raw | ConvertFrom-Json
        $localConfig = Get-Content -LiteralPath (Join-Path $CodeRoot 'configs/tc2_setup.json') -Raw | ConvertFrom-Json
        if (-not $localConfig.preparation.mvtec_ad_mirror.approved -or $localConfig.preparation.input_source_revision -ne 'readme_recovery_v1') { throw 'Approved data-source configuration missing.' }
        foreach ($name in @('archive_sources','input_source_revision','mvtec_ad_mirror')) {
            $candidate.preparation | Add-Member -MemberType NoteProperty -Name $name -Value $localConfig.preparation.$name -Force
        }
        $payload = Join-Path $localRoot 'sources_payload'
        $null = New-Item -ItemType Directory -Path (Join-Path $payload 'configs') -Force
        $null = New-Item -ItemType Directory -Path (Join-Path $payload 'scripts') -Force
        [IO.File]::WriteAllText((Join-Path $payload 'configs/tc2_setup.json'),($candidate | ConvertTo-Json -Depth 30) + "`n",$utf8)
        Copy-Item -LiteralPath (Join-Path $CodeRoot 'scripts/prepare_tc2_gpu_inputs.py') -Destination (Join-Path $payload 'scripts/prepare_tc2_gpu_inputs.py')
        $manifestLines = @()
        foreach ($relative in $oldHashes.Keys) {
            $newHash = (Get-FileHash -LiteralPath (Join-Path $payload $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($newHash -eq $oldHashes[$relative]) { throw ('Data-source update has not been applied: ' + $relative) }
            $manifestLines += $oldHashes[$relative] + ' ' + $newHash + ' ' + $relative
        }
        $manifestText = ($manifestLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'sources.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'input-sources.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','sources.sha256') + @($oldHashes.Keys))
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. Data-source update bundle built; no connection or submission.'; exit 0 }
        $sourcePreflight = @'
cd -- "$root"
[[ "$(cat "$(setup_record "last_prepare_inputs_job.txt")")" == 43944 ]] || { echo 'Latest inputs job differs from recorded 43944; collect and inspect before updating.' >&2; exit 2; }
grep -Fq 'HTTPError: HTTP Error 404: Not Found' "$(setup_record "job_43944_prepare_inputs/preparation_status.json")" || exit 2
environment_job=$(cat "$(setup_record "last_prepare_environment_job.txt")")
[[ "$environment_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"ready": true' "$(setup_record "job_${environment_job}_prepare_environment/preparation_status.json")" || exit 2
printf '%s' '__MANIFEST__' | base64 -d | while read -r old_hash new_hash relative; do
    case "$relative" in configs/tc2_setup.json|scripts/prepare_tc2_gpu_inputs.py) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || { echo "Unrecognized source file; no update: $relative" >&2; exit 2; }
done
'@
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $sourcePreflight = $sourcePreflight.Replace('__MANIFEST__',$manifestEncoded)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $sourcePreflight)
        $remoteBundle = $remoteRoot + '/_downloads/input-sources-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $sourceUpdate = @'
archive="$root/_downloads/input-sources-__RUNID__.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == __BUNDLEHASH__ ]] || { echo 'Source-update bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/input-sources-__RUNID__"
backup="$root/run/setup_tc2_gpu/input_sources___RUNID__"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
while read -r old_hash new_hash relative; do
    case "$relative" in configs/tc2_setup.json|scripts/prepare_tc2_gpu_inputs.py) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    [[ "$(sha256sum "$incoming/$relative" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
done < "$incoming/sources.sha256"
mkdir -- "$backup"
cp -- "$incoming/sources.sha256" "$backup/sources.sha256"
while read -r old_hash new_hash relative; do
    mkdir -p -- "$backup/$(dirname -- "$relative")"
    cp -p -- "$root/$relative" "$backup/$relative"
done < "$incoming/sources.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    if [[ "$current_hash" != "$new_hash" ]]; then mv -T -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
    printf '%s %s %s\n' "$old_hash" "$new_hash" "$relative" >> "$backup/applied.txt"
done < "$incoming/sources.sha256"
echo 'Approved AD mirror and original official LOCO sources deployed; frozen manifests retained.'
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal __GPUARG__ --output="$root/run/setup_tc2_gpu/slurm-%j.out" --error="$root/run/setup_tc2_gpu/slurm-%j.err" scripts/slurm/prepare_tc2_gpu.sh inputs)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_tc2_gpu/last_prepare_inputs_job.txt
printf '%s\n' "$job_id" > "$backup/inputs_job.txt"
'@
        $gpuArgument = if ($PreparationGpu -eq 1) { '--gres=gpu:1' } else { '' }
        $sourceUpdate = $sourceUpdate.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash).Replace('__GPUARG__',$gpuArgument)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $sourcePreflight + "`n" + $sourceUpdate + "`n" + $wait + "`n" + $collect)
    } elseif ($Action -eq 'RepairActivation') {
        # Only the two approved SLURM activation entry points may be replaced.
        $oldHashes = [ordered]@{
            'scripts/slurm/prepare_tc2_gpu.sh' = 'a818e3c2eca6e816353f7029033b8e26eb5ef85bfd7d22817abecc61f0a5a02f'
            'scripts/slurm/check_tc2_gpu_setup.sh' = 'a8d04b61ab2efc6cb9ac10cf5b7367370d7cd020f67e260e11f73b9256800b9e'
        }
        $payload = Join-Path $localRoot 'activation_payload'
        $null = New-Item -ItemType Directory -Path $payload
        $manifestLines = @()
        foreach ($relative in $oldHashes.Keys) {
            $source = Join-Path $CodeRoot $relative
            $destination = Join-Path $payload $relative
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force
            Copy-Item -LiteralPath $source -Destination $destination
            $newHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($newHash -eq $oldHashes[$relative]) { throw ('Local activation fix has not been applied: ' + $relative) }
            $manifestLines += $oldHashes[$relative] + ' ' + $newHash + ' ' + $relative
        }
        $manifestText = ($manifestLines -join "`n") + "`n"
        [IO.File]::WriteAllText((Join-Path $payload 'activation.sha256'),$manifestText,$utf8)
        $bundle = Join-Path $localRoot 'activation-fix.tar'
        Native $tar (@('-cf',$bundle,'-C',$payload,'--','activation.sha256') + @($oldHashes.Keys))
        $bundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ValidateOnly) { Log 'LOCAL VALIDATION ONLY. Activation fix bundle built; no remote action.'; exit 0 }
        $manifestEncoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($manifestText))
        $repairPreflight = @'
cd -- "$root"
prior_inputs=$(cat "$(setup_record "last_prepare_inputs_job.txt")")
environment_job=$(cat "$(setup_record "last_prepare_environment_job.txt")")
[[ "$prior_inputs" =~ ^[0-9]+$ && "$environment_job" =~ ^[0-9]+$ ]] || exit 2
grep -Fq 'QT_XCB_GL_INTEGRATION: unbound variable' "$(setup_record "slurm-$prior_inputs.err")" || { echo 'Latest input job is not the recorded activation failure.' >&2; exit 2; }
[[ ! -e "$(setup_record "job_${prior_inputs}_prepare_inputs")" ]] || { echo 'Input Python already started; inspect before any retry.' >&2; exit 2; }
grep -Eq '"ready": true' "$(setup_record "job_${environment_job}_prepare_environment/preparation_status.json")" || exit 2
printf '%s' '__MANIFEST__' | base64 -d | while read -r old_hash new_hash relative; do
    case "$relative" in scripts/slurm/prepare_tc2_gpu.sh|scripts/slurm/check_tc2_gpu_setup.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || { echo "Unrecognized script; no replacement: $relative" >&2; exit 2; }
done
'@
        $repairPreflight = $repairPreflight.Replace('__MANIFEST__',$manifestEncoded)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $repairPreflight)
        $remoteBundle = $remoteRoot + '/_downloads/activation-fix-' + $runId + '.tar'
        Native $scp @('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22',$bundle,($server + ':' + $remoteBundle))
        $repair = @'
archive="$root/_downloads/activation-fix-__RUNID__.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == __BUNDLEHASH__ ]] || { echo 'Activation bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/activation-fix-__RUNID__"
backup="$root/run/setup_tc2_gpu/activation_fix___RUNID__"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
# Verify all old/new pairs before replacing either script.
while read -r old_hash new_hash relative; do
    case "$relative" in scripts/slurm/prepare_tc2_gpu.sh|scripts/slurm/check_tc2_gpu_setup.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    [[ "$(sha256sum "$incoming/$relative" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
done < "$incoming/activation.sha256"
mkdir -- "$backup"
cp -- "$incoming/activation.sha256" "$backup/activation.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    mkdir -p -- "$backup/$(dirname -- "$relative")"
    cp -p -- "$target" "$backup/$relative"
done < "$incoming/activation.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    if [[ "$current_hash" != "$new_hash" ]]; then
        mv -T -- "$incoming/$relative" "$target"
    fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
    printf '%s %s %s\n' "$old_hash" "$new_hash" "$relative" >> "$backup/applied.txt"
done < "$incoming/activation.sha256"
echo 'Two activation entry points updated; installed environment retained.'
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal __GPUARG__ --output="$root/run/setup_tc2_gpu/slurm-%j.out" --error="$root/run/setup_tc2_gpu/slurm-%j.err" scripts/slurm/prepare_tc2_gpu.sh inputs)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_tc2_gpu/last_prepare_inputs_job.txt
printf '%s\n' "$job_id" > "$backup/retry_inputs_job.txt"
'@
        $gpuArgument = if ($PreparationGpu -eq 1) { '--gres=gpu:1' } else { '' }
        $repair = $repair.Replace('__RUNID__',$runId).Replace('__BUNDLEHASH__',$bundleHash).Replace('__GPUARG__',$gpuArgument)
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $repairPreflight + "`n" + $repair + "`n" + $wait + "`n" + $collect)
    } elseif ($Action -eq 'UploadInputs') {
        if ($ValidateOnly) { throw 'ValidateOnly is supported with Probe only.' }
        if (-not $InputDirectory) { throw 'Supply -InputDirectory with approved input archives.' }
        $allowed = @('bottle.tar.xz','cable.tar.xz','capsule.tar.xz','screw.tar.xz','tile.tar.xz','wood.tar.xz','juice_bottle.tar.xz','screw_bag.tar.xz','resnet18-f37072fd.pth','mvtec_anomaly_detection.tar.xz')
        $inputs = @(Get-ChildItem -LiteralPath $InputDirectory -File | Where-Object { $allowed -contains $_.Name })
        if ($inputs.Count -eq 0) { throw 'No allowed archive or weight filename found.' }
        $hashLines = @($inputs | ForEach-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $_.Name })
        $uploadPreflight = @'
[[ -d "$root" && -d "$root/_downloads" && ! -L "$root/_downloads" ]] || exit 2
probe_id=$(cat "$(setup_record "last_probe_job.txt")")
[[ "$probe_id" =~ ^[0-9]+$ ]] || exit 2
grep -Eq '"ready": true' "$(setup_record "job_${probe_id}_hardware/hardware.json")" || { echo 'Hardware gate not passed.' >&2; exit 2; }
mkdir -- "$root/_downloads/upload-__RUNID__"
'@
        Ssh ($guard + "`n" + $noOtherJobs + "`n" + $uploadPreflight.Replace('__RUNID__',$runId))
        Native $scp (@('-o','StrictHostKeyChecking=yes','-o','NumberOfPasswordPrompts=1','-P','22') + @($inputs.FullName) + @($server + ':' + $remoteRoot + '/_downloads/upload-' + $runId + '/'))
        $encodedHashes = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($hashLines -join "`n") + "`n"))
        $publish = @'
cd -- "$root/_downloads/upload-__RUNID__"
printf '%s' '__HASHES__' | base64 -d > upload.sha256
sha256sum --check upload.sha256
while read -r hash name; do
    target="$root/_downloads/$name"
    [[ ! -L "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Existing archive differs: $name" >&2; exit 2; }
    fi
done < upload.sha256
while read -r hash name; do
    target="$root/_downloads/$name"
    if [[ ! -e "$target" ]]; then ln -- "$PWD/$name" "$target"; fi
done < upload.sha256
echo 'Uploaded inputs published without overwriting. No preparation job submitted.'
'@
        Ssh ($guard + "`n" + $publish.Replace('__RUNID__',$runId).Replace('__HASHES__',$encodedHashes) + "`n" + $collect)
    } else {
        if ($ValidateOnly) { throw 'ValidateOnly is supported with Probe only.' }
        $stage = '[[ -d "$root" && ( -d "$root/run/setup_tc2_gpu" || -d "$root/run/setup_v2" ) && ! -L "$root/run/setup_tc2_gpu" && ! -L "$root/tmp" ]] || exit 2' + "`n" + 'cd -- "$root"' + "`n"
        if ($Action -eq 'Collect') {
            if (-not $JobId) { throw 'Collect requires -JobId from the submission output.' }
            $stage += 'job_id=' + $JobId + "`n"
        } else {
            $stage += $noOtherJobs + "`n"
            $stage += @'
probe_id=$(cat "$(setup_record "last_probe_job.txt")")
[[ "$probe_id" =~ ^[0-9]+$ ]] || exit 2
grep -Eq '"ready": true' "$(setup_record "job_${probe_id}_hardware/hardware.json")" || { echo 'Hardware gate not passed.' >&2; exit 2; }
'@ + "`n"
            if ($Action -ne 'PrepareEnvironment') {
                $stage += @'
environment_job=$(cat "$(setup_record "last_prepare_environment_job.txt")")
[[ "$environment_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"ready": true' "$(setup_record "job_${environment_job}_prepare_environment/preparation_status.json")" || { echo 'Dedicated package environment not ready.' >&2; exit 2; }
'@ + "`n"
            }
            if ($Action -eq 'CheckAll') {
                $stage += @'
inputs_job=$(cat "$(setup_record "last_prepare_inputs_job.txt")")
environment_check_job=$(cat "$(setup_record "last_check_environment_job.txt")")
[[ "$inputs_job" =~ ^[0-9]+$ && "$environment_check_job" =~ ^[0-9]+$ ]] || exit 2
grep -Eq '"ready": true' "$(setup_record "job_${inputs_job}_prepare_inputs/preparation_status.json")" || { echo 'Input restoration not ready.' >&2; exit 2; }
grep -Eq '"environment_ready": true' "$(setup_record "job_${environment_check_job}_environment/setup_status.json")" || { echo 'GPU environment check not ready.' >&2; exit 2; }
'@ + "`n"
            }
            if ($Action -eq 'PrepareEnvironment' -or $Action -eq 'PrepareInputs') {
                $mode = if ($Action -eq 'PrepareEnvironment') { 'environment' } else { 'inputs' }
                $gpuArgument = if ($PreparationGpu -eq 1) { ' --gres=gpu:1' } else { '' }
                $stage += 'job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal' + $gpuArgument + ' --output="$root/run/setup_tc2_gpu/slurm-%j.out" --error="$root/run/setup_tc2_gpu/slurm-%j.err" scripts/slurm/prepare_tc2_gpu.sh ' + $mode + ')' + "`n"
                $phase = 'prepare_' + $mode
            } else {
                $mode = if ($Action -eq 'CheckEnvironment') { 'environment' } else { 'all' }
                $stage += 'job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --export=ALL,TC2_ANACONDA_MODULE=anaconda/25.5.1 --output="$root/run/setup_tc2_gpu/slurm-%j.out" --error="$root/run/setup_tc2_gpu/slurm-%j.err" scripts/slurm/check_tc2_gpu_setup.sh "$root/envs/ca6129-ad-v2" ' + $mode + ')' + "`n"
                $phase = 'check_' + $mode
            }
            $stage += 'job_id=${job_id%%;*}' + "`n" + '[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2' + "`n"
            $stage += 'printf ''%s\n'' "$job_id" > run/setup_tc2_gpu/last_' + $phase + '_job.txt' + "`n" + $wait + "`n"
        }
        Ssh ($guard + "`n" + $stage + "`n" + $collect)
    }
    Log 'Action finished. Read the relevant status JSON: step 2 requires all-mode step_2_complete=true; metrics require full-mode step_3_complete=true; algorithms require full-mode step_4_complete=true.'
    Log ('Send this local output path back: ' + $logPath)
} catch {
    Log ('STOPPED: ' + $_.Exception.Message)
    Log ('Send this local output path back: ' + $logPath)
    exit 2
}
