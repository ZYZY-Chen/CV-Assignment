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
$validationRoot = Join-Path 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output' ('s8_analysis_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $validationRoot
$env:ANALYSIS_TRANSPORT_FIXTURES = $validationRoot
$env:ANALYSIS_TRANSPORT_PLAN = Join-Path $PSScriptRoot 'validated_inputs_final.json'
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
foreach ($case in @('collect','run','validate_only','stale_plan','missing_job','invalid_job','collect_validate','bad_path','bad_hash','oversize','duplicate','missing_markers','bad_page','duplicate_job','loco_switch')) {
    $env:ANALYSIS_TRANSPORT_MODE = $case
    $action = if ($case -in @('run','validate_only','stale_plan','duplicate_job')) { 'RunAnalysis' } else { 'CollectAnalysis' }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$simulatorPath,'-Action',$action)
    if ($action -eq 'CollectAnalysis' -and $case -ne 'missing_job') { $arguments += @('-JobId',$(if ($case -eq 'invalid_job') { '9999999999999' } else { '90001' })) }
    if ($case -in @('validate_only','collect_validate')) { $arguments += '-ValidateOnly' }
    if ($case -eq 'loco_switch') { $arguments += '-LocoCollection' }
    & $powershell @arguments | Out-Null
    $code = $LASTEXITCODE
    $latest = Get-ChildItem -LiteralPath $validationRoot -Directory -Filter 'tc2_gpu_setup_*' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $callPath = Join-Path $latest.FullName 'offline_calls.jsonl'
    $calls = if (Test-Path -LiteralPath $callPath) { @(Get-Content -LiteralPath $callPath | ConvertFrom-Json) } else { @() }
    if ($case -in @('collect','run')) {
        if ($code) { throw ('Valid analysis flow failed: ' + $case + '. See ' + (Join-Path $latest.FullName 'terminal.txt')) }
        if (@($calls | Where-Object kind -eq 'verify').Count -ne 3) { throw 'Not every collection verification operation ran.' }
        $expectedSsh = if ($case -eq 'run') { 3 } else { 1 }
        $expectedUpload = if ($case -eq 'run') { 1 } else { 0 }
        if (@($calls | Where-Object kind -eq 'ssh').Count -ne $expectedSsh -or @($calls | Where-Object kind -eq 'upload').Count -ne $expectedUpload) { throw 'Unexpected upload or SSH flow.' }
    } elseif ($case -eq 'validate_only') {
        if ($code -or $calls.Count -or -not (Test-Path -LiteralPath (Join-Path $latest.FullName 'analysis-package-validation.json'))) { throw 'ValidateOnly attempted transport or failed packaging.' }
    } elseif (-not $code) { throw ('Invalid analysis flow accepted: ' + $case) }
    if ($case -in @('stale_plan','missing_job','invalid_job','collect_validate','loco_switch') -and $calls.Count) { throw 'Invalid options triggered transport.' }
    if ($case -in @('bad_path','oversize','duplicate','missing_markers') -and @($calls | Where-Object kind -eq 'download').Count) { throw 'Invalid metadata triggered download.' }
    if ($case -eq 'bad_hash' -and (Test-Path -LiteralPath (Join-Path $latest.FullName 'remote'))) { throw 'Wrong index hash triggered extraction.' }
    $cases += [pscustomobject]@{name=$case;exit_code=$code;status='passed'}
}
$result = [ordered]@{status='passed';validation_root=$validationRoot;cases=$cases;actual_tc2_connections=0;actual_slurm_submissions=0;all_collection_verification_uses_analysis_collector=$true}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'analysis_transport_validation.json'),($result | ConvertTo-Json -Depth 5) + "`n",$utf8)
$result | ConvertTo-Json -Depth 5
exit 0
