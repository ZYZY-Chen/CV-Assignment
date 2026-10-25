# Offline fixtures only. All SSH/SCP calls are replaced; no network is used.
$ErrorActionPreference = 'Stop'
$sourcePath = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_setup_v2.ps1'
$source = Get-Content -LiteralPath $sourcePath -Raw
$tokens = $null
$errors = $null
$tree = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$validationRoot = Join-Path $PSScriptRoot ('transport_validation_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $validationRoot
$utf8 = New-Object Text.UTF8Encoding($false)
$functions = @($tree.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
$replacements = @()
foreach ($name in @('Ssh','Native')) {
    $definition = $functions | Where-Object Name -eq $name
    if ($name -eq 'Ssh') {
        $replacement = @'
function Ssh([string]$remoteScript) {
    $name = 'command_' + [Guid]::NewGuid().ToString('N') + '.sh'
    [IO.File]::WriteAllText((Join-Path $localRoot $name), $remoteScript.Replace("`r",'') + "`n", $utf8)
    Log 'SIMULATED SSH ONLY: rendered commands saved; no remote action.'
}
'@
    } else {
        $replacement = $definition.Extent.Text.Replace('function Native(', 'function OriginalNative(') + "`n" + @'
function Native([string]$program, [string[]]$nativeArguments) {
    if ($program -eq $scp -or $program -eq $PythonExecutable) { Log 'SIMULATED TRANSFER/DOWNLOAD ONLY: no network.'; return }
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
$simulatorPath = Join-Path $validationRoot 'simulated_transport.ps1'
[IO.File]::WriteAllText($simulatorPath,$simulator,$utf8)
$fixtureInput = Join-Path $validationRoot 'fixture_inputs'
$null = New-Item -ItemType Directory -Path $fixtureInput
[IO.File]::WriteAllText((Join-Path $fixtureInput 'bottle.tar.xz'),'Synthetic transfer fixture; never uploaded.',$utf8)
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
foreach ($action in @('Probe','PrepareEnvironment','PrepareInputs','CheckEnvironment','CheckAll','Collect','UploadInputs','RepairActivation','UpdateInputSources','DownloadInputs','CheckMetrics')) {
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$simulatorPath,'-Action',$action)
    if ($action -eq 'Collect') { $arguments += @('-JobId','12345') }
    if ($action -eq 'UploadInputs') { $arguments += @('-InputDirectory',$fixtureInput) }
    & $powershell @arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw ('Offline rendering failed: ' + $action) }
}
$rendered = @(Get-ChildItem -LiteralPath $validationRoot -Recurse -Filter 'command_*.sh')
if ($rendered.Count -ne 15) { throw ('Unexpected rendered transport command count: ' + $rendered.Count) }
foreach ($renderedFile in $rendered) {
    $bytes=[Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText($renderedFile.FullName)+"`n")
    if ([Convert]::ToBase64String($bytes).Length+60 -gt 26000) { throw 'Rendered SSH command exceeds the command-length guard.' }
}

# Run the real output decoder against a local fake SSH executable.
foreach ($function in $functions) { Invoke-Expression $function.Extent.Text }
$tar = Join-Path $env:WINDIR 'System32\tar.exe'
$server = 'offline-fixture'
$fixtureRoot = Join-Path $validationRoot 'artifact_fixture'
$null = New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'run/setup_v2') -Force
[IO.File]::WriteAllText((Join-Path $fixtureRoot 'run/setup_v2/fixture.json'),'{"synthetic":true}',$utf8)
$null = New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'run/validation_v2') -Force
[IO.File]::WriteAllText((Join-Path $fixtureRoot 'run/validation_v2/fixture.json'),'{"synthetic":true}',$utf8)
$goodArchive = Join-Path $validationRoot 'good.tar.gz'
& $tar -czf $goodArchive -C $fixtureRoot run/setup_v2/fixture.json run/validation_v2/fixture.json
if ($LASTEXITCODE -ne 0) { throw 'Cannot build local fixture archive.' }
[IO.File]::WriteAllText((Join-Path $fixtureRoot 'unexpected.txt'),'Not an allowed output path.',$utf8)
$badArchive = Join-Path $validationRoot 'bad.tar.gz'
& $tar -czf $badArchive -C $fixtureRoot unexpected.txt
if ($LASTEXITCODE -ne 0) { throw 'Cannot build negative fixture archive.' }
$ssh = Join-Path $validationRoot 'fake_ssh.ps1'
function FakeSsh([string]$archive,[string]$hash) {
    $body = [Convert]::ToBase64String([IO.File]::ReadAllBytes($archive))
    $text = "Write-Output 'OFFLINE SSH FIXTURE'`nWrite-Output 'TC2_ARTIFACT_SHA256=$hash'`nWrite-Output '__TC2_ARTIFACT_BEGIN__'`nWrite-Output '$body'`nWrite-Output '__TC2_ARTIFACT_END__'`nexit 0`n"
    [IO.File]::WriteAllText($ssh,$text,$utf8)
}
foreach ($case in @('good','bad_hash','bad_path')) {
    $localRoot = Join-Path $validationRoot $case
    $null = New-Item -ItemType Directory -Path $localRoot
    $logPath = Join-Path $localRoot 'terminal.txt'
    $archive = if ($case -eq 'bad_path') { $badArchive } else { $goodArchive }
    $hash = if ($case -eq 'bad_hash') { '0' * 64 } else { (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash }
    FakeSsh $archive $hash
    $refused = $false
    try { Ssh 'This is ignored by the local fake executable.' } catch { $refused = $true }
    if ($case -eq 'good') {
        if ($refused -or -not (Test-Path -LiteralPath (Join-Path $localRoot 'remote/run/setup_v2/fixture.json')) -or -not (Test-Path -LiteralPath (Join-Path $localRoot 'remote/run/validation_v2/fixture.json'))) { throw 'Valid output stream did not round-trip.' }
    } elseif (-not $refused -or (Test-Path -LiteralPath (Join-Path $localRoot 'remote'))) {
        throw ('Unsafe output stream was not refused: ' + $case)
    }
}
$result = [ordered]@{status='PASS'; validation_root=$validationRoot; rendered_shell_commands=$rendered.Count; actual_ssh_calls=0; actual_scp_calls=0; archive_round_trip='PASS'; hash_mismatch_refusal='PASS'; unexpected_archive_path_refusal='PASS'}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'local_transport_validation.json'),($result | ConvertTo-Json) + "`n",$utf8)
$result | ConvertTo-Json
