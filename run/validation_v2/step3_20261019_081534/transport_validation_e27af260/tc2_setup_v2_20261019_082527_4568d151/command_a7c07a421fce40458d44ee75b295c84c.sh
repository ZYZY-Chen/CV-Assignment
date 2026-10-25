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
if [[ -e "$root" ]]; then
    [[ -d "$root" && "$(stat -c %u -- "$root")" == "$(id -u)" ]] || exit 2
    echo '[Existing staging entries]'
    find "$root" -mindepth 1 -maxdepth 2 -print
fi
echo '[Quota and shared filesystem]'
if command -v quota >/dev/null 2>&1; then quota -s || true; else echo 'Personal quota command unavailable; quota remains unknown.'; fi
df -h "$HOME"
for directory in "$root" "$root/run" "$root/run/setup_v2" "$root/_downloads" "$root/tmp"; do
    [[ ! -L "$directory" ]] || exit 2
    mkdir -p -- "$directory"
done
