set -euo pipefail
[[ "$(id -un)" == huajie001 && "$HOME" == /home/mcaai/huajie001 ]] || { echo 'Unexpected remote identity or HOME.' >&2; exit 2; }
root=/home/mcaai/huajie001/ca6129_v2_setup
[[ ! -L "$root" && "$(readlink -m -- "$root")" == "$root" ]] || { echo 'Unexpected root or symbolic link.' >&2; exit 2; }
for relative in run run/setup_v2 run/validation_v2 configs scripts tmp _downloads _package_cache envs; do
    candidate="$root/$relative"
    [[ ! -L "$candidate" && "$(readlink -m -- "$candidate")" == "$candidate" ]] || { echo "Unsafe staging path: $relative" >&2; exit 2; }
done
if [[ -n "$(squeue --noheader --user=huajie001 --format=%i)" ]]; then
    echo 'A personal job is already queued or running. Collect it before submitting another setup job.' >&2
    exit 2
fi
cd -- "$root"
prior_inputs=$(cat run/setup_v2/last_prepare_inputs_job.txt)
environment_job=$(cat run/setup_v2/last_prepare_environment_job.txt)
[[ "$prior_inputs" =~ ^[0-9]+$ && "$environment_job" =~ ^[0-9]+$ ]] || exit 2
grep -Fq 'QT_XCB_GL_INTEGRATION: unbound variable' "run/setup_v2/slurm-$prior_inputs.err" || { echo 'Latest input job is not the recorded activation failure.' >&2; exit 2; }
[[ ! -e "run/setup_v2/job_${prior_inputs}_prepare_inputs" ]] || { echo 'Input Python already started; inspect before any retry.' >&2; exit 2; }
grep -Eq '"ready": true' "run/setup_v2/job_${environment_job}_prepare_environment/preparation_status.json" || exit 2
printf '%s' 'YTgxOGUzYzJlY2E2ZTgxNjM1M2Y3MDI5MDMzYjhlMjZlYjVlZjg1YmZkN2QyMjgxN2FiZWNjNjFmMGE1YTAyZiAxNWUyNWQyNTgzYWUyMDhjYjg3MTBiMWY4ZWE3ZGRiM2VlMTcyMDllMDk1MGI0MmRiYzE5YTIyZWJmNjgwMDI3IHNjcmlwdHMvc2x1cm0vcHJlcGFyZV90YzJfdjIuc2gKYThkMDRiNjFhYjJlZmM2Y2I5YWMxMGNmNWI3MzY3MzcwZDdjZDAyMGY2N2UyNjBlMTFmNzNiOTI1NjgwMGI5ZSBmYzljZjNkZDg4YTk0YmJjZTJjZGUyNDdlYmYzNGM0MTgzNmQ3YjNlNmY5MmU5NTdiMDNkYzMyZjdiNDM0OGNlIHNjcmlwdHMvc2x1cm0vY2hlY2tfc2V0dXBfdjIuc2gK' | base64 -d | while read -r old_hash new_hash relative; do
    case "$relative" in scripts/slurm/prepare_tc2_v2.sh|scripts/slurm/check_setup_v2.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || { echo "Unrecognized script; no replacement: $relative" >&2; exit 2; }
done
