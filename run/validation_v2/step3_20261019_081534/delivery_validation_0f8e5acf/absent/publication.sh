set -euo pipefail
root="$(pwd -P)"
archive="$root/_downloads/metrics-files-20261019_082537_fdb7aec7.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 04dc02ca0a0cf1d6734e35882edaf22f39febdbe0550f5bf85a6b770fec88e13 ]] || { echo 'Metric bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/metrics-files-20261019_082537_fdb7aec7"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check metrics.sha256 )
while read -r hash relative; do
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py|tests/test_metrics_v2.py|scripts/slurm/check_metrics_v2.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Existing source differs; no overwrite: $relative" >&2; exit 2; }
    fi
done < "$incoming/metrics.sha256"
mkdir -p -- "$root/run/validation_v2"
stage_record="$root/run/validation_v2/metrics_stage_20261019_082537_fdb7aec7"
mkdir -- "$stage_record"
cp -- "$incoming/metrics.sha256" "$stage_record/metrics.sha256"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then cp --no-clobber -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/metrics.sha256"
echo 'Five verified metric test files staged; requesting CPU-only acceptance.'
