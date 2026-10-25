"""Frozen protocol, identities, paths and runtime contracts; no eager torch import."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from importlib import metadata
from itertools import product
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import uuid

from tc2_gpu_provenance import (read_current_config, current_source_sha, historical_config,
    require_current_acceptance)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_SHA256 = current_source_sha(ROOT, "configs/tc2_gpu/protocol.json")
SHAPES = {"layer1": (64, 64, 64), "layer2": (128, 32, 32), "layer3": (256, 16, 16)}
RULES = ("native", "max", "top_0.001", "top_0.01", "top_0.05")
EXECUTION = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "extraction_batch_size": 1,
             "prediction_batch_size": 1, "workers": 0, "cpu_threads": 2, "warmup_iterations": 20,
             "padim_position_chunk_size": 256, "patchcore_query_chunk_size": 1024,
             "patchcore_bank_chunk_size": 4096, "patchcore_sampling_chunk_size": 16384}
SOURCE_FILES = ("src/tc2_gpu_provenance.py", "src/tc2_gpu_protocol.py", "src/tc2_gpu_cache.py", "src/tc2_gpu_runner.py",
                "scripts/run_tc2_gpu.py", "configs/tc2_gpu/runtime.json", "src/data.py",
                "src/padim_adapter.py", "src/patchcore_adapter.py", "src/sampling.py",
                "src/scoring.py", "src/anomaly_postprocess.py", "src/metric_core.py", "src/evaluate.py")
CACHE_SOURCES = ("src/tc2_gpu_provenance.py", "src/tc2_gpu_protocol.py", "src/tc2_gpu_cache.py", "src/data.py", "configs/tc2_gpu/runtime.json")


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest().upper()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n")


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Use a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value or value == ".":
        raise ValueError("Path must be canonical and remain inside its root")
    return value


def inside(root, value):
    root = Path(root).absolute()
    path = root / relative(value)
    if root.is_symlink():
        raise ValueError("Symbolic-link roots are unsupported")
    for ancestor in [path, *path.parents]:
        if ancestor == root.parent:
            break
        if ancestor.is_symlink():
            raise ValueError("Symbolic links are unsupported in workflow paths")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes its root")
    return path


@contextmanager
def exclusive(parent, key):
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    lock = inside(parent, "." + key + ".lock")
    token = uuid.uuid4().hex
    try:
        write_json(lock, {"owner": token, "pid": os.getpid(), "slurm_job_id": os.environ.get("SLURM_JOB_ID")})
    except FileExistsError as error:
        raise RuntimeError("Work is locked; preserve the lock and inspect its owner: " + str(lock)) from error
    try:
        yield
    finally:
        if lock.is_file() and read_json(lock).get("owner") == token:
            lock.unlink()


def fingerprints(root, names=SOURCE_FILES):
    return {name: sha(inside(root, name)) for name in names}


def versions():
    result = {"python": platform.python_version()}
    for name in ("numpy", "torch", "torchvision", "pillow", "scikit-learn", "pyyaml"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def contract(root=ROOT):
    root = Path(root).resolve()
    if sha(root / "configs/tc2_gpu/protocol.json") != PROTOCOL_SHA256:
        raise ValueError("Frozen protocol changed")
    protocol = read_json(root / "configs/tc2_gpu/protocol.json")
    naming = read_json(root / "configs/tc2_gpu/workflow.json")
    execution = read_json(root / "configs/tc2_gpu/runtime.json")
    if execution != EXECUTION or naming["workflow_id"] != "tc2_gpu" or naming["frozen_protocol"]["sha256"] != PROTOCOL_SHA256:
        raise ValueError("Workflow configuration differs from the approved design")
    for entry in protocol["data"]["frozen_manifests"]:
        if sha(inside(root, entry["path"])) != entry["file_sha256"]:
            raise ValueError("Frozen manifest changed")
    for key in ("results", "logs", "summaries", "resources", "feature_cache"):
        if naming["outputs"][key] != "run/tc2_gpu/" + key:
            raise ValueError("Unexpected formal output mapping")
    return protocol, naming, execution


@dataclass(frozen=True)
class Context:
    root: Path
    storage: Path
    datasets: Path
    weights: Path
    namespace: str

    def output(self, name):
        if name not in ("feature_cache", "results", "logs", "resources", "summaries"):
            raise ValueError("Unsupported workflow output")
        return inside(self.storage, name)


def context(root=ROOT, sandbox=None):
    root = Path(root).resolve()
    contract(root)
    if sandbox is None:
        return Context(root, inside(root, "run/tc2_gpu"), inside(root, "datasets"),
                       inside(root, "weights/resnet18-f37072fd.pth"), "formal")
    sandbox = Path(sandbox).absolute()
    allowed = (root / "run/validation_tc2_gpu").resolve()
    if sandbox == allowed or not sandbox.resolve().is_relative_to(allowed):
        raise ValueError("Synthetic contexts must stay strictly inside validation")
    inside(allowed, sandbox.relative_to(allowed).as_posix())
    return Context(root, inside(sandbox, "workflow"), inside(sandbox, "datasets"),
                   inside(root, "weights/resnet18-f37072fd.pth"), "validation")


def manifest(root, dataset, category):
    protocol, _, _ = contract(root)
    for entry in protocol["data"]["frozen_manifests"]:
        value = read_json(inside(root, entry["path"]))
        if (value["dataset"], value["category"]) == (dataset, category):
            return value, entry["file_sha256"]
    raise ValueError("Category is outside the frozen protocol")


def image_entries(value):
    rows = value["dev"] + value["fit_pool"] + value["test"]["good"] + value["test"]["anomalies"]
    seen, result = set(), []
    for row in rows:
        path = relative(row["path"])
        if path in seen:
            raise ValueError("Manifest splits contain overlapping image paths")
        seen.add(path)
        result.append({"path": path, "sha256": row["sha256"]})
    return result


def samples(value, seed, count):
    pool = {entry["path"]: entry for entry in value["fit_pool"]}
    chosen = value["runs"][str(seed)][str(count)]
    if len(chosen) != count or len(set(chosen)) != count or any(path not in pool for path in chosen):
        raise ValueError("Invalid normal training list")
    normal = lambda row, defect: {"path": relative(row["path"]), "label": 0, "defect_type": defect, "mask_paths": []}
    fit = [normal(pool[path], "") for path in chosen]
    dev = [normal(row, "") for row in value["dev"]]
    test = [normal(row, "good") for row in value["test"]["good"]]
    for row in value["test"]["anomalies"]:
        if row["label"] != 1:
            raise ValueError("Invalid anomaly label")
        test.append({"path": relative(row["path"]), "label": 1, "defect_type": row["defect_type"],
                     "mask_paths": [relative(mask["path"]) for mask in row["masks"]]})
    groups = [{item["path"] for item in group} for group in (fit, dev, test)]
    if any(groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("Fit, development and test lists overlap")
    return {"fit": fit, "dev": dev, "test": test}


def build_plan(root=ROOT):
    protocol, naming, execution = contract(root)
    fits, counts = [], {}
    for stage in protocol["experiment_matrix"]["fit_stages"]:
        scan = stage["scan"]
        keys = list(scan)
        variants = list(product(*(scan[key] for key in keys))) if keys else [()]
        before = len(fits)
        for category, method, seed, count, values in product(stage["categories"], stage["methods"], stage["run_seeds"], stage["normal_train_sizes"], variants):
            changes = {**stage["overrides"], **dict(zip(keys, values))}
            cfg = {"stage": stage["stage_id"], "dataset": stage["dataset"], "category": category,
                   "method": method, "run_seed": seed, "normal_train_n": count, "execution": dict(execution)}
            if method == "padim":
                cfg["layers"] = changes.get("padim.layers", protocol["padim"]["baseline_layers"])
                cfg["padim"] = {"n_dims": changes.get("padim.feature_dimensions", protocol["padim"]["baseline_feature_dimensions"]),
                                "eps": protocol["padim"]["covariance"]["identity_regularization"], "dims_seed": seed}
            else:
                cfg["layers"] = protocol["patchcore"]["layers"]
                cfg["patchcore"] = {"coreset_ratio": changes.get("patchcore.coreset_ratio", protocol["patchcore"]["baseline_coreset_ratio"]),
                                    "num_neighbors": protocol["patchcore"]["native_image_score"]["support_neighbors"],
                                    "sampling": changes.get("patchcore.sampling", protocol["patchcore"]["baseline_sampling"]), "sampling_seed": seed}
            key = "_".join([stage["stage_id"], stage["dataset"], category, method, f"s{seed}", f"n{count}", digest(cfg)[:12]])
            fits.append({"run_key": key, "configuration": cfg})
        counts[stage["stage_id"]] = len(fits) - before
        if counts[stage["stage_id"]] != stage["expected_new_fits"]:
            raise ValueError("Expanded matrix disagrees with frozen stage counts")
    if len(fits) != 66 or len({item["run_key"] for item in fits}) != 66:
        raise ValueError("Expected 66 distinct fits")
    return {"workflow_id": "tc2_gpu", "protocol_sha256": PROTOCOL_SHA256, "fits": fits, "stage_counts": counts,
            "main_fit_count": 62, "extension_fit_count": 4, "offline_stages": protocol["experiment_matrix"]["offline_stages"],
            "execution_order": protocol["experiment_matrix"]["execution_order"], "outputs": naming["outputs"]}


def select_spec(root, run_key):
    matches = [item["configuration"] for item in build_plan(root)["fits"] if item["run_key"] == run_key]
    if len(matches) != 1:
        raise ValueError("Select exactly one run_key from plan")
    return matches[0]


def accepted_inputs(root, *, allow_local_summary=False):
    """Current input receipts only; isolated validation may reference frozen weight identity."""
    root = Path(root).resolve()
    validation = (ROOT / "run/validation_tc2_gpu").resolve()
    isolated = root != ROOT and root.is_relative_to(validation)
    if allow_local_summary and root == ROOT:
        # This is metadata for synthetic fixtures, never a current acceptance receipt.
        historical = historical_config(ROOT, "setup")["final_acceptance"]
        return {"job": None, "weights_sha256": historical["weights_sha256"],
                "export_hashes": {}, "source": "historical_weight_identity_for_synthetic_validation"}
    if not isolated:
        require_current_acceptance(root, "setup")
    pointer = root / "run/setup_tc2_gpu/last_check_all_job.txt"
    if not pointer.is_file():
        raise RuntimeError("Actual current combined environment/input acceptance is required")
    job = pointer.read_text().strip()
    if not job.isdigit():
        raise RuntimeError("Invalid current environment acceptance pointer")
    path = root / f"run/setup_tc2_gpu/job_{job}_all/setup_status.json"
    ready = read_json(path)
    if ready.get("step_2_complete") is not True or ready.get("weights_ready") is not True:
        raise RuntimeError("Current combined environment/input acceptance has not passed")
    weight_path = path.parent / "weights_info.json"
    return {"job": job, "weights_sha256": read_json(weight_path)["sha256"],
            "export_hashes": {Path(item["path"]).name: item["sha256"] for item in ready["environment_export"]["files"]},
            "record_sha256": sha(path), "weights_record_sha256": sha(weight_path)}


def prerequisites(root=ROOT):
    root = Path(root).resolve()
    contract(root)
    require_current_acceptance(root, "workflow")
    setup = read_json(root / "configs/tc2_gpu/setup.json")
    if platform.system() != "Linux" or not os.environ.get("SLURM_JOB_ID", "").isdigit():
        raise RuntimeError("GPU work requires a Linux SLURM compute job")
    if root != Path(setup["remote"]["setup_root"]) or Path(sys.prefix) != Path(setup["remote"]["conda_environment_prefix"]):
        raise RuntimeError("Use the accepted staging root and Conda environment")
    if os.environ.get("SLURM_JOB_PARTITION") != setup["remote"]["partition"]:
        raise RuntimeError("Allocated partition differs from accepted setup")
    expected = {"numpy": "1.26.4", "torch": "2.11.0+cu128", "torchvision": "0.26.0+cu128", "pillow": "12.3.0", "scikit-learn": "1.7.2"}
    if sys.version_info[:2] != (3, 10) or any(versions()[name] != version for name, version in expected.items()):
        raise RuntimeError("Installed environment differs from accepted versions")
    accepted = accepted_inputs(root)
    for name, value in accepted["export_hashes"].items():
        if sha(root / name) != value:
            raise RuntimeError("Actual environment lock changed")
    records = {}
    for action, prefix, completion in [("metrics", "step3", "step_3_complete"), ("algorithms", "step4", "step_4_complete")]:
        job = (root / f"run/validation_tc2_gpu/last_check_{action}_job.txt").read_text().strip()
        if not job.isdigit():
            raise RuntimeError("Invalid acceptance job pointer")
        result = read_json(root / f"run/validation_tc2_gpu/{prefix}_job_{job}/setup_status.json")
        if result.get("status") != "passed" or result.get("mode") != "full" or result.get(completion) is not True:
            raise RuntimeError("Required acceptance has not passed")
        if any(sha(inside(root, name)) != value for name, value in result["source_hashes"].items()):
            raise RuntimeError("Accepted source fingerprint changed")
        records[action] = job
    records["setup"] = accepted["job"]
    return records


def prepare_torch(ctx, device="cuda", seed=17):
    if device not in ("cpu", "cuda") or (ctx.namespace == "formal" and device != "cuda"):
        raise ValueError("Formal computation requires CUDA")
    records = prerequisites(ctx.root) if device == "cuda" else {}
    import numpy as np
    import torch
    if device == "cuda" and (not torch.cuda.is_available() or torch.cuda.device_count() != 1):
        raise RuntimeError("Exactly one allocated CUDA device is required; no CPU fallback")
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(EXECUTION["cpu_threads"])
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    if torch.get_default_dtype() != torch.float32:
        raise RuntimeError("The default tensor dtype must be FP32")
    driver = None
    if device == "cuda":
        drivers = set(subprocess.check_output(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                                             text=True, timeout=10).split())
        if len(drivers) != 1:
            raise RuntimeError("Cannot identify one actual node driver version")
        driver = drivers.pop()
    return {"device": device, "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
            "driver": driver, "cuda_build": torch.version.cuda, "software": versions(), "acceptance_jobs": records,
            "compatibility_configuration_sha256": sha(ctx.root / "configs/tc2_gpu/setup.json"),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "tf32": False, "autocast": False}
