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
