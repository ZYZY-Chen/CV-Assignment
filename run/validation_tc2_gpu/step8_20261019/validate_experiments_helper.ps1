# All transport calls are replaced before executing the offline action branches.
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
Copy-Item -LiteralPath (Join-Path $codeRoot 'configs/experiments_tc2_gpu.json') -Destination (Join-Path $fixtureRoot 'configs/experiments_tc2_gpu.json')
$null = New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'tmp') -Force
$env:EXPERIMENTS_FIXTURE = Join-Path $fixtureRoot 'tmp/experiments-12345-offline'
& $python -I -B (Join-Path $codeRoot 'scripts/collect_experiments_tc2_gpu.py') export --root $fixtureRoot --job-id 12345 --directory $env:EXPERIMENTS_FIXTURE --stage B0 | Out-Null
if ($LASTEXITCODE) { throw 'Cannot prepare a bounded local experiment output fixture.' }
$functions = @($tree.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
$replacements = @()
foreach ($name in @('Ssh','Native')) {
    $definition = $functions | Where-Object Name -eq $name
    if ($name -eq 'Ssh') {
        $replacement = @'
function Ssh([string]$remoteScript) {
    $name = 'command_' + [Guid]::NewGuid().ToString('N') + '.sh'
    [IO.File]::WriteAllText((Join-Path $localRoot $name),$remoteScript.Replace("`r",'') + "`n",$utf8)
    if ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript.Replace("`r",'')+"`n")).Length + 60 -gt 26000) { throw 'Rendered experiment SSH command exceeds its length guard.' }
    Log 'SIMULATED SSH ONLY: no network or job submission.'
    if ($remoteScript.Contains('EXPERIMENTS_BOOTSTRAP_PY')) { Log 'TC2_JOB_ID=12345' }
    if ($remoteScript.Contains('export_json=$(')) {
        $path = $remoteRoot + '/tmp/experiments-12345-' + $runId + '/index.json'
        $hash = (Get-FileHash -LiteralPath (Join-Path $env:EXPERIMENTS_FIXTURE 'index.json') -Algorithm SHA256).Hash
        $count = 1
        if ($env:EXPERIMENTS_STUB_MODE -eq 'bad_path') { $path = '/tmp/untrusted/index.json' }
        if ($env:EXPERIMENTS_STUB_MODE -eq 'bad_hash') { $hash = '0' * 64 }
        if ($env:EXPERIMENTS_STUB_MODE -eq 'oversize') { $count = 33 }
        Log ('EXPERIMENTS_INDEX_PATH=' + $path)
        Log ('EXPERIMENTS_INDEX_SHA256=' + $hash)
        Log ('EXPERIMENTS_PAGE_COUNT=' + $count)
        if ($env:EXPERIMENTS_STUB_MODE -eq 'duplicate') { Log ('EXPERIMENTS_INDEX_PATH=' + $path) }
    }
}
'@
    } else {
        $replacement = $definition.Extent.Text.Replace('function Native(', 'function OriginalNative(') + "`n" + @'
function Native([string]$program,[string[]]$nativeArguments) {
    if ($program -eq $scp) {
        $target = $nativeArguments[-1]
        if ($target -eq (Join-Path $localRoot 'experiments-index.json')) {
            Copy-Item -LiteralPath (Join-Path $env:EXPERIMENTS_FIXTURE 'index.json') -Destination $target
        } elseif ($target -match 'page_[0-9]{3}\.tar\.gz$') {
            Copy-Item -LiteralPath (Join-Path $env:EXPERIMENTS_FIXTURE ([IO.Path]::GetFileName($target))) -Destination $target
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
$simulatorPath = Join-Path $validationRoot 'simulated_experiments.ps1'
[IO.File]::WriteAllText($simulatorPath,$simulator,$utf8)
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cases = @()
foreach ($case in @('RunExperiments_B0','RunExperiments_H1','RunExperiments_H2','RunExperiments_C1','RunExperiments_I1_seed17','RunExperiments_R0','RunExperiments_C1R','RunExperiments_C2','RunExperiments_F1','RunExperiments_I1_all_seeds','RunExperiments_I2','RunExperiments_B0_LOCO','CollectExperiments','bad_path','bad_hash','oversize','duplicate','missing_stage')) {
    $env:EXPERIMENTS_STUB_MODE = $case
    $action = if ($case -like 'RunExperiments*' -or $case -eq 'missing_stage') { 'RunExperiments' } else { 'CollectExperiments' }
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$simulatorPath,'-Action',$action)
    if ($action -eq 'CollectExperiments') { $arguments += @('-JobId','12345') }
    elseif ($case -like 'RunExperiments_*') { $arguments += @('-Stage',$case.Substring('RunExperiments_'.Length)) }
    & $powershell @arguments | Out-Null
    $code = $LASTEXITCODE
    if ($case -like 'RunExperiments_*' -or $case -eq 'CollectExperiments') {
        if ($code -ne 0) { throw ('Valid offline experiment transport failed: ' + $case) }
    } elseif ($code -eq 0) { throw ('Unsafe experiment metadata was accepted: ' + $case) }
    $cases += [pscustomobject]@{name=$case; exit_code=$code; status='passed'}
}
& $powershell -NoProfile -ExecutionPolicy Bypass -File $simulatorPath -Action RunExperiments -Stage B0 -ValidateOnly | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Offline experiment package validation failed.' }
$rendered = @(Get-ChildItem -LiteralPath $validationRoot -Recurse -Filter 'command_*.sh')
if ($rendered.Count -ne 41) { throw ('Unexpected rendered experiment command count: ' + $rendered.Count) }
$fitSubmission = @($rendered | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -match 'sbatch.*--gres=gpu:1' })
$cpuSubmission = @($rendered | Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -match 'sbatch.*--mem=8G' })
if ($fitSubmission.Count -ne 9 -or $cpuSubmission.Count -ne 3) { throw 'Expected nine rendered fit and three rendered analysis submissions.' }
foreach ($file in @($fitSubmission + $cpuSubmission)) {
    $text = Get-Content -LiteralPath $file.FullName -Raw
    if ($text -notmatch '(?s)cd -- "\$root".*sbatch --chdir="\$root"') { throw 'Submission directory protections are missing.' }
    if ($text -notmatch '\[\[ "\$\(pwd -P\)" == "\$root" \]\]') { throw 'Submission directory identity check is missing.' }
    if ($text -notmatch 'sbatch[^\n]*--partition=MGPU-TC2 --qos=normal') { throw 'Submission partition or QoS changed.' }
    if ($text -notmatch 'TC2_EXPERIMENT_STAGE=(B0|H1|H2|C1|I1_seed17|R0|C1R|C2|F1|I1_all_seeds|I2|B0_LOCO)"') { throw 'Submission stage was not rendered.' }
}
foreach ($file in $fitSubmission) {
    $text = Get-Content -LiteralPath $file.FullName -Raw
    $submission = [regex]::Match($text,'(?m)^job_id=\$\(sbatch[^\r\n]+').Value
    if ($submission -notmatch '--nodelist=TC2N01') { throw 'Fit stage does not select TC2N01.' }
    if ([regex]::Matches($submission,'--nodelist=').Count -ne 1) { throw 'Fit stage has an ambiguous node request.' }
    if ($submission -notmatch '--gres=gpu:1 --cpus-per-task=2 --mem=24G --time=02:00:00') { throw 'Fit resource request changed.' }
}
foreach ($file in $cpuSubmission) {
    $text = Get-Content -LiteralPath $file.FullName -Raw
    $submission = [regex]::Match($text,'(?m)^job_id=\$\(sbatch[^\r\n]+').Value
    if ($submission -match '--gres|--nodelist|--constraint') { throw 'CPU analysis unexpectedly selects a GPU or node.' }
    if ($submission -notmatch '--cpus-per-task=2 --mem=8G --time=00:15:00') { throw 'Analysis resource request changed.' }
}
$result = [ordered]@{status='passed'; validation_root=$validationRoot; rendered_shell_commands=$rendered.Count; gpu_fit_stages=$fitSubmission.Count; cpu_analysis_stages=$cpuSubmission.Count; all_fit_stages_select_TC2N01=$true; analysis_stages_do_not_select_nodes=$true; cases=$cases; validate_only='passed'; actual_tc2_connections=0; actual_slurm_submissions=0}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'experiments_transport_validation.json'),($result | ConvertTo-Json -Depth 5)+"`n",$utf8)
$result | ConvertTo-Json -Depth 5
