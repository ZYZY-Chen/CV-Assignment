"""Record real-pilot evidence without modifying sources or returned artifacts."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import re
import sys
import tarfile
import numpy as np

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
COURSE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS")
SOURCE = COURSE / "output/tc2_gpu_setup_20261019_135738_92cb31b0"
SUBMITTED = COURSE / "output/tc2_gpu_setup_20261019_135139_00697660"
AUDIT = ROOT / "run/validation_tc2_gpu/step6_20261019"
DEST = AUDIT / "accepted_job_44024"
REMOTE = SOURCE / "remote"
sys.path.insert(0, str(ROOT / "src"))
import tc2_gpu_protocol as p
import tc2_gpu_runner as runner


def xp(path):
    value = str(path)
    return Path(value if value.startswith("\\\\?\\") else "\\\\?\\" + value)


def sha(path):
    return p.sha(xp(path))


def read(path):
    return p.read_json(xp(path))


def ranking(labels, scores):
    positive, negative = scores[labels == 1], scores[labels == 0]
    delta = positive[:, None] - negative[None, :]
    auc = float(((delta > 0) + 0.5 * (delta == 0)).mean())
    ap = sum(np.count_nonzero(positive == value) / positive.size * float(labels[scores >= value].mean()) for value in np.unique(positive))
    return auc, float(ap)


assert not DEST.exists(), "Preserve completed verification records"
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8-sig")
assert re.search(r"^44024\s+ca6129_pi\+\s+COMPLETED\s+0:0\s+00:02:33\s+TC2N01\s+2\s+24G", terminal, re.M)
assert "3522000K" in terminal
expected_archive = re.search(r"PILOT_EXPORT_SHA256=([0-9A-F]{64})", terminal).group(1)
assert sha(SOURCE / "pilot-output.tar.gz") == expected_archive
files, file_hashes = {}, {}
with tarfile.open(SOURCE / "pilot-output.tar.gz") as archive:
    observed = set()
    for member in archive:
        assert member.isfile() and not member.issym() and not member.islnk()
        name = member.name
        path = PurePosixPath(name)
        assert name not in observed and not path.is_absolute() and ".." not in path.parts and path.as_posix() == name
        observed.add(name)
        data = archive.extractfile(member).read()
        assert hashlib.sha256(data).hexdigest().upper() == sha(REMOTE / name)
        files[name] = data
        file_hashes[name] = sha(REMOTE / name)
manifest = json.loads(files.pop("pilot_export_manifest.json"))
assert len(files) == 41 and manifest["partial"] is False
assert {row["path"] for row in manifest["files"]} == set(files)
assert all(len(files[row["path"]]) == row["size"] and file_hashes[row["path"]] == row["sha256"] for row in manifest["files"])
spec = importlib.util.spec_from_file_location("verified_pilot_collector", ROOT / "scripts/collect_tc2_gpu_pilot.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
collector._semantic(files, "44024", manifest)
state = read(REMOTE / "run/validation_tc2_gpu/step6_job_44024/setup_status.json")
assert state["status"] == "passed" and state["step_6_complete"] is True
expected_phases = ["extract", "padim_run", "padim_verify", "patchcore_run", "patchcore_verify", "padim_reuse", "patchcore_reuse"]
assert [row["phase"] for row in state["phases"]] == expected_phases
assert [row["result"]["status"] for row in state["phases"]] == ["extracted", "completed", "passed", "completed", "passed", "skipped", "skipped"]
for fitted, reused in ((state["phases"][1], state["phases"][5]), (state["phases"][3], state["phases"][6])):
    assert all(fitted["result"][key] == reused["result"][key] for key in ("path", "identity_sha256", "namespace"))
design = read(ROOT / "configs/pilot_tc2_gpu.json")
assert all(sha(ROOT / name) == value for name, value in design["workflow_source_hashes"].items())
assert all(sha(ROOT / name) == value for name, value in state["pilot_sources"].items())
with tarfile.open(SUBMITTED / "pilot-files.tar") as archive:
    members = {item.name.removeprefix("./"): item for item in archive if item.isfile()}
    assert set(members) == {"pilot.sha256", *state["pilot_sources"]}
    for name, value in state["pilot_sources"].items():
        assert hashlib.sha256(archive.extractfile(members[name]).read()).hexdigest().upper() == value
submission_terminal = (SUBMITTED / "terminal.txt").read_text(encoding="utf-8-sig")
assert "Pilot submission directory: /home/mcaai/huajie001/ca6129_v2_setup" in submission_terminal
assert state["submission"]["source_sha256"] == state["submission"]["submitted_sha256"] == sha(ROOT / "scripts/slurm/pilot_tc2_gpu.sh")
cache = xp(REMOTE / state["cache"]["path"])
meta, complete = read(cache / "metadata.json"), read(cache / "COMPLETE")
value, manifest_sha = p.manifest(ROOT, "mvtec_ad", "bottle")
assert meta["identity"]["images"] == p.image_entries(value) and meta["identity"]["manifest_sha256"] == manifest_sha
assert len(meta["index"]) == 292
assert [row["path"] for row in meta["index"]] == [row["path"] for row in meta["identity"]["images"]]
for layer, shape in p.SHAPES.items():
    assert meta["layers"][layer]["dtype"] == "float32" and meta["layers"][layer]["shape"] == [292, *shape]
first = COURSE / "output/tc2_gpu_setup_20261019_135139_00697660/remote"
for name in ("metadata.json", "COMPLETE"):
    assert sha(cache / name) == sha(first / state["cache"]["path"] / name)
partial = COURSE / "output/tc2_gpu_setup_20261019_135352_e953f96f/remote"
checks = []
for row in state["results"]:
    directory = xp(REMOTE / row["path"])
    evidence = read(directory / "evidence.json")
    identity, cfg = evidence["identity"], evidence["identity"]["configuration"]
    assert p.digest(identity) == directory.name and identity["sources"] == p.fingerprints(ROOT)
    groups = read(directory / "samples.json")
    assert groups == runner.groups_with_sizes(value, cfg, meta["index"])
    assert row["verified"] is True and row["reuse"] == "skipped"
    arrays = runner.read_predictions(directory / "predictions.npz")
    runner.validate_predictions(groups, arrays, row["method"])
    saved = read(directory / "metrics.json")
    labels = arrays["test_labels"]
    defects = arrays["test_defect_types"]
    maximum = 0.0
    for rule in p.RULES:
        scores, dev = arrays["test_score_" + rule].astype(np.float64), arrays["dev_score_" + rule].astype(np.float64)
        auc, ap = ranking(labels, scores)
        threshold = float(np.percentile(dev, 95, method="linear"))
        predicted = scores > threshold
        independent = {"image_auroc": auc, "image_ap": ap, "threshold_95pct": threshold,
                       "normal_fpr": float(predicted[labels == 0].mean()), "anomaly_recall": float(predicted[labels == 1].mean()),
                       "per_defect_recall": {name: float(predicted[defects == name].mean()) for name in sorted(set(defects) - {"good"})}}
        runner.compare_metrics(saved["image"][rule], independent)
        for key in independent:
            expected, actual = saved["image"][rule][key], independent[key]
            maximum = max(maximum, max((abs(expected[name] - actual[name]) for name in expected), default=0.0) if isinstance(expected, dict) else abs(expected - actual))
    assert saved["pixel"]["n_pixels"] == sum(item["orig_hw"][0] * item["orig_hw"][1] for item in groups["test"]) == 67230000
    detail = evidence["method_detail"]
    if row["method"] == "padim":
        assert len(detail["dim_indices"]) == len(set(detail["dim_indices"])) == 100 and detail["dims_seed"] == 17
        for name in (*runner.ARTIFACTS, "artifacts.sha256", "SUCCESS"):
            assert sha(directory / name) == sha(partial / row["path"] / name)
    else:
        assert detail["memory_bank_full"] == 102400 and detail["memory_bank_kept"] == 5120
        assert len(detail["retained_indices"]) == len(set(detail["retained_indices"])) == 5120 and detail["sampling_seed"] == 17
    checks.append({"method": row["method"], "run_key": row["run_key"], "identity_sha256": row["identity_sha256"],
                   "sample_counts": {name: len(items) for name, items in groups.items()}, "prediction_validation": "passed",
                   "local_image_metric_max_abs_error": maximum, "image": saved["image"], "pixel": saved["pixel"],
                   "pixel_metric_reproduction_scope": "Passed full saved-result reproduction on TC2; raw masks and cache arrays are not downloaded or recomputed locally.",
                   "reuse": row["reuse"], "timings": row["timings"], "gpu_peak_allocated_bytes": row["gpu_peak_allocated_bytes"],
                   "gpu_peak_reserved_bytes": row["gpu_peak_reserved_bytes"]})
resources = read(REMOTE / "run/validation_tc2_gpu/step6_job_44024/resources.json")
assert resources["requested"] == design["resources"]
assert resources["slurm_environment"]["SLURM_MEM_PER_NODE"] == "24576" and resources["slurm_environment"]["SLURM_CPUS_PER_TASK"] == "2"
report = {"status": "passed", "step_6_complete": True, "verified_at_utc": datetime.now(timezone.utc).isoformat(),
          "job_id": "44024", "scheduler_state": "COMPLETED", "exit_code": "0:0", "node": "TC2N01", "elapsed": "00:02:33",
          "source_terminal": str(SOURCE / "terminal.txt"), "terminal_sha256": sha(SOURCE / "terminal.txt"),
          "archive_sha256": expected_archive, "archive_bytes": (SOURCE / "pilot-output.tar.gz").stat().st_size,
          "archive_payload_files_verified": 41, "archive_total_files_including_manifest": 42,
          "accepted_workflow_fingerprints_verified": 31, "submitted_pilot_files_verified": 6,
          "initial_cache_metadata_preserved": True, "earlier_padim_artifacts_preserved": True,
          "cache_images": 292, "cache_layers": 3, "cache_dtype": "float32", "cache_array_validation": "Full remote validation; local metadata/fingerprint verification only.",
          "runtime": state["runtime"], "phases": expected_phases, "results": checks,
          "accounting_max_rss": "3522000K", "child_peak_rss_kib": resources["child_peak_rss_kib"],
          "completed_fits_within_frozen_matrix": 2, "frozen_matrix_total_fits": 66,
          "completion_scope": "Bottle real-data cache and two B0 seed-17/N100 pilots only. Remaining matrix entries require their separately approved execution steps."}
DEST.mkdir()
for name, item in (("verification.json", report), ("archive_file_hashes.json", file_hashes),
                   ("remote_setup_status.json", state), ("resources.json", resources)):
    (DEST / name).write_text(json.dumps(item, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: report[key] for key in ("status", "step_6_complete", "job_id", "archive_payload_files_verified", "submitted_pilot_files_verified", "completed_fits_within_frozen_matrix")}, indent=2))
