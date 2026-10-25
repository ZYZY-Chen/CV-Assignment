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
all_job=$(cat "$(setup_record "last_check_all_job.txt")")
[[ "$all_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"step_2_complete": true' "$(setup_record "job_${all_job}_all/setup_status.json")" || { echo 'Step 2 all-mode acceptance has not passed.' >&2; exit 2; }
printf '%s' 'MzA5OGI2YTg2ZGJhNjRlZTQzOWJmZTYxYzdhNGZjZmZjZDA4MjM3MWQ1YTgwZmZiYzc5NDA5OTdlZDZhMWVkMSAgY29uZmlncy9wcm90b2NvbF92Mi5qc29uCjI5MjJmYTZlNTEzZjk4MGNiZGU1M2EzMDNmODZmZTExNjA1ODhkZjdlZmIwNzk2ZjY4ODhjOTVkMmJhYjYxNDAgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF9ib3R0bGUuanNvbgplMTg4ZDA1YmQyNDZjMjk1MDNhMzVkYmFmNDlkYmNjMzI2YTM1MDc5ZWNjMDc5NzNhZTFhN2JjY2ZkMDhmZDk1ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfY2FibGUuanNvbgowZTlmMWJmNTM2OGRlMDNhMmE2YmU1N2NkOGIxM2Q4Y2U5ZDQ4NGRlM2EwNTYzNTIwNmM3ZDhmYzI4ZDFlMzY3ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfY2Fwc3VsZS5qc29uCmUyMDlmNDQyOWM0MDU2ZWNmYTZmMmRhODJmYWE5YjViM2FlNDk1ZWJmZGJmOTRkNTgwOGM5Njc2ZDhhOTlmOWIgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF9zY3Jldy5qc29uCjJiNDI3NGZlNzZiYmNiY2UzYjk2OGNjY2FhMGYzZGFhNjE1MWZhZjlhYTYzNTg0NDVhY2RhMWI1ZGZiZWU5NGMgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF90aWxlLmpzb24KNTc2NDYwMDdlYmFmZThmMDE1Zjk3NjE4NjE5N2E3YTA4ZDMzOGVjYWViNmJmOGI1ZDM3NjRkZTlhNDY4ODhhZSAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX3dvb2QuanNvbgplNTRhYjNmYTM1NGUyNThkNTkxZjZjNTNiMzk1ZWQ5ZWVkMjU1MThjZjI1ZjAzOWZlYjg4MDQwYTJlYzQ2Yzg2ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfbG9jb19qdWljZV9ib3R0bGUuanNvbgo3YzAyZWQxY2YzM2FmZDM1ZjhiZWZiNzM0MjUyNWY1MzIyMTNjYzY4NGFkYzMzMDQxNDUyMmRiNTFiMWM2NmNhICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfbG9jb19zY3Jld19iYWcuanNvbgo0N2YxZGFhODNhNzQ0NzQzOTQ2YzgzZTZkYzE5NjNiOGZhN2U4MzVhNGEwZjcwMTBhM2IwNTAxZWY1YTNkZjM4ICBlbnZpcm9ubWVudC10YzIueW1sCmY3Yjg0OGYxMGZmYjNmM2NjZWI3MDc0NTBiMmE1ZmU0ZGNkOWE2YzNiNDg5OTYzYTg5MzIwOTRlMDE2ODQwYjYgIHJlcXVpcmVtZW50cy10YzItbG9jay50eHQK' | base64 -d | sha256sum --check -
printf '%s' 'ZDIxOGE0MzgwMzFkZTZiMGE4M2IxNDk1MTM1NGNkNjZhODVlZDY1Zjk3ZmZjMmNmYmFlZmYxZDRmYjkxZGI3OCAgc3JjL21ldHJpY19jb3JlLnB5CjRkYjI0MTNjYzZhYWY0MjEwYjE0MzI4NWZlNWZkN2ZjNmE4YzA4ZTk4YzY3MDczZTlhOTJkMzEzNTllNjhiYzYgIHNyYy9ldmFsdWF0ZS5weQo5YTgyZDU4NTIwM2IzNzZmNDFjMzIwMGEzMmQ2OTcxMjg4ZGQ3MGI1YzdlNzEyMTBmM2UyMWY4YzVjMWYxZjg5ICBzcmMvZGF0YS5weQo4MGI0ODliODM5OTBkZTI1YzJiZTRmMDU1ZmEzODIyNDdmZDBiOTA5MWQxOTQ3NjRlYzNjMDJkZDM3MDMxM2ZkICB0ZXN0cy90ZXN0X21ldHJpY3NfdGMyX2dwdS5weQo5M2U2NDMwOTM0ODA4MmUxZWJkZWYyYjE3MDdiYTVhMWE1OGVmOTVjM2U2ZTUzOTVhODIwOTE5MWZiMGQxNTE5ICBzY3JpcHRzL3NsdXJtL2NoZWNrX3RjMl9ncHVfbWV0cmljcy5zaAo=' | base64 -d | while read -r hash relative; do
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py|tests/test_metrics_tc2_gpu.py|scripts/slurm/check_tc2_gpu_metrics.sh) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" ]] || exit 2
        current_hash=$(sha256sum "$target" | cut -d' ' -f1)
        [[ "$current_hash" == "$hash" ]] || metric_source_is_accepted "$relative" "$current_hash" || { echo "Unknown metric source; no overwrite: $relative" >&2; exit 2; }
    fi
done
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
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" scripts/slurm/check_tc2_gpu_metrics.sh)
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_check_metrics_job.txt"
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
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
archive="$root/tmp/collect_20261019_091347_76d50ada.tar.gz"
list="$root/tmp/collect_20261019_091347_76d50ada.list"
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
