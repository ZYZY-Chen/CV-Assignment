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
archive="$root/_downloads/activation-fix-20261019_082938_3ef94c54.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == ec5960798c2ff1d91d1257457905c3528e2598534e71b0c7e4e2a7d4938c85a1 ]] || { echo 'Activation bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/activation-fix-20261019_082938_3ef94c54"
backup="$root/run/setup_v2/activation_fix_20261019_082938_3ef94c54"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
# Verify all old/new pairs before replacing either script.
while read -r old_hash new_hash relative; do
    case "$relative" in scripts/slurm/prepare_tc2_v2.sh|scripts/slurm/check_setup_v2.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    [[ "$(sha256sum "$incoming/$relative" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
done < "$incoming/activation.sha256"
mkdir -- "$backup"
cp -- "$incoming/activation.sha256" "$backup/activation.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    mkdir -p -- "$backup/$(dirname -- "$relative")"
    cp -p -- "$target" "$backup/$relative"
done < "$incoming/activation.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    if [[ "$current_hash" != "$new_hash" ]]; then
        mv -T -- "$incoming/$relative" "$target"
    fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
    printf '%s %s %s\n' "$old_hash" "$new_hash" "$relative" >> "$backup/applied.txt"
done < "$incoming/activation.sha256"
echo 'Two activation entry points updated; installed environment retained.'
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal  --output="$root/run/setup_v2/slurm-%j.out" --error="$root/run/setup_v2/slurm-%j.err" scripts/slurm/prepare_tc2_v2.sh inputs)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_v2/last_prepare_inputs_job.txt
printf '%s\n' "$job_id" > "$backup/retry_inputs_job.txt"
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
    for log_root in "$root/run/setup_v2" "$root/run/validation_v2"; do
        for log in "$log_root/slurm-$job_id.out" "$log_root/slurm-$job_id.err"; do
            if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
        done
    done
fi
cd -- "$root"
archive="$root/tmp/collect_20261019_082938_3ef94c54.tar.gz"
list="$root/tmp/collect_20261019_082938_3ef94c54.list"
[[ ! -e "$archive" && ! -e "$list" ]] || exit 2
find run/setup_v2 -type f -print0 > "$list"
if [[ -d run/validation_v2 ]]; then find run/validation_v2 -type f -print0 >> "$list"; fi
for extra in configs/tc2_setup.json environment-tc2.yml requirements-tc2-lock.txt; do
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
