set -euo pipefail
root="$(pwd -P)"
metric_source_is_accepted() {
    local relative="$1" current_hash="$2" expected
    case "$relative" in
        src/metric_core.py) expected=E3A444608FF1D5B3D489CECA981D9B480E48D7FA53DB41EA6C46D9888ACB5CCD ;;
        src/evaluate.py) expected=99852A3E9E7C99FBD872ED37EAF7C1527FFED970D99BBD08A1911310C93CA3C1 ;;
        *) return 1 ;;
    esac
    [[ "${current_hash^^}" == "$expected" ]]
}
archive="$root/_downloads/metrics-files-20261019_091347_76d50ada.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 061b10a4ed6aaeb915be813546eb30056de62fd6d3a7532eb5b6763eb45b9dda ]] || { echo 'Metric bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/metrics-files-20261019_091347_76d50ada"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check metrics.sha256 )
while read -r hash relative; do
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py|tests/test_metrics_tc2_gpu.py|scripts/slurm/check_tc2_gpu_metrics.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" ]] || exit 2
        current_hash=$(sha256sum "$target" | cut -d' ' -f1)
        [[ "$current_hash" == "$hash" ]] || metric_source_is_accepted "$relative" "$current_hash" || { echo "Unknown metric source; no overwrite: $relative" >&2; exit 2; }
    fi
done < "$incoming/metrics.sha256"
mkdir -p -- "$root/run/validation_tc2_gpu"
stage_record="$root/run/validation_tc2_gpu/metrics_stage_20261019_091347_76d50ada"
mkdir -- "$stage_record"
cp -- "$incoming/metrics.sha256" "$stage_record/metrics.sha256"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then
        cp --no-clobber -- "$incoming/$relative" "$target"
    elif [[ "$(sha256sum "$target" | cut -d' ' -f1)" != "$hash" ]]; then
        current_hash=$(sha256sum "$target" | cut -d' ' -f1)
        metric_source_is_accepted "$relative" "$current_hash" || exit 2
        mkdir -p -- "$stage_record/source_originals/$(dirname -- "$relative")"
        cp -p -- "$target" "$stage_record/source_originals/$relative"
        cp -- "$incoming/$relative" "$target"
    fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/metrics.sha256"
echo 'Five verified metric test files staged; requesting CPU-only acceptance.'
