# Local fixtures only. Replace every SSH/SCP entry point before executing the helper.
$ErrorActionPreference = 'Stop'
$sourcePath = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1'
$codeRoot = 'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code'
$python = 'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$utf8 = New-Object Text.UTF8Encoding($false)
$source = Get-Content -LiteralPath $sourcePath -Raw
$tokens = $null; $errors = $null
$tree = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$validationRoot = Join-Path 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output' ('s8_loco_transport_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $validationRoot
$env:LOCO_TRANSPORT_FIXTURES = $validationRoot
foreach ($kind in @('default','loco')) {
    $fixture = Join-Path $validationRoot ($kind + '_fixture')
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'configs') -Force
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'tmp') -Force
    Copy-Item -LiteralPath (Join-Path $codeRoot 'configs/experiments_tc2_gpu.json') -Destination (Join-Path $fixture 'configs/experiments_tc2_gpu.json')
    $name = if ($kind -eq 'loco') { 'scripts/collect_experiments_loco_tc2_gpu.py' } else { 'scripts/collect_experiments_tc2_gpu.py' }
    $stage = if ($kind -eq 'loco') { 'B0_LOCO' } else { 'B0' }
    & $python -I -B (Join-Path $codeRoot $name) export --root $fixture --job-id 44235 --directory (Join-Path $fixture 'tmp/experiments-44235-offline') --stage $stage | Out-Null
    if ($LASTEXITCODE) { throw 'Cannot prepare a bounded local collection fixture.' }
}
foreach ($kind in @('wrong_base','missing_collector')) {
    $fixture = Join-Path $validationRoot $kind
    $null = New-Item -ItemType Directory -Path (Join-Path $fixture 'scripts') -Force
    Copy-Item -LiteralPath (Join-Path $codeRoot 'scripts/collect_experiments_tc2_gpu.py') -Destination (Join-Path $fixture 'scripts/collect_experiments_tc2_gpu.py')
    if ($kind -eq 'wrong_base') {
        [IO.File]::AppendAllText((Join-Path $fixture 'scripts/collect_experiments_tc2_gpu.py'),"`n# Local negative fixture only.`n",$utf8)
        Copy-Item -LiteralPath (Join-Path $codeRoot 'scripts/collect_experiments_loco_tc2_gpu.py') -Destination (Join-Path $fixture 'scripts/collect_experiments_loco_tc2_gpu.py')
    }
}
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
    if ($remoteScript.Contains('sbatch') -or $remoteScript.Contains('EXPERIMENTS_BOOTSTRAP_PY')) { throw 'Collection attempted a job submission.' }
    if ($remoteScript.Contains('LOCO_COLLECTION_PUBLISH_PY')) {
        if ($env:LOCO_TRANSPORT_MODE -eq 'publish_failure') { throw 'Synthetic remote publication refusal.' }
        Log ('LOCO_COLLECTION_REMOTE_COLLECTOR_SHA256=' + (Get-FileHash -LiteralPath (Join-Path $CodeRoot 'scripts/collect_experiments_loco_tc2_gpu.py') -Algorithm SHA256).Hash)
    }
    if ($remoteScript.Contains('export_json=$(')) {
        $kind = if ($LocoCollection) { 'loco' } else { 'default' }
        $fixture = Join-Path $env:LOCO_TRANSPORT_FIXTURES ($kind + '_fixture/tmp/experiments-44235-offline')
        $path = $remoteRoot + '/tmp/experiments-44235-' + $runId + '/index.json'
        $hash = (Get-FileHash -LiteralPath (Join-Path $fixture 'index.json') -Algorithm SHA256).Hash
        $count = 1
        if ($env:LOCO_TRANSPORT_MODE -eq 'bad_path') { $path = '/tmp/untrusted/index.json' }
        if ($env:LOCO_TRANSPORT_MODE -eq 'bad_hash') { $hash = '0' * 64 }
        if ($env:LOCO_TRANSPORT_MODE -eq 'oversize') { $count = 33 }
        Log ('EXPERIMENTS_INDEX_PATH=' + $path)
        Log ('EXPERIMENTS_INDEX_SHA256=' + $hash)
        Log ('EXPERIMENTS_PAGE_COUNT=' + $count)
        if ($env:LOCO_TRANSPORT_MODE -eq 'duplicate') { Log ('EXPERIMENTS_INDEX_PATH=' + $path) }
    }
}
'@
    } else {
        $replacement = $definition.Extent.Text.Replace('function Native(', 'function OriginalNative(') + "`n" + @'
function Native([string]$program,[string[]]$nativeArguments) {
    if ($program -eq $scp) {
        $target = $nativeArguments[-1]
        $kind = if ($LocoCollection) { 'loco' } else { 'default' }
        $fixture = Join-Path $env:LOCO_TRANSPORT_FIXTURES ($kind + '_fixture/tmp/experiments-44235-offline')
        $callKind = 'download'
        if ($target -like '*:_downloads/*') { throw 'Unexpected unrooted upload.' }
        if ($target -match '/_downloads/loco-collector-[0-9_]+[a-f0-9]*\.py$') {
            if ($nativeArguments[-2] -cne (Join-Path $CodeRoot 'scripts/collect_experiments_loco_tc2_gpu.py')) { throw 'A frozen source was selected for upload.' }
            $callKind = 'upload'
        } elseif ($target -eq (Join-Path $localRoot 'experiments-index.json')) {
            Copy-Item -LiteralPath (Join-Path $fixture 'index.json') -Destination $target
        } elseif ($target -match 'page_[0-9]{3}\.tar\.gz$') {
            Copy-Item -LiteralPath (Join-Path $fixture ([IO.Path]::GetFileName($target))) -Destination $target
        } else { throw ('Unexpected synthetic SCP target: ' + $target) }
        [IO.File]::AppendAllText((Join-Path $localRoot 'offline_calls.jsonl'),('{"kind":"' + $callKind + '"}') + "`n",$utf8)
        return
    }
    if ($program -eq $PythonExecutable) {
        $expected = if ($LocoCollection) { 'scripts/collect_experiments_loco_tc2_gpu.py' } else { 'scripts/collect_experiments_tc2_gpu.py' }
        if ($nativeArguments[2] -cne (Join-Path $CodeRoot $expected)) { throw 'Local verification selected another collector.' }
        [IO.File]::AppendAllText((Join-Path $localRoot 'offline_calls.jsonl'),('{"kind":"verify","action":"' + $nativeArguments[3] + '"}') + "`n",$utf8)
    }
    OriginalNative $program $nativeArguments
}
'@
    }
    $replacements += [pscustomobject]@{start=$definition.Extent.StartOffset; length=$definition.Extent.EndOffset-$definition.Extent.StartOffset; text=$replacement}
}
$simulator = $source
foreach ($replacement in ($replacements | Sort-Object start -Descending)) {
    $simulator = $simulator.Remove($replacement.start,$replacement.length).Insert($replacement.start,$replacement.text)
}
$simulatorPath = Join-Path $validationRoot 'simulated_loco.ps1'
[IO.File]::WriteAllText($simulatorPath,$simulator,$utf8)
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cases = @()
foreach ($case in @('default','loco','wrong_action','missing_job','validate_only','wrong_base','missing_collector','publish_failure','bad_path','bad_hash','oversize','duplicate')) {
    $env:LOCO_TRANSPORT_MODE = $case
    $action = if ($case -eq 'wrong_action') { 'Probe' } else { 'CollectExperiments' }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$simulatorPath,'-Action',$action)
    if ($case -ne 'default') { $arguments += '-LocoCollection' }
    if ($case -ne 'missing_job') { $arguments += @('-JobId','44235') }
    if ($case -eq 'validate_only') { $arguments += '-ValidateOnly' }
    if ($case -in @('wrong_base','missing_collector')) { $arguments += @('-CodeRoot',(Join-Path $validationRoot $case)) }
    & $powershell @arguments | Out-Null
    $code = $LASTEXITCODE
    $latest = Get-ChildItem -LiteralPath $validationRoot -Directory -Filter 'tc2_gpu_setup_*' | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    $callPath = Join-Path $latest.FullName 'offline_calls.jsonl'
    $calls = if (Test-Path -LiteralPath $callPath) { @(Get-Content -LiteralPath $callPath | ConvertFrom-Json) } else { @() }
    if ($case -in @('default','loco')) {
        if ($code) { throw ('Valid collection failed: ' + $case) }
        if (@($calls | Where-Object kind -eq 'verify').Count -ne 3) { throw 'Not every local verification action ran.' }
        $expectedSsh = if ($case -eq 'loco') { 2 } else { 1 }
        $expectedUpload = if ($case -eq 'loco') { 1 } else { 0 }
        if (@($calls | Where-Object kind -eq 'ssh').Count -ne $expectedSsh -or @($calls | Where-Object kind -eq 'upload').Count -ne $expectedUpload) { throw 'Unexpected collection upload/SSH flow.' }
        if ($case -eq 'loco') {
            $prov = Get-Content -LiteralPath (Join-Path $latest.FullName 'loco-collection-provenance.json') -Raw | ConvertFrom-Json
            $index = Get-Content -LiteralPath (Join-Path $latest.FullName 'experiments-index.json') -Raw | ConvertFrom-Json
            if ($prov.collector_sha256 -cne $index.collector_provenance.collector_sha256 -or $prov.base_collector_sha256 -cne $index.collector_provenance.base_collector_sha256) { throw 'Local provenance differs from the downloaded index.' }
        }
    } elseif (-not $code) { throw ('Invalid collection accepted: ' + $case) }
    if ($case -in @('wrong_action','missing_job','validate_only','wrong_base','missing_collector') -and $calls.Count) { throw 'Invalid local options triggered transport.' }
    if ($case -in @('bad_path','oversize','duplicate','publish_failure') -and @($calls | Where-Object kind -eq 'download').Count) { throw 'Invalid metadata triggered a download.' }
    if ($case -eq 'bad_hash' -and (Test-Path -LiteralPath (Join-Path $latest.FullName 'remote'))) { throw 'Wrong index hash triggered extraction.' }
    $cases += [pscustomobject]@{name=$case; exit_code=$code; status='passed'}
}
$rendered = @(Get-ChildItem -LiteralPath $validationRoot -Recurse -Filter 'command_*.sh')
$result = [ordered]@{status='passed'; validation_root=$validationRoot; rendered_shell_commands=$rendered.Count; cases=$cases; all_four_collection_operations_use_selected_collector=$true; all_rendered_bash_syntax='checked_separately'; actual_tc2_connections=0; actual_slurm_submissions=0}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'loco_transport_validation.json'),($result | ConvertTo-Json -Depth 5) + "`n",$utf8)
$result | ConvertTo-Json -Depth 5
