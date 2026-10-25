# Parse only local generated scripts; this script never evaluates remote commands.
$ErrorActionPreference = 'Stop'
$bash = 'C:\Program Files\Git\bin\bash.exe'
$validation = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'pilot_transport_validation.json') -Raw | ConvertFrom-Json
$files = @(Get-ChildItem -LiteralPath $validation.validation_root -Recurse -Filter 'command_*.sh')
$files += Get-Item -LiteralPath 'C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code\scripts\slurm\pilot_tc2_gpu.sh'
foreach ($file in $files) {
    & $bash -n $file.FullName.Replace('\','/')
    if ($LASTEXITCODE -ne 0) { throw ('Bash syntax failed: ' + $file.FullName) }
}
$value = [ordered]@{status='passed'; scripts_parsed=$files.Count; parsing_only=$true; actual_tc2_connections=0; actual_slurm_submissions=0}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'helper_bash_validation.json'),($value | ConvertTo-Json)+"`n",(New-Object Text.UTF8Encoding($false)))
$value | ConvertTo-Json
