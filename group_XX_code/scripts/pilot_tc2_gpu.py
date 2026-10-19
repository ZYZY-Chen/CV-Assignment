"""Fixed real-data pilot; existing scientific implementations remain unchanged."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid

FILES = ("configs/pilot_tc2_gpu.json", "scripts/pilot_tc2_gpu.py", "scripts/slurm/pilot_tc2_gpu.sh",
         "scripts/collect_tc2_gpu_pilot.py", "tests/test_pilot_tc2_gpu.py", "docs/TC2_GPU_PILOT.md")
RUN_KEYS = ("B0_mvtec_ad_bottle_padim_s17_n100_B7B86DBB2043", "B0_mvtec_ad_bottle_patchcore_s17_n100_BBC2B85C2FA8")


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def protocol(root):
    sys.path.insert(0, str(Path(root) / "src"))
    import tc2_gpu_protocol
    return tc2_gpu_protocol


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name("." + path.name + ".partial." + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")
    if path.is_symlink():
        raise ValueError("Refuse symbolic-link records")
    os.replace(temporary, path)


def load_design(root, config_path=None):
    root = Path(root)
    p = protocol(root)
    value = read(config_path or root / FILES[0])
    fixed = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "protocol_sha256": p.PROTOCOL_SHA256,
             "dataset": "mvtec_ad", "category": "bottle", "run_seed": 17, "normal_train_n": 100,
             "run_keys": list(RUN_KEYS), "expected_counts": {"images": 292, "fit_pool": 167, "dev": 42, "test": 83},
             "workflow_acceptance_job_id": "44012", "minimum_free_bytes": 4 * 1024**3,
             "maximum_export_bytes": 512 * 1024**2, "expected_gpu": "NVIDIA A40", "expected_driver": "570.148.08",
             "expected_cuda_build": "12.8", "resources": {"partition": "MGPU-TC2", "qos": "normal", "nodes": 1,
             "tasks": 1, "gpus": 1, "cpus_per_task": 2, "memory_gib": 24, "time_limit": "02:00:00"}}
    if set(value) != {*fixed, "fits", "workflow_source_hashes"} or any(value[key] != item for key, item in fixed.items()):
        raise ValueError("Pilot configuration differs from the approved two-run design")
    expected = [item for item in p.build_plan(root)["fits"] if item["run_key"] in RUN_KEYS]
    if value["fits"] != expected or [item["run_key"] for item in expected] != list(RUN_KEYS):
        raise ValueError("Pilot fits differ from the exact frozen B0 entries")
    if len(value["workflow_source_hashes"]) != 31:
        raise ValueError("Require all 31 accepted scientific source fingerprints")
    return value


def accepted_workflow(root, design):
    root = Path(root)
    pointer = protocol(root).inside(root, "run/validation_tc2_gpu/last_check_workflow_job.txt")
    if pointer.is_symlink() or pointer.read_text().strip() != design["workflow_acceptance_job_id"]:
        raise RuntimeError("The accepted workflow job pointer differs")
    path = protocol(root).inside(root, "run/validation_tc2_gpu/step5_job_" + design["workflow_acceptance_job_id"] + "/setup_status.json")
    record = read(path)
    if record.get("mode") != "full" or record.get("status") != "passed" or record.get("step_5_complete") is not True:
        raise RuntimeError("Full workflow acceptance is required before real-data work")
    if record.get("source_hashes") != design["workflow_source_hashes"]:
        raise RuntimeError("Workflow acceptance fingerprints differ from the approved snapshot")
    for name, value in design["workflow_source_hashes"].items():
        if sha(protocol(root).inside(root, name)) != value:
            raise RuntimeError("Accepted scientific source changed: " + name)
    try:
        checks = [(record["core"], 16), (record["gpu"], 4), (record["metric_regression"], 24),
                  (record["algorithm_regression"]["cpu"], 19), (record["algorithm_regression"]["gpu"], 2)]
        if any(item["tests_run"] != count or any(item[key] != 0 for key in ("failures", "errors", "skipped")) for item, count in checks):
            raise RuntimeError("Workflow acceptance contains incomplete or failed tests")
        if any(item.get("passed") is not True for item in (record["core"], record["gpu"], record["algorithm_regression"]["cpu"], record["algorithm_regression"]["gpu"])):
            raise RuntimeError("Nested workflow acceptance has not passed")
        for item, completion in ((record["metric_regression"], "step_3_complete"), (record["algorithm_regression"], "step_4_complete")):
            if item.get("status") != "passed" or item.get(completion) is not True:
                raise RuntimeError("Required regression acceptance has not passed")
    except KeyError as error:
        raise RuntimeError("Incomplete full workflow acceptance record") from error
    return record


def preflight(root, design=None):
    root = Path(root).resolve()
    p = protocol(root)
    design = design or load_design(root)
    record = accepted_workflow(root, design)
    setup = read(root / "configs/tc2_setup.json")
    if root != Path(setup["remote"]["setup_root"]) or Path(sys.prefix) != Path(setup["remote"]["conda_environment_prefix"]):
        raise RuntimeError("Use the accepted TC2 directory and dedicated Python environment")
    if sha(root / "configs/tc2_setup.json") != record["runtime"]["compatibility_configuration_sha256"]:
        raise RuntimeError("Remote compatibility snapshot changed; never overwrite it")
    accepted = p.accepted_inputs(root)
    for name, value in accepted["export_hashes"].items():
        if sha(root / name) != value:
            raise RuntimeError("Accepted environment lock changed")
    if sha(root / "weights/resnet18-f37072fd.pth") != accepted["weights_sha256"]:
        raise RuntimeError("Actual ResNet18 weight file changed")
    if p.versions() != record["runtime"]["software"]:
        raise RuntimeError("Actual software differs from workflow acceptance")
    manifest, manifest_sha = p.manifest(root, "mvtec_ad", "bottle")
    counts = {"images": len(p.image_entries(manifest)), "fit_pool": len(manifest["fit_pool"]),
              "dev": len(manifest["dev"]), "test": len(manifest["test"]["good"]) + len(manifest["test"]["anomalies"])}
    if counts != design["expected_counts"]:
        raise RuntimeError("Frozen bottle sample counts differ")
    free = shutil.disk_usage(root).free
    if free < design["minimum_free_bytes"]:
        raise RuntimeError("At least 4 GiB free storage is required for the pilot")
    quota = subprocess.run(["bash", "-c", "if command -v quota >/dev/null 2>&1; then quota -s; else echo 'Quota query unavailable'; fi"],
                           capture_output=True, text=True, timeout=20)
    return {"status": "passed", "workflow_job_id": design["workflow_acceptance_job_id"], "workflow_status_sha256": sha(root / ("run/validation_tc2_gpu/step5_job_" + design["workflow_acceptance_job_id"] + "/setup_status.json")),
            "source_hashes": record["source_hashes"], "manifest_sha256": manifest_sha, "counts": counts,
            "free_bytes": free, "quota_query": {"exit_code": quota.returncode, "output": quota.stdout + quota.stderr,
            "personal_quota_verified": False}, "weights_sha256": accepted["weights_sha256"]}


def perform_steps(design, invoke, record):
    extracted = invoke("extract", ["--dataset", "mvtec_ad", "--category", "bottle"])
    if extracted.get("status") not in ("extracted", "cached") or extracted.get("identity", {}).get("namespace") != "formal":
        raise RuntimeError("Real-data extraction did not return a validated formal cache")
    record("extract", extracted)
    results = []
    for method, key in zip(("padim", "patchcore"), design["run_keys"]):
        fitted = invoke("run", ["--run-key", key])
        if fitted.get("status") not in ("completed", "skipped") or fitted.get("namespace") != "formal":
            raise RuntimeError("Formal fit did not complete")
        record(method + "_run", fitted)
        verified = invoke("verify", ["--result", fitted["path"]])
        if verified.get("status") != "passed" or verified.get("namespace") != "formal" or any(verified.get(name) != fitted.get(name) for name in ("path", "identity_sha256")):
            raise RuntimeError("Saved result verification failed or refers to another result")
        record(method + "_verify", verified)
        results.append({"run_key": key, "run": fitted, "verify": verified})
    for method, item in zip(("padim", "patchcore"), results):
        reused = invoke("run", ["--run-key", item["run_key"]])
        if reused.get("status") != "skipped" or reused.get("namespace") != "formal" or any(reused.get(name) != item["run"].get(name) for name in ("path", "identity_sha256")):
            raise RuntimeError("Validated reuse must skip fitting and preserve result identity")
        record(method + "_reuse", reused)
        item["reuse"] = reused
    return {"cache": extracted, "results": results}


def publish(root, incoming, stage):
    root, incoming = Path(root).resolve(), Path(incoming).resolve()
    p = protocol(root)
    stage = p.inside(root, Path(stage).relative_to(root).as_posix())
    if incoming.is_symlink() or not incoming.is_relative_to(root / "tmp") or stage.exists():
        raise ValueError("Use fresh staging paths below the approved remote root")
    rows = (incoming / "pilot.sha256").read_text().splitlines()
    values = dict((name, value.upper()) for value, name in (row.split(None, 1) for row in rows))
    if len(rows) != len(FILES) or set(values) != set(FILES):
        raise ValueError("The pilot publication contains unexpected files")
    design = load_design(root, incoming / FILES[0])
    checked = preflight(root, design)
    for name, value in values.items():
        source, target = p.inside(incoming, name), p.inside(root, name)
        if sha(source) != value or (target.exists() and (not target.is_file() or sha(target) != value)):
            raise ValueError("Conflicting pilot source; no overwrite: " + name)
    stage.mkdir()
    for name, value in values.items():
        target = p.inside(root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as output, (incoming / name).open("rb") as source:
                shutil.copyfileobj(source, output)
        if sha(target) != value:
            raise RuntimeError("Published source differs")
    (stage / "pilot.sha256").write_bytes((incoming / "pilot.sha256").read_bytes())
    atomic_json(stage / "preflight.json", checked)
    return {"status": "published", "files": len(values), "stage": str(stage)}


def run_pilot(root):
    root = Path(root).resolve()
    job = os.environ.get("SLURM_JOB_ID", "")
    if platform.system() != "Linux" or not job.isdigit():
        raise RuntimeError("Real-data pilots require a Linux SLURM compute job")
    p = protocol(root)
    design = load_design(root)
    checked = preflight(root, design)
    if os.environ.get("SLURM_CPUS_PER_TASK") != "2":
        raise RuntimeError("The pilot requires the approved two-CPU allocation")
    if os.environ.get("SLURM_MEM_PER_NODE") not in (None, "24576"):
        raise RuntimeError("Allocated host memory differs from the approved 24 GiB request")
    directory = p.inside(root, "run/validation_tc2_gpu/step6_job_" + job)
    directory.mkdir()
    status_path = directory / "setup_status.json"
    state = {"mode": "real_data_pilot", "job_id": job, "status": "running", "step_6_complete": False,
             "started_at_utc": now(), "design_sha256": sha(root / FILES[0]), "preflight": checked,
             "cache": None, "results": [], "phases": []}
    atomic_json(status_path, state)
    try:
        runtime = p.prepare_torch(p.context(root))
        if any(runtime[key] != design["expected_" + key] for key in ("gpu", "driver", "cuda_build")):
            raise RuntimeError("Allocated GPU, driver or CUDA differs from the accepted pilot design")
        stage_relative = os.environ.get("TC2_PILOT_STAGE", "")
        stage = p.inside(root, stage_relative)
        if not stage_relative.startswith("run/validation_tc2_gpu/pilot_stage_"):
            raise ValueError("Missing approved submission evidence directory")
        submitted = (stage / "submission_lf.sh").read_bytes()
        if b"\r" in submitted or hashlib.sha256(submitted).hexdigest().upper() != sha(root / "scripts/slurm/pilot_tc2_gpu.sh"):
            raise ValueError("Submitted LF script differs from the approved wrapper")
        source_hashes = {name: sha(root / name) for name in FILES}
        state.update(runtime=runtime, pilot_sources=source_hashes, submission={"stage": stage_relative,
                     "source_sha256": sha(root / "scripts/slurm/pilot_tc2_gpu.sh"), "submitted_sha256": sha(stage / "submission_lf.sh")})
        atomic_json(directory / "pilot_sources.json", {"files": source_hashes, "submission": state["submission"]})
        atomic_json(directory / "plan.json", {"fits": design["fits"], "expected_counts": design["expected_counts"]})
        resources = {"requested": design["resources"], "runtime": runtime, "slurm_environment": {key: os.environ.get(key) for key in ("SLURM_JOB_ID", "SLURM_JOB_PARTITION", "SLURM_JOB_NODELIST", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE", "SLURM_JOB_QOS")}}
        atomic_json(directory / "resources.json", resources)
        phase_number = 0

        def invoke(action, arguments):
            nonlocal phase_number
            phase_number += 1
            label = "phase_%02d_%s" % (phase_number, action)
            print("Starting " + label, flush=True)
            with (directory / (label + ".stdout.txt")).open("x", encoding="utf-8") as out, (directory / (label + ".stderr.txt")).open("x", encoding="utf-8") as err:
                completed = subprocess.run([sys.executable, "-B", "-u", str(root / "scripts/run_tc2_gpu.py"), action, *arguments], cwd=root, stdout=out, stderr=err)
            if completed.returncode:
                raise RuntimeError("Pilot phase failed: " + label + " (exit " + str(completed.returncode) + ")")
            return read(directory / (label + ".stdout.txt"))

        snapshots = {}

        def record(phase, result):
            state["phases"].append({"phase": phase, "finished_at_utc": now(), "result": result})
            if phase == "extract":
                path = Path(result["path"])
                p.inside(root, path.relative_to(root).as_posix())
                meta = read(path / "metadata.json")
                state["cache"] = {"path": path.relative_to(root).as_posix(), "identity": result["identity"],
                                  "metadata_sha256": sha(path / "metadata.json"), "layer_hashes": {name: entry["sha256"] for name, entry in meta["layers"].items()}}
                atomic_json(directory / "cache_validation.json", {"status": "passed", "images": len(meta["index"]), "cache": state["cache"], "verification": "Extraction validates all saved FP32 arrays; each full saved-result verification repeats cache validation."})
            elif phase.endswith("_run"):
                path = Path(result["path"])
                relative = path.relative_to(root).as_posix()
                p.inside(root, relative)
                evidence = read(path / "evidence.json")
                method = phase.split("_")[0]
                snapshots[method] = {file.name: sha(file) for file in path.iterdir()}
                state["results"].append({"run_key": design["run_keys"][0 if method == "padim" else 1], "path": relative,
                                         "identity_sha256": result["identity_sha256"], "method": method, "run_seed": 17,
                                         "run_status": result["status"], "verified": False, "reuse": None, "timings": evidence["timings"],
                                         "gpu_peak_allocated_bytes": evidence["gpu_peak_allocated_bytes"], "gpu_peak_reserved_bytes": evidence["gpu_peak_reserved_bytes"]})
            elif phase.endswith("_verify"):
                state["results"][-1]["verified"] = True
            else:
                method = phase.split("_")[0]
                path = Path(result["path"])
                if snapshots[method] != {file.name: sha(file) for file in path.iterdir()}:
                    raise RuntimeError("Reuse changed a result artifact")
                next(item for item in state["results"] if item["method"] == method)["reuse"] = "skipped"
            atomic_json(status_path, state)
            print("Completed " + phase, flush=True)

        perform_steps(design, invoke, record)
        accepted_workflow(root, design)
        if any(sha(root / name) != value for name, value in source_hashes.items()):
            raise RuntimeError("Pilot sources changed during execution")
        import resource
        resources["child_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        resources["memory_scope"] = "Maximum RSS among completed child phases on Linux; GPU fit peaks are recorded separately for each method."
        atomic_json(directory / "resources.json", resources)
        atomic_json(directory / "result_summary.json", {"results": state["results"], "cache": state["cache"], "fits_counted_in_frozen_matrix": 2})
        state.update(status="passed", step_6_complete=True, finished_at_utc=now())
        atomic_json(status_path, state)
        return state
    except BaseException as error:
        state.update(status="failed", step_6_complete=False, finished_at_utc=now(), error=type(error).__name__ + ": " + str(error))
        atomic_json(status_path, state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("preflight", "publish", "run"):
        command = commands.add_parser(action)
        command.add_argument("--root", required=True, type=Path)
        if action == "publish":
            command.add_argument("--incoming", required=True, type=Path)
            command.add_argument("--stage", required=True, type=Path)
    args = parser.parse_args()
    result = preflight(args.root) if args.action == "preflight" else publish(args.root, args.incoming, args.stage) if args.action == "publish" else run_pilot(args.root)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
