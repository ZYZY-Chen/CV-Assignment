"""Independently verify and retain the returned failed B0 snapshot."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[2]
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_143605_00f2db11")
DESTINATION = AUDIT / "failed_job_44047"
INDEX_SHA = "5998B5A99C63A9A46265ADFC79DEDE52E02FA2A9F7A405103F211F7DD1D3421F"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as collector


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


DESTINATION.mkdir()
index_path = DESTINATION / "index.json"
with index_path.open("xb") as stream:
    stream.write((SOURCE / "experiments-index.json").read_bytes())
checked_index = collector.verify_index(index_path, INDEX_SHA, "44047")
index = json.loads(index_path.read_text(encoding="utf-8"))
pages = []
for page in index["pages"]:
    pages.append(collector.verify_archive(SOURCE / page["name"], page["sha256"], "44047",
                                          DESTINATION / ("page_%03d" % page["page_number"]), index_path))
checked_collection = collector.verify_collection(index_path, DESTINATION, "44047")
state_path = DESTINATION / "page_001/run/validation_tc2_gpu/step7_job_44047/setup_status.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
source_hashes = {name: sha(ROOT / name) for name in state["experiment_sources"]}
payload_hashes = {name: sha(SOURCE / "experiments_payload" / name) for name in state["experiment_sources"]}
design = json.loads((ROOT / "configs/experiments_tc2_gpu.json").read_text(encoding="utf-8"))
protected = {name: sha(ROOT / name) for name in {**design["scientific_source_hashes"], **design["pilot_source_hashes"]}}
passed = (state["status"] == "failed" and not state["stage_complete"] and not state["step_7_complete"]
          and all(state[name] == [] for name in ("caches", "results", "analyses", "phases"))
          and state["experiment_sources"] == source_hashes == payload_hashes
          and protected == {**design["scientific_source_hashes"], **design["pilot_source_hashes"]}
          and checked_collection["partial"] is True and checked_collection["stage_complete"] is False
          and checked_collection["result_count"] == 0 and "runtime" not in state)
with (DESTINATION / "terminal.txt").open("xb") as stream:
    stream.write((SOURCE / "terminal.txt").read_bytes())
value = {"verification_status": "passed" if passed else "failed", "stage_accepted": False,
         "step_7_complete": False, "job_id": "44047", "stage_id": "B0", "slurm_state": "FAILED",
         "slurm_exit_code": "1:0", "elapsed": "00:00:17", "node": "TC2N03",
         "checked_at_utc": datetime.now(timezone.utc).isoformat(), "source_directory": str(SOURCE),
         "index_sha256": INDEX_SHA, "pages": pages, "collection": checked_collection,
         "source_hashes": source_hashes, "submitted_payload_matches_sources": source_hashes == payload_hashes,
         "accepted_scientific_and_pilot_sources_unchanged": len(protected), "error": state["error"],
         "runtime_details_recorded": False, "actual_mismatching_field": "unknown",
         "expected_hardware": design["expected_hardware"], "experiment_phases_started": 0,
         "new_stage_results": 0, "existing_pilot_results_accepted": 2,
         "diagnosis": "The allocated runtime failed the exact GPU/driver/CUDA comparison before extraction or fitting. Actual runtime values were not persisted before the exception, so the mismatching field cannot be identified from this snapshot.",
         "next_action": "Await approval of a scheduling supplement; preserve the seven published experiment source files and target the previously accepted TC2N01 for fitting stages.",
         "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0,
         "project_source_files_modified": 0, "external_helper_modified": False}
write(DESTINATION / "verification.json", value)
print(json.dumps({key: value[key] for key in ("verification_status", "stage_accepted", "job_id", "slurm_state", "node", "runtime_details_recorded", "experiment_phases_started", "new_stage_results")}, indent=2))
raise SystemExit(0 if passed else 1)
