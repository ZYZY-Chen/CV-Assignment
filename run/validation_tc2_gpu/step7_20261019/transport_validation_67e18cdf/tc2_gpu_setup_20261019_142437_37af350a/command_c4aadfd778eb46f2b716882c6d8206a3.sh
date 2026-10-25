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
all_job=$(cat "$(setup_record last_check_all_job.txt)")
[[ "$all_job" =~ ^[0-9]+$ && -x "$root/envs/ca6129-ad-v2/bin/python" ]] || exit 2
grep -Eq '"step_2_complete": true' "$(setup_record "job_${all_job}_all/setup_status.json")" || exit 2
metric_job=$(cat run/validation_tc2_gpu/last_check_metrics_job.txt)
[[ "$metric_job" =~ ^[0-9]+$ ]] || exit 2
metric_status="$root/run/validation_tc2_gpu/step3_job_${metric_job}/setup_status.json"
[[ -f "$metric_status" && ! -L "$metric_status" ]] || exit 2
grep -Eq '"step_3_complete": true' "$metric_status" || { echo 'Run CheckMetrics and verify its full acceptance before CheckAlgorithms.' >&2; exit 2; }
grep -Eq '"mode": "full"' "$metric_status" || exit 2
grep -Eq '"status": "passed"' "$metric_status" || exit 2
printf '%s' 'MzA5OGI2YTg2ZGJhNjRlZTQzOWJmZTYxYzdhNGZjZmZjZDA4MjM3MWQ1YTgwZmZiYzc5NDA5OTdlZDZhMWVkMSAgY29uZmlncy9wcm90b2NvbF92Mi5qc29uCjI5MjJmYTZlNTEzZjk4MGNiZGU1M2EzMDNmODZmZTExNjA1ODhkZjdlZmIwNzk2ZjY4ODhjOTVkMmJhYjYxNDAgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF9ib3R0bGUuanNvbgplMTg4ZDA1YmQyNDZjMjk1MDNhMzVkYmFmNDlkYmNjMzI2YTM1MDc5ZWNjMDc5NzNhZTFhN2JjY2ZkMDhmZDk1ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfY2FibGUuanNvbgowZTlmMWJmNTM2OGRlMDNhMmE2YmU1N2NkOGIxM2Q4Y2U5ZDQ4NGRlM2EwNTYzNTIwNmM3ZDhmYzI4ZDFlMzY3ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfYWRfY2Fwc3VsZS5qc29uCmUyMDlmNDQyOWM0MDU2ZWNmYTZmMmRhODJmYWE5YjViM2FlNDk1ZWJmZGJmOTRkNTgwOGM5Njc2ZDhhOTlmOWIgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF9zY3Jldy5qc29uCjJiNDI3NGZlNzZiYmNiY2UzYjk2OGNjY2FhMGYzZGFhNjE1MWZhZjlhYTYzNTg0NDVhY2RhMWI1ZGZiZWU5NGMgIG1hbmlmZXN0cy9tYW5pZmVzdF9tdnRlY19hZF90aWxlLmpzb24KNTc2NDYwMDdlYmFmZThmMDE1Zjk3NjE4NjE5N2E3YTA4ZDMzOGVjYWViNmJmOGI1ZDM3NjRkZTlhNDY4ODhhZSAgbWFuaWZlc3RzL21hbmlmZXN0X212dGVjX2FkX3dvb2QuanNvbgplNTRhYjNmYTM1NGUyNThkNTkxZjZjNTNiMzk1ZWQ5ZWVkMjU1MThjZjI1ZjAzOWZlYjg4MDQwYTJlYzQ2Yzg2ICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfbG9jb19qdWljZV9ib3R0bGUuanNvbgo3YzAyZWQxY2YzM2FmZDM1ZjhiZWZiNzM0MjUyNWY1MzIyMTNjYzY4NGFkYzMzMDQxNDUyMmRiNTFiMWM2NmNhICBtYW5pZmVzdHMvbWFuaWZlc3RfbXZ0ZWNfbG9jb19zY3Jld19iYWcuanNvbgo0N2YxZGFhODNhNzQ0NzQzOTQ2YzgzZTZkYzE5NjNiOGZhN2U4MzVhNGEwZjcwMTBhM2IwNTAxZWY1YTNkZjM4ICBlbnZpcm9ubWVudC10YzIueW1sCmY3Yjg0OGYxMGZmYjNmM2NjZWI3MDc0NTBiMmE1ZmU0ZGNkOWE2YzNiNDg5OTYzYTg5MzIwOTRlMDE2ODQwYjYgIHJlcXVpcmVtZW50cy10YzItbG9jay50eHQK' | base64 -d | sha256sum --check -
printf '%s' 'ODAzZTMwZjFhZDFmNTkxYmRkMjZjMGQ0NThkMjUyZDM5NzU3OGY4ZTUzOTg0ODY4NTVkYWMwMjU3ZjQ0M2FiMyAgc3JjL3BhZGltX2FkYXB0ZXIucHkKNDg3N2Q2NjYyNTE4MGJiMzYyNThlYTZiOTlkZTk0MjdlNTQ1NzY0NjE0YWIwY2IyNDVmNWZhZmM0NGVjMzA3ZiAgc3JjL3BhdGNoY29yZV9hZGFwdGVyLnB5CmJlZGIzMzA1N2JjN2U5MzgxMDhlNGI5YjE3N2VjZGUxMjE0MThiMjRkYzM0OGNkZjA3YWQwNGYzZjAyODRiNzkgIHNyYy9zYW1wbGluZy5weQplODM0ODU1MGYwYTU1Y2M4YTFlZGJiNGIxMzEwZmJlOTg1NDkzZjIyZGFlNzFiNmI1NjJmMzQ3MjBjM2Q0YjBiICBzcmMvc2NvcmluZy5weQo0YmQ5ZTliZTNjYWQ3YjkwYTI0ZjdkYmZhYWJkYjU1ZWI0MDNjOTRiY2Y0Yjc3MWZmOWQ3M2EwNjMxYjlkNGJkICBzcmMvYW5vbWFseV9wb3N0cHJvY2Vzcy5weQo1MjAwYWFlMjQwZTY0ZDIyY2FlY2NiZDQ2NjE1ZGRlMTFmNTExODljNjEyOTM4MDQ2ZGMyZDRhMDA5ZTE2ZWRmICB0ZXN0cy90ZXN0X2FsZ29yaXRobXNfdGMyX2dwdS5weQozMjg3OWJjYTMxN2I0NGRkN2YxOTYwODhmMjcxOGIzMTg4ODg5ZTQ3ZDM0YjIzYzhhMjRkNjAyNDcyMGU4ZGNjICBzY3JpcHRzL3NsdXJtL2NoZWNrX3RjMl9ncHVfYWxnb3JpdGhtcy5zaApkMjE4YTQzODAzMWRlNmIwYTgzYjE0OTUxMzU0Y2Q2NmE4NWVkNjVmOTdmZmMyY2ZiYWVmZjFkNGZiOTFkYjc4ICBzcmMvbWV0cmljX2NvcmUucHkKNGRiMjQxM2NjNmFhZjQyMTBiMTQzMjg1ZmU1ZmQ3ZmM2YThjMDhlOThjNjcwNzNlOWE5MmQzMTM1OWU2OGJjNiAgc3JjL2V2YWx1YXRlLnB5CjlhODJkNTg1MjAzYjM3NmY0MWMzMjAwYTMyZDY5NzEyODhkZDcwYjVjN2U3MTIxMGYzZTIxZjhjNWMxZjFmODkgIHNyYy9kYXRhLnB5CmViMjg5OWIyZTY4ODgyMzM4NzRjOGZhOTdiMTI0N2FiZDNlNjhiMzkxNTM4Yzg2YTM2MTA1NDEwOTE3YTAwZjAgIGNvbmZpZ3MvdGMyX2dwdS5qc29uCg==' | base64 -d | while read -r hash relative; do
    case "$relative" in src/padim_adapter.py|src/patchcore_adapter.py|src/sampling.py|src/scoring.py|src/anomaly_postprocess.py|tests/test_algorithms_tc2_gpu.py|scripts/slurm/check_tc2_gpu_algorithms.sh|src/metric_core.py|src/evaluate.py|src/data.py|configs/tc2_gpu.json) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    case "$relative" in src/metric_core.py|src/evaluate.py|src/data.py)
        [[ -f "$target" ]] || exit 2
        grep -Fiq "\"$relative\": \"$hash\"" "$metric_status" || { echo "Read-only metric dependency changed: $relative" >&2; exit 2; } ;;
    esac
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Existing algorithm source differs; no overwrite: $relative" >&2; exit 2; }
    fi
