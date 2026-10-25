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
job_id=12345
echo '[Personal queue]'
squeue --user=huajie001
echo "TC2_JOB_ID=$job_id"
sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList,AllocCPUS,ReqMem,MaxRSS,TotalCPU || true
for log in "$root/run/validation_tc2_gpu/slurm-$job_id.out" "$root/run/validation_tc2_gpu/slurm-$job_id.err"; do
    if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
done
collector="$root/scripts/collect_experiments_tc2_gpu.py"
[[ -f "$collector" && ! -L "$collector" && "$(sha256sum "$collector" | cut -d' ' -f1)" == ac61772f65c9f2c4124761d2361e0a85e9f65dbcf4df5bab3e939b5111466010 ]] || { echo 'Experiment collector fingerprint differs; no export executed.' >&2; exit 2; }
directory="$root/tmp/experiments-$job_id-20261019_142605_ebe27e1f"
[[ ! -e "$directory" && ! -L "$directory" ]] || exit 2
export_json=$("$root/envs/ca6129-ad-v2/bin/python" -I -B "$collector" export --root "$root" --job-id "$job_id" --directory "$directory")
printf '%s' "$export_json" | "$root/envs/ca6129-ad-v2/bin/python" -I -B -c 'import json,re,sys; v=json.load(sys.stdin); assert v["job_id"] == sys.argv[1]; assert v["directory"] == sys.argv[2]; assert v["index_path"] == sys.argv[2]+"/index.json"; assert re.fullmatch("[0-9a-fA-F]{64}",v["index_sha256"]); assert 1 <= len(v["pages"]) <= 32; print("EXPERIMENTS_INDEX_PATH="+v["index_path"]); print("EXPERIMENTS_INDEX_SHA256="+v["index_sha256"].upper()); print("EXPERIMENTS_PAGE_COUNT="+str(len(v["pages"]))); print("EXPERIMENTS_PARTIAL="+str(v["partial"]))' "$job_id" "$directory"
