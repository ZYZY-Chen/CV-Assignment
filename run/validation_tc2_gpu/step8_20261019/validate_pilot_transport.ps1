# Offline fixtures only: SSH and SCP are replaced before any branch is invoked.
$ErrorActionPreference = 'Stop'
$sourcePath = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1'
$codeRoot = 'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code'
$python = 'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$utf8 = New-Object Text.UTF8Encoding($false)
$source = Get-Content -LiteralPath $sourcePath -Raw
$tokens = $null; $errors = $null
$tree = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$validationRoot = Join-Path 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output' ('s8_loco_offline_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $validationRoot
$fixtureRoot = Join-Path $validationRoot 'fixture'
$null = New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'configs') -Force
Copy-Item -LiteralPath (Join-Path $codeRoot 'configs/pilot_tc2_gpu.json') -Destination (Join-Path $fixtureRoot 'configs/pilot_tc2_gpu.json')
$env:PILOT_FIXTURE_ARCHIVE = Join-Path $validationRoot 'fixture.tar.gz'
& $python -I -B (Join-Path $codeRoot 'scripts/collect_tc2_gpu_pilot.py') export --root $fixtureRoot --job-id 12345 --archive $env:PILOT_FIXTURE_ARCHIVE | Out-Null
if ($LASTEXITCODE) { throw 'Cannot prepare local pilot output fixture.' }
$functions = @($tree.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
$replacements = @()
foreach ($name in @('Ssh','Native')) {
    $definition = $functions | Where-Object Name -eq $name
    if ($name -eq 'Ssh') {
        $replacement = @'
function Ssh([string]$remoteScript) {
    $name = 'command_' + [Guid]::NewGuid().ToString('N') + '.sh'
    [IO.File]::WriteAllText((Join-Path $localRoot $name),$remoteScript.Replace("`r",'') + "`n",$utf8)
    if ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript.Replace("`r",'')+"`n")).Length + 60 -gt 26000) { throw 'Rendered pilot SSH command exceeds its length guard.' }
    Log 'SIMULATED SSH ONLY: no network or job submission.'
    if ($remoteScript.Contains('PILOT_BOOTSTRAP_PY')) { Log 'TC2_JOB_ID=12345' }
    if ($remoteScript.Contains('export_json=$(')) {
        $path = $remoteRoot + '/tmp/pilot-12345-' + $runId + '.tar.gz'
        $hash = (Get-FileHash -LiteralPath $env:PILOT_FIXTURE_ARCHIVE -Algorithm SHA256).Hash
        $size = (Get-Item -LiteralPath $env:PILOT_FIXTURE_ARCHIVE).Length
        if ($env:PILOT_STUB_MODE -eq 'bad_path') { $path = '/tmp/untrusted.tar.gz' }
        if ($env:PILOT_STUB_MODE -eq 'bad_hash') { $hash = '0' * 64 }
        if ($env:PILOT_STUB_MODE -eq 'oversize') { $size = 536870913 }
        Log ('PILOT_EXPORT_PATH=' + $path)
        Log ('PILOT_EXPORT_SHA256=' + $hash)
        Log ('PILOT_EXPORT_BYTES=' + $size)
        if ($env:PILOT_STUB_MODE -eq 'duplicate') { Log ('PILOT_EXPORT_PATH=' + $path) }
    }
}
'@
    } else {
        $replacement = $definition.Extent.Text.Replace('function Native(', 'function OriginalNative(') + "`n" + @'
function Native([string]$program,[string[]]$nativeArguments) {
    if ($program -eq $scp) {
        if ($nativeArguments[-1] -eq (Join-Path $localRoot 'pilot-output.tar.gz')) {
            Copy-Item -LiteralPath $env:PILOT_FIXTURE_ARCHIVE -Destination $nativeArguments[-1]
        }
        Log 'SIMULATED SCP ONLY: local fixture transfer.'
        return
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
$simulatorPath = Join-Path $validationRoot 'simulated_pilot.ps1'
[IO.File]::WriteAllText($simulatorPath,$simulator,$utf8)
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cases = @()
foreach ($case in @('RunPilot','CollectPilot','bad_path','bad_hash','oversize','duplicate')) {
    $env:PILOT_STUB_MODE = $case
    $action = if ($case -eq 'RunPilot') { 'RunPilot' } else { 'CollectPilot' }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$simulatorPath,'-Action',$action)
    if ($action -eq 'CollectPilot') { $arguments += @('-JobId','12345') }
    & $powershell @arguments | Out-Null
    $code = $LASTEXITCODE
    if ($case -in @('RunPilot','CollectPilot')) {
        if ($code -ne 0) { throw ('Valid offline pilot transport failed: ' + $case) }
    } elseif ($code -eq 0) { throw ('Unsafe pilot metadata was accepted: ' + $case) }
    $cases += [pscustomobject]@{name=$case; exit_code=$code; status='passed'}
}
$env:PILOT_STUB_MODE = 'ValidateOnly'
& $powershell -NoProfile -ExecutionPolicy Bypass -File $simulatorPath -Action RunPilot -ValidateOnly | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Offline pilot package validation failed.' }
$rendered = @(Get-ChildItem -LiteralPath $validationRoot -Recurse -Filter 'command_*.sh')
if ($rendered.Count -ne 8) { throw ('Unexpected rendered pilot command count: ' + $rendered.Count) }
foreach ($output in Get-ChildItem -LiteralPath $validationRoot -Directory -Filter 'tc2_gpu_setup_*') {
    $log = Get-Content -LiteralPath (Join-Path $output.FullName 'terminal.txt') -Raw
    if ($log -match 'PILOT_EXPORT_PATH=/tmp/untrusted|PILOT_EXPORT_BYTES=536870913' -or ([regex]::Matches($log,'(?m)^PILOT_EXPORT_PATH=').Count -gt 1)) {
        if (Test-Path -LiteralPath (Join-Path $output.FullName 'pilot-output.tar.gz')) { throw 'Unsafe metadata led to a download.' }
    }
    if ($log -match ('PILOT_EXPORT_SHA256=' + ('0' * 64)) -and (Test-Path -LiteralPath (Join-Path $output.FullName 'remote'))) { throw 'Hash failure led to extraction.' }
}
$result = [ordered]@{status='passed'; validation_root=$validationRoot; rendered_shell_commands=$rendered.Count; cases=$cases; validate_only='passed'; actual_tc2_connections=0; actual_slurm_submissions=0}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'pilot_transport_validation.json'),($result | ConvertTo-Json -Depth 5)+"`n",$utf8)
$result | ConvertTo-Json -Depth 5
