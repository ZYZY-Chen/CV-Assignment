"""Record local implementation readiness separately from remote acceptance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

audit = Path(__file__).resolve().parent
root = audit.parents[2]
read = lambda path: json.loads(path.read_text(encoding="utf-8"))
scope = read(audit / "scope_verification.json")
tests = read(audit / "offline_final/setup_status.json")
design = read(root / "configs/experiments_tc2_gpu.json")
helper = read(audit / "helper_final_validation.json")
if scope["status"] != "passed" or tests["status"] != "passed":
    raise RuntimeError("Local checks must pass before readiness is recorded")
command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\Users\\mhjv_\\Desktop\\CharGPT projects\\CA6129 COMPUTER VISION & APPLICATIONS\\output\\tc2_gpu_setup.ps1" -Action RunExperiments -Stage B0'
value = {"mode": "local_implementation", "status": "local_ready", "local_validation_status": "passed",
         "step_7_complete": False, "remote_acceptance": "pending", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
         "protocol_display_name": "TC2 GPU Experiment Protocol", "accepted_workflow_job_id": "44012",
         "accepted_pilot_job_id": "44024", "planned_total_fits": 66, "accepted_pilot_fits_reused": 2,
         "planned_new_fits": 64, "design_sha256": scope["new_sources"]["configs/experiments_tc2_gpu.json"],
         "experiment_sources": scope["new_sources"], "external_helper_sha256": scope["external_helper_sha256"],
         "stages": [row["stage_id"] for row in design["stages"]], "accepted_step_7_stages": [],
         "offline_tests": {key: tests[key] for key in ("tests_run", "failures", "errors", "skipped", "torch_imported")},
         "collector_offline_checks": 32, "protected_files_checked": scope["protected_files_checked"],
         "scope_verification_sha256": hashlib.sha256((audit / "scope_verification.json").read_bytes()).hexdigest().upper(),
         "checks": {"syntax_python": "passed", "syntax_slurm_bash": "passed", "syntax_powershell": "passed",
                    "legacy_helper_compatibility": "passed", "pilot_helper_compatibility": "passed",
                    "new_helper_fit_cpu_collection_transport": "passed", "isolated_bootstrap_and_publication": "passed",
                    "final_local_seven_file_bundle": "passed", "approved_change_scope": "passed"},
         "actual_tc2_connections": 0, "actual_model_calls": 0, "actual_slurm_submissions": 0,
         "next_stage": "B0", "next_stage_new_fits": 10, "next_stage_pilot_verifications": 2,
         "next_user_terminal_command": command,
         "next_acceptance": "Return the generated terminal.txt path. Verify the completed SLURM state, every collection page and source/result identities before proceeding to H1. A partial snapshot is not acceptance.",
         "completion_boundary": "All twelve returned stage collections must pass before local step-7 completion. The final remote status covers its current stage and remote dependency evidence; earlier local collections remain required."}
(audit / "setup_status.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value[key] for key in ("status", "step_7_complete", "remote_acceptance", "planned_new_fits", "next_stage")}, indent=2))
