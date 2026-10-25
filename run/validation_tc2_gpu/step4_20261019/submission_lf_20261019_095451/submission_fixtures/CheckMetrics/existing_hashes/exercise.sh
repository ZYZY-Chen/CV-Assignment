set -euo pipefail
root="$(pwd -P)"
stage_record="$root/run/validation_tc2_gpu/fixture_stage"
sbatch() {
    printf 'stub invocation\n' >> "$root/stub_calls.txt"
    printf '%s\0' "$@" > "$root/stub_arguments.bin"
    local script="${!#}"
    [[ "$script" == "$stage_record/submission_lf.sh" && -s "$script" ]] || return 20
    [[ "$(head -n 1 -- "$script")" == '#!/bin/bash' ]] || return 21
    if LC_ALL=C grep -q $'\r' "$script"; then return 22; fi
    bash -n "$script" || return 23
    if [[ "${STUB_FAIL:-0}" == 1 ]]; then echo 'Simulated sbatch rejection.' >&2; return 17; fi
    printf '%s\n' "${STUB_JOB_ID:-91234;offline}"
}
# Preserve the verified source; submit a separately recorded LF-only copy.
submission_source="$root/scripts/slurm/check_tc2_gpu_metrics.sh"
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
printf '%s\n' "$job_id" > "$root/run/validation_tc2_gpu/last_check_metrics_job.txt"
printf '%s\n' "$job_id" > "$stage_record/job_id.txt"
