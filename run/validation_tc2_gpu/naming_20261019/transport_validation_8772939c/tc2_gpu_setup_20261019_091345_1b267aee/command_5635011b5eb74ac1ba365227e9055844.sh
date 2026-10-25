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
