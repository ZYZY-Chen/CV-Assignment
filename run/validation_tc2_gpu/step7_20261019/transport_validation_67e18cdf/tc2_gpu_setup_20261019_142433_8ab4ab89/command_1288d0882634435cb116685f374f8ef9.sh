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
prior_inputs=$(cat "$(setup_record "last_prepare_inputs_job.txt")")
environment_job=$(cat "$(setup_record "last_prepare_environment_job.txt")")
[[ "$prior_inputs" =~ ^[0-9]+$ && "$environment_job" =~ ^[0-9]+$ ]] || exit 2
grep -Fq 'QT_XCB_GL_INTEGRATION: unbound variable' "$(setup_record "slurm-$prior_inputs.err")" || { echo 'Latest input job is not the recorded activation failure.' >&2; exit 2; }
[[ ! -e "$(setup_record "job_${prior_inputs}_prepare_inputs")" ]] || { echo 'Input Python already started; inspect before any retry.' >&2; exit 2; }
grep -Eq '"ready": true' "$(setup_record "job_${environment_job}_prepare_environment/preparation_status.json")" || exit 2
printf '%s' 'YTgxOGUzYzJlY2E2ZTgxNjM1M2Y3MDI5MDMzYjhlMjZlYjVlZjg1YmZkN2QyMjgxN2FiZWNjNjFmMGE1YTAyZiAxMzQzNDlhZWVkMWFjOTk3NzRjOWE1ZDI1YTQ4NDMzNGFmYWFjMzIwMThhN2MyZjQ0MTYwZGIwNTFjM2U5NTMyIHNjcmlwdHMvc2x1cm0vcHJlcGFyZV90YzJfZ3B1LnNoCmE4ZDA0YjYxYWIyZWZjNmNiOWFjMTBjZjViNzM2NzM3MGQ3Y2QwMjBmNjdlMjYwZTExZjczYjkyNTY4MDBiOWUgNjcyODQ3YThmMDFkNzA5MGEyZGQ2MzRmYzQ2ZjgyOTg4NmEwYTc5ZDA3NjU4ZmQ4ZGZjMWY0N2YxZWU1NDhhNSBzY3JpcHRzL3NsdXJtL2NoZWNrX3RjMl9ncHVfc2V0dXAuc2gK' | base64 -d | while read -r old_hash new_hash relative; do
    case "$relative" in scripts/slurm/prepare_tc2_gpu.sh|scripts/slurm/check_tc2_gpu_setup.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || { echo "Unrecognized script; no replacement: $relative" >&2; exit 2; }
done
