#!/usr/bin/env python3
"""Audit TC2 GPU inputs locally, or validate the existing environment in a SLURM job.

No installation, download, feature cache extraction, fitting or legacy writes.
Torch is imported only after the compute-job guard has passed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
import zipfile

import importlib.util as _import_util
_bootstrap_spec = _import_util.spec_from_file_location(
    "_tc2_gpu_bootstrap", Path(__file__).resolve().parents[1] / "_bootstrap.py")
_bootstrap = _import_util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)
ROOT = _bootstrap.configure(__file__)
PROJECT = ROOT
import tc2_gpu_protocol as current_protocol
import tc2_gpu_provenance as provenance

EXPECTED_PROTOCOL_SHA256 = current_protocol.PROTOCOL_SHA256
REQUIRED_PACKAGES = ("torch", "torchvision", "numpy", "scipy", "scikit-learn",
                     "pillow", "pandas", "matplotlib", "PyYAML", "tqdm")


def setup_record(relative):
    path = Path(relative)
    if path.anchor or str(relative) in ("", ".") or ".." in path.parts or "\\" in str(relative) or ":" in str(relative):
        raise ValueError("Invalid setup-record path")
    # Historical records are read explicitly through the archive provenance API.
    return PROJECT / "run/setup_tc2_gpu" / path


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def resolve_project_path(value):
    path = Path(value).expanduser()
    return (PROJECT / path).resolve() if not path.is_absolute() else path.resolve()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                     allow_nan=False) + "\n", encoding="utf-8")


def read_contract(config_path):
    canonical = PROJECT / "configs/tc2_gpu/setup.json"
    if Path(config_path).resolve() != canonical.resolve():
        raise ValueError("Use the current canonical TC2 GPU setup configuration")
    setup = provenance.read_current_config(PROJECT, "setup")
    protocol, _, _ = current_protocol.contract(PROJECT)
    if sha256(PROJECT / "configs/tc2_gpu/protocol.json") != EXPECTED_PROTOCOL_SHA256:
        raise ValueError("Current protocol fingerprint mismatch")
    manifests = []
    for entry in protocol["data"]["frozen_manifests"]:
        path = (PROJECT / entry["path"]).resolve()
        if not path.is_relative_to((PROJECT / "manifests").resolve()):
            raise ValueError("Manifest path leaves the declared manifest directory")
        if sha256(path) != entry["file_sha256"]:
            raise ValueError("Frozen manifest fingerprint mismatch: " + entry["path"])
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest["split_hash"] != entry["split_hash"]:
            raise ValueError("Manifest split hash mismatch: " + entry["path"])
        manifests.append(manifest)
    if len(manifests) != setup["expected_inputs"]["category_manifests"]:
        raise ValueError("Unexpected category manifest count")
    return setup, protocol, manifests


def required_files(manifests):
    expected = {}
    for manifest in manifests:
        images = (manifest["dev"] + manifest["fit_pool"] +
                  manifest["test"]["good"] + manifest["test"]["anomalies"])
        masks = [mask for item in manifest["test"]["anomalies"] for mask in item["masks"]]
        for kind, entries in (("image", images), ("mask", masks)):
            for entry in entries:
                relative = entry["path"]
                record = {"path": relative, "expected_sha256": entry["sha256"].upper(),
                          "kind": kind, "dataset": manifest["dataset"],
                          "category": manifest["category"]}
                if relative in expected and expected[relative] != record:
                    raise ValueError("Conflicting manifest entries: " + relative)
                expected[relative] = record
    return [expected[key] for key in sorted(expected)]


def inspect_file(root, entry):
    result = dict(entry)
    try:
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root):
            result["status"] = "path_outside_dataset_root"
        elif not target.is_file():
            result["status"] = "missing"
        else:
            result["size_bytes"] = target.stat().st_size
            result["actual_sha256"] = sha256(target)
            result["status"] = ("match" if result["actual_sha256"] ==
                                entry["expected_sha256"] else "hash_mismatch")
    except (OSError, ValueError) as error:
        result.update(status="read_error", error=str(error))
    return result


def audit_inputs(root, manifests, setup):
    expected = required_files(manifests)
    image_count = sum(row["kind"] == "image" for row in expected)
    mask_count = sum(row["kind"] == "mask" for row in expected)
    if (image_count, mask_count) != (setup["expected_inputs"]["images"],
                                    setup["expected_inputs"]["masks"]):
        raise ValueError("Manifest file counts differ from the approved scope")
    root = Path(root).expanduser().resolve()
    records = [inspect_file(root, row) for row in expected]
    counts = {status: sum(row["status"] == status for row in records)
              for status in sorted({row["status"] for row in records})}
    return {"checked_at_utc": now_utc(), "datasets_root": str(root),
            "expected_images": image_count, "expected_masks": mask_count,
            "counts": counts, "ready": all(row["status"] == "match" for row in records),
            "files": records,
            "policy": "Read-only verification. Missing or mismatched files are not repaired."}


def audit_weights(path, setup):
    result = {"expected_enum": setup["expected_inputs"]["weights_enum"],
              "official_url": setup["expected_inputs"]["weights_official_url"],
              "ready": False, "status": "path_not_configured"}
    if not path:
        return result
    target = Path(path).expanduser().resolve()
    result["path"] = str(target)
    try:
        if not target.is_file():
            result["status"] = "missing"
            return result
        result.update(size_bytes=target.stat().st_size, sha256=sha256(target))
        prefix = setup["expected_inputs"]["weights_official_sha256_prefix"].upper()
        result["ready"] = result["sha256"].startswith(prefix)
        result["status"] = "official_hash_prefix_match" if result["ready"] else "hash_prefix_mismatch"
    except OSError as error:
        result.update(status="read_error", error=str(error))
    result["note"] = "Full SHA-256 recorded; model compatibility is checked separately on GPU."
    return result


def audit_legacy_caches():
    records = []
    for path in sorted((PROJECT / "run" / "feature_cache").glob("*.npz")):
        record = {"path": str(path), "size_bytes": path.stat().st_size,
                  "tc2_gpu_eligible": False, "policy": "Historical input; never rewritten or converted here."}
        try:
            import numpy as np
            with np.load(path, allow_pickle=False) as archive:
                record["metadata"] = json.loads(str(archive["__meta__"].item()))
        except (ImportError, OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            record["metadata_error"] = str(error)
        records.append(record)
    return records


def command_output(arguments, timeout=60):
    try:
        result = subprocess.run(arguments, text=True, encoding="utf-8", errors="replace",
                                capture_output=True, check=False, timeout=timeout)
        return {"returncode": result.returncode, "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": 127, "stdout": "", "stderr": type(error).__name__ + ": " + str(error)}


def require_compute_job():
    if platform.system() != "Linux" or not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Environment/GPU checks must run inside an allocated Linux SLURM job")


def require_verified_remote(setup):
    # Historical jobs cannot authorize this source profile or a reclaimed deployment.
    provenance.require_current_acceptance(PROJECT, "setup")
    required = ("home", "setup_root", "conda_environment_prefix", "partition", "qos")
    missing = [key for key in required if not setup["remote"].get(key)]
    if missing:
        raise ValueError("Complete remote discovery before the GPU job: " + ", ".join(missing))
    home = Path(setup["remote"]["home"]).resolve()
    staging = Path(setup["remote"]["setup_root"]).resolve()
    if staging == home or not staging.is_relative_to(home):
        raise ValueError("Configured TC2 GPU setup root must remain strictly inside the verified personal home")
    if not Path(setup["remote"]["conda_environment_prefix"]).resolve().is_relative_to(staging / "envs"):
        raise ValueError("Configured environment must remain inside the project envs directory")
    if PROJECT.resolve() != staging:
        raise ValueError("Run GPU audits from the verified staging copy, not an existing project directory")
    if Path(setup["remote"]["conda_environment_prefix"]).resolve() != Path(sys.prefix).resolve():
        raise ValueError("Active Python prefix differs from the verified environment configuration")
    if os.environ.get("SLURM_JOB_PARTITION") != setup["remote"]["partition"]:
        raise ValueError("Allocated partition differs from the verified configuration")
    actual_qos = os.environ.get("SLURM_JOB_QOS")
    if actual_qos and actual_qos != setup["remote"]["qos"]:
        raise ValueError("Allocated QoS differs from the verified configuration")


def validate_gpu(weights, protocol, include_backbone):
    require_compute_job()
    result = {"ready": False, "gpu_operation": "not_run", "backbone": {"status": "not_requested"}}
    try:
        import torch
        import torchvision
        result.update(torch_version=torch.__version__, torchvision_version=torchvision.__version__,
                      torch_cuda_build=torch.version.cuda)
        if not torch.cuda.is_available():
            result["error"] = "CUDA unavailable; CPU fallback is not allowed"
            return result
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        with torch.inference_mode(), torch.autocast(device_type="cuda", enabled=False):
            identity = torch.eye(16, dtype=torch.float32, device="cuda")
            product = identity @ identity
            torch.cuda.synchronize()
            if product.dtype != torch.float32 or not torch.equal(product, identity):
                raise RuntimeError("FP32 CUDA matrix multiplication check failed")
            result.update(gpu_operation="pass", gpu_name=torch.cuda.get_device_name(0),
                          visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
                          device_memory_bytes=torch.cuda.get_device_properties(0).total_memory,
                          autocast_enabled=False, matmul_tf32=False, cudnn_tf32=False)
            if include_backbone:
                if not weights.get("ready"):
                    result["backbone"] = {"status": "blocked_weights_not_verified"}
                    return result
                from torchvision.models import resnet18, ResNet18_Weights
                if ResNet18_Weights.IMAGENET1K_V1.url != weights["official_url"]:
                    raise RuntimeError("Installed torchvision weight source differs from the frozen enum")
                # weights=None prevents an implicit download. Only the verified local file is loaded.
                model = resnet18(weights=None)
                state = torch.load(weights["path"], map_location="cpu", weights_only=True)
                model.load_state_dict(state, strict=True)
                model.requires_grad_(False).eval().float().to("cuda")
                captured = {}
                handles = []
                for name in ("layer1", "layer2", "layer3"):
                    handles.append(getattr(model, name).register_forward_hook(
                        lambda module, inputs, output, key=name: captured.__setitem__(key, output)))
                try:
                    model(torch.zeros((1, 3, 256, 256), device="cuda", dtype=torch.float32))
                    torch.cuda.synchronize()
                finally:
                    for handle in handles:
                        handle.remove()
                shapes = {}
                for name, expected in protocol["backbone"]["expected_feature_shapes_chw"].items():
                    feature = captured[name]
                    shapes[name] = list(feature.shape[1:])
                    if shapes[name] != expected or feature.dtype != torch.float32 or not torch.isfinite(feature).all().item():
                        raise RuntimeError("Backbone feature validation failed: " + name)
                result["backbone"] = {"status": "pass", "feature_shapes_chw": shapes,
                                      "dtype": "float32", "input": "synthetic_zero_tensor",
                                      "weights_sha256": weights["sha256"]}
        result["ready"] = True
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    return result


def probe_environment(weights, protocol, include_backbone):
    require_compute_job()
    versions = {}
    for name in REQUIRED_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    result = {"checked_at_utc": now_utc(), "python": sys.version,
              "python_executable": sys.executable, "environment_prefix": sys.prefix,
              "platform": platform.platform(), "node": platform.node(),
              "slurm_job_id": os.environ["SLURM_JOB_ID"],
              "slurm_partition": os.environ.get("SLURM_JOB_PARTITION"),
              "slurm_qos_if_exposed": os.environ.get("SLURM_JOB_QOS"),
              "slurm_cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
              "slurm_memory_per_node_mb": os.environ.get("SLURM_MEM_PER_NODE"),
              "packages": versions, "missing_packages": [name for name, version in versions.items() if version is None]}
    result["nvidia_smi"] = command_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
    result["pip_check"] = command_output([sys.executable, "-m", "pip", "check"])
    result["gpu"] = validate_gpu(weights, protocol, include_backbone)
    result["ready"] = (sys.version_info >= (3, 10) and not result["missing_packages"]
                       and result["nvidia_smi"]["returncode"] == 0
                       and result["pip_check"]["returncode"] == 0 and result["gpu"]["ready"])
    return result


def export_environment(output_dir):
    """Export actual versions only into this new check record, never over templates."""
    destination = Path(output_dir).resolve()
    allowed = (PROJECT / "run/setup_tc2_gpu").resolve()
    if destination == allowed or not destination.is_relative_to(allowed):
        raise ValueError("Actual environment exports must stay inside a setup check record")
    conda = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not conda:
        return {"ready": False, "error": "Conda executable unavailable; no environment export fabricated"}
    exported = command_output([conda, "env", "export", "--prefix", sys.prefix], timeout=120)
    if exported["returncode"]:
        return {"ready": False, "error": exported["stderr"]}
    import yaml
    environment = yaml.safe_load(exported["stdout"])
    environment.pop("prefix", None)
    environment.pop("variables", None)
    # Do not put credentials or Conda environment variables in exported files.
    def has_private_url(value):
        if isinstance(value, dict):
            return any(has_private_url(item) for item in value.values())
        if isinstance(value, list):
            return any(has_private_url(item) for item in value)
        if isinstance(value, str) and "://" in value:
            url = urlsplit(value.split(" @ ")[-1])
            return bool(url.username or url.password or url.query or "/t/" in url.path)
        return False
    if has_private_url(environment):
        return {"ready": False, "error": "Environment contains a credential-bearing or private URL; review export sources before saving"}
    yml = yaml.safe_dump(environment, sort_keys=False, allow_unicode=True)
    packages = sorted({f"{dist.metadata['Name']}=={dist.version}"
                       for dist in metadata.distributions() if dist.metadata.get("Name")}, key=str.lower)
    lock = "# Actual TC2 Python distribution versions; pair with environment-tc2_gpu-actual.yml and GPU metadata.\n" + "\n".join(packages) + "\n"
    files = {destination / "environment-tc2_gpu-actual.yml": yml,
             destination / "requirements-tc2_gpu-actual.txt": lock}
    conflicts = [str(path) for path, content in files.items()
                 if path.exists() and path.read_text(encoding="utf-8") != content]
    if conflicts:
        return {"ready": False, "error": "Existing lock differs; review before replacing", "conflicts": conflicts}
    for path, content in files.items():
        if not path.exists():
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
    return {"ready": True, "files": [{"path": str(path), "sha256": sha256(path)} for path in files]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("environment", "inputs", "all"), default="all")
    parser.add_argument("--config", default="configs/tc2_gpu/setup.json")
    parser.add_argument("--datasets-root")
    parser.add_argument("--weights-path")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    output = resolve_project_path(args.output_dir)
    output_root = (PROJECT / "run" / "setup_tc2_gpu").resolve()
    if output == output_root or not output.is_relative_to(output_root):
        parser.error("Use a new check-ID directory strictly under run/setup_tc2_gpu")
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory is nonempty; use a fresh check ID")
    setup, protocol, manifests = read_contract(resolve_project_path(args.config))
    if args.mode != "inputs":
        require_verified_remote(setup)
        require_compute_job()
    data_root = args.datasets_root or setup["remote"]["datasets_root"]
    weight_path = args.weights_path or setup["remote"]["weights_path"]
    if args.mode in ("inputs", "all") and not data_root:
        parser.error("Specify the verified datasets root explicitly")
    output.mkdir(parents=True, exist_ok=True)
    status = {"checked_at_utc": now_utc(), "mode": args.mode, "step_2_complete": False,
              "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
              "modifications": "Audit records and verified environment exports only; no repairs or experiments"}
    weights = audit_weights(weight_path, setup)
    write_json(output / "weights_info.json", weights)
    if args.mode in ("inputs", "all"):
        inputs = audit_inputs(data_root, manifests, setup)
        inputs["legacy_caches"] = audit_legacy_caches()
        write_json(output / "data_audit.json", inputs)
        status["inputs_ready"] = inputs["ready"]
        status["input_counts"] = inputs["counts"]
    if args.mode in ("environment", "all"):
        environment = probe_environment(weights, protocol, args.mode == "all")
        write_json(output / "environment.json", environment)
        write_json(output / "gpu_info.txt", environment.get("gpu", {}))
        (output / "versions.txt").write_text(json.dumps({"python": environment["python"],
            "packages": environment["packages"]}, indent=2) + "\n", encoding="utf-8")
        status["environment_ready"] = environment["ready"]
        if environment["ready"]:
            status["environment_export"] = export_environment(output)
        status["backbone_ready"] = environment["gpu"]["backbone"]["status"] == "pass"
    status["weights_ready"] = weights["ready"]
    status["step_2_complete"] = (args.mode == "all" and status.get("inputs_ready", False)
        and status.get("environment_ready", False) and status.get("backbone_ready", False)
        and status.get("environment_export", {}).get("ready", False) and weights["ready"])
    status["status"] = "ready" if status["step_2_complete"] else "incomplete"
    write_json(output / "setup_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["step_2_complete"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        raise SystemExit(2)
