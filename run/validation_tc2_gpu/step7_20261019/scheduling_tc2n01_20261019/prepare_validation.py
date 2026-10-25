"""Extend the prior isolated transport harness without touching historical audits."""
from pathlib import Path

audit = Path(__file__).parent
path = audit / "validate_experiments_helper.ps1"
source = path.read_text(encoding="utf-8")
source = source.replace(
    "foreach ($case in @('RunExperimentsFit','RunExperimentsAnalysis','CollectExperiments','bad_path','bad_hash','oversize','duplicate','missing_stage')) {",
    "foreach ($case in @('RunExperiments_B0','RunExperiments_H1','RunExperiments_H2','RunExperiments_C1','RunExperiments_I1_seed17','RunExperiments_R0','RunExperiments_C1R','RunExperiments_C2','RunExperiments_F1','RunExperiments_I1_all_seeds','RunExperiments_I2','RunExperiments_B0_LOCO','CollectExperiments','bad_path','bad_hash','oversize','duplicate','missing_stage')) {",
)
source = source.replace(
    "elseif ($case -eq 'RunExperimentsAnalysis') { $arguments += @('-Stage','I1_seed17') }\n    elseif ($case -ne 'missing_stage') { $arguments += @('-Stage','B0') }",
    "elseif ($case -like 'RunExperiments_*') { $arguments += @('-Stage',$case.Substring('RunExperiments_'.Length)) }",
)
source = source.replace(
    "if ($case -in @('RunExperimentsFit','RunExperimentsAnalysis','CollectExperiments')) {",
    "if ($case -like 'RunExperiments_*' -or $case -eq 'CollectExperiments') {",
)
start = source.index("if ($rendered.Count -ne 11)")
end = source.index("$result = [ordered]", start)
source = source[:start] + r'''if ($rendered.Count -ne 41) { throw ('Unexpected rendered experiment command count: ' + $rendered.Count) }
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
''' + source[end:]
source = source.replace("rendered_shell_commands=$rendered.Count;", "rendered_shell_commands=$rendered.Count; gpu_fit_stages=$fitSubmission.Count; cpu_analysis_stages=$cpuSubmission.Count; all_fit_stages_select_TC2N01=$true; analysis_stages_do_not_select_nodes=$true;")
path.write_text(source, encoding="utf-8", newline="\n")
print("Prepared isolated validation for all twelve stages.")
