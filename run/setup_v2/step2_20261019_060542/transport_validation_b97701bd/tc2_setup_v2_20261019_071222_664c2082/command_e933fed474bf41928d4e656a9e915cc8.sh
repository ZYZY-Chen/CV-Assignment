set -euo pipefail
[[ "$(id -un)" == huajie001 && "$HOME" == /home/mcaai/huajie001 ]] || { echo 'Unexpected remote identity or HOME.' >&2; exit 2; }
root=/home/mcaai/huajie001/ca6129_v2_setup
[[ ! -L "$root" && "$(readlink -m -- "$root")" == "$root" ]] || { echo 'Unexpected root or symbolic link.' >&2; exit 2; }
for relative in run run/setup_v2 configs scripts tmp _downloads _package_cache envs; do
    candidate="$root/$relative"
    [[ ! -L "$candidate" && "$(readlink -m -- "$candidate")" == "$candidate" ]] || { echo "Unsafe staging path: $relative" >&2; exit 2; }
done
cd -- "$root/_downloads/upload-20261019_071222_664c2082"
printf '%s' 'MzMyOTI2ZGVmNjgwZWIxNjg2ZTgwYjhkMWY5NjJjMDQ2MDU2ZDRjNzkwZTg0ZGEyYjJhNzI3NGVkNzI3NDFjMCAgYm90dGxlLnRhci54ego=' | base64 -d > upload.sha256
sha256sum --check upload.sha256
while read -r hash name; do
    target="$root/_downloads/$name"
    [[ ! -L "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Existing archive differs: $name" >&2; exit 2; }
    fi
done < upload.sha256
while read -r hash name; do
    target="$root/_downloads/$name"
    if [[ ! -e "$target" ]]; then ln -- "$PWD/$name" "$target"; fi
done < upload.sha256
echo 'Uploaded inputs published without overwriting. No preparation job submitted.'
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
archive="$root/tmp/collect_20261019_071222_664c2082.tar.gz"
list="$root/tmp/collect_20261019_071222_664c2082.list"
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
