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
archive="$root/_downloads/setup-files-20261019_082932_c9dac9bf.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 29e93f3e331159b23eb5c0ac5d690dc85362209d5d46679d1bff4b7fec212a25 ]] || { echo 'Upload hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/stage-20261019_082932_c9dac9bf"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check payload.sha256 )
while read -r hash relative; do
    [[ "$relative" != /* && "$relative" != *..* && "$relative" != *\\* ]] || exit 2
    target="$root/$relative"
    [[ "$(readlink -m -- "$target")" == "$target" && ! -L "$target" ]] || exit 2
    if [[ -e "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" != "$hash" ]]; then
        echo "Existing staging file differs; no overwrite: $relative" >&2
        exit 2
    fi
done < "$incoming/payload.sha256"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then cp --no-clobber -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/payload.sha256"
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/setup_v2/slurm-%j.out" --error="$root/run/setup_v2/slurm-%j.err" scripts/slurm/probe_hardware_v2.sh)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > run/setup_v2/last_probe_job.txt
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
archive="$root/tmp/collect_20261019_082932_c9dac9bf.tar.gz"
list="$root/tmp/collect_20261019_082932_c9dac9bf.list"
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
