job_id=__JOBID__
echo '[Personal queue]'
squeue --user=huajie001
echo "TC2_JOB_ID=$job_id"
sacct --jobs="$job_id" --user=huajie001 --format=JobID,JobName,State,ExitCode,Elapsed,NodeList,AllocCPUS,ReqMem,MaxRSS,TotalCPU || true
for log in "$root/run/validation_tc2_gpu/slurm-$job_id.out" "$root/run/validation_tc2_gpu/slurm-$job_id.err"; do
    if [[ -f "$log" && ! -L "$log" ]]; then echo "[Tail: $log]"; tail -n 50 -- "$log"; fi
done
collector="$root/scripts/collect_experiments_tc2_gpu.py"
[[ -f "$collector" && ! -L "$collector" && "$(sha256sum "$collector" | cut -d' ' -f1)" == __COLLECTORHASH__ ]] || { echo 'Experiment collector fingerprint differs; no export executed.' >&2; exit 2; }
directory="$root/tmp/experiments-$job_id-__RUNID__"
[[ ! -e "$directory" && ! -L "$directory" ]] || exit 2
export_json=$("$root/envs/ca6129-ad-v2/bin/python" -I -B "$collector" export --root "$root" --job-id "$job_id" --directory "$directory")
printf '%s' "$export_json" | "$root/envs/ca6129-ad-v2/bin/python" -I -B -c 'import json,re,sys; v=json.load(sys.stdin); assert v["job_id"] == sys.argv[1]; assert v["directory"] == sys.argv[2]; assert v["index_path"] == sys.argv[2]+"/index.json"; assert re.fullmatch("[0-9a-fA-F]{64}",v["index_sha256"]); assert 1 <= len(v["pages"]) <= 32; print("EXPERIMENTS_INDEX_PATH="+v["index_path"]); print("EXPERIMENTS_INDEX_SHA256="+v["index_sha256"].upper()); print("EXPERIMENTS_PAGE_COUNT="+str(len(v["pages"]))); print("EXPERIMENTS_PARTIAL="+str(v["partial"]))' "$job_id" "$directory"
