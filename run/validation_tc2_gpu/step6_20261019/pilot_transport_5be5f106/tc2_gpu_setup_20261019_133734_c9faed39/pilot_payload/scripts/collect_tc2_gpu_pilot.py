"""Bounded, read-only pilot snapshots and safe standard-library verification."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import tempfile
import uuid

LIMIT = 512 * 1024 * 1024
MAX_MEMBERS = 512
MANIFEST = "pilot_export_manifest.json"
PROTOCOL_SHA256 = "3098B6A86DBA64EE439BFE61C7A4FCFFCD082371D5A80FFBC7940997ED6A1ED1"
CONFIG = "configs/pilot_tc2_gpu.json"
RUN_KEYS = {
    "padim": "B0_mvtec_ad_bottle_padim_s17_n100_B7B86DBB2043",
    "patchcore": "B0_mvtec_ad_bottle_patchcore_s17_n100_BBC2B85C2FA8",
}
ARTIFACTS = ("config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json")
RESULT_FILES = (*ARTIFACTS, "artifacts.sha256", "SUCCESS")
JOB_FILES = {"setup_status.json", "plan.json", "resources.json", "cache_validation.json",
             "result_summary.json", "pilot_sources.json"}
HEX = r"[0-9A-F]{64}"
PHASE = re.compile(r"phase_[a-z0-9][a-z0-9_-]{0,63}\.(?:stdout|stderr)\.txt\Z")
EXECUTION = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "extraction_batch_size": 1,
             "prediction_batch_size": 1, "workers": 0, "cpu_threads": 2, "warmup_iterations": 20,
             "padim_position_chunk_size": 256, "patchcore_query_chunk_size": 1024,
             "patchcore_bank_chunk_size": 4096, "patchcore_sampling_chunk_size": 16384}
SCIENCE_SOURCES = ("src/tc2_gpu_protocol.py", "src/tc2_gpu_cache.py", "src/tc2_gpu_runner.py",
                   "scripts/run_tc2_gpu.py", "configs/runtime_tc2_gpu.json", "src/data.py",
                   "src/padim_adapter.py", "src/patchcore_adapter.py", "src/sampling.py",
                   "src/scoring.py", "src/anomaly_postprocess.py", "src/metric_core.py", "src/evaluate.py")
CACHE_SOURCES = ("src/tc2_gpu_protocol.py", "src/tc2_gpu_cache.py", "src/data.py", "configs/runtime_tc2_gpu.json")


def _extended(path):
    """Keep file operations usable for deep Windows evidence directories."""
    value = os.path.abspath(os.fspath(path))
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return Path(value)


def _plain(path):
    value = str(path)
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    return value[4:] if value.startswith("\\\\?\\") else value


def _job(value):
    value = str(value)
    if not re.fullmatch(r"[0-9]{1,12}", value):
        raise ValueError("Job ID must contain one to twelve digits")
    return value


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError("Snapshot paths must be relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")) or path.as_posix() != value:
        raise ValueError("Noncanonical snapshot path")
    return value


def _no_links(path):
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Links and Windows reparse points are unsupported")


def _inside(root, name):
    path = root / _relative(name)
    _no_links(path)
    return path


def _sha(path):
    digest = hashlib.sha256()
    with _extended(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _bytes_sha(value):
    return hashlib.sha256(value).hexdigest().upper()


def _read_bounded(path, maximum):
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("Snapshot file exceeds its remaining size allowance")
    return value


def _json(value):
    def object_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = item
        return result
    return json.loads(value.decode("utf-8"), object_pairs_hook=object_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON value")))


def _encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def _digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return _bytes_sha(data)


def _role(name, job_id):
    _relative(name)
    if name == CONFIG:
        return "pilot_configuration"
    prefix = "run/validation_tc2_gpu/"
    if name in {prefix + "slurm-" + job_id + suffix for suffix in (".out", ".err")}:
        return "slurm_log"
    job_prefix = prefix + "step6_job_" + job_id + "/"
    if name.startswith(job_prefix):
        tail = name[len(job_prefix):]
        if tail in JOB_FILES:
            return "pilot_record"
        if PHASE.fullmatch(tail):
            return "phase_log"
    if re.fullmatch(r"run/tc2_gpu/feature_cache/mvtec_ad/bottle/" + HEX + r"/(?:metadata\.json|COMPLETE)", name):
        return "cache_metadata"
    if re.fullmatch(r"run/tc2_gpu/results/" + HEX + r"/(?:" + "|".join(re.escape(item) for item in RESULT_FILES) + ")", name):
        return "published_result"
    raise ValueError("File is outside the pilot export whitelist: " + name)


def _cache_path(name):
    _relative(name)
    if not re.fullmatch(r"run/tc2_gpu/feature_cache/mvtec_ad/bottle/" + HEX, name):
        raise ValueError("Pilot cache path is outside the approved category")
    return name


def _result_path(name):
    _relative(name)
    if not re.fullmatch(r"run/tc2_gpu/results/" + HEX, name):
        raise ValueError("Pilot result path is not a published formal result")
    return name


def _status(value, job_id):
    if not isinstance(value, dict) or value.get("job_id") != job_id or value.get("mode") != "real_data_pilot":
        raise ValueError("Pilot record has a different job or execution mode")
    if value.get("status") not in ("running", "passed", "failed") or type(value.get("step_6_complete")) is not bool:
        raise ValueError("Pilot record has an invalid state")
    if value["step_6_complete"] != (value["status"] == "passed"):
        raise ValueError("Pilot completion state is inconsistent")
    if value.get("cache") is not None:
        if not isinstance(value["cache"], dict):
            raise ValueError("Invalid cache record")
        _cache_path(value["cache"]["path"])
    rows = value.get("results", [])
    if not isinstance(rows, list) or len(rows) > 2:
        raise ValueError("Pilot contains unexpected result records")
    observed, paths = set(), set()
    for row in rows:
        if not isinstance(row, dict) or row.get("method") not in RUN_KEYS:
            raise ValueError("Unsupported pilot result method")
        if row.get("run_key") != RUN_KEYS[row["method"]] or row["method"] in observed:
            raise ValueError("Unexpected or duplicate pilot run key")
        path = _result_path(row["path"])
        if path in paths:
            raise ValueError("Duplicate pilot result path")
        observed.add(row["method"]); paths.add(path)
    if value["step_6_complete"] and (value.get("cache") is None or observed != set(RUN_KEYS)):
        raise ValueError("Completed pilot must identify its cache and both methods")
    return value


def _pilot_config(value):
    required = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "protocol_sha256": PROTOCOL_SHA256,
                "dataset": "mvtec_ad", "category": "bottle", "run_seed": 17, "normal_train_n": 100,
                "workflow_acceptance_job_id": "44012"}
    for key, expected in required.items():
        actual = value.get(key)
        if key == "workflow_acceptance_job_id":
            actual = str(actual)
        if actual != expected:
            raise ValueError("Pilot configuration differs at " + key)
    if value.get("expected_counts") != {"images": 292, "fit_pool": 167, "dev": 42, "test": 83}:
        raise ValueError("Pilot data counts differ from the approved design")
    sources = value.get("workflow_source_hashes")
    if not isinstance(sources, dict) or len(sources) != 31:
        raise ValueError("Expected the 31 accepted workflow source fingerprints")
    for name, digest in sources.items():
        _relative(name)
        if not isinstance(digest, str) or not re.fullmatch(HEX, digest):
            raise ValueError("Invalid workflow source fingerprint")
    fits = value.get("fits")
    if not isinstance(fits, list) or len(fits) != 2:
        raise ValueError("Pilot configuration must contain exactly two fits")
    result = {}
    for item in fits:
        if set(item) != {"run_key", "configuration"}:
            raise ValueError("Pilot fit fields differ")
        cfg = item["configuration"]
        method = cfg.get("method")
        if method not in RUN_KEYS or method in result or item["run_key"] != RUN_KEYS[method]:
            raise ValueError("Pilot fit is outside the approved two run keys")
        if set(cfg) != {"stage", "dataset", "category", "method", "run_seed", "normal_train_n", "execution", "layers", method}:
            raise ValueError("Pilot effective configuration fields differ")
        for key, expected in {"stage": "B0", "dataset": "mvtec_ad", "category": "bottle", "run_seed": 17,
                              "normal_train_n": 100, "execution": EXECUTION}.items():
            if cfg[key] != expected:
                raise ValueError("Pilot effective configuration differs at " + key)
        if not item["run_key"].endswith(_digest(cfg)[:12]):
            raise ValueError("Pilot configuration fingerprint differs from its fixed run key")
        result[method] = item
    if value.get("run_keys") != [RUN_KEYS["padim"], RUN_KEYS["patchcore"]]:
        raise ValueError("Pilot run order differs")
    return result


def _semantic(files, job_id, manifest):
    """Verify byte evidence and published markers without loading NumPy or torch."""
    status_name = "run/validation_tc2_gpu/step6_job_" + job_id + "/setup_status.json"
    value = _status(_json(files[status_name]), job_id) if status_name in files else None
    snapshot = value if value is not None else {"job_id": job_id, "status": "missing", "step_6_complete": False}
    if manifest["snapshot_status"] != snapshot or manifest["partial"] is not (not snapshot["step_6_complete"]):
        raise ValueError("Archive snapshot state differs from the recorded job state")
    expected_names = {name for name in files if _role(name, job_id) in ("pilot_configuration", "slurm_log", "pilot_record", "phase_log")}
    config = _json(files[CONFIG]) if CONFIG in files else None
    fits = _pilot_config(config) if config is not None else None
    if value is None:
        if any(_role(name, job_id) in ("pilot_record", "phase_log", "cache_metadata", "published_result") for name in files):
            raise ValueError("Snapshot without a job record may contain only configuration and SLURM logs")
        return snapshot
    if value["step_6_complete"] and fits is None:
        raise ValueError("Completed pilot is missing its configuration")
    cache = value.get("cache")
    cache_identity, cache_fingerprint = None, None
    if cache is not None:
        prefix = cache["path"] + "/"
        marker_name = prefix + "COMPLETE"
        meta_name = prefix + "metadata.json"
        available = marker_name in files or meta_name in files
        if available:
            if marker_name not in files or meta_name not in files:
                raise ValueError("Cache snapshot must contain metadata and completion marker together")
            expected_names.update((marker_name, meta_name))
            complete, meta = _json(files[marker_name]), _json(files[meta_name])
            identity = meta["identity"]
            cache_identity = identity
            cache_id = _digest(identity)
            if cache["path"].split("/")[-1] != cache_id or meta.get("cache_id") != cache_id:
                raise ValueError("Cache path does not match its identity")
            if complete != {"status": "complete", "cache_id": cache_id, "metadata_sha256": _bytes_sha(files[meta_name])}:
                raise ValueError("Cache completion marker differs")
            for key, expected in {"namespace": "formal", "protocol_sha256": PROTOCOL_SHA256,
                                  "dataset": "mvtec_ad", "category": "bottle", "dtype": "float32",
                                  "format": "tc2_gpu_fp32_npy_1"}.items():
                if identity.get(key) != expected:
                    raise ValueError("Cache identity differs at " + key)
            images, index = identity["images"], meta["index"]
            paths = [row["path"] for row in images]
            if len(paths) != 292 or len(set(paths)) != 292 or [row["path"] for row in index] != paths:
                raise ValueError("Cache does not identify exactly the 292 approved images in order")
            layers = meta["layers"]
            shapes = {"layer1": [292, 64, 64, 64], "layer2": [292, 128, 32, 32], "layer3": [292, 256, 16, 16]}
            if set(layers) != set(shapes):
                raise ValueError("Cache must contain all three raw layers")
            for name, shape in shapes.items():
                if set(layers[name]) != {"dtype", "shape", "sha256"} or layers[name]["dtype"] != "float32" or layers[name]["shape"] != shape or not re.fullmatch(HEX, layers[name]["sha256"]):
                    raise ValueError("Cache layer metadata differs")
            cache_fingerprint = {"cache_id": cache_id, "metadata_sha256": complete["metadata_sha256"],
                                 "layer_hashes": {name: row["sha256"] for name, row in layers.items()}}
            if config is not None and identity.get("extraction_sources") != {name: config["workflow_source_hashes"][name] for name in CACHE_SOURCES}:
                raise ValueError("Cache extraction sources differ from the accepted workflow")
        elif value["step_6_complete"]:
            raise ValueError("Completed pilot is missing its cache metadata")
    for row in value.get("results", []):
        prefix = row["path"] + "/"
        names = {prefix + item for item in RESULT_FILES}
        available = bool(names & set(files))
        if not available:
            if value["step_6_complete"]:
                raise ValueError("Completed pilot is missing a published result")
            continue
        if not names.issubset(files):
            raise ValueError("Published result is incomplete in the snapshot")
        expected_names.update(names)
        cfg = _json(files[prefix + "config.yaml"])
        if fits is None or cfg != fits[row["method"]]["configuration"]:
            raise ValueError("Published result configuration differs from the approved pilot")
        evidence = _json(files[prefix + "evidence.json"])
        identity = evidence["identity"]
        identity_id = _digest(identity)
        if identity.get("namespace") != "formal" or identity.get("protocol_sha256") != PROTOCOL_SHA256 or identity.get("configuration") != cfg or identity_id != row["path"].split("/")[-1]:
            raise ValueError("Published result identity differs")
        source_hashes = identity.get("sources")
        if source_hashes != {name: config["workflow_source_hashes"][name] for name in SCIENCE_SOURCES}:
            raise ValueError("Published result source fingerprints differ from the accepted workflow")
        if cache_identity is None or evidence.get("cache_identity") != cache_identity or identity.get("cache") != cache_fingerprint:
            raise ValueError("Published result does not reference the exported cache metadata")
        success = _json(files[prefix + "SUCCESS"])
        if success != {"status": "passed", "namespace": "formal", "identity_sha256": identity_id,
                       "artifacts_sha256": _bytes_sha(files[prefix + "artifacts.sha256"])}:
            raise ValueError("Published result completion marker differs")
        rows = files[prefix + "artifacts.sha256"].decode("utf-8").splitlines()
        seen = set()
        for line in rows:
            parts = line.split(None, 1)
            if len(parts) != 2 or parts[1] not in ARTIFACTS or parts[1] in seen or parts[0] != _bytes_sha(files[prefix + parts[1]]):
                raise ValueError("Published result artifact fingerprint differs")
            seen.add(parts[1])
        if seen != set(ARTIFACTS):
            raise ValueError("Incomplete published result artifact manifest")
        report = _json(files[prefix + "validation.json"])
        if report != {"status": "passed", "identity_sha256": identity_id, "metric_abs_tolerance": 1e-12,
                      "prediction_dtype": "float32", "saved_metric_reproduction": True}:
            raise ValueError("Published result has not passed prediction and metric validation")
        samples = _json(files[prefix + "samples.json"])
        if set(samples) != {"fit", "dev", "test"} or any(len(samples[role]) != count for role, count in (("fit", 100), ("dev", 42), ("test", 83))) or _digest(samples) != identity.get("samples_sha256"):
            raise ValueError("Published result sample counts or fingerprints differ")
        paths = [item["path"] for role in ("fit", "dev", "test") for item in samples[role]]
        if len(set(paths)) != len(paths) or not set(paths).issubset(item["path"] for item in cache_identity["images"]):
            raise ValueError("Published result samples overlap or reference images outside its cache")
    if expected_names != set(files):
        raise ValueError("Archive contains files not referenced by its job snapshot")
    return snapshot


def _atomic_publish(source, target):
    """Publish atomically using each platform's no-replacement primitive."""
    if os.name == "nt":
        # Windows rename refuses an existing target; POSIX rename would replace it.
        os.rename(source, target)
    else:
        os.link(source, target)
        source.unlink()


