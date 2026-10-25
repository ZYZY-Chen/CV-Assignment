"""Independently inspect the returned synthetic acceptance without GPU execution."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import tarfile
import numpy as np
from PIL import Image

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
COURSE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS")
SOURCE = COURSE / "output/tc2_gpu_setup_20261019_131604_9dce9b4a"
SUBMITTED = COURSE / "output/tc2_gpu_setup_20261019_131140_f1662970"
AUDIT = ROOT / "run/validation_tc2_gpu/step5_20261019"
DEST = AUDIT / "accepted_job_44012"
REMOTE = SOURCE / "remote"
JOB = REMOTE / "run/validation_tc2_gpu/step5_job_44012"
sys.path.insert(0, str(ROOT / "src"))
import tc2_gpu_protocol as protocol
import tc2_gpu_runner as runner


def xp(path):
    value = str(path)
    return Path(value if value.startswith("\\\\?\\") else "\\\\?\\" + value)


def sha(path):
    return protocol.sha(xp(path))


def read(path):
    return json.loads(xp(path).read_text(encoding="utf-8"))


def archive_files(path, extracted=None):
    result = {}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            name = member.name.removeprefix("./")
            assert not member.issym() and not member.islnk(), name
            assert not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts, name
            if not member.isfile():
                continue
            assert name not in result, name
            result[name] = hashlib.sha256(archive.extractfile(member).read()).hexdigest().upper()
            if extracted is not None:
                assert sha(extracted / name) == result[name], name
    if extracted is not None:
        actual = {p.relative_to(xp(extracted)).as_posix() for p in xp(extracted).rglob("*") if p.is_file()}
        assert set(result) == actual
    return result


def ranking(labels, scores):
    """Pairwise AUROC and grouped threshold AP, independent of project metrics."""
    labels, scores = np.asarray(labels), np.asarray(scores)
    positive, negative = scores[labels == 1], scores[labels == 0]
    delta = positive[:, None] - negative[None, :]
    auc = float(((delta > 0) + 0.5 * (delta == 0)).mean())
    ap = 0.0
    for threshold in np.unique(positive):
        selected = scores >= threshold
        ap += np.count_nonzero(positive == threshold) / positive.size * float(labels[selected].mean())
    return auc, ap


def resize_map(values, shape):
    """NumPy bilinear half-pixel interpolation at the original image size."""
    height, width = shape
    y = np.maximum((np.arange(height, dtype=np.float32) + np.float32(0.5)) * np.float32(values.shape[0] / height) - np.float32(0.5), 0)
    x = np.maximum((np.arange(width, dtype=np.float32) + np.float32(0.5)) * np.float32(values.shape[1] / width) - np.float32(0.5), 0)
    y0, x0 = y.astype(int), x.astype(int)
    y1, x1 = np.minimum(y0 + 1, values.shape[0] - 1), np.minimum(x0 + 1, values.shape[1] - 1)
    wy, wx = (y - y0).astype(np.float32)[:, None], (x - x0).astype(np.float32)[None, :]
    return (1 - wy) * ((1 - wx) * values[y0[:, None], x0] + wx * values[y0[:, None], x1]) + wy * ((1 - wx) * values[y1[:, None], x0] + wx * values[y1[:, None], x1])


def independent_metrics(groups, arrays, datasets):
    labels = np.asarray([item["label"] for item in groups["test"]])
    image = {}
    for rule in protocol.RULES:
        test = arrays["test_score_" + rule].astype(np.float64)
        dev = arrays["dev_score_" + rule].astype(np.float64)
        threshold = float(np.percentile(dev, 95, method="linear"))
        predicted = test > threshold
        auc, ap = ranking(labels, test)
        defects = np.asarray([item["defect_type"] for item in groups["test"]])
        image[rule] = {"image_auroc": auc, "image_ap": ap, "threshold_95pct": threshold,
                       "normal_fpr": float(predicted[labels == 0].mean()), "anomaly_recall": float(predicted[labels == 1].mean()),
                       "per_defect_recall": {name: float(predicted[defects == name].mean()) for name in sorted(set(defects) - {"good"})}}
    scores, masks = [], []
    for item, values in zip(groups["test"], arrays["test_maps"]):
        shape = tuple(item["orig_hw"])
        scores.extend(resize_map(values, shape).ravel())
        union = np.zeros(shape, dtype=np.uint8)
        for name in item["mask_paths"]:
            with Image.open(xp(datasets / name)) as image_mask:
                assert image_mask.size == (shape[1], shape[0])
                union |= (np.asarray(image_mask) > 0).astype(np.uint8)
        masks.extend(union.ravel())
    auc, ap = ranking(masks, scores)
    return {"image": image, "pixel": {"pixel_auroc": auc, "pixel_ap": ap, "n_pixels": len(masks), "n_positive_pixels": int(np.sum(masks))},
            "metric_policy": {"version": "tc2_gpu_tie_grouped", "ties": "equal-score threshold groups", "threshold_percentile": 95.0,
                              "percentile_method": "linear", "decision": "score > threshold", "pixel_scope": "all pixels at original resolution"}}


assert not DEST.exists(), "Preserve existing verification records"
terminal = (SOURCE / "terminal.txt").read_text(encoding="utf-8-sig")
assert re.search(r"^44012\s+ca6129_wo\+\s+COMPLETED\s+0:0\s+00:01:08\s+TC2N02\s*$", terminal, re.M)
expected_archive = re.search(r"TC2_ARTIFACT_SHA256=([0-9a-f]{64})", terminal).group(1).upper()
assert sha(SOURCE / "remote-output.tar.gz") == expected_archive
files = archive_files(SOURCE / "remote-output.tar.gz", REMOTE)
assert len(files) == 421
prior = COURSE / "output/tc2_gpu_setup_20261019_100241_1978a29d/remote-output.tar.gz"
assert sha(prior) == "8CD977DF7D2EEB0E714A52B3FD30E47EB2C922F83DBD611A402BD7DF40482689"
old = archive_files(prior)
assert len(old) == 163 and all(files.get(name) == value for name, value in old.items())
status = read(JOB / "setup_status.json")
assert status["mode"] == "full" and status["status"] == "passed" and status["step_5_complete"] is True
assert status["runtime"]["slurm_job_id"] == "44012" and status["runtime"]["device"] == "cuda"
assert status["runtime"]["gpu"] == "NVIDIA A40" and status["runtime"]["acceptance_jobs"] == {"metrics": "43968", "algorithms": "43970", "setup": "43950"}
assert not status["runtime"]["tf32"] and not status["runtime"]["autocast"]
assert status["metric_regression"] == read(JOB / "metric_regression/setup_status.json")
assert status["algorithm_regression"] == read(JOB / "algorithm_regression/setup_status.json")
assert status["metric_regression"]["step_3_complete"] and status["algorithm_regression"]["step_4_complete"]
groups_to_check = [(status["metric_regression"], 24), (status["algorithm_regression"]["cpu"], 19),
                   (status["algorithm_regression"]["gpu"], 2), (status["core"], 16), (status["gpu"], 4)]
for result, expected in groups_to_check:
    assert result["tests_run"] == expected and result["failures"] == result["errors"] == result["skipped"] == 0
assert len(status["source_hashes"]) == 31 and len(status["payload_hashes"]) == 32
assert all(sha(ROOT / name) == value for name, value in status["payload_hashes"].items())
assert all(status["payload_hashes"][name] == value for name, value in status["source_hashes"].items())
with tarfile.open(SUBMITTED / "workflow-files.tar") as archive:
    bundled = {member.name.removeprefix("./"): member for member in archive.getmembers() if member.isfile()}
    assert set(bundled) == {*status["payload_hashes"], "workflow.sha256"}
    for name, value in status["payload_hashes"].items():
        assert hashlib.sha256(archive.extractfile(bundled[name]).read()).hexdigest().upper() == value
stage = REMOTE / "run/validation_tc2_gpu/workflow_stage_20261019_131140_f1662970"
rows = (stage / "workflow.sha256").read_text().splitlines()
assert {name: value.upper() for value, name in (row.split(None, 1) for row in rows)} == status["payload_hashes"]
submission = (stage / "submission_lf.sh").read_bytes()
assert b"\r" not in submission and hashlib.sha256(submission).hexdigest().upper() == status["source_hashes"]["scripts/slurm/check_tc2_gpu_workflow.sh"]
for option in (b"--gres=gpu:1", b"--cpus-per-task=2", b"--mem=8G", b"--time=00:15:00"):
    assert option in submission
assert (stage / "job_id.txt").read_text().strip() == "44012"
for name, value in (('metric_regression_job.txt', '43968'), ('algorithm_acceptance_job.txt', '43970')):
    assert (stage / name).read_text().strip() == value
assert status["runtime"]["compatibility_configuration_sha256"] in (stage / "compatibility_configuration.sha256").read_text().upper()
cache_parent = xp(JOB / "g/workflow/feature_cache/mvtec_ad/bottle")
cache = next(cache_parent.iterdir())
meta, complete = read(cache / "metadata.json"), read(cache / "COMPLETE")
assert protocol.digest(meta["identity"]) == cache.name == meta["cache_id"]
assert complete == {"status": "complete", "cache_id": cache.name, "metadata_sha256": sha(cache / "metadata.json")}
assert meta["identity"]["namespace"] == "validation" and len(meta["index"]) == 8
assert [item["path"] for item in meta["index"]] == [item["path"] for item in meta["identity"]["images"]]
datasets = JOB / "g/datasets"
for item in meta["identity"]["images"]:
    assert sha(datasets / item["path"]) == item["sha256"]
for layer, shape in protocol.SHAPES.items():
    entry = meta["layers"][layer]
    assert entry == {"dtype": "float32", "shape": [8, *shape], "sha256": sha(cache / (layer + ".npy"))}
    values = np.load(cache / (layer + ".npy"), mmap_mode="r", allow_pickle=False)
    assert values.dtype == np.float32 and values.shape == (8, *shape) and np.isfinite(values).all()
    del values
result_checks = []
for directory in sorted(xp(JOB / "g/workflow/results").iterdir()):
    if directory.name.startswith("."):
        assert (directory / "FAILED.json").exists() and not (directory / "SUCCESS").exists()
        continue
    evidence, cfg = read(directory / "evidence.json"), read(directory / "config.yaml")
    identity = evidence["identity"]
    assert protocol.digest(identity) == directory.name and identity["namespace"] == "validation"
    assert identity["configuration"] == cfg and identity["hardware"] == meta["identity"]["hardware"]
    assert identity["software"] == status["runtime"]["software"]
    assert all(status["source_hashes"][name] == value for name, value in identity["sources"].items())
    assert evidence["cache_identity"] == meta["identity"]
    assert identity["cache"] == {"cache_id": cache.name, "metadata_sha256": sha(cache / "metadata.json"), "layer_hashes": {name: value["sha256"] for name, value in meta["layers"].items()}}
    assert evidence["runtime"] == status["runtime"]
    assert evidence["warmup_iterations"] == 20 and evidence["prediction_batch_size"] == 1
    assert all(np.isfinite(value) and value >= 0 for value in evidence["timings"].values())
    method, seed = cfg["method"], cfg["run_seed"]
    seed_key = "dims_seed" if method == "padim" else "sampling_seed"
    assert cfg[method][seed_key] == seed == evidence["method_detail"][seed_key]
    groups = read(directory / "samples.json")
    assert protocol.digest(groups) == identity["samples_sha256"]
    for item in evidence["validation_manifest"]["test"]["anomalies"]:
        for mask in item["masks"]:
            assert sha(datasets / mask["path"]) == mask["sha256"]
    arrays = runner.read_predictions(directory / "predictions.npz")
    runner.validate_predictions(groups, arrays, method)
    failures = []
    artifact_rows = (directory / "artifacts.sha256").read_text().splitlines()
    assert len(artifact_rows) == len(runner.ARTIFACTS)
    assert {row.split(None, 1)[1] for row in artifact_rows} == set(runner.ARTIFACTS)
    for row in artifact_rows:
        value, name = row.split(None, 1)
        if sha(directory / name) != value:
            failures.append(name)
    corrupt = method == "padim" and seed == 29
    incomplete = method == "patchcore" and seed == 43
    assert failures == (["metrics.json"] if corrupt else [])
    if incomplete:
        assert not (directory / "SUCCESS").exists()
    else:
        assert read(directory / "SUCCESS") == {"status": "passed", "namespace": "validation", "identity_sha256": directory.name, "artifacts_sha256": sha(directory / "artifacts.sha256")}
    if corrupt:
        assert read(directory / "metrics.json") == {}
    else:
        runner.compare_metrics(read(directory / "metrics.json"), independent_metrics(groups, arrays, datasets))
    result_checks.append({"method": method, "run_seed": seed, "identity": directory.name,
                          "arrays_and_scores": "passed", "artifact_checks": "intentional_corruption_detected" if corrupt else "passed",
                          "completion_marker": "intentionally_missing" if incomplete else "present",
                          "independent_saved_metrics": "intentionally_corrupt" if corrupt else "reproduced_within_1e-12"})
assert {(item["method"], item["run_seed"]) for item in result_checks} == {(method, seed) for method in ('padim', 'patchcore') for seed in (17, 29, 43)}
assert not (ROOT / "run/tc2_gpu").exists()
report = {"status": "passed", "step_5_complete": True, "verified_at_utc": datetime.now(timezone.utc).isoformat(),
          "job_id": "44012", "scheduler_state": "COMPLETED", "exit_code": "0:0", "elapsed": "00:01:08", "node": "TC2N02",
          "source_terminal": str(SOURCE / "terminal.txt"), "terminal_sha256": sha(SOURCE / "terminal.txt"),
          "archive_sha256": expected_archive, "archive_files_verified": len(files), "prior_archive_files_preserved": len(old),
          "source_fingerprints_verified": 31, "submitted_payload_files_verified": 32, "submission_lf_verified": True,
          "runtime": status["runtime"], "metric_tests": 24, "algorithm_cpu_tests": 19, "algorithm_gpu_tests": 2,
          "workflow_core_tests": 16, "workflow_gpu_tests": 4, "failures": 0, "errors": 0, "skipped": 0,
          "synthetic_cache": {"images": 8, "layers": 3, "dtype": "float32", "status": "passed"},
          "synthetic_results": result_checks, "formal_output_directory_absent": True,
          "completion_scope": "Synthetic workflow integration only. Real-data extraction and pilots require the separately approved step 6."}
DEST.mkdir()
for name, value in (("verification.json", report), ("archive_file_hashes.json", files), ("remote_setup_status.json", status)):
    (DEST / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
for name in ('core_tests.txt', 'gpu_tests.txt', 'metric_regression.txt', 'algorithm_regression.txt'):
    (DEST / name).write_bytes((JOB / name).read_bytes())
(DEST / 'terminal.txt').write_bytes((SOURCE / 'terminal.txt').read_bytes())
print(json.dumps({key: report[key] for key in ('status', 'step_5_complete', 'job_id', 'archive_files_verified', 'prior_archive_files_preserved', 'source_fingerprints_verified', 'submitted_payload_files_verified')}, indent=2))
