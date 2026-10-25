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
[[ -d "$root" && -d "$root/_downloads" && ! -L "$root/_downloads" ]] || exit 2
probe_id=$(cat "$root/run/setup_v2/last_probe_job.txt")
[[ "$probe_id" =~ ^[0-9]+$ ]] || exit 2
grep -Eq '"ready": true' "$root/run/setup_v2/job_${probe_id}_hardware/hardware.json" || { echo 'Hardware gate not passed.' >&2; exit 2; }
mkdir -- "$root/_downloads/upload-20261019_064711_5d51daf9"
