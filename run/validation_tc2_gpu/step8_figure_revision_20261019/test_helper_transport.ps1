$ErrorActionPreference = 'Stop'
$helper = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup.ps1'
$fixtureRoot = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\fr_transport_20261019_b'
$localRoot = Join-Path $fixtureRoot ('client_' + [Guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $localRoot
$CodeRoot = 'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code'
$PythonExecutable = 'C:\Users\mhjv_\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$PSScriptRootForHelper = 'C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output'
$runId = '20261019_223000_a1b2c3d4'
$remoteRoot = '/home/mcaai/huajie001/ca6129_v2_setup'
$server = 'huajie001@10.96.189.12'
$scp = '__MOCK_SCP_NO_NETWORK__'
$tar = Join-Path $env:WINDIR 'System32\tar.exe'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$logPath = Join-Path $localRoot 'terminal.txt'
$JobId = ''; $ExperimentStage = ''; $InputDirectory = ''; $PreparationGpu = 0; $ValidateOnly = $false
$script:calls = New-Object Collections.Generic.List[object]
$script:sshCount = 0
$script:uploadCount = 0
$script:downloadCount = 0
function Log([string]$value) { [IO.File]::AppendAllText($logPath,$value + "`n",$utf8) }
function Native([string]$program,[string[]]$nativeArguments) {
    if ($program -eq $scp) {
        if ($nativeArguments[-1].StartsWith($server + ':')) { $script:uploadCount += 1; return }
        $script:downloadCount += 1
        $remote = $nativeArguments[-2]
        $name = if ($remote.EndsWith('/index.json')) { 'index.json' } elseif ($remote.EndsWith('/page_001.tar.gz')) { 'page_001.tar.gz' } else { throw 'Unexpected mock download.' }
        Copy-Item -LiteralPath (Join-Path $fixtureRoot ('source/tmp/export/' + $name)) -Destination $nativeArguments[-1]
        return
    }
    if ($program -notin @($PythonExecutable,$tar)) { throw 'Unapproved local executable in mock.' }
    & $program @nativeArguments > (Join-Path $localRoot ('native_' + $script:calls.Count + '_' + [Guid]::NewGuid().ToString('N').Substring(0,4) + '.txt')) 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('Local verification command failed: ' + $LASTEXITCODE) }
}
function Ssh([string]$remoteScript) {
    $script:sshCount += 1
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remoteScript.Replace("`r",'') + "`n"))
    $length = ("printf '%s' '" + $encoded + "' | base64 -d | bash -l -s").Length
    if ($length -gt 26000) { throw 'Generated SSH command exceeds real helper bound.' }
    $target = Join-Path $localRoot ('captured_' + $script:sshCount + '.sh')
    [IO.File]::WriteAllText($target,$remoteScript.Replace("`r",'') + "`n",$utf8)
    $script:calls.Add([ordered]@{path=$target;encoded_command_chars=$length;actual_executed=$false})
    if ($remoteScript.Contains('FIGURE_BOOTSTRAP_PY')) { Log 'TC2_JOB_ID=99991' }
    if ($remoteScript.Contains('export_json=')) {
        $fixture = Get-Content -LiteralPath (Join-Path $fixtureRoot 'fixture.json') -Raw | ConvertFrom-Json
        Log ('FIGURE_INDEX_PATH=' + $remoteRoot + '/tmp/figure-revision-99991-' + $runId + '/index.json')
        Log ('FIGURE_INDEX_SHA256=' + $fixture.index_sha256)
        Log 'FIGURE_PARTIAL=True'
    }
}
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($helper,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw 'Helper parse failure.' }
foreach ($name in @('Receive-FigureRevision','Run-FigureRevision')) {
    $node = @($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | Where-Object Name -eq $name)
    if ($node.Count -ne 1) { throw 'Missing helper function.' }
    $text = $node[0].Extent.Text.Replace('$PSScriptRoot','$PSScriptRootForHelper')
    Invoke-Expression $text
}
foreach ($name in @('guard','noOtherJobs','wait')) {
    $nodes = @($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst]},$false) | Where-Object { $_.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and $_.Left.VariablePath.UserPath -ceq $name })
    if ($nodes.Count -ne 1) { throw 'Missing helper remote guard.' }
    Invoke-Expression $nodes[0].Extent.Text
}
Log 'Local transport mock: no remote command is executed.'
Run-FigureRevision
if ($script:sshCount -ne 3 -or $script:uploadCount -ne 1 -or $script:downloadCount -ne 2) { throw 'Unexpected transport sequence.' }
$bootstrap = [IO.File]::ReadAllText($script:calls[1].path)
if ([regex]::Matches($bootstrap,'(?m)^job_id=\$\(sbatch ').Count -ne 1 -or $bootstrap.Contains('--gres') -or $bootstrap.Contains('--nodelist') -or -not $bootstrap.Contains('--cpus-per-task=2 --mem=8G --time=00:15:00')) { throw 'Resource/submission scope differs.' }
$receipt = [ordered]@{status='passed';actual_tc2_connections=0;actual_slurm_submissions=0;mock_submissions=1;mock_uploads=$script:uploadCount;mock_downloads=$script:downloadCount;remote_scripts=$script:calls.ToArray();pending_snapshot_verified=$true;client_directory=$localRoot;helper_sha256=(Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash}
[IO.File]::WriteAllText((Join-Path $localRoot 'transport_mock.json'),($receipt | ConvertTo-Json -Depth 6) + "`n",$utf8)
Write-Output ('Transport mock passed: ' + $localRoot)
