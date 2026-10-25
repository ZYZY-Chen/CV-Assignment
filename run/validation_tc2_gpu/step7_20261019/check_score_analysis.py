"""Offline evidence for the new CPU analysis; never contacts TC2."""
from pathlib import Path
import importlib.util
import json
import shutil
import sys
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("score_analysis", ROOT / "scripts/analyze_scores_tc2_gpu.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
case = Path(__file__).parent / ("score_" + uuid.uuid4().hex[:6])
case.mkdir()
design = m.read(ROOT / m.DESIGN_FILE)
for name in {*design["scientific_source_hashes"], m.DESIGN_FILE, m.ANALYSIS_FILE}:
    target = case / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, target)


def records(stage):
    selected = m.load_stage(case, stage)[1]
    return [{"run_key": key, "path": "run/tc2_gpu/results/" + m.p.digest(key), "identity_sha256": m.p.digest(key)}
            for key in selected["source_run_keys"]]


def source(root, record, value):
    cfg = next(item["configuration"] for item in value["fits"] if item["run_key"] == record["run_key"])
    image = {rule: m.image_metrics([0, 0, 1, 1], [0.0, 0.1, 0.2, 0.3], [0.0, 0.1], ["good", "good", "crack", "dent"])
             for rule in m.p.RULES}
    row = {**record, "artifacts_sha256": "A" * 64, "artifact_hashes": {name: "B" * 64 for name in m.RESULT_ARTIFACTS},
           "cache_metadata": {"path": "run/tc2_gpu/feature_cache/mvtec_ad/" + cfg["category"] + "/" + "C" * 64,
                              "metadata_sha256": "D" * 64, "complete_sha256": "E" * 64}, "configuration": cfg}
    return {"source": row, "image": image, "pixel_reference": {"path": record["path"] + "/metrics.json", "sha256": "F" * 64,
            "field": "pixel", "validation_path": record["path"] + "/validation.json", "validation_sha256": "A" * 64,
            "recomputed_by_analysis": False}, "n_dev": 2, "n_good": 2, "n_anomaly": 2}


checks = []
with mock.patch.object(m, "verify_source_result", side_effect=source):
    for stage in m.STAGE_RULES:
        parent = case / ("run/tc2_gpu/summaries/" + stage)
        supplied = records(stage)
        result = m.analyze(case, stage, supplied, parent)
        directory = case / result["path"]
        assert result["status"] == "passed" and result["reuse"] == "created"
        assert result["rows"] == m.load_stage(case, stage)[1]["expected_rows"]
        assert m.verify_analysis(case, directory, stage)["status"] == "passed"
        before = {path.name: (m.sha(path), path.stat().st_mtime_ns) for path in directory.iterdir()}
        reused = m.analyze(case, stage, supplied, parent)
        assert reused["reuse"] == "skipped"
        assert before == {path.name: (m.sha(path), path.stat().st_mtime_ns) for path in directory.iterdir()}
        checks.append(stage + ": row count, five files, full verification, unchanged reuse")
        try:
            m.analyze(case, stage, supplied[:-1], parent)
            raise AssertionError("Incomplete source list was accepted")
        except ValueError:
            pass
        lock = parent / ("." + result["identity_sha256"] + ".lock")
        lock.write_text('{"owner":"unknown"}', encoding="utf-8")
        try:
            m.analyze(case, stage, supplied, parent)
            raise AssertionError("Unknown lock was ignored")
        except RuntimeError:
            assert lock.read_text() == '{"owner":"unknown"}'
        lock.unlink()
        checks.append(stage + ": missing source and unknown lock refused")
    data = m.read(directory / "analysis.json")
    data["rows"][0]["image_auroc"] = 0.0
    (directory / "analysis.json").write_text(json.dumps(data), encoding="utf-8")
    (directory / "analysis.csv").write_text(m._csv(data), encoding="utf-8", newline="\n")
    (directory / "analysis.sha256").write_text("".join(m.sha(directory / name) + "  " + name + "\n" for name in m.ANALYSIS_ARTIFACTS), encoding="utf-8")
    marker = m.read(directory / "SUCCESS")
    marker["analysis_manifest_sha256"] = m.sha(directory / "analysis.sha256")
    (directory / "SUCCESS").write_text(json.dumps(marker), encoding="utf-8")
    for recompute in (False, True):
        try:
            m.verify_analysis(case, directory, recompute=recompute)
            raise AssertionError("Resealed analysis row corruption was accepted")
        except ValueError:
            pass
    checks.append("Resealed row corruption refused with and without full recomputation")

score = m.np.asarray([0.5, 1.25, 2.0], dtype=m.np.float32)
assert abs(m.normal_dev_threshold(score) - 1.925) < 1e-12
assert m.image_metrics([0, 0, 1, 1], [0, 1, 1, 2], [0, 1], ["good", "good", "crack", "dent"])["image_auroc"] == 0.875
assert "torch" not in sys.modules
checks.append("Accepted percentile interpolation, tied metrics, and no torch import")
report = {"status": "passed", "checks": checks, "check_count": len(checks), "fixture": str(case),
          "actual_source_verifier": "Separate source check uses the accepted bottle result from job 44024",
          "transaction_source_verifier": "Mocked approved run metadata; no fit, extraction, TC2 connection, or job"}
(case / "analysis_checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
