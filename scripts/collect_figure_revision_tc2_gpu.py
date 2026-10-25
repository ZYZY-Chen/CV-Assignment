"""Bounded snapshots of the approved TC2 GPU figure revision only.

The collector never runs rendering, statistics, model prediction or a scheduler.
Its single archive is verified against a separately pinned index before any
destination is created. The preserved pilot collector supplies the frozen path
and raw-tar protections used by the other approved TC2 collection workflows.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_tc2_gpu_pilot import (
    _extended, _plain, _job, _relative, _no_links, _inside, _sha,
    _bytes_sha, _json as _strict_json, _encode, _digest, _read_bounded,
    _tar_layout, _atomic_publish,
)

LIMIT = 512 * 1024 * 1024
MAX_MEMBERS = 512
MAX_INDEX = 8 * 1024 * 1024
MANIFEST = "figure_revision_export_manifest.json"
RECEIPT = "page_verification.json"
HEX = r"[0-9A-F]{64}"
STAGE = "figure_revision"
SOURCES = {
    "configs/figure_revision_tc2_gpu.json",
    "scripts/revise_figures_tc2_gpu.py",
    "scripts/collect_figure_revision_tc2_gpu.py",
    "scripts/slurm/figure_revision_tc2_gpu.sh",
    "tests/test_figure_revision_tc2_gpu.py",
    "docs/TC2_GPU_FIGURE_REVISION.md",
}
TOP = {
    "plan.json", "figure_revision_config.json", "tables.json", "cases.json",
    "data_invariance.json", "verification.json", "plot_manifest.json",
    "artifacts.sha256", "SUCCESS",
}
JOB_FILES = {
    "state.json", "plan.json", "publication.json", "resources.json",
    "wrapper_status.json", "tests.stdout.txt", "tests.stderr.txt",
    "tests/test_report.json", "tests/tests_summary.json", "tests/setup_status.json",
    "tests/tests_receipt.json",
}
FIGURE_NAMES = {
    "F1_methods", "baseline_comparison", "F3_hyperparameters", "F3_components",
    "F3_fewshot", "F4_improvement", "F4_q_sensitivity",
    "F4_score_distributions", "F4_defect_size", "F5_resources", "loco_extension",
    "F2_cases_01", "F2_cases_02", "F2_cases_03", "F2_cases_04",
}
PHASE = re.compile(r"phase_[a-z0-9][a-z0-9_-]{0,63}\.(?:stdout|stderr)\.txt\Z")
PROTECTION_SHA256 = "D8D3B072A6B769D81023AC0BE0770A24C999C822B5A63869992BFF084848DAC4"


def _json(data):
    value = _strict_json(data)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Nonfinite figure-revision metadata")
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


def _hex(value):
    if not isinstance(value, str) or re.fullmatch(HEX, value) is None:
        raise ValueError("Expected an uppercase SHA256 fingerprint")
    return value


def _regular(path):
    _no_links(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Figure-revision files must be regular and have no hard-link aliases")
    return path


def _provenance():
    source = Path(__file__).with_name("collect_tc2_gpu_pilot.py")
    _no_links(source)
    if _sha(source) != PROTECTION_SHA256:
        raise ValueError("Frozen path and archive protection source differs")
    return {
        "schema_version": "1.0", "purpose": "tc2_gpu_figure_revision_collection_only",
        "collector_path": "scripts/collect_figure_revision_tc2_gpu.py",
        "collector_sha256": _sha(Path(__file__)),
        "path_protection_source_sha256": PROTECTION_SHA256,
    }


def _output_path(value):
    _relative(value)
    if re.fullmatch(r"run/tc2_gpu/summaries/figure_revision/" + HEX, value) is None:
        raise ValueError("Figure revisions require their immutable identity namespace")
    return value


def _output_name(name):
    _relative(name)
    if name in TOP:
        return True
    parts = name.split("/")
    if len(parts) == 2 and parts[0] in ("figures", "source_data", "qa"):
        suffixes = {"figures": (".png", ".pdf"), "source_data": (".json",), "qa": (".alignment.json",)}
        if any(parts[1] == figure + suffix for figure in FIGURE_NAMES for suffix in suffixes[parts[0]]):
            return True
    if re.fullmatch(r"cases/(?:00[1-9]|01[0-6])/(?:image\.png|mask_union\.png|padim_map\.npy|patchcore_map\.npy|case\.json)", name):
        return True
    if re.fullmatch(r"cases/(?:00[1-9]|01[0-6])/masks/[0-9]{3}\.png", name):
        return True
    raise ValueError("File is outside the figure-revision output whitelist: " + name)


def _role(name, job_id, output_relative):
    _relative(name)
    if name in SOURCES:
        return "revision_source"
    prefix = "run/validation_tc2_gpu/"
    if name in {prefix + "slurm-" + job_id + suffix for suffix in (".out", ".err")}:
        return "slurm_log"
    job_prefix = prefix + "step8_figure_revision_job_" + job_id + "/"
    if name.startswith(job_prefix):
        tail = name[len(job_prefix):]
        if tail in JOB_FILES:
            return "revision_record"
        if PHASE.fullmatch(tail):
            return "phase_log"
    if output_relative and name.startswith(output_relative + "/"):
        _output_name(name[len(output_relative) + 1:])
        return "published_figure_revision"
    raise ValueError("File is outside the figure-revision collection whitelist: " + name)


def _status(value, job_id):
    if not isinstance(value, dict) or value.get("job_id") != job_id:
        raise ValueError("Figure-revision state belongs to another job")
    if value.get("status") == "pending":
        if value != {"schema_version": "1.0", "job_id": job_id, "status": "pending"}:
            raise ValueError("Pending figure-revision state has unexpected fields")
        return value
    if value.get("schema_version") != "1.0" or value.get("status") not in ("running", "passed", "failed"):
        raise ValueError("Invalid figure-revision execution state")
    identity = _hex(value.get("identity"))
    output = value.get("output_relative")
    if output is None and value["status"] != "passed":
        return value
    if _output_path(output) != "run/tc2_gpu/summaries/figure_revision/" + identity:
        raise ValueError("Figure-revision state output and identity differ")
    return value


def _artifact_manifest(data):
    result, folded = {}, set()
    for line in data.decode("utf-8").splitlines():
        match = re.fullmatch(r"(" + HEX + r")  (.+)", line)
        if not match:
            raise ValueError("Malformed figure-revision artifact manifest")
        fingerprint, name = match.groups()
        _output_name(name)
        if name in ("SUCCESS", "artifacts.sha256") or name.casefold() in folded:
            raise ValueError("Repeated or reserved figure-revision artifact")
        result[name] = fingerprint
        folded.add(name.casefold())
    if not TOP - {"artifacts.sha256", "SUCCESS"} <= set(result):
        raise ValueError("Figure revision lacks required publication metadata")
    if len(result) + 2 >= MAX_MEMBERS:
        raise ValueError("Figure-revision publication exceeds the member bound")
    return result


def _verify_publication(root, output_relative, state):
    path = _inside(root, output_relative)
    declared = _artifact_manifest(_read_bounded(_regular(_inside(path, "artifacts.sha256")), MAX_INDEX))
    actual = set()
    for entry in path.rglob("*"):
        _no_links(entry)
        if entry.is_file():
            _regular(entry)
            name = entry.relative_to(path).as_posix()
            _output_name(name)
            actual.add(name)
        elif not entry.is_dir():
            raise ValueError("Unsupported figure-revision filesystem member")
    if actual != set(declared) | {"artifacts.sha256", "SUCCESS"}:
        raise ValueError("Published figure revision contains missing or undeclared files")
    for name, expected in declared.items():
        if _sha(_regular(_inside(path, name))) != expected:
            raise ValueError("A published figure-revision fingerprint differs")
    # This dependency-light verifier reads existing outputs; it does not render.
    from revise_figures_tc2_gpu import verify_output
    verify_output(path, expected_identity=state["identity"])
    return actual


def _rows(rows, job_id, output_relative):
    if not isinstance(rows, list) or not rows or len(rows) >= MAX_MEMBERS:
        raise ValueError("Invalid figure-revision collection member count")
    result, folded = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256", "role"}:
            raise ValueError("Invalid figure-revision file record")
        name = _relative(row["path"])
        if name.casefold() in folded or type(row["size"]) is not int or not 0 <= row["size"] <= LIMIT:
            raise ValueError("Duplicate, case-aliased or oversized collection artifact")
        _hex(row["sha256"])
        if row["role"] != _role(name, job_id, output_relative):
            raise ValueError("Figure-revision file role differs")
        result[name] = row
        folded.add(name.casefold())
    return result


def _tar_size(rows, manifest_bytes):
    size = sum(512 + ((row["size"] + 511) // 512) * 512 for row in rows)
    size += 512 + ((len(manifest_bytes) + 511) // 512) * 512 + 1024
    return ((size + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE


def _record(path, name, job_id, output_relative):
    _regular(path)
    if path.stat().st_size > LIMIT:
        raise ValueError("Missing or oversized figure-revision artifact")
    return {"path": name, "size": path.stat().st_size, "sha256": _sha(path),
            "role": _role(name, job_id, output_relative)}


def _check_metadata(directory, rows, state, job_id, output_relative):
    source_hashes = {name: rows[name]["sha256"] for name in SOURCES}
    if source_hashes["scripts/collect_figure_revision_tc2_gpu.py"] != _provenance()["collector_sha256"]:
        raise ValueError("Snapshot used a different revision collector")
    status_name = "run/validation_tc2_gpu/step8_figure_revision_job_" + job_id + "/state.json"
    if state["status"] == "pending":
        if status_name in rows:
            raise ValueError("Pending state unexpectedly exports a live execution state")
    elif status_name not in rows or _json(_read_bounded(_inside(directory, status_name), MAX_INDEX)) != state:
        raise ValueError("Collected execution state differs from the pinned snapshot")
    if state["status"] == "passed":
        names = _verify_publication(directory, output_relative, state)
        expected = {output_relative + "/" + name for name in names}
        actual = {name for name in rows if name.startswith(output_relative + "/")}
        if actual != expected:
            raise ValueError("Figure-revision collection omits a publication artifact")
        plan = _json(_read_bounded(_inside(directory, output_relative + "/plan.json"), MAX_INDEX))
        planned = plan.get("figure_revision_sources")
        if planned != source_hashes:
            raise ValueError("Published plan source hashes differ from the collected sources")


def _write_page(target, rows, manifest, sources):
    encoded = _encode(manifest)
    if len(rows) + 1 > MAX_MEMBERS or len(encoded) > MAX_INDEX or _tar_size(rows, encoded) > LIMIT:
        raise ValueError("Figure-revision archive exceeds its fixed bounds")
    with target.open("xb") as destination:
        with gzip.GzipFile(fileobj=destination, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as package:
                for row in rows:
                    source = sources[row["path"]]
                    if source.stat().st_size != row["size"] or _sha(source) != row["sha256"]:
                        raise ValueError("Figure-revision source changed during collection")
                    info = tarfile.TarInfo(row["path"])
                    info.size, info.mode = row["size"], 0o600
                    with source.open("rb") as stream:
                        package.addfile(info, stream)
                info = tarfile.TarInfo(MANIFEST)
                info.size, info.mode = len(encoded), 0o600
                package.addfile(info, io.BytesIO(encoded))
        destination.flush()
        os.fsync(destination.fileno())
    if target.stat().st_size > LIMIT:
        raise ValueError("Figure-revision compressed archive exceeds 512 MiB")
    for row in rows:
        if _sha(sources[row["path"]]) != row["sha256"]:
            raise ValueError("A figure-revision snapshot changed during archive creation")


def export_archive(root, job_id, destination):
    job_id = _job(job_id)
    if not Path(destination).is_absolute():
        raise ValueError("Figure-revision export destination must be absolute")
    root, destination = _extended(root), _extended(destination)
    _no_links(root)
    _no_links(destination)
    if not root.is_dir() or not destination.parent.is_dir() or destination.exists():
        raise ValueError("Figure-revision export needs an existing root and parent, and a fresh destination")
    status_name = "run/validation_tc2_gpu/step8_figure_revision_job_" + job_id + "/state.json"
    status_path = _inside(root, status_name)
    status_bytes = _read_bounded(_regular(status_path), MAX_INDEX) if status_path.is_file() else None
    state = _status(_json(status_bytes), job_id) if status_bytes is not None else {
        "schema_version": "1.0", "job_id": job_id, "status": "pending"}
    output_relative = state["output_relative"] if state["status"] == "passed" else None
    names = set(SOURCES)
    for suffix in (".out", ".err"):
        name = "run/validation_tc2_gpu/slurm-" + job_id + suffix
        if _inside(root, name).is_file():
            names.add(name)
    record_prefix = "run/validation_tc2_gpu/step8_figure_revision_job_" + job_id + "/"
    record = _inside(root, record_prefix.rstrip("/"))
    if record.is_dir():
        # Failed/running render staging is deliberately not traversed. Only
        # bounded records are eligible; partial assets never become outputs.
        for tail in JOB_FILES:
            entry = _inside(record, tail)
            if entry.is_file():
                names.add(record_prefix + tail)
        for entry in record.iterdir():
            _no_links(entry)
            if entry.is_file() and PHASE.fullmatch(entry.name):
                names.add(record_prefix + entry.name)
            elif not entry.is_file() and not entry.is_dir():
                raise ValueError("Unsupported figure-revision job record member")
    if state["status"] == "passed":
        names.update(output_relative + "/" + name for name in _verify_publication(root, output_relative, state))
        # Recheck the accepted immutable analysis and all 51 protected source
        # bytes on the exporting host. Local extraction checks their pinned
        # plan records, without requiring any scientific data to be copied.
        from revise_figures_tc2_gpu import verify_plan
        verify_plan(root, _json(_read_bounded(_inside(root, output_relative + "/plan.json"), MAX_INDEX)))
    with tempfile.TemporaryDirectory(prefix="figure-revision-snapshot-", dir=destination.parent) as temporary:
        snapshot = _extended(temporary)
        sources = {}
        total = 0
        for name in sorted(names):
            source, target = _inside(root, name), _inside(snapshot, name)
            _regular(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as copied:
                if name == status_name and status_bytes is not None:
                    copied.write(status_bytes)
                    total += len(status_bytes)
                else:
                    with source.open("rb") as original:
                        for block in iter(lambda: original.read(1024 * 1024), b""):
                            total += len(block)
                            if total > LIMIT:
                                raise ValueError("Figure-revision snapshot exceeds 512 MiB")
                            copied.write(block)
            sources[name] = target
        rows = [_record(sources[name], name, job_id, output_relative) for name in sorted(sources)]
        expected = _rows(rows, job_id, output_relative)
        _check_metadata(snapshot, expected, state, job_id, output_relative)
        provenance = _provenance()
        base = {
            "schema_version": "1.0", "stage_id": STAGE, "job_id": job_id,
            "export_id": uuid.uuid4().hex.upper(), "created_utc": datetime.now(timezone.utc).isoformat(),
            "snapshot_status": state, "snapshot_sha256": _digest(state),
            "output_relative": output_relative, "partial": state["status"] != "passed",
            "collector_provenance": provenance, "page_count": 1,
        }
        manifest = {**base, "page_number": 1, "files": rows}
        if len(_encode(manifest)) > MAX_INDEX or _tar_size(rows, _encode(manifest)) > LIMIT:
            raise ValueError("Figure-revision archive exceeds the decompressed 512 MiB bound")
        destination.mkdir()
        archive = destination / "page_001.tar.gz"
        _write_page(archive, rows, manifest, sources)
        page = {"name": "page_001.tar.gz", "page_number": 1, "sha256": _sha(archive),
                "bytes": archive.stat().st_size, "files": rows}
        index = {**base, "pages": [page], "all_artifact_paths": sorted(expected)}
        encoded = _encode(index)
        if len(encoded) > MAX_INDEX:
            raise ValueError("Figure-revision index exceeds its 8 MiB bound")
        path = destination / "index.json"
        with path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return {"job_id": job_id, "stage_id": STAGE, "index_path": _plain(path),
                "index_sha256": _sha(path), "directory": _plain(destination), "pages": [page],
                "page_count": 1, "partial": index["partial"], "stage_complete": state["status"] == "passed",
                "step_8_complete": False, "post_download_visual_review_required": True}


def _validate_index(value, job_id=None):
    if not isinstance(value, dict):
        raise ValueError("Figure-revision index must be an object")
    job_id = _job(value.get("job_id")) if job_id is None else _job(job_id)
    if value.get("schema_version") != "1.0" or value.get("job_id") != job_id or value.get("stage_id") != STAGE:
        raise ValueError("Figure-revision index identity differs")
    if re.fullmatch(r"[0-9A-F]{32}", value.get("export_id", "")) is None:
        raise ValueError("Invalid figure-revision snapshot identifier")
    if not isinstance(value.get("created_utc"), str) or not value["created_utc"]:
        raise ValueError("Figure-revision snapshot has no creation timestamp")
    state = _status(value.get("snapshot_status"), job_id)
    if value.get("snapshot_sha256") != _digest(state) or type(value.get("partial")) is not bool or value["partial"] != (state["status"] != "passed"):
        raise ValueError("Figure-revision index snapshot differs")
    if value.get("collector_provenance") != _provenance():
        raise ValueError("Figure-revision index collector fingerprint differs")
    output = value.get("output_relative")
    if output != (state.get("output_relative") if state["status"] == "passed" else None):
        raise ValueError("Incomplete figure revisions must not export publication files")
    pages = value.get("pages")
    if type(value.get("page_count")) is not int or value["page_count"] != 1 or not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Figure revision must have exactly one bounded archive")
    page = pages[0]
    if not isinstance(page, dict) or set(page) != {"name", "page_number", "sha256", "bytes", "files"}:
        raise ValueError("Invalid figure-revision archive record")
    if page.get("name") != "page_001.tar.gz" or type(page.get("page_number")) is not int or page["page_number"] != 1:
        raise ValueError("Figure-revision archive is not the canonical single page")
    _hex(page["sha256"])
    if type(page["bytes"]) is not int or not 0 < page["bytes"] <= LIMIT:
        raise ValueError("Figure-revision compressed archive exceeds its bound")
    rows = _rows(page["files"], job_id, output)
    if not SOURCES <= set(rows) or value.get("all_artifact_paths") != sorted(rows):
        raise ValueError("Figure-revision index artifact coverage differs")
    manifest = {key: item for key, item in value.items() if key not in ("pages", "all_artifact_paths")}
    manifest.update(page_number=1, files=page["files"])
    if _tar_size(page["files"], _encode(manifest)) > LIMIT:
        raise ValueError("Figure-revision indexed archive exceeds the decompressed bound")
    return value


def _index(path, job_id=None):
    path = _extended(path)
    _regular(path)
    return _validate_index(_json(_read_bounded(path, MAX_INDEX)), job_id)


def verify_index(path, expected_sha, job_id):
    path = _extended(path)
    _regular(path)
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9A-Fa-f]{64}", expected_sha) is None or _sha(path) != expected_sha.upper():
        raise ValueError("Figure-revision index SHA256 differs")
    value = _index(path, job_id)
    return {"status": "verified", "job_id": value["job_id"], "stage_id": STAGE,
            "index_sha256": _sha(path), "page_count": 1, "pages": value["pages"],
            "partial": value["partial"], "stage_complete": False, "step_8_complete": False}


def _check_manifest(manifest, index, page):
    required = {key: value for key, value in index.items() if key not in ("pages", "all_artifact_paths")}
    required.update(page_number=1, files=page["files"])
    if manifest != required:
        raise ValueError("Figure-revision archive belongs to another index or snapshot")


def verify_archive(archive, destination, index_path, page_id=1, expected_sha=None, job_id=None):
    index = _index(index_path, job_id)
    if str(page_id) != "1":
        raise ValueError("Figure revision has only page 1")
    page = index["pages"][0]
    if expected_sha is not None and (not isinstance(expected_sha, str) or expected_sha.upper() != page["sha256"]):
        raise ValueError("Figure-revision archive expected SHA256 differs")
    archive, destination = _extended(archive), _extended(destination)
    _regular(archive)
    _no_links(destination)
    if not archive.is_file() or archive.stat().st_size != page["bytes"] or _sha(archive) != page["sha256"]:
        raise ValueError("Figure-revision archive bytes or SHA256 differ")
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Figure-revision extraction requires a fresh destination")
    expected = _rows(page["files"], index["job_id"], index["output_relative"])
    with tempfile.TemporaryDirectory(prefix="figure-revision-verified-", dir=destination.parent) as temporary:
        staging = _extended(temporary)
        with tempfile.TemporaryFile(dir=archive.parent) as raw:
            length = 0
            with gzip.open(archive, "rb") as compressed:
                while True:
                    block = compressed.read(min(1024 * 1024, LIMIT - length + 1))
                    if not block:
                        break
                    length += len(block)
                    if length > LIMIT:
                        raise ValueError("Figure-revision archive exceeds the decompressed 512 MiB bound")
                    raw.write(block)
            raw.seek(0)
            _tar_layout(raw, length)
            observed, total, manifest_bytes = set(), 0, None
            with tarfile.open(fileobj=raw, mode="r:") as package:
                for item in package:
                    name = _relative(item.name)
                    if name.casefold() in observed or len(observed) >= MAX_MEMBERS or not item.isfile() or item.pax_headers or item.size < 0 or item.size > LIMIT - total:
                        raise ValueError("Duplicate, linked, extended or oversized figure-revision archive member")
                    observed.add(name.casefold())
                    total += item.size
                    stream = package.extractfile(item)
                    if stream is None:
                        raise ValueError("Unreadable figure-revision archive member")
                    if name == MANIFEST:
                        if item.size > MAX_INDEX:
                            raise ValueError("Figure-revision archive manifest is too large")
                        manifest_bytes = stream.read(item.size + 1)
                        if len(manifest_bytes) != item.size:
                            raise ValueError("Truncated figure-revision archive manifest")
                        continue
                    if name not in expected or item.size != expected[name]["size"]:
                        raise ValueError("Undeclared or differently sized figure-revision archive member")
                    target = _inside(staging, name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest, copied = hashlib.sha256(), 0
                    with target.open("xb") as output:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            copied += len(block)
                            if copied > item.size:
                                raise ValueError("Figure-revision member exceeds its declared size")
                            digest.update(block)
                            output.write(block)
                    if copied != item.size or digest.hexdigest().upper() != expected[name]["sha256"]:
                        raise ValueError("Figure-revision member fingerprint differs")
            if manifest_bytes is None or observed != {name.casefold() for name in expected} | {MANIFEST.casefold()}:
                raise ValueError("Figure-revision archive is incomplete")
            _check_manifest(_json(manifest_bytes), index, page)
            _check_metadata(staging, expected, index["snapshot_status"], index["job_id"], index["output_relative"])
            with (staging / MANIFEST).open("xb") as stream:
                stream.write(manifest_bytes)
        receipt = {"status": "verified", "job_id": index["job_id"], "stage_id": STAGE,
                   "export_id": index["export_id"], "page_number": 1,
                   "index_sha256": _sha(index_path), "archive_sha256": page["sha256"],
                   "manifest_sha256": _bytes_sha(manifest_bytes), "file_count": len(expected),
                   "collector_provenance": index["collector_provenance"],
                   "stage_complete": False, "step_8_complete": False}
        with (staging / RECEIPT).open("xb") as stream:
            stream.write(_encode(receipt))
        destination.mkdir()
        for name in [*expected, MANIFEST, RECEIPT]:
            target = _inside(destination, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_publish(_inside(staging, name), target)
    return {**receipt, "destination": _plain(destination), "partial": index["partial"],
            "remote_stage_complete": index["snapshot_status"]["status"] == "passed"}


def verify_collection(index_path, directory, job_id=None):
    index = _index(index_path, job_id)
    directory = _extended(directory)
    _no_links(directory)
    base = _inside(directory, "page_001")
    receipt = _json(_read_bounded(_regular(_inside(base, RECEIPT)), MAX_INDEX))
    page = index["pages"][0]
    required = {"status": "verified", "job_id": index["job_id"], "stage_id": STAGE,
                "export_id": index["export_id"], "page_number": 1,
                "index_sha256": _sha(index_path), "archive_sha256": page["sha256"],
                "collector_provenance": index["collector_provenance"]}
    if any(receipt.get(key) != value for key, value in required.items()):
        raise ValueError("Figure-revision collection has no matching page receipt")
    manifest_bytes = _read_bounded(_regular(_inside(base, MANIFEST)), MAX_INDEX)
    if _bytes_sha(manifest_bytes) != receipt.get("manifest_sha256"):
        raise ValueError("Verified figure-revision manifest changed")
    _check_manifest(_json(manifest_bytes), index, page)
    rows = _rows(page["files"], index["job_id"], index["output_relative"])
    observed = set()
    for path in base.rglob("*"):
        _no_links(path)
        if path.is_file():
            observed.add(path.relative_to(base).as_posix())
        elif not path.is_dir():
            raise ValueError("Unsupported extracted figure-revision filesystem member")
    if observed != set(rows) | {MANIFEST, RECEIPT}:
        raise ValueError("Figure-revision collection has missing or extra files")
    for name, row in rows.items():
        path = _inside(base, name)
        _regular(path)
        if path.stat().st_size != row["size"] or _sha(path) != row["sha256"]:
            raise ValueError("An extracted figure-revision artifact changed")
    _check_metadata(base, rows, index["snapshot_status"], index["job_id"], index["output_relative"])
    return {"status": "verified", "job_id": index["job_id"], "stage_id": STAGE,
            "index_sha256": _sha(index_path), "page_count": 1, "file_count": len(rows),
            "partial": index["partial"], "stage_complete": index["snapshot_status"]["status"] == "passed",
            "step_8_complete": False, "post_download_visual_review_required": True,
            "visual_review_performed": False, "raw_dataset_exported": False,
            "feature_cache_arrays_exported": False, "new_statistics": 0,
            "collector_provenance": index["collector_provenance"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("export")
    export.add_argument("--root", required=True)
    export.add_argument("--job-id", required=True)
    export.add_argument("--destination", "--directory", dest="destination", required=True)
    check_index = commands.add_parser("verify-index")
    for name in ("index", "sha256", "job-id"):
        check_index.add_argument("--" + name, required=True)
    verify = commands.add_parser("verify")
    for name in ("index", "archive", "destination"):
        verify.add_argument("--" + name, required=True)
    verify.add_argument("--page-id", default="1")
    verify.add_argument("--job-id")
    verify.add_argument("--sha256")
    collection = commands.add_parser("verify-collection")
    for name in ("index", "directory"):
        collection.add_argument("--" + name, required=True)
    collection.add_argument("--job-id")
    args = parser.parse_args()
    if args.action == "export":
        value = export_archive(args.root, args.job_id, args.destination)
    elif args.action == "verify-index":
        value = verify_index(args.index, args.sha256, args.job_id)
    elif args.action == "verify":
        value = verify_archive(args.archive, args.destination, args.index, args.page_id, args.sha256, args.job_id)
    else:
        value = verify_collection(args.index, args.directory, args.job_id)
    print(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
