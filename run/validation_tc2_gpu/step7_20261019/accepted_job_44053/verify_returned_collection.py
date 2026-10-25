"""Independently verify the completed B0 collection without changing its files."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parents[3]
SOURCE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_151040_d90ef21c")
INDEX_SHA = "8EDF2AE1F1483545C8B61DC86550859F1171B3C1B660F9551B49CF676E4642BF"
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_tc2_gpu as collector

sha = collector._sha
read = lambda path: json.loads(collector._extended(path).read_text(encoding="utf-8"))
design = read(ROOT / "configs/experiments_tc2_gpu.json")
local = read(DIRECTORY.parent / "setup_status.json")
index_path = SOURCE / "experiments-index.json"
index_check = collector.verify_index(index_path, INDEX_SHA, "44053")
index = read(index_path)
for page in index["pages"]:
    archive = SOURCE / page["name"]
    if archive.stat().st_size != page["bytes"] or sha(archive) != page["sha256"]:
        raise ValueError("Downloaded archive bytes differ from the pinned index")
collection = collector.verify_collection(index_path, SOURCE / "remote", "44053")
remote_root = SOURCE / "remote/page_001"
state = read(remote_root / "run/validation_tc2_gpu/step7_job_44053/setup_status.json")
resources = read(remote_root / "run/validation_tc2_gpu/step7_job_44053/resources.json")
spec = next(value for value in design["stages"] if value["stage_id"] == "B0")
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8")
if not re.search(r"(?m)^44053\s+\S+\s+COMPLETED\s+0:0\s+00:17:55\s+TC2N01\s+2\s+24G", terminal):
    raise ValueError("The returned accounting record does not establish successful completion")
if (state["status"] != "passed" or state["stage_complete"] is not True or state["step_7_complete"] is not False
        or state["job_id"] != "44053" or state["stage_id"] != "B0" or state["cumulative_fits"] != 12
        or [value["stage_id"] for value in state["completed_stages"]] != ["B0"]
        or [value["run_key"] for value in state["results"]] != spec["run_keys"]
        or len(state["phases"]) != 28 or any(value["exit_code"] != 0 for value in state["phases"])
        or state["analyses"] or state["predecessor"] is not None):
    raise ValueError("The completed B0 record differs from the approved plan")
if (collection["partial"] is not False or collection["stage_complete"] is not True
        or collection["result_count"] != 12 or collection["page_count"] != 6):
    raise ValueError("Every completed B0 page is required")
if (state["experiment_sources"] != local["experiment_sources"]
        or state["design_sha256"] != sha(ROOT / "configs/experiments_tc2_gpu.json")):
    raise ValueError("Experiment design or source identities differ")
protected = {**state["experiment_sources"], **design["scientific_source_hashes"], **design["pilot_source_hashes"]}
if any(sha(ROOT / name) != expected for name, expected in protected.items()):
    raise ValueError("A protected source file changed")
if resources["requested"] != spec["resources"] or resources["runtime"] != state["runtime"]:
    raise ValueError("Resource evidence differs from the approved allocation")
runtime = state["runtime"]
if (any(runtime[key] != expected for key, expected in design["expected_hardware"].items())
        or runtime["device"] != "cuda" or runtime["slurm_job_id"] != "44053"
        or runtime["tf32"] is not False or runtime["autocast"] is not False
        or runtime["compatibility_configuration_sha256"] != "EDF3D1D0380E0105A5173607CE360221FD43B059478915EEC0EC04ED9110F913"
        or resources["slurm_environment"]["SLURM_JOB_NODELIST"] != "TC2N01"
        or resources["slurm_environment"]["SLURM_CPUS_PER_TASK"] != "2"
        or resources["slurm_environment"]["SLURM_MEM_PER_NODE"] != "24576"):
    raise ValueError("Actual execution differs from the accepted hardware or resources")
unique, total, locations = {}, 0, {}
for page in index["pages"]:
    parent = SOURCE / "remote" / ("page_%03d" % page["page_number"])
    manifest = read(parent / "experiments_export_manifest.json")
    total += len(manifest["files"])
    for item in manifest["files"]:
        if item["path"] in unique and unique[item["path"]] != item["sha256"]:
            raise ValueError("Repeated page metadata differs")
        unique[item["path"]] = item["sha256"]
    for key in page["result_ids"]:
        locations[key] = str(parent)
pilot = read(ROOT / "run/validation_tc2_gpu/step6_20261019/accepted_job_44024/archive_file_hashes.json")
preserved = {}
for result in state["results"]:
    if result["verified"] is not True:
        raise ValueError("An unverified result cannot complete B0")
    if result["accepted_pilot_reuse"]:
        if result["run_status"] != "skipped":
            raise ValueError("Accepted pilot results must never be fitted again")
        for name, expected in pilot.items():
            if name.startswith(result["path"] + "/"):
                if unique.get(name) != expected:
                    raise ValueError("Accepted pilot artifact bytes changed")
                preserved[name] = expected
    elif result["run_status"] != "completed":
        raise ValueError("All ten planned new fits must have completed")
if len(preserved) != 16 or sum(result["accepted_pilot_reuse"] for result in state["results"]) != 2:
    raise ValueError("The two accepted pilot results are incomplete")
caches = []
for item in state["caches"]:
    meta = read(remote_root / item["path"] / "metadata.json")
    if set(meta["layers"]) != {"layer1", "layer2", "layer3"} or any(value["dtype"] != "float32" for value in meta["layers"].values()):
        raise ValueError("A category cache differs from the accepted FP32 format")
    caches.append({"category": item["identity"]["category"], "images": len(meta["index"]), "path": item["path"], "metadata_sha256": item["metadata_sha256"]})
if len(caches) != 6 or sum(item["images"] for item in caches) != 2170:
    raise ValueError("The six AD category caches are incomplete")
for name in ("terminal.txt", "experiments-index.json"):
    with (DIRECTORY / name).open("xb") as stream:
        stream.write((SOURCE / name).read_bytes())
for original, target in (("setup_status.json", "remote_setup_status.json"), ("resources.json", "resources.json"), ("result_summary.json", "result_summary.json")):
    with (DIRECTORY / target).open("xb") as stream:
        stream.write((remote_root / "run/validation_tc2_gpu/step7_job_44053" / original).read_bytes())
result = {"verification_status": "passed", "stage_id": "B0", "job_id": "44053",
          "checked_at_utc": datetime.now(timezone.utc).isoformat(), "slurm_state": "COMPLETED", "exit_code": "0:0",
          "elapsed": "00:17:55", "node": "TC2N01", "slurm_max_rss_kib": 5285508,
          "source_directory": str(SOURCE), "index_sha256": INDEX_SHA, "index_verification": index_check,
          "collection_verification": collection, "pages_checked": 6, "total_page_payload_entries": total,
          "unique_payload_files": len(unique), "result_count": 12, "new_fits": 10, "pilot_reuses": 2,
          "pilot_artifact_files_preserved": 16, "phases_passed": 28, "protected_sources_checked": len(protected),
          "runtime": runtime, "resources": resources, "caches": caches, "result_page_locations": locations,
          "remote_full_result_metric_verification": "All twelve accepted verify phases passed, including original-resolution pixel metrics and full feature-cache checks.",
          "local_pixel_metrics_recomputed": False, "cache_npy_arrays_downloaded": False,
          "local_acceptance_status": "awaiting_independent_array_and_image_metric_reports", "step_7_complete": False,
          "actual_agent_tc2_connections": 0, "actual_agent_slurm_submissions": 0, "implementation_files_modified": 0}
for filename, value in (("collection_verification.json", result), ("archive_file_hashes.json", unique)):
    with (DIRECTORY / filename).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
print(json.dumps({key: result[key] for key in ("verification_status", "pages_checked", "unique_payload_files", "result_count", "new_fits", "pilot_reuses", "phases_passed", "local_acceptance_status")}, indent=2))
