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
if [[ -n "$(squeue --noheader --user=huajie001 --format=%i)" ]]; then
    echo 'A personal job is already queued or running. Collect it before submitting another setup job.' >&2
    exit 2
fi
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
printf '%s' 'MzA5OGI2YTg2ZGJhNjRlZTQzOWJmZTYxYzdhNGZjZmZjZDA4MjM3MWQ1YTgwZmZiYzc5NDA5OTdlZDZhMWVkMSAgY29uZmlncy9wcm90b2NvbF92Mi5qc29uCjI5MjJmYTZlNTEzZjk4MGNiZGU1M2EzMDNmODZmZTExNjA1ODhkZjdlZmIwNzk2ZjY4ODhjOTVkMmJhYjYxNDAgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF9ib3R0bGUuanNvbgplMTg4ZDA1YmQyNDZjMjk1MDNhMzVkYmFmNDlkYmNjMzI2YTM1MDc5ZWNjMDc5NzNhZTFhN2JjY2ZkMDhmZDk1ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfY2FibGUuanNvbgowZTlmMWJmNTM2OGRlMDNhMmE2YmU1N2NkOGIxM2Q4Y2U5ZDQ4NGRlM2EwNTYzNTIwNmM3ZDhmYzI4ZDFlMzY3ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfY2Fwc3VsZS5qc29uCmUyMDlmNDQyOWM0MDU2ZWNmYTZmMmRhODJmYWE5YjViM2FlNDk1ZWJmZGJmOTRkNTgwOGM5Njc2ZDhhOTlmOWIgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF9zY3Jldy5qc29uCjJiNDI3NGZlNzZiYmNiY2UzYjk2OGNjY2FhMGYzZGFhNjE1MWZhZjlhYTYzNTg0NDVhY2RhMWI1ZGZiZWU5NGMgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF90aWxlLmpzb24KNTc2NDYwMDdlYmFmZThmMDE1Zjk3NjE4NjE5N2E3YTA4ZDMzOGVjYWViNmJmOGI1ZDM3NjRkZTlhNDY4ODhhZSAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX3dvb2QuanNvbgplNTRhYjNmYTM1NGUyNThkNTkxZjZjNTNiMzk1ZWQ5ZWVkMjU1MThjZjI1ZjAzOWZlYjg4MDQwYTJlYzQ2Yzg2ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfbG9jb19qdWljZV9ib3R0bGUuanNvbgo3YzAyZWQxY2YzM2FmZDM1ZjhiZWZiNzM0MjUyNWY1MzIyMTNjYzY4NGFkYzMzMDQxNDUyMmRiNTFiMWM2NmNhICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfbG9jb19zY3Jld19iYWcuanNvbgo0N2YxZGFhODNhNzQ0NzQzOTQ2YzgzZTZkYzE5NjNiOGZhN2U4MzVhNGEwZjcwMTBhM2IwNTAxZWY1YTNkZjM4ICBlbnZpcm9ubWVudC10YzIueW1sCmY3Yjg0OGYxMGZmYjNmM2NjZWI3MDc0NTBiMmE1ZmU0ZGNkOWE2YzNiNDg5OTYzYTg5MzIwOTRlMDE2ODQwYjYgIHJlcXVpcmVtZW50cy10YzItbG9jay50eHQK' | base64 -d | sha256sum --check -
# Preserve the original remote compatibility snapshot; never upload the local summary.
[[ "$(sha256sum configs/tc2_setup.json | cut -d' ' -f1)" == edf3d1d0380e0105a5173607ce360221fd43b059478915eec0ec04ed9110f913 ]] || { echo 'Unknown remote compatibility configuration; no overwrite.' >&2; exit 2; }
[[ "$(sha256sum weights/resnet18-f37072fd.pth | cut -d' ' -f1)" == f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec ]] || exit 2
printf '%s' 'ZGQ2NDZmMjZlNjFjODliNjIyZDBkMmIxZGU1MDQ2MjM4M2NlMjJkMmFlZjVjN2FhNzlmM2FmNWI5OWRlNDRiNiAgc3JjL3RjMl9ncHVfcHJvdG9jb2wucHkKODY3YzMxZGZkODdlNWJmYzZlYzQ3ODMxODNkOTI3MTkyYWJiYzJhMTE0MDYxMGM3OWU1YThkODQyNjc0MjQ5NSAgc3JjL3RjMl9ncHVfY2FjaGUucHkKY2VkYzRlY2Q1NDNkYzI1ZWZhNmU0MDAzZjE1ODk1NGM3NzViODQyYjk4YTI2MDliZTk0MzkyOGFhOTAwNjI4ZCAgc3JjL3RjMl9ncHVfcnVubmVyLnB5CjVmOTE5OWQ4MjBjY2FkODBmMGM2MDY1ZjYxMjc3NmUzNDY3YmRlNWY5NzhhYzI0MGIzNjBiNDJkNmQzNmY5MjEgIHNjcmlwdHMvcnVuX3RjMl9ncHUucHkKYjA1Nzc2NmFmZGY0NzNhODllNzQwMTZiMmY5ZGY2YjMxMTUxMGJhOGU0NDRkNDJlZTE0YzA3NWJhZjA4YWVhYSAgY29uZmlncy9ydW50aW1lX3RjMl9ncHUuanNvbgo1MTMwMTg0ZDliZDc2ODQwYWYxYmQ4Y2EyMTdjMTg2NDYxOGIyMjhlZDE1YjdhMmYzNzJmMGI1ZTk0OTczNGNjICB0ZXN0cy90ZXN0X3dvcmtmbG93X3RjMl9ncHUucHkKODk0MDYxMjg0MmI5MWZkMzcwOWZkNjQzZWI3MjA0YWI4YmZmMjMyNDljMTM5ZTBiNDQxYmVkNzIwMmM4YzE2ZCAgc2NyaXB0cy9zbHVybS9jaGVja190YzJfZ3B1X3dvcmtmbG93LnNoCmFiMWY4OTQxZGI2MmY3MDFhYThmN2FlMWJhNjA0MzBlMjhmNGVjNGM4OTJkMGYwNDNjY2Y4M2UwN2FmYWUxZWMgIGRvY3MvVEMyX0dQVV9XT1JLRkxPVy5tZAo4MDNlMzBmMWFkMWY1OTFiZGQyNmMwZDQ1OGQyNTJkMzk3NTc4ZjhlNTM5ODQ4Njg1NWRhYzAyNTdmNDQzYWIzICBzcmMvcGFkaW1fYWRhcHRlci5weQo0ODc3ZDY2NjI1MTgwYmIzNjI1OGVhNmI5OWRlOTQyN2U1NDU3NjQ2MTRhYjBjYjI0NWY1ZmFmYzQ0ZWMzMDdmICBzcmMvcGF0Y2hjb3JlX2FkYXB0ZXIucHkKYmVkYjMzMDU3YmM3ZTkzODEwOGU0YjliMTc3ZWNkZTEyMTQxOGIyNGRjMzQ4Y2RmMDdhZDA0ZjNmMDI4NGI3OSAgc3JjL3NhbXBsaW5nLnB5CmU4MzQ4NTUwZjBhNTVjYzhhMWVkYmI0YjEzMTBmYmU5ODU0OTNmMjJkYWU3MWI2YjU2MmYzNDcyMGMzZDRiMGIgIHNyYy9zY29yaW5nLnB5CjRiZDllOWJlM2NhZDdiOTBhMjRmN2RiZmFhYmRiNTVlYjQwM2M5NGJjZjRiNzcxZmY5ZDczYTA2MzFiOWQ0YmQgIHNyYy9hbm9tYWx5X3Bvc3Rwcm9jZXNzLnB5CjUyMDBhYWUyNDBlNjRkMjJjYWVjY2JkNDY2MTVkZGUxMWY1MTE4OWM2MTI5MzgwNDZkYzJkNGEwMDllMTZlZGYgIHRlc3RzL3Rlc3RfYWxnb3JpdGhtc190YzJfZ3B1LnB5CjMyODc5YmNhMzE3YjQ0ZGQ3ZjE5NjA4OGYyNzE4YjMxODg4ODllNDdkMzRiMjNjOGEyNGQ2MDI0NzIwZThkY2MgIHNjcmlwdHMvc2x1cm0vY2hlY2tfdGMyX2dwdV9hbGdvcml0aG1zLnNoCmQyMThhNDM4MDMxZGU2YjBhODNiMTQ5NTEzNTRjZDY2YTg1ZWQ2NWY5N2ZmYzJjZmJhZWZmMWQ0ZmI5MWRiNzggIHNyYy9tZXRyaWNfY29yZS5weQo0ZGIyNDEzY2M2YWFmNDIxMGIxNDMyODVmZTVmZDdmYzZhOGMwOGU5OGM2NzA3M2U5YTkyZDMxMzU5ZTY4YmM2ICBzcmMvZXZhbHVhdGUucHkKOWE4MmQ1ODUyMDNiMzc2ZjQxYzMyMDBhMzJkNjk3MTI4OGRkNzBiNWM3ZTcxMjEwZjNlMjFmOGM1YzFmMWY4OSAgc3JjL2RhdGEucHkKZWIyODk5YjJlNjg4ODIzMzg3NGM4ZmE5N2IxMjQ3YWJkM2U2OGIzOTE1MzhjODZhMzYxMDU0MTA5MTdhMDBmMCAgY29uZmlncy90YzJfZ3B1Lmpzb24KODBiNDg5YjgzOTkwZGUyNWMyYmU0ZjA1NWZhMzgyMjQ3ZmQwYjkwOTFkMTk0NzY0ZWMzYzAyZGQzNzAzMTNmZCAgdGVzdHMvdGVzdF9tZXRyaWNzX3RjMl9ncHUucHkKOTNlNjQzMDkzNDgwODJlMWViZGVmMmIxNzA3YmE1YTFhNThlZjk1YzNlNmU1Mzk1YTgyMDkxOTFmYjBkMTUxOSAgc2NyaXB0cy9zbHVybS9jaGVja190YzJfZ3B1X21ldHJpY3Muc2gKMzA5OGI2YTg2ZGJhNjRlZTQzOWJmZTYxYzdhNGZjZmZjZDA4MjM3MWQ1YTgwZmZiYzc5NDA5OTdlZDZhMWVkMSAgY29uZmlncy9wcm90b2NvbF92Mi5qc29uCjQ3ZjFkYWE4M2E3NDQ3NDM5NDZjODNlNmRjMTk2M2I4ZmE3ZTgzNWE0YTBmNzAxMGEzYjA1MDFlZjVhM2RmMzggIGVudmlyb25tZW50LXRjMi55bWwKZjdiODQ4ZjEwZmZiM2YzY2NlYjcwNzQ1MGIyYTVmZTRkY2Q5YTZjM2I0ODk5NjNhODkzMjA5NGUwMTY4NDBiNiAgcmVxdWlyZW1lbnRzLXRjMi1sb2NrLnR4dAoyOTIyZmE2ZTUxM2Y5ODBjYmRlNTNhMzAzZjg2ZmUxMTYwNTg4ZGY3ZWZiMDc5NmY2ODg4Yzk1ZDJiYWI2MTQwICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfYm90dGxlLmpzb24KZTE4OGQwNWJkMjQ2YzI5NTAzYTM1ZGJhZjQ5ZGJjYzMyNmEzNTA3OWVjYzA3OTczYWUxYTdiY2NmZDA4ZmQ5NSAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX2NhYmxlLmpzb24KMGU5ZjFiZjUzNjhkZTAzYTJhNmJlNTdjZDhiMTNkOGNlOWQ0ODRkZTNhMDU2MzUyMDZjN2Q4ZmMyOGQxZTM2NyAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX2NhcHN1bGUuanNvbgplMjA5ZjQ0MjljNDA1NmVjZmE2ZjJkYTgyZmFhOWI1YjNhZTQ5NWViZmRiZjk0ZDU4MDhjOTY3NmQ4YTk5ZjliICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfc2NyZXcuanNvbgoyYjQyNzRmZTc2YmJjYmNlM2I5NjhjY2NhYTBmM2RhYTYxNTFmYWY5YWE2MzU4NDQ1YWNkYTFiNWRmYmVlOTRjICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfdGlsZS5qc29uCjU3NjQ2MDA3ZWJhZmU4ZjAxNWY5NzYxODYxOTdhN2EwOGQzMzhlY2FlYjZiZjhiNWQzNzY0ZGU5YTQ2ODg4YWUgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF93b29kLmpzb24KZTU0YWIzZmEzNTRlMjU4ZDU5MWY2YzUzYjM5NWVkOWVlZDI1NTE4Y2YyNWYwMzlmZWI4ODA0MGEyZWM0NmM4NiAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2xvY29fanVpY2VfYm90dGxlLmpzb24KN2MwMmVkMWNmMzNhZmQzNWY4YmVmYjczNDI1MjVmNTMyMjEzY2M2ODRhZGMzMzA0MTQ1MjJkYjUxYjFjNjZjYSAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2xvY29fc2NyZXdfYmFnLmpzb24K' | base64 -d | while read -r hash relative; do
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
archive="$root/_downloads/workflow-files-20261019_103904_58024765.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 77da778d11e11373bff72833327bb34e7bb73f46ee293fc0cbb1d0e186c10953 ]] || { echo 'Workflow bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/workflow-files-20261019_103904_58024765"
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
stage_record="$root/run/validation_tc2_gpu/workflow_stage_20261019_103904_58024765"
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
echo "TC2_JOB_ID=$job_id"
for attempt in 1 2 3 4; do
    [[ -n "$(squeue --noheader --jobs="$job_id" --format=%i)" ]] || break
    sleep 10
done
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
archive="$root/tmp/collect_20261019_103904_58024765.tar.gz"
list="$root/tmp/collect_20261019_103904_58024765.list"
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