done
archive="$root/_downloads/algorithm-files-20261019_142437_37af350a.tar"
[[ "$(sha256sum "$archive" | cut -d' ' -f1)" == 859369a3ebbf8cb55b827fc95127d7af3b57b036d5b60246dad4a34457322db5 ]] || { echo 'Algorithm bundle hash mismatch.' >&2; exit 2; }
incoming="$root/tmp/algorithm-files-20261019_142437_37af350a"
mkdir -- "$incoming"
tar -xf "$archive" -C "$incoming" --no-same-owner --no-same-permissions
( cd "$incoming"; sha256sum --check algorithms.sha256 )
while read -r hash relative; do
    case "$relative" in src/padim_adapter.py|src/patchcore_adapter.py|src/sampling.py|src/scoring.py|src/anomaly_postprocess.py|tests/test_algorithms_tc2_gpu.py|scripts/slurm/check_tc2_gpu_algorithms.sh|src/metric_core.py|src/evaluate.py|src/data.py|configs/tc2_gpu.json) ;; *) exit 2 ;; esac
    target="$root/$relative"
    [[ ! -L "$target" && "$(readlink -m "$target")" == "$target" ]] || exit 2
    if [[ -e "$target" ]]; then
        [[ -f "$target" && "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || { echo "Unknown algorithm source; no overwrite: $relative" >&2; exit 2; }
    fi
done < "$incoming/algorithms.sha256"
mkdir -p -- "$root/run/validation_tc2_gpu"
stage_record="$root/run/validation_tc2_gpu/algorithms_stage_20261019_142437_37af350a"
mkdir -- "$stage_record"
cp -- "$incoming/algorithms.sha256" "$stage_record/algorithms.sha256"
printf '%s\n' "$metric_job" > "$stage_record/metric_regression_job.txt"
while read -r hash relative; do
    target="$root/$relative"
    mkdir -p -- "$(dirname -- "$target")"
    if [[ ! -e "$target" ]]; then cp --no-clobber -- "$incoming/$relative" "$target"; fi
    [[ "$(sha256sum "$target" | cut -d' ' -f1)" == "$hash" ]] || exit 2
done < "$incoming/algorithms.sha256"
echo 'Eleven verified algorithm files staged; requesting one GPU for synthetic acceptance.'
# Preserve the verified source; submit a separately recorded LF-only copy.
submission_source="$root/scripts/slurm/check_tc2_gpu_algorithms.sh"
submission_script="$stage_record/submission_lf.sh"
submission_hashes="$stage_record/submission.sha256"
[[ -f "$submission_source" && ! -L "$submission_source" ]] || exit 2
[[ ! -e "$submission_script" && ! -L "$submission_script" && ! -e "$submission_hashes" && ! -L "$submission_hashes" ]] || exit 2
( set -o noclobber; sed 's/\r$//' "$submission_source" > "$submission_script" )
[[ -s "$submission_script" ]] || exit 2
if LC_ALL=C grep -q $'\r' "$submission_script"; then
    echo 'Submission script contains an unsupported carriage return.' >&2
    exit 2
fi
bash -n "$submission_script"
( set -o noclobber; sha256sum -- "$submission_source" "$submission_script" > "$submission_hashes" )
echo "LF submission script: $submission_script"
cat -- "$submission_hashes"
job_id=$(sbatch --parsable --partition=MGPU-TC2 --qos=normal --output="$root/run/validation_tc2_gpu/slurm-%j.out" --error="$root/run/validation_tc2_gpu/slurm-%j.err" "$submission_script")
job_id=${job_id%%;*}
[[ "$job_id" =~ ^[0-9]+$ ]] || exit 2
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_check_algorithms_job.txt"
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
archive="$root/tmp/collect_20261019_142437_37af350a.tar.gz"
list="$root/tmp/collect_20261019_142437_37af350a.list"
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