def export_archive(root, job_id, archive):
    job_id = _job(job_id)
    if not Path(archive).is_absolute():
        raise ValueError("Archive path must be absolute")
    root, archive = _extended(root), _extended(archive)
    _no_links(root); _no_links(archive)
    if not root.is_dir() or not archive.parent.is_dir() or archive.exists():
        raise ValueError("Export requires an existing root and parent, and a fresh archive name")
    prefix = "run/validation_tc2_gpu/step6_job_" + job_id + "/"
    status_path = _inside(root, prefix + "setup_status.json")
    raw_status = _read_bounded(status_path, min(LIMIT, 8 * 1024 * 1024)) if status_path.is_file() else None
    status_value = _status(_json(raw_status), job_id) if raw_status is not None else None
    names, notes = set(), []
    if _inside(root, CONFIG).is_file():
        names.add(CONFIG)
    for suffix in (".out", ".err"):
        name = "run/validation_tc2_gpu/slurm-" + job_id + suffix
        if _inside(root, name).is_file():
            names.add(name)
    if status_value is not None:
        directory = status_path.parent
        for path in directory.iterdir():
            if path.name in JOB_FILES or PHASE.fullmatch(path.name):
                _no_links(path)
                if path.is_file():
                    names.add(prefix + path.name)
        if status_value.get("cache") is not None:
            cache = status_value["cache"]["path"]
            if _inside(root, cache + "/COMPLETE").is_file():
                names.update((cache + "/metadata.json", cache + "/COMPLETE"))
            else:
                notes.append("Cache is not published; feature arrays and partial directories were excluded.")
        for row in status_value.get("results", []):
            path = row["path"]
            if _inside(root, path + "/SUCCESS").is_file():
                names.update(path + "/" + item for item in RESULT_FILES)
            else:
                notes.append("Result is not published: " + row["run_key"])
    else:
        notes.append("Job record is absent; this snapshot contains only available configuration and SLURM logs.")
    if len(names) >= MAX_MEMBERS:
        raise ValueError("Too many files in the pilot snapshot")
    files, total, rows = {}, 0, []
    for name in sorted(names):
        role = _role(name, job_id)
        path = _inside(root, name)
        if not path.is_file() or path.stat().st_size > LIMIT - total:
            raise ValueError("Missing, invalid or oversized snapshot source")
        data = raw_status if name == prefix + "setup_status.json" else _read_bounded(path, LIMIT - total)
        total += len(data)
        if total > LIMIT:
            raise ValueError("Pilot snapshot exceeds the 512 MiB uncompressed limit")
        files[name] = data
        rows.append({"path": name, "size": len(data), "sha256": _bytes_sha(data), "role": role})
    snapshot = status_value if status_value is not None else {"job_id": job_id, "status": "missing", "step_6_complete": False}
    manifest = {"schema_version": "1.0", "job_id": job_id, "snapshot_status": snapshot,
                "status_source": prefix + "setup_status.json" if status_value is not None else None,
                "partial": not snapshot["step_6_complete"], "files": rows, "notes": notes,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "validation_scope": {"cache_array_bytes_downloaded": False,
                                     "prediction_arrays_loaded_locally": False,
                                     "published_artifact_bytes_verified": True}}
    _semantic(files, job_id, manifest)
    encoded = _encode(manifest)
    contents = [(MANIFEST, encoded), *files.items()]
    tar_bytes = sum(512 + ((len(data) + 511) // 512) * 512 for _, data in contents) + 1024
    tar_bytes = ((tar_bytes + 10239) // 10240) * 10240
    if tar_bytes > LIMIT:
        raise ValueError("Pilot manifest exceeds the uncompressed limit")
    temporary = archive.parent / ("." + archive.name + ".partial." + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz", format=tarfile.USTAR_FORMAT) as package:
                for name, data in contents:
                    item = tarfile.TarInfo(name)
                    item.size, item.mode = len(data), 0o600
                    package.addfile(item, io.BytesIO(data))
            stream.flush(); os.fsync(stream.fileno())
        if temporary.stat().st_size > LIMIT:
            raise ValueError("Pilot archive exceeds the 512 MiB compressed limit")
        digest = _sha(temporary)
        _atomic_publish(temporary, archive)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"archive": _plain(archive), "sha256": digest, "bytes": archive.stat().st_size,
            "job_id": job_id, "pilot_status": snapshot["status"], "partial": manifest["partial"],
            "step_6_complete": snapshot["step_6_complete"], "file_count": len(files)}


def verify_archive(archive, expected_sha, job_id, destination):
    job_id = _job(job_id)
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        raise ValueError("Expected SHA256 must contain 64 hexadecimal characters")
    archive, destination = _extended(archive), _extended(destination)
    _no_links(archive); _no_links(destination)
    if not archive.is_file() or archive.stat().st_size > LIMIT or _sha(archive) != expected_sha.upper():
        raise ValueError("Archive size or SHA256 differs")
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Extraction requires a fresh destination with an existing parent")
    files, total, observed = {}, 0, set()
    # Bound every decompressed byte, including extension headers and trailing data,
    # before tarfile interprets any attacker-controlled size or PAX metadata.
    with tempfile.TemporaryFile(dir=archive.parent) as raw:
        uncompressed = 0
        with gzip.open(archive, "rb") as compressed:
            while True:
                block = compressed.read(min(1024 * 1024, LIMIT - uncompressed + 1))
                if not block:
                    break
                uncompressed += len(block)
                if uncompressed > LIMIT:
                    raise ValueError("Archive exceeds the 512 MiB decompressed limit")
                raw.write(block)
        raw.seek(0)
        with tarfile.open(fileobj=raw, mode="r:") as package:
            for item in package:
                name = _relative(item.name)
                if name in observed or name.casefold() in {value.casefold() for value in observed}:
                    raise ValueError("Duplicate or aliased archive member")
                observed.add(name)
                if len(observed) > MAX_MEMBERS or not item.isfile() or item.size < 0 or item.size > LIMIT - total or item.pax_headers:
                    raise ValueError("Unsupported archive member or uncompressed size limit")
                if name != MANIFEST:
                    _role(name, job_id)
                total += item.size
                stream = package.extractfile(item)
                if stream is None:
                    raise ValueError("Unreadable archive member")
                data = stream.read(item.size + 1)
                if len(data) != item.size:
                    raise ValueError("Truncated or oversized archive member")
                files[name] = data
    if MANIFEST not in files:
        raise ValueError("Archive manifest is missing")
    manifest_bytes = files.pop(MANIFEST)
    manifest = _json(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0" or manifest.get("job_id") != job_id or type(manifest.get("partial")) is not bool:
        raise ValueError("Archive manifest job, format or state differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != len(files):
        raise ValueError("Archive manifest file count differs")
    listed = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256", "role"}:
            raise ValueError("Archive file record fields differ")
        name = _relative(row["path"])
        if name not in files or name in listed or row["role"] != _role(name, job_id) or type(row["size"]) is not int or row["size"] != len(files[name]) or row["sha256"] != _bytes_sha(files[name]):
            raise ValueError("Archive file record size, role or SHA256 differs")
        listed.add(name)
    if listed != set(files):
        raise ValueError("Archive manifest does not identify every member")
    status = _semantic(files, job_id, manifest)
    expected_source = "run/validation_tc2_gpu/step6_job_" + job_id + "/setup_status.json" if status["status"] != "missing" else None
    if manifest.get("status_source") != expected_source:
        raise ValueError("Archive status source differs")
    # Exclusive creation also protects a destination created during archive validation.
    destination.mkdir()
    try:
        for name, data in [(MANIFEST, manifest_bytes), *files.items()]:
            path = _inside(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
            if _sha(path) != _bytes_sha(data):
                raise ValueError("Extracted file differs from verified bytes")
    except Exception:
        # Preserve failed extraction evidence; never remove an unknown destination.
        raise
    return {"status": "verified", "destination": _plain(destination), "job_id": job_id,
            "sha256": expected_sha.upper(), "file_count": len(files), "partial": manifest["partial"],
            "pilot_status": status["status"], "step_6_complete": status["step_6_complete"],
            "cache_array_bytes_downloaded": False, "prediction_arrays_loaded_locally": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    export = actions.add_parser("export")
    export.add_argument("--root", required=True)
    export.add_argument("--job-id", required=True)
    export.add_argument("--archive", required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("--archive", required=True)
    verify.add_argument("--sha256", required=True)
    verify.add_argument("--job-id", required=True)
    verify.add_argument("--destination", required=True)
    args = parser.parse_args()
    result = export_archive(args.root, args.job_id, args.archive) if args.action == "export" else verify_archive(args.archive, args.sha256, args.job_id, args.destination)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
