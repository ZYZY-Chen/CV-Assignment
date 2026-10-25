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
[[ "$(cat "$(setup_record "last_prepare_inputs_job.txt")")" == 43944 ]] || { echo 'Latest inputs job differs from recorded 43944; collect and inspect before updating.' >&2; exit 2; }
grep -Fq 'HTTPError: HTTP Error 404: Not Found' "$(setup_record "job_43944_prepare_inputs/preparation_status.json")" || exit 2
environment_job=$(cat "$(setup_record "last_prepare_environment_job.txt")")
[[ "$environment_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"ready": true' "$(setup_record "job_${environment_job}_prepare_environment/preparation_status.json")" || exit 2
printf '%s' 'Zjk0YjcxMDhmZDhiMmY5ZWY5YWY2ZGQ0MzllNjMyMTljM2EzMTEwY2RhZDhmOTljOWM5ZDAyZmJlYzczOTQwNSBiYWM4YzdkY2JhYTIzZDg0ZGE3OTk2YTgyZTk2NGJhY2Q4ZThkYjJmYjA3NDYwZDRlYWRjMWI0NGYzNWE2ZmQ4IGNvbmZpZ3MvdGMyX3NldHVwLmpzb24KZGE4MmY4OGYwNjY1YWI2NTU2NzdjZDljYjA3MTI1NzUyYTBmNjA5ODA3YTQ3ZjUyYzNhYTFlMjA5ZGM1NGUzOCA3ZGJjMjZlY2FhNThjYWYzODMxZTUwZjEzY2I3ZDAyZjg5OTgwNDRlNDIyNjcxZDY2ZmRiOGIzNjU0YTM5NjhlIHNjcmlwdHMvcHJlcGFyZV90YzJfZ3B1X2lucHV0cy5weQo=' | base64 -d | while read -r old_hash new_hash relative; do
    case "$relative" in configs/tc2_setup.json|scripts/prepare_tc2_gpu_inputs.py) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || { echo "Unrecognized source file; no update: $relative" >&2; exit 2; }
done
archive="$root/_downloads/input-sources-20261019_091345_1b267aee.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 6906164e03c9ffc53b0099c752789e72c8acd962d435fcb2722b6a8be12280a4 ]] || { echo 'Source-update bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/input-sources-20261019_091345_1b267aee"
backup="$root/run/setup_tc2_gpu/input_sources_20261019_091345_1b267aee"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
while read -r old_hash new_hash relative; do
    case "$relative" in configs/tc2_setup.json|scripts/prepare_tc2_gpu_inputs.py) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    [[ "$(sha256sum "$incoming/$relative" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
done < "$incoming/sources.sha256"
mkdir -- "$backup"
cp -- "$incoming/sources.sha256" "$backup/sources.sha256"
while read -r old_hash new_hash relative; do
    mkdir -p -- "$backup/$(dirname -- "$relative")"
    cp -p -- "$root/$relative" "$backup/$relative"
done < "$incoming/sources.sha256"
while read -r old_hash new_hash relative; do
    target="$root/$relative"
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || exit 2
    if [[ "$current_hash" != "$new_hash" ]]; then mv -T -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$new_hash" ]] || exit 2
    printf '%s %s %s\n' "$old_hash" "$new_hash" "$relative" >> "$backup/applied.txt"
done < "$incoming/sources.sha256"
echo 'Approved AD mirror and original official LOCO sources deployed; frozen manifests retained.'
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal  --output="$root/run/setup_tc2_gpu/slurm-%j.out" --error="$root/run/setup_tc2_gpu/slurm-%j.err" scripts/slurm/prepare_tc2_gpu.sh inputs)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_tc2_gpu/last_prepare_inputs_job.txt
printf '%s\n' "$job_id" > "$backup/inputs_job.txt"
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
archive="$root/tmp/collect_20261019_091345_1b267aee.tar.gz"
list="$root/tmp/collect_20261019_091345_1b267aee.list"
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
