# Offline fixtures only. Replace every SSH/SCP entry point before invoking the helper.
$ErrorActionPreference = 'Stop'
$sourcePath = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1'
$codeRoot = 'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code'
$python = 'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$utf8 = New-Object Text.UTF8Encoding($false)
$source = Get-Content -LiteralPath $sourcePath -Raw
$tokens = $null; $errors = $null
$tree = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$validationRoot = Join-Path 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output' ('s8_dep_transport_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $validationRoot
$env:ANALYSIS_TRANSPORT_FIXTURES = $validationRoot
$env:ANALYSIS_TRANSPORT_PLAN = Join-Path (Join-Path $PSScriptRoot '../step8_20261019') 'validated_inputs_final.json'
if (-not (Test-Path -LiteralPath $env:ANALYSIS_TRANSPORT_PLAN)) { throw 'Generate the actual local input plan first.' }
$fixture = Join-Path $validationRoot 'fixture'
foreach ($relative in @('configs/analysis_tc2_gpu.json','configs/experiments_tc2_gpu.json','configs/protocol_v2.json')) {
    $target = Join-Path $fixture $relative
    $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
    Copy-Item -LiteralPath (Join-Path $codeRoot $relative) -Destination $target
}
foreach ($manifest in (Get-ChildItem -LiteralPath (Join-Path $codeRoot 'manifests') -Filter 'manifest_*.json' -File)) {
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'manifests') -Force
    Copy-Item -LiteralPath $manifest.FullName -Destination (Join-Path $fixture 'manifests')
}
$null = New-Item -ItemType Directory -Path (Join-Path $fixture 'tmp') -Force
& $python -I -B (Join-Path $codeRoot 'scripts/collect_analysis_tc2_gpu.py') export --root $fixture --job-id 90001 --directory (Join-Path $fixture 'tmp/analysis-90001-offline') | Out-Null
if ($LASTEXITCODE) { throw 'Cannot prepare the local pending-analysis fixture.' }
$functions = @($tree.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
$replacements = @()
foreach ($name in @('Ssh','Native')) {
    $definition = $functions | Where-Object Name -eq $name
    if ($name -eq 'Ssh') {
        $replacement = @'
function Ssh([string]$remoteScript) {
    $name = 'command_' + [Guid]::NewGuid().ToString('N') + '.sh'
    [IO.File]::WriteAllText((Join-Path $localRoot $name),$remoteScript.Replace("`r",'') + "`n",$utf8)
    if ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript.Replace("`r",'')+"`n")).Length + 60 -gt 26000) { throw 'Rendered SSH command exceeds its length guard.' }
    [IO.File]::AppendAllText((Join-Path $localRoot 'offline_calls.jsonl'),'{"kind":"ssh"}' + "`n",$utf8)
    if ($remoteScript.Contains("<<'ANALYSIS_DEPENDENCY_PY'")) {
        $dependencyMode = if ($remoteScript -match '\"\$root\" repair ') { 'repair' } else { 'check' }
        [IO.File]::AppendAllText((Join-Path $localRoot 'offline_calls.jsonl'),('{"kind":"dependency","mode":"' + $dependencyMode + '"}') + "`n",$utf8)
        if ($dependencyMode -eq 'repair') {
            if ($remoteScript.Contains('sbatch') -or $remoteScript.Contains('scp ') -or $remoteScript.Contains('ANALYSIS_BOOTSTRAP_PY')) { throw 'Repair exceeds its approved scope.' }
            $receipt = [ordered]@{schema_version='1.0';action='RepairAnalysisDependency';status='dependency_verified';outcome='created';source='scripts/collect_experiments_loco_tc2_gpu_09ac7432f8f6bce3.py';target='scripts/collect_experiments_loco_tc2_gpu.py';sha256='09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967';base_collector='scripts/collect_experiments_tc2_gpu.py';base_collector_sha256='AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010';record_path=('run/validation_tc2_gpu/analysis_dependency_repair_' + $runId + '/repair.json');recorded_at_utc='2026-10-19T14:00:00+00:00';step_8_complete=$false;slurm_jobs_submitted=0;model_calls=0}
            switch ($env:ANALYSIS_TRANSPORT_MODE) {
                'repair_already' {$receipt.outcome='already_exact'}
                'receipt_path' {$receipt.record_path='run/elsewhere/repair.json'}
                'receipt_source' {$receipt.source='scripts/unaccepted.py'}
                'receipt_submitted' {$receipt.slurm_jobs_submitted=1}
                'receipt_complete' {$receipt.step_8_complete=$true}
                'receipt_bool_string' {$receipt.step_8_complete='false'}
                'receipt_int_string' {$receipt.model_calls='0'}
                'receipt_int_float' {$receipt.slurm_jobs_submitted=0.0}
            }
            $json=$receipt | ConvertTo-Json -Compress
            if ($env:ANALYSIS_TRANSPORT_MODE -eq 'receipt_int_float') {$json=$json.Replace('"slurm_jobs_submitted":0,','"slurm_jobs_submitted":0.0,')}
            $hasher=[Security.Cryptography.SHA256]::Create()
            try {$fingerprint=[BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($json+"`n"))).Replace('-','')} finally {$hasher.Dispose()}
            if ($env:ANALYSIS_TRANSPORT_MODE -eq 'receipt_hash') {$fingerprint='0'*64}
            if ($env:ANALYSIS_TRANSPORT_MODE -ne 'receipt_missing') {
                Log ('ANALYSIS_DEPENDENCY_REPAIR_JSON='+$json)
                Log ('ANALYSIS_DEPENDENCY_REPAIR_SHA256='+$fingerprint)
            }
            if ($env:ANALYSIS_TRANSPORT_MODE -eq 'receipt_duplicate') {Log ('ANALYSIS_DEPENDENCY_REPAIR_JSON='+$json)}
            return
        }
        if ($remoteScript.IndexOf("<<'ANALYSIS_DEPENDENCY_PY'") -gt $remoteScript.IndexOf("<<'ANALYSIS_BOOTSTRAP_PY'") -and $remoteScript.Contains('ANALYSIS_BOOTSTRAP_PY')) {throw 'The publication dependency check occurs too late.'}
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'dependency_before_upload' -and -not $remoteScript.Contains('ANALYSIS_BOOTSTRAP_PY')) {throw 'Offline missing dependency before upload.'}
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'dependency_before_publish' -and $remoteScript.Contains('ANALYSIS_BOOTSTRAP_PY')) {throw 'Offline changed dependency before publication.'}
        Log 'ANALYSIS_DEPENDENCY_CHECK_SHA256=09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967'
    }
    if ($remoteScript.Contains('sbatch')) {
        if ($Action -ne 'RunAnalysis' -or $remoteScript -match '--gres|--gpus|--nodelist') { throw 'Unexpected submission resource request.' }
        foreach ($text in @('--chdir="$root"','--cpus-per-task=2','--mem=8G','--time=00:15:00','--nodes=1','--ntasks=1','TC2_ANALYSIS_INPUTS_SHA256=')) {
            if (-not $remoteScript.Contains($text)) { throw ('Missing analysis submission contract: ' + $text) }
        }
        Log 'TC2_JOB_ID=90001'
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'duplicate_job') { Log 'TC2_JOB_ID=90002' }
    }
    if ($remoteScript.Contains('export_json=$(')) {
        $fixture = Join-Path $env:ANALYSIS_TRANSPORT_FIXTURES 'fixture/tmp/analysis-90001-offline'
        $path = $remoteRoot + '/tmp/analysis-90001-' + $runId + '/index.json'
        $hash = (Get-FileHash -LiteralPath (Join-Path $fixture 'index.json') -Algorithm SHA256).Hash
        $count = 1
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'bad_path') { $path = '/tmp/untrusted/index.json' }
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'bad_hash') { $hash = '0' * 64 }
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'oversize') { $count = 33 }
        if ($env:ANALYSIS_TRANSPORT_MODE -ne 'missing_markers') {
            Log ('ANALYSIS_INDEX_PATH=' + $path)
            Log ('ANALYSIS_INDEX_SHA256=' + $hash)
            Log ('ANALYSIS_PAGE_COUNT=' + $count)
            Log 'ANALYSIS_PARTIAL=True'
        }
        if ($env:ANALYSIS_TRANSPORT_MODE -eq 'duplicate') { Log ('ANALYSIS_INDEX_PATH=' + $path) }
    }
}
'@
    } else {
        $replacement = $definition.Extent.Text.Replace('function Native(', 'function OriginalNative(') + "`n" + @'
function Native([string]$program,[string[]]$nativeArguments) {
    if ($program -eq $scp) {
        $target = $nativeArguments[-1]
        $fixture = Join-Path $env:ANALYSIS_TRANSPORT_FIXTURES 'fixture/tmp/analysis-90001-offline'
        $kind = 'download'
        if ($target -match '/_downloads/analysis-files-[0-9_]+[a-f0-9]*\.tar$') {
            if ($Action -ne 'RunAnalysis' -or $nativeArguments[-2] -ne (Join-Path $localRoot 'analysis-files.tar')) { throw 'Unexpected upload.' }
            $kind = 'upload'
        } elseif ($target -eq (Join-Path $localRoot 'analysis-index.json')) {
            Copy-Item -LiteralPath (Join-Path $fixture 'index.json') -Destination $target
        } elseif ($target -match 'page_[0-9]{3}\.tar\.gz$') {
            Copy-Item -LiteralPath (Join-Path $fixture ([IO.Path]::GetFileName($target))) -Destination $target
            if ($env:ANALYSIS_TRANSPORT_MODE -eq 'bad_page') { [IO.File]::AppendAllText($target,'corrupt',$utf8) }
        } else { throw ('Unexpected synthetic SCP target: ' + $target) }
        [IO.File]::AppendAllText((Join-Path $localRoot 'offline_calls.jsonl'),('{"kind":"' + $kind + '"}') + "`n",$utf8)
        return
    }
    if ($program -eq $PythonExecutable) {
        $operation = $nativeArguments[3]
        if ($operation -eq 'plan') {
            if ($nativeArguments[2] -ne (Join-Path $CodeRoot 'scripts/analyze_results_tc2_gpu.py')) { throw 'Wrong planning source.' }
            Copy-Item -LiteralPath $env:ANALYSIS_TRANSPORT_PLAN -Destination $nativeArguments[-1]
            if ($env:ANALYSIS_TRANSPORT_MODE -eq 'stale_plan') {
                $value = Get-Content -LiteralPath $nativeArguments[-1] -Raw | ConvertFrom-Json
                $value.analysis_sources.'scripts/plot_results_tc2_gpu.py' = '0' * 64
                [IO.File]::WriteAllText($nativeArguments[-1],($value | ConvertTo-Json -Depth 80),$utf8)
            }
            return
        }
        if ($nativeArguments[2] -ne (Join-Path $CodeRoot 'scripts/collect_analysis_tc2_gpu.py')) { throw 'Wrong collection source.' }
        [IO.File]::AppendAllText((Join-Path $localRoot 'offline_calls.jsonl'),('{"kind":"verify","action":"' + $operation + '"}') + "`n",$utf8)
    }
    OriginalNative $program $nativeArguments
}
'@
    }
    $replacements += [pscustomobject]@{start=$definition.Extent.StartOffset; length=$definition.Extent.EndOffset-$definition.Extent.StartOffset; text=$replacement}
}
$simulator = $source
foreach ($replacement in ($replacements | Sort-Object start -Descending)) { $simulator = $simulator.Remove($replacement.start,$replacement.length).Insert($replacement.start,$replacement.text) }
$simulatorPath = Join-Path $validationRoot 'simulated_analysis.ps1'
[IO.File]::WriteAllText($simulatorPath,$simulator,$utf8)
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cases = @()
foreach ($case in @('repair_created','repair_already','receipt_hash','receipt_path','receipt_source','receipt_submitted','receipt_complete','receipt_bool_string','receipt_int_string','receipt_int_float','receipt_missing','receipt_duplicate','repair_job','repair_stage','repair_input','repair_gpu','repair_validate','repair_loco','dependency_before_upload','dependency_before_publish','run','validate_only','collect')) {
    $env:ANALYSIS_TRANSPORT_MODE = $case
    $action = if ($case -in @('run','validate_only','dependency_before_upload','dependency_before_publish')) { 'RunAnalysis' } elseif ($case -eq 'collect') { 'CollectAnalysis' } else { 'RepairAnalysisDependency' }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$simulatorPath,'-Action',$action)
    if ($action -eq 'CollectAnalysis' -and $case -ne 'missing_job') { $arguments += @('-JobId',$(if ($case -eq 'invalid_job') { '9999999999999' } else { '90001' })) }
    if ($case -in @('validate_only','collect_validate')) { $arguments += '-ValidateOnly' }
    if ($case -eq 'repair_job') {$arguments += @('-JobId','90001')}
    if ($case -eq 'repair_stage') {$arguments += @('-Stage','B0')}
    if ($case -eq 'repair_input') {$arguments += @('-InputDirectory',$fixture)}
    if ($case -eq 'repair_gpu') {$arguments += @('-PreparationGpu','1')}
    if ($case -eq 'repair_validate') {$arguments += '-ValidateOnly'}
    if ($case -eq 'repair_loco') {$arguments += '-LocoCollection'}
    & $powershell @arguments | Out-Null
    $code = $LASTEXITCODE
    $latest = Get-ChildItem -LiteralPath $validationRoot -Directory -Filter 'tc2_gpu_setup_*' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $callPath = Join-Path $latest.FullName 'offline_calls.jsonl'
    $calls = if (Test-Path -LiteralPath $callPath) { @(Get-Content -LiteralPath $callPath | ConvertFrom-Json) } else { @() }
    if ($case -in @('repair_created','repair_already')) {
        if ($code -or @($calls | Where-Object kind -eq 'ssh').Count -ne 1 -or $calls.Count -ne 2 -or -not (Test-Path -LiteralPath (Join-Path $latest.FullName 'analysis-dependency-repair.json'))) {throw ('Valid repair transport failed: '+$case+' '+$latest.FullName)}
        if (@($calls | Where-Object { $_.kind -in @('upload','download','verify') }).Count) {throw 'Repair performed a transport mutation.'}
    } elseif ($case -in @('collect','run')) {
        if ($code) { throw ('Valid analysis flow failed: ' + $case + '. See ' + (Join-Path $latest.FullName 'terminal.txt')) }
        if (@($calls | Where-Object kind -eq 'verify').Count -ne 3) { throw 'Not every collection verification operation ran.' }
        $expectedSsh = if ($case -eq 'run') { 3 } else { 1 }
        $expectedUpload = if ($case -eq 'run') { 1 } else { 0 }
        if (@($calls | Where-Object kind -eq 'ssh').Count -ne $expectedSsh -or @($calls | Where-Object kind -eq 'upload').Count -ne $expectedUpload) { throw 'Unexpected upload or SSH flow.' }
    } elseif ($case -eq 'validate_only') {
        if ($code -or $calls.Count -or -not (Test-Path -LiteralPath (Join-Path $latest.FullName 'analysis-package-validation.json'))) { throw 'ValidateOnly attempted transport or failed packaging.' }
    } elseif (-not $code) { throw ('Invalid analysis flow accepted: ' + $case) }
    if ($case -in @('repair_job','repair_stage','repair_input','repair_gpu','repair_validate','repair_loco') -and $calls.Count) { throw 'Invalid options triggered transport.' }
    if ($case -in @('bad_path','oversize','duplicate','missing_markers') -and @($calls | Where-Object kind -eq 'download').Count) { throw 'Invalid metadata triggered download.' }
    if ($case -eq 'bad_hash' -and (Test-Path -LiteralPath (Join-Path $latest.FullName 'remote'))) { throw 'Wrong index hash triggered extraction.' }
    if ($case -eq 'dependency_before_upload' -and @($calls | Where-Object kind -eq 'upload').Count) {throw 'Missing dependency allowed upload.'}
    if ($case -eq 'dependency_before_publish' -and @($calls | Where-Object kind -eq 'upload').Count -ne 1) {throw 'Second dependency refusal did not follow exactly one upload.'}
    if ($case -in @('dependency_before_upload','dependency_before_publish') -and (Test-Path -LiteralPath (Join-Path $latest.FullName 'analysis-index.json'))) {throw 'Dependency refusal allowed submission or collection.'}
    if ($case -eq 'run' -and @($calls | Where-Object { $_.kind -eq 'dependency' -and $_.mode -eq 'check' }).Count -ne 2) {throw 'RunAnalysis must check before upload and before publication.'}
    $cases += [pscustomobject]@{name=$case;exit_code=$code;status='passed';calls=@($calls)}
}
$rendered = @(Get-ChildItem -LiteralPath $validationRoot -Recurse -File -Filter 'command_*.sh' | ForEach-Object FullName)
$result = [ordered]@{status='passed';validation_root=$validationRoot;rendered_shell_commands=$rendered;helper_sha256=(Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash;cases=$cases;actual_tc2_connections=0;actual_slurm_submissions=0;all_collection_verification_uses_analysis_collector=$true}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'dependency_transport_validation.json'),($result | ConvertTo-Json -Depth 5) + "`n",$utf8)
$result | ConvertTo-Json -Depth 5
exit 0
