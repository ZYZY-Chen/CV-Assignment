"""Fixed formal experiment stages for the TC2 GPU Experiment Protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

# Isolated publication loads the current pilot controller from the verified root.
_root_argument = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root_argument.resolve() / "scripts"))
import pilot_tc2_gpu as pilot

FILES = ("configs/tc2_gpu/experiments.json", "scripts/experiments_tc2_gpu.py",
         "scripts/analyze_scores_tc2_gpu.py", "scripts/slurm/experiments_tc2_gpu.sh",
         "scripts/collect_experiments_tc2_gpu.py", "tests/test_experiments_tc2_gpu.py",
         "docs/TC2_GPU_EXPERIMENTS.md")
STAGES = ("B0", "H1", "H2", "C1", "I1_seed17", "R0", "C1R", "C2", "F1",
          "I1_all_seeds", "I2", "B0_LOCO")
FIT_COUNTS = (12, 4, 4, 2, 0, 24, 4, 4, 8, 0, 0, 4)
ANALYSIS_RULES = {"I1_seed17": ["native", "max", "top_0.01"],
                  "I1_all_seeds": ["native", "max", "top_0.01"],
                  "I2": ["top_0.001", "top_0.05"]}
RESULT_FILES = ("config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json")
sha, read, atomic_json, now = pilot.sha, pilot.read, pilot.atomic_json, pilot.now


def load_design(root, config_path=None):
    root = Path(root).resolve()
    p = pilot.protocol(root)
    value = read(config_path or root / FILES[0])
    accepted = pilot.load_design(root)
    for field in ("accepted_workflow_job_id", "accepted_pilot_job_id"):
        if value.get(field) is not None:
            pilot.acceptance_job(value[field])
    reused = value.get("accepted_pilot_results")
    if not isinstance(reused, list) or len(reused) not in (0, 2):
        raise ValueError("Current pilot reuse must identify zero or two results")
    if reused and value.get("accepted_pilot_job_id") is None:
        raise ValueError("Pilot reuse requires an explicitly accepted current job")
    fixed = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "protocol_sha256": p.PROTOCOL_SHA256,
             "accepted_workflow_job_id": value.get("accepted_workflow_job_id"), "accepted_pilot_job_id": value.get("accepted_pilot_job_id"),
             "scientific_source_hashes": accepted["workflow_source_hashes"],
             "pilot_source_hashes": pilot.current_source_hashes(root, "pilot"),
             "expected_total_fits": 66, "expected_new_fits": 66 - len(reused), "expected_main_fits": 62,
             "expected_extension_fits": 4, "expected_hardware": {"gpu": "NVIDIA A40", "driver": "570.148.08", "cuda_build": "12.8"},
             "minimum_free_remote_bytes": 20 * 1024**3, "minimum_free_local_bytes": 8 * 1024**3,
             "maximum_export_bytes": 512 * 1024**2, "maximum_results_per_page": 4,
             "checkpoints": [{"checkpoint_id": "core", "after_stage": "I1_seed17", "expected_fits": 22},
                             {"checkpoint_id": "standard", "after_stage": "I2", "expected_fits": 62},
                             {"checkpoint_id": "full", "after_stage": "B0_LOCO", "expected_fits": 66}]}
    if set(value) != {*fixed, "fits", "stages", "accepted_pilot_results"} or any(value.get(key) != item for key, item in fixed.items()):
        raise ValueError("Experiment configuration differs from the approved stage design")
    fits = p.build_plan(root)["fits"]
    if value["fits"] != fits or len(fits) != 66 or len({item["run_key"] for item in fits}) != 66:
        raise ValueError("The experiment matrix must be the exact 66 frozen fits")
    if reused and ([item.get("run_key") for item in reused] != list(pilot.RUN_KEYS)
            or any(item.get("verified") is not True or item.get("reuse") != "skipped"
                   or item.get("path") != "run/tc2_gpu/results/" + item.get("identity_sha256", "") for item in reused)):
        raise ValueError("Require the two accepted current bottle results")
    expected_stages, cumulative = [], 0
    for index, (stage, count) in enumerate(zip(STAGES, FIT_COUNTS)):
        kind = "analysis" if stage in ANALYSIS_RULES else "fit"
        keys = [item["run_key"] for item in fits if item["configuration"]["stage"] == stage] if kind == "fit" else []
        sources = [item["run_key"] for item in fits if item["configuration"]["stage"] in ("B0", "R0")
                   and item["configuration"]["method"] == "patchcore"
                   and (stage != "I1_seed17" or item["configuration"]["run_seed"] == 17)] if kind == "analysis" else []
        if len(keys) != count:
            raise ValueError("Frozen stage fit count differs: " + stage)
        cumulative += count
        rules = ANALYSIS_RULES.get(stage, [])
        expected_stages.append({"stage_id": stage, "kind": kind, "predecessor": STAGES[index - 1] if index else None,
            "run_keys": keys, "source_run_keys": sources, "score_rules": rules,
            "expected_rows": len(sources) * len(rules), "expected_cumulative_fits": cumulative,
            "planned_new_fits": count - sum(key in {row["run_key"] for row in reused} for key in keys),
            "resources": {"partition": "MGPU-TC2", "qos": "normal", "nodes": 1, "tasks": 1,
                          "gpus": int(kind == "fit"), "cpus_per_task": 2, "memory_gib": 24 if kind == "fit" else 8,
                          "time_limit": "02:00:00" if kind == "fit" else "00:15:00"}})
    if value["stages"] != expected_stages:
        raise ValueError("Stage order, dependencies, rules or allocations differ")
    return value


def stage_spec(design, stage):
    return next(item for item in design["stages"] if item["stage_id"] == stage)


def sources(root):
    return {name: sha(Path(root) / name) for name in FILES}


def verify_artifacts(root, record, design, *, analysis=False):
    """Head-node verification uses file hashes and metadata, without tensor imports."""
    root = Path(root)
    p = pilot.protocol(root)
    path = p.inside(root, record["path"])
    identifier = record["identity_sha256"]
    stage = record.get("stage_id")
    expected_parent = "run/tc2_gpu/summaries/" + str(stage) if analysis else "run/tc2_gpu/results"
    if record["path"] != expected_parent + "/" + identifier or len(identifier) != 64:
        raise ValueError("Noncanonical immutable artifact directory")
    artifacts = ("analysis.json", "analysis.csv", "evidence.json") if analysis else RESULT_FILES
    manifest = "analysis.sha256" if analysis else "artifacts.sha256"
    if {item.name for item in path.iterdir()} != {*artifacts, manifest, "SUCCESS"}:
        raise ValueError("Artifact directory is incomplete or contains unexpected files")
    rows = (path / manifest).read_text(encoding="utf-8").splitlines()
    observed = {}
    for row in rows:
        digest, name = row.split(None, 1)
        if name not in artifacts or name in observed or sha(p.inside(path, name)) != digest:
            raise ValueError("Saved artifact fingerprint differs")
        observed[name] = digest
    if set(observed) != set(artifacts) or len(rows) != len(artifacts):
        raise ValueError("Incomplete artifact manifest")
    identity = read(path / "evidence.json")["identity"]
    if p.digest(identity) != identifier or identity.get("namespace") != "formal" or identity.get("protocol_sha256") != p.PROTOCOL_SHA256:
        raise ValueError("Saved artifact identity differs")
    marker = {"status": "passed", "namespace": "formal", "identity_sha256": identifier,
              "analysis_manifest_sha256" if analysis else "artifacts_sha256": sha(path / manifest)}
    if read(path / "SUCCESS") != marker:
        raise ValueError("Saved artifact completion marker differs")
    if analysis:
        spec = stage_spec(design, stage)
        value = read(path / "analysis.json")
        if (record.get("status") != "passed" or record.get("rows") != spec["expected_rows"]
                or value.get("row_count") != spec["expected_rows"] or identity.get("stage") != stage
                or identity.get("score_rules") != spec["score_rules"] or identity.get("rows_sha256") != p.digest(value["rows"])
                or [item["run_key"] for item in identity["sources"]] != spec["source_run_keys"]):
            raise ValueError("Saved score-analysis stage differs")
    else:
        fit = next(item for item in design["fits"] if item["run_key"] == record["run_key"])
        scientific = {name: design["scientific_source_hashes"][name] for name in p.SOURCE_FILES}
        if (record.get("verified") is not True or identity.get("configuration") != fit["configuration"]
                or read(path / "config.yaml") != fit["configuration"] or identity.get("sources") != scientific
                or identity.get("hardware") != design["expected_hardware"] or identity.get("software") != p.versions()
                or p.digest(read(path / "samples.json")) != identity["samples_sha256"]):
            raise ValueError("Saved formal result does not match the frozen fit")
    return record


def verify_stage_record(root, value, design, expected_stage, source_hashes, design_sha):
    spec = stage_spec(design, expected_stage)
    if (value.get("mode") != "formal_experiment_stage" or value.get("stage_id") != expected_stage
            or value.get("status") != "passed" or value.get("stage_complete") is not True
            or value.get("design_sha256") != design_sha or value.get("experiment_sources") != source_hashes
            or [item["run_key"] for item in value.get("results", [])] != spec["run_keys"]
            or len(value.get("analyses", [])) != int(spec["kind"] == "analysis")):
        raise RuntimeError("The latest predecessor stage is not fully accepted: " + expected_stage)
    for item in value["results"]:
        verify_artifacts(root, item, design)
    for item in value["analyses"]:
        if item.get("stage_id") != expected_stage:
            raise ValueError("Unexpected predecessor analysis stage")
        verify_artifacts(root, item, design, analysis=True)


def predecessors(root, stage, design, source_hashes, design_sha):
    p = pilot.protocol(root)
    completed = []
    previous = None
    for expected in STAGES[:STAGES.index(stage)]:
        pointer = p.inside(root, "run/validation_tc2_gpu/last_experiments_" + expected + "_job.txt")
        job = pointer.read_text(encoding="utf-8").strip()
        if not job.isdigit():
            raise ValueError("Invalid latest predecessor job pointer")
        path = p.inside(root, "run/validation_tc2_gpu/step7_job_" + job + "/setup_status.json")
        value = read(path)
        if value.get("job_id") != job or value.get("predecessor") != previous:
            raise RuntimeError("Latest stage dependency chain changed: " + expected)
        verify_stage_record(root, value, design, expected, source_hashes, design_sha)
        completed.append({key: value[key] for key in ("stage_id", "job_id", "status", "stage_complete", "design_sha256", "results", "analyses")})
        completed[-1]["status_sha256"] = sha(path)
        previous = {"stage_id": expected, "job_id": job, "status_sha256": sha(path)}
    return completed, previous


def preflight(root, stage, config_path=None, *, running=False):
    root = Path(root).resolve()
    p = pilot.protocol(root)
    design = load_design(root, config_path)
    checked = pilot.preflight(root)
    pilot.require_current_acceptance(root, "pilot", design)
    pilot_job = pilot.acceptance_job(design.get("accepted_pilot_job_id"))
    pointer = p.inside(root, "run/validation_tc2_gpu/last_pilot_job.txt")
    if pointer.read_text().strip() != design["accepted_pilot_job_id"]:
        raise RuntimeError("Require the latest accepted current real-data pilot job")
    accepted_path = p.inside(root, "run/validation_tc2_gpu/step6_job_" + pilot_job + "/setup_status.json")
    accepted = read(accepted_path)
    if (accepted.get("mode") != "real_data_pilot" or accepted.get("status") != "passed"
            or accepted.get("step_6_complete") is not True or accepted.get("pilot_sources") != design["pilot_source_hashes"]
            or accepted.get("results") != design["accepted_pilot_results"] or len(accepted.get("phases", [])) != 7):
        raise RuntimeError("Pilot acceptance differs from the approved two-result snapshot")
    if checked["free_bytes"] < design["minimum_free_remote_bytes"]:
        raise RuntimeError("At least 20 GiB of free remote storage is required")
    for record in design["accepted_pilot_results"]:
        verify_artifacts(root, record, design)
    hashes = sources(root) if config_path is None else {name: sha(Path(config_path).parents[2] / name) for name in FILES}
    design_sha = sha(config_path or root / FILES[0])
    completed, previous = predecessors(root, stage, design, hashes, design_sha)
    current = p.inside(root, "run/validation_tc2_gpu/last_experiments_" + stage + "_job.txt")
    if current.exists() and not running:
        job = current.read_text().strip()
        if not job.isdigit():
            raise ValueError("Invalid current stage job pointer")
        status = p.inside(root, "run/validation_tc2_gpu/step7_job_" + job + "/setup_status.json")
        if status.exists() and read(status).get("stage_complete") is True:
            raise RuntimeError("This stage already completed; collect and review its existing job")
    return {"status": "passed", "stage_id": stage, "pilot_job_id": pilot_job, "pilot_status_sha256": sha(accepted_path),
            "workflow_preflight": checked, "design_sha256": design_sha, "experiment_sources": hashes,
            "predecessor": previous, "completed_stages": completed,
            "free_bytes": checked["free_bytes"], "quota_query": checked["quota_query"]}


def publish(root, incoming, stage, record):
    root, incoming, record = Path(root).resolve(), Path(incoming).resolve(), Path(record).absolute()
    p = pilot.protocol(root)
    p.inside(root, incoming.relative_to(root).as_posix())
    p.inside(root, record.relative_to(root).as_posix())
    if not incoming.is_relative_to(root / "tmp") or record.exists() or record.parent != root / "run/validation_tc2_gpu" or not record.name.startswith("experiments_stage_"):
        raise ValueError("Require fresh approved publication paths")
    rows = (incoming / "experiments.sha256").read_text().splitlines()
    values = {}
    for row in rows:
        digest, name = row.split(None, 1)
        if name in values or name not in FILES or len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest):
            raise ValueError("Invalid publication manifest")
        values[name] = digest.upper()
    if set(values) != set(FILES) or len(rows) != len(FILES):
        raise ValueError("Require exactly the seven approved new source files")
    for name, digest in values.items():
        source, target = p.inside(incoming, name), p.inside(root, name)
        if sha(source) != digest or (target.exists() and (not target.is_file() or sha(target) != digest)):
            raise ValueError("Conflicting experiment source; no overwrite: " + name)
    checked = preflight(root, stage, incoming / FILES[0])
    record.mkdir()
    for name in FILES:
        target = p.inside(root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as output, (incoming / name).open("rb") as source:
                shutil.copyfileobj(source, output)
        if sha(target) != values[name]:
            raise RuntimeError("Published source fingerprint differs")
    (record / "experiments.sha256").write_bytes((incoming / "experiments.sha256").read_bytes())
    atomic_json(record / "preflight.json", checked)
    return {"status": "published", "stage_id": stage, "files": len(FILES), "record": str(record)}


def perform_fits(design, spec, invoke, emit, *, root=None):
    """Run only the selected stage, keeping accepted pilot fits read-only."""
    root = Path(root or Path.cwd()).resolve()
    accepted = {item["run_key"]: item for item in design["accepted_pilot_results"]}
    configurations = {item["run_key"]: item["configuration"] for item in design["fits"]}
    categories = list(dict.fromkeys((configurations[key]["dataset"], configurations[key]["category"]) for key in spec["run_keys"]))
    for dataset, category in categories:
        cache = invoke("extract", ["--dataset", dataset, "--category", category])
        if cache.get("status") not in ("extracted", "cached") or cache.get("identity", {}).get("namespace") != "formal":
            raise RuntimeError("Formal cache extraction did not pass")
        emit("cache", cache)
    for key in spec["run_keys"]:
        known = accepted.get(key)
        fitted = {"status": "skipped", "namespace": "formal", "path": str(root / known["path"]), "identity_sha256": known["identity_sha256"]} if known else invoke("run", ["--run-key", key])
        if fitted.get("status") not in ("completed", "skipped") or fitted.get("namespace") != "formal":
            raise RuntimeError("Formal fit did not complete: " + key)
        verified = invoke("verify", ["--result", fitted["path"]])
        if verified.get("status") != "passed" or verified.get("namespace") != "formal" or any(verified.get(name) != fitted.get(name) for name in ("path", "identity_sha256")):
            raise RuntimeError("Saved result verification failed: " + key)
        emit("result", {"run_key": key, "run": fitted, "verify": verified, "accepted_pilot_reuse": known is not None})


def complete_state(state, design):
    stage = state["stage_id"]
    current = {key: state[key] for key in ("stage_id", "job_id", "design_sha256", "results", "analyses")}
    current.update(status="passed", stage_complete=True)
    completed = [*state["preflight"]["completed_stages"], current]
    if [entry["stage_id"] for entry in completed] != list(STAGES[:STAGES.index(stage) + 1]):
        raise RuntimeError("Completion requires the exact ordered stage chain")
    for entry in completed:
        spec = stage_spec(design, entry["stage_id"])
        if (entry.get("status") != "passed" or entry.get("stage_complete") is not True
                or entry.get("design_sha256") != state["design_sha256"]
                or [item["run_key"] for item in entry["results"]] != spec["run_keys"]
                or any(item.get("verified") is not True or item.get("run_status") not in ("completed", "skipped") for item in entry["results"])
                or len(entry["analyses"]) != int(spec["kind"] == "analysis")):
            raise RuntimeError("Completion requires all verified stage outputs")
        for analysis in entry["analyses"]:
            if (analysis.get("stage_id") != spec["stage_id"] or analysis.get("status") != "passed"
                    or analysis.get("rows") != spec["expected_rows"]):
                raise RuntimeError("Completion requires the exact saved-score analysis rows")
    keys = [item["run_key"] for entry in completed for item in entry["results"]]
    expected = [key for spec in design["stages"][:STAGES.index(stage) + 1] for key in spec["run_keys"]]
    if keys != expected or len(keys) != len(set(keys)):
        raise RuntimeError("Cumulative fits differ from the frozen stage plan")
    checkpoints = [{**item, "complete": STAGES.index(stage) >= STAGES.index(item["after_stage"])} for item in design["checkpoints"]]
    full = stage == STAGES[-1]
    if full and (len(keys) != 66 or [entry["stage_id"] for entry in completed] != list(STAGES)
                 or [analysis["rows"] for entry in completed for analysis in entry["analyses"]] != [18, 54, 36]):
        raise RuntimeError("Full experiment completion requires 66 fits and all three analyses")
    state.update(status="passed", stage_complete=True, step_7_complete=full, finished_at_utc=now(),
                 completed_stages=completed, cumulative_fits=len(keys), checkpoints=checkpoints)


def run_stage(root, stage):
    root = Path(root).resolve()
    job = os.environ.get("SLURM_JOB_ID", "")
    if platform.system() != "Linux" or not job.isdigit():
        raise RuntimeError("Formal stages require an allocated Linux SLURM compute job")
    p = pilot.protocol(root)
    directory = p.inside(root, "run/validation_tc2_gpu/step7_job_" + job)
    directory.mkdir()
    state = {"mode": "formal_experiment_stage", "stage_id": stage, "job_id": job, "status": "running",
             "stage_complete": False, "step_7_complete": False, "started_at_utc": now(),
             "design_sha256": sha(root / FILES[0]), "experiment_sources": sources(root),
             "caches": [], "results": [], "analyses": [], "phases": []}
    status_path = directory / "setup_status.json"
    atomic_json(status_path, state)
    try:
        design = load_design(root)
        spec = stage_spec(design, stage)
        checked = preflight(root, stage, running=True)
        state.update(preflight=checked, predecessor=checked["predecessor"])
        if os.environ.get("SLURM_JOB_PARTITION") != spec["resources"]["partition"] or os.environ.get("SLURM_JOB_QOS") not in (None, spec["resources"]["qos"]):
            raise RuntimeError("The allocation differs from the approved partition or QoS")
        if os.environ.get("SLURM_CPUS_PER_TASK") != "2" or os.environ.get("SLURM_MEM_PER_NODE") not in (None, str(spec["resources"]["memory_gib"] * 1024)):
            raise RuntimeError("The allocation differs from the approved CPU or memory request")
        pointer = p.inside(root, "run/validation_tc2_gpu/last_experiments_" + stage + "_job.txt")
        if pointer.read_text().strip() != job:
            raise RuntimeError("The submitted job is not the latest stage job")
        submitted_stage = os.environ.get("TC2_EXPERIMENT_STAGE_DIR", "")
        submitted = p.inside(root, submitted_stage)
        if not submitted_stage.startswith("run/validation_tc2_gpu/experiments_stage_") or os.environ.get("TC2_EXPERIMENT_STAGE") != stage:
            raise ValueError("Missing approved stage submission evidence")
        script = (submitted / "submission_lf.sh").read_bytes()
        if b"\r" in script or hashlib.sha256(script).hexdigest().upper() != sha(root / FILES[3]):
            raise ValueError("Submitted LF wrapper differs from the approved source")
        runtime = p.prepare_torch(p.context(root)) if spec["kind"] == "fit" else {"device": "cpu", "software": p.versions(), "slurm_job_id": job, "torch_imported": False}
        if spec["kind"] == "fit" and any(runtime[key] != value for key, value in design["expected_hardware"].items()):
            raise RuntimeError("Allocated GPU, driver or CUDA build differs from accepted experiments")
        state.update(runtime=runtime, submission={"stage": submitted_stage, "source_sha256": sha(root / FILES[3]), "submitted_sha256": sha(submitted / "submission_lf.sh")})
        resources = {"requested": spec["resources"], "runtime": runtime,
                     "slurm_environment": {key: os.environ.get(key) for key in ("SLURM_JOB_ID", "SLURM_JOB_PARTITION", "SLURM_JOB_NODELIST", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE", "SLURM_JOB_QOS")}}
        atomic_json(directory / "resources.json", resources)
        atomic_json(directory / "experiment_sources.json", {"files": state["experiment_sources"], "submission": state["submission"]})
        atomic_json(directory / "plan.json", {"stage": spec, "design_sha256": state["design_sha256"]})
        atomic_json(status_path, state)

        def invoke(action, arguments, script_name="run_tc2_gpu.py"):
            label = "phase_%03d_%s" % (len(state["phases"]) + 1, action)
            print("Starting " + label, flush=True)
            with (directory / (label + ".stdout.txt")).open("x", encoding="utf-8") as out, (directory / (label + ".stderr.txt")).open("x", encoding="utf-8") as err:
                command = [sys.executable, "-B", "-u", str(root / "scripts" / script_name)]
                if script_name == "run_tc2_gpu.py":
                    command.append(action)
                completed = subprocess.run([*command, *arguments], cwd=root, stdout=out, stderr=err)
            state["phases"].append({"phase": label, "exit_code": completed.returncode, "finished_at_utc": now()})
            atomic_json(status_path, state)
            if completed.returncode:
                raise RuntimeError("Experiment phase failed: " + label + " (exit " + str(completed.returncode) + ")")
            return read(directory / (label + ".stdout.txt"))

        snapshots = {item["path"]: {file.name: sha(file) for file in p.inside(root, item["path"]).iterdir()} for item in design["accepted_pilot_results"]}

        def emit(kind, value):
            if kind == "cache":
                path = Path(value["path"])
                relative = path.relative_to(root).as_posix()
                p.inside(root, relative)
                meta = read(path / "metadata.json")
                state["caches"].append({"path": relative, "identity": value["identity"], "metadata_sha256": sha(path / "metadata.json"),
                                        "layer_hashes": {name: entry["sha256"] for name, entry in meta["layers"].items()}})
            else:
                fit = next(item["configuration"] for item in design["fits"] if item["run_key"] == value["run_key"])
                path = Path(value["run"]["path"])
                if not path.is_absolute():
                    path = p.inside(root, value["run"]["path"])
                relative = path.relative_to(root).as_posix()
                evidence = read(path / "evidence.json")
                entry = {"run_key": value["run_key"], "path": relative, "identity_sha256": value["run"]["identity_sha256"],
                         **{key: fit[key] for key in ("method", "dataset", "category", "run_seed", "normal_train_n")},
                         "run_status": value["run"]["status"], "verified": True, "accepted_pilot_reuse": value["accepted_pilot_reuse"],
                         "timings": evidence["timings"], "gpu_peak_allocated_bytes": evidence["gpu_peak_allocated_bytes"],
                         "gpu_peak_reserved_bytes": evidence["gpu_peak_reserved_bytes"]}
                verify_artifacts(root, entry, design)
                if value["accepted_pilot_reuse"] and snapshots[relative] != {file.name: sha(file) for file in path.iterdir()}:
                    raise RuntimeError("Accepted pilot artifact bytes changed")
                state["results"].append(entry)
            atomic_json(status_path, state)
            print("Verified " + kind, flush=True)

        if spec["kind"] == "fit":
            if stage == "B0_LOCO":
                from tc2_gpu_cache import input_index
                dimensions = []
                for dataset, category in dict.fromkeys((item["configuration"]["dataset"], item["configuration"]["category"]) for item in design["fits"] if item["run_key"] in spec["run_keys"]):
                    manifest, _ = p.manifest(root, dataset, category)
                    index = input_index(p.context(root), manifest, include_masks=True)
                    pixels = sum(item["orig_hw"][0] * item["orig_hw"][1] for item in index)
                    test_paths = {row["path"] for row in manifest["test"]["good"] + manifest["test"]["anomalies"]}
                    test_pixels = sum(item["orig_hw"][0] * item["orig_hw"][1] for item in index if item["path"] in test_paths)
                    dimensions.append({"dataset": dataset, "category": category, "images": len(index), "original_pixels": pixels,
                                       "unique_original_hw": sorted({tuple(item["orig_hw"]) for item in index}),
                                       "test_original_pixels": test_pixels, "conservative_host_bytes": 4 * 1024**3 + 20 * test_pixels})
                state["loco_original_dimensions"] = dimensions
                atomic_json(status_path, state)
                print(json.dumps({"loco_original_dimensions": dimensions}), flush=True)
                if any(item["conservative_host_bytes"] > spec["resources"]["memory_gib"] * 1024**3 for item in dimensions):
                    raise RuntimeError("LOCO original-resolution evaluation exceeds the fixed host-memory estimate; review resources before fitting")
            perform_fits(design, spec, invoke, emit, root=root)
        else:
            registry = {item["run_key"]: item for entry in checked["completed_stages"] for item in entry["results"]}
            selected = [registry[key] for key in spec["source_run_keys"]]
            atomic_json(directory / "analysis_index.json", {"results": selected})
            result = invoke("analyze", ["--root", str(root), "--stage", stage, "--index", str(directory / "analysis_index.json"),
                                      "--output", str(root / "run/tc2_gpu/summaries" / stage)], "analyze_scores_tc2_gpu.py")
            if result.get("status") != "passed" or result.get("stage") != stage or result.get("rows") != spec["expected_rows"]:
                raise RuntimeError("Saved-score analysis did not pass")
            result["stage_id"] = stage
            verify_artifacts(root, result, design, analysis=True)
            state["analyses"].append(result)
            cache_ids = set()
            for record in selected:
                evidence = read(p.inside(root, record["path"]) / "evidence.json")
                cache_id = p.digest(evidence["cache_identity"])
                if cache_id not in cache_ids:
                    cached = evidence["cache_identity"]
                    path = p.inside(root, "run/tc2_gpu/feature_cache/" + cached["dataset"] + "/" + cached["category"] + "/" + cache_id)
                    meta = read(path / "metadata.json")
                    state["caches"].append({"path": path.relative_to(root).as_posix(), "identity": evidence["cache_identity"],
                                            "metadata_sha256": sha(path / "metadata.json"), "layer_hashes": {name: entry["sha256"] for name, entry in meta["layers"].items()}})
                    cache_ids.add(cache_id)
        for relative, before in snapshots.items():
            if before != {file.name: sha(file) for file in p.inside(root, relative).iterdir()}:
                raise RuntimeError("Accepted pilot result bytes changed during this stage")
        if sources(root) != state["experiment_sources"]:
            raise RuntimeError("Experiment source files changed during execution")
        load_design(root)
        pilot.accepted_workflow(root, pilot.load_design(root))
        predecessors(root, stage, design, state["experiment_sources"], state["design_sha256"])
        import resource
        resources["child_peak_rss_kib"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        resources["free_bytes_after"] = shutil.disk_usage(root).free
        atomic_json(directory / "resources.json", resources)
        complete_state(state, design)
        atomic_json(directory / "result_summary.json", {key: state[key] for key in ("results", "analyses", "caches", "cumulative_fits", "checkpoints", "completed_stages", "step_7_complete")})
        atomic_json(status_path, state)
        return state
    except BaseException as error:
        state.update(status="failed", stage_complete=False, step_7_complete=False, finished_at_utc=now(), error=type(error).__name__ + ": " + str(error))
        atomic_json(status_path, state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "preflight", "publish", "run"):
        command = commands.add_parser(action)
        command.add_argument("--root", required=True, type=Path)
        command.add_argument("--stage", choices=STAGES, required=action != "plan")
        if action == "preflight":
            command.add_argument("--config", type=Path)
        if action == "publish":
            command.add_argument("--incoming", required=True, type=Path)
            command.add_argument("--record", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        design = load_design(args.root)
        result = {"status": "planned", "fits": len(design["fits"]), "new_fits": design["expected_new_fits"], "stages": design["stages"]}
    elif args.action == "preflight":
        result = preflight(args.root, args.stage, args.config)
    elif args.action == "publish":
        result = publish(args.root, args.incoming, args.stage, args.record)
    else:
        result = run_stage(args.root, args.stage)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
