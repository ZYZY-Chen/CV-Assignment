set -euo pipefail
[[ "$(id -un)" == huajie001 && "$HOME" == /home/mcaai/huajie001 ]] || { echo 'Unexpected remote identity or HOME.' >&2; exit 2; }
root=/home/mcaai/huajie001/ca6129_v2_setup
[[ ! -L "$root" && "$(readlink -m -- "$root")" == "$root" ]] || { echo 'Unexpected root or symbolic link.' >&2; exit 2; }
for relative in run run/setup_v2 configs scripts tmp _downloads _package_cache envs; do
    candidate="$root/$relative"
    [[ ! -L "$candidate" && "$(readlink -m -- "$candidate")" == "$candidate" ]] || { echo "Unsafe staging path: $relative" >&2; exit 2; }
done
if [[ -n "$(squeue --noheader --user=huajie001 --format=%i)" ]]; then
    echo 'A personal job is already queued or running. Collect it before submitting another setup job.' >&2
    exit 2
fi
cd -- "$root"
[[ "$(cat run/setup_v2/last_prepare_inputs_job.txt)" == 43944 ]] || { echo 'Latest inputs job differs from recorded 43944; collect and inspect before updating.' >&2; exit 2; }
grep -Fq 'HTTPError: HTTP Error 404: Not Found' run/setup_v2/job_43944_prepare_inputs/preparation_status.json || exit 2
environment_job=$(cat run/setup_v2/last_prepare_environment_job.txt)
[[ "$environment_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"ready": true' "run/setup_v2/job_${environment_job}_prepare_environment/preparation_status.json" || exit 2
printf '%s' 'Zjk0YjcxMDhmZDhiMmY5ZWY5YWY2ZGQ0MzllNjMyMTljM2EzMTEwY2RhZDhmOTljOWM5ZDAyZmJlYzczOTQwNSBiYWM4YzdkY2JhYTIzZDg0ZGE3OTk2YTgyZTk2NGJhY2Q4ZThkYjJmYjA3NDYwZDRlYWRjMWI0NGYzNWE2ZmQ4IGNvbmZpZ3MvdGMyX3NldHVwLmpzb24KZGE4MmY4OGYwNjY1YWI2NTU2NzdjZDljYjA3MTI1NzUyYTBmNjA5ODA3YTQ3ZjUyYzNhYTFlMjA5ZGM1NGUzOCBiYzZhOGU1ZjllMWY2YmE2MmVhOTczYWY5OGQ2YzFkMjgwMzg3ZjkyMWYwNmU0Mzc4OWFhZTVjMGExODBiMTQzIHNjcmlwdHMvcHJlcGFyZV90YzJfaW5wdXRzX3YyLnB5Cg==' | base64 -d | while read -r old_hash new_hash relative; do
    case "$relative" in configs/tc2_setup.json|scripts/prepare_tc2_inputs_v2.py) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ -f "$target" && ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    current_hash=$(sha256sum "$target" | cut -d' ' -f1)
    [[ "$current_hash" == "$old_hash" || "$current_hash" == "$new_hash" ]] || { echo "Unrecognized source file; no update: $relative" >&2; exit 2; }
done
archive="$root/_downloads/input-sources-20261019_072852_666afe05.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == db1b1cbeb1676e131e17da96370d6661d1c399cd09091c697ac4a291cfc7bed7 ]] || { echo 'Source-update bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/input-sources-20261019_072852_666afe05"
backup="$root/run/setup_v2/input_sources_20261019_072852_666afe05"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
while read -r old_hash new_hash relative; do
    case "$relative" in configs/tc2_setup.json|scripts/prepare_tc2_inputs_v2.py) ;; *) exit 2 ;; esac
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
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal  --output="$root/run/setup_v2/slurm-%j.out" --error="$root/run/setup_v2/slurm-%j.err" scripts/slurm/prepare_tc2_v2.sh inputs)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_v2/last_prepare_inputs_job.txt
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
    for log in "$root/run/setup_v2/slurm-$job_id.out" "$root/run/setup_v2/slurm-$job_id.err"; do
        if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
    done
fi
cd -- "$root"
archive="$root/tmp/collect_20261019_072852_666afe05.tar.gz"
list="$root/tmp/collect_20261019_072852_666afe05.list"
[[ ! -e "$archive" && ! -e "$list" ]] || exit 2
find run/setup_v2 -type f -print0 > "$list"
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
