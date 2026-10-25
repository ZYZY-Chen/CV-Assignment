"""Step-3 acceptance. core needs NumPy; full reuses the verified TC2 CPU environment."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from metric_core import binary_auroc_ap, binary_inputs, finite_scores
from tc2_gpu_provenance import current_source_sha, require_current_acceptance

PROTOCOL_HASH = current_source_sha(ROOT, "configs/tc2_gpu/protocol.json")
REFERENCE = {"cases": 0, "max_auroc_abs_error": 0.0, "max_ap_abs_error": 0.0}
OUTPUT = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def brute_metrics(y, scores):
    """Independent small-case oracle: enumerate pairs and whole thresholds."""
    y, scores = np.asarray(y), np.asarray(scores)
    positive, negative = scores[y == 1], scores[y == 0]
    auc = sum(float(p > n) + 0.5 * float(p == n) for p in positive for n in negative)
    auc /= len(positive) * len(negative)
    ap = 0.0
    previous_recall = 0.0
    for threshold in sorted(set(scores.tolist()), reverse=True):
        selected = scores >= threshold
        tp = int(y[selected].sum())
        recall = tp / len(positive)
        ap += (recall - previous_recall) * tp / int(selected.sum())
        previous_recall = recall
    return auc, ap


class CoreTests(unittest.TestCase):
    def close(self, actual, expected):
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)

    def test_complete_ties_and_permutations(self):
        for y in ([0, 1], [1, 0], [0, 0, 0, 1], [1, 0, 0, 0]):
            for chunk in (1, 2, 3, 100):
                self.close(binary_auroc_ap(y, np.ones(len(y), dtype=np.float32), chunk_size=chunk),
                           (0.5, sum(y) / len(y)))

    def test_perfect_and_reversed(self):
        self.close(binary_auroc_ap([0, 0, 1, 1], [0, 1, 2, 3]), (1, 1))
        self.close(binary_auroc_ap([0, 0, 1, 1], [3, 2, 1, 0]), (0, 5 / 12))

    def test_small_cases_against_independent_oracle(self):
        rng = np.random.default_rng(6129)
        for n in (2, 3, 7, 17, 43):
            for _ in range(15):
                y = rng.integers(0, 2, n, dtype=np.uint8)
                y[0], y[-1] = 0, 1
                scores = rng.integers(-3, 4, n).astype(np.float32)
                expected = brute_metrics(y, scores)
                for chunk in (1, 2, 7, 256):
                    self.close(binary_auroc_ap(y, scores, chunk_size=chunk), expected)

    def test_ties_across_every_chunk_boundary(self):
        scores = np.repeat(np.array([-2, 0, 1, 4], dtype=np.float32), [17, 51, 6, 43])
        y = (np.arange(scores.size) % 5 == 0).astype(np.uint8)
        expected = brute_metrics(y, scores)
        for chunk in (1, 2, 7, 16, 17, 18, 50, 51, 64, 116, 117):
            self.close(binary_auroc_ap(y, scores, chunk_size=chunk), expected)

    def test_permutation_invariance(self):
        rng = np.random.default_rng(29)
        y = rng.integers(0, 2, 101, dtype=np.uint8)
        scores = rng.integers(-5, 6, 101).astype(np.float32)
        expected = binary_auroc_ap(y, scores)
        for _ in range(10):
            idx = rng.permutation(y.size)
            self.close(binary_auroc_ap(y[idx], scores[idx], chunk_size=13), expected)

    def test_readonly_and_noncontiguous_arrays(self):
        y = np.array([0, 9, 1, 9, 0, 9, 1, 9])[::2]
        scores = np.array([-1, 9, 0, 9, 0, 9, 2, 9], dtype=np.float32)[::2]
        before_y, before_scores = y.copy(), scores.copy()
        y.flags.writeable = scores.flags.writeable = False
        self.close(binary_auroc_ap(y, scores, chunk_size=2), brute_metrics(y, scores))
        np.testing.assert_array_equal(y, before_y)
        np.testing.assert_array_equal(scores, before_scores)

    def test_near_scores_are_not_rounded_into_ties(self):
        lo = np.float32(1)
        hi = np.nextafter(lo, np.float32(2))
        self.close(binary_auroc_ap([0, 1], np.array([lo, hi])), (1, 1))

    def test_invalid_labels_scores_and_chunks(self):
        cases = [([], []), ([0, 1], [0]), ([[0, 1]], [0, 1]), ([0, 1], [[0, 1]]),
                 ([0, 2], [0, 1]), ([0, 0.5], [0, 1]), ([0, -1], [0, 1]),
                 ([0, np.nan], [0, 1]), ([0, np.inf], [0, 1]),
                 ([0, 1], [0, np.nan]), ([0, 1], [0, np.inf]),
                 ([0, 1], [0, -np.inf]), ([0, 1], [0, 1j]),
                 ([0, 1], ["0", "1"]), ([0, 0], [0, 1]), ([1, 1], [0, 1])]
        for y, scores in cases:
            with self.subTest(labels=str(y), scores=str(scores)), self.assertRaises(ValueError):
                binary_auroc_ap(y, scores)
        for chunk in (0, -1, 1.5, True, "2"):
            with self.subTest(chunk=chunk), self.assertRaises(ValueError):
                binary_auroc_ap([0, 1], [0, 1], chunk_size=chunk)

    def test_numpy_only_dependency_boundary(self):
        # Full suite loads other libraries later; core mode must never import them.
        if "evaluate" not in sys.modules:
            self.assertNotIn("torch", sys.modules)
            self.assertNotIn("sklearn", sys.modules)


def reference_check(test, y, scores, *, chunk_size=262144):
    from sklearn.metrics import roc_auc_score, average_precision_score
    expected = (roc_auc_score(y, scores), average_precision_score(y, scores))
    actual = binary_auroc_ap(y, scores, chunk_size=chunk_size)
    errors = np.abs(np.asarray(actual) - np.asarray(expected))
    REFERENCE["cases"] += 1
    REFERENCE["max_auroc_abs_error"] = max(REFERENCE["max_auroc_abs_error"], float(errors[0]))
    REFERENCE["max_ap_abs_error"] = max(REFERENCE["max_ap_abs_error"], float(errors[1]))
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)
    return expected


class ReferenceTests(unittest.TestCase):
    def test_random_and_quantized_scores(self):
        rng = np.random.default_rng(20261017)
        for n in (2, 17, 1001, 10000):
            for positive_rate in (0.01, 0.5, 0.99):
                y = (rng.random(n) < positive_rate).astype(np.uint8)
                y[0], y[-1] = 0, 1
                for scores in (rng.standard_normal(n).astype(np.float32),
                               rng.integers(-20, 21, n).astype(np.float32), np.zeros(n, dtype=np.float32)):
                    for chunk in (7, 262144):
                        reference_check(self, y, scores, chunk_size=chunk)

    def test_large_default_chunk_boundary(self):
        rng = np.random.default_rng(43)
        n = 300003
        y = (rng.random(n) < 0.013).astype(np.uint8)
        for scores in (rng.standard_normal(n).astype(np.float32),
                       rng.integers(0, 13, n).astype(np.float32), np.ones(n, dtype=np.float32)):
            reference_check(self, y, scores)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        import torch
        from PIL import Image
        import evaluate
        torch.set_num_threads(2)
        self.torch, self.Image, self.ev = torch, Image, evaluate
        self.root = OUTPUT / "synthetic_fixtures" / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=False)
        assert self.root.resolve().is_relative_to(OUTPUT.resolve())
        self.masks = {
            "logical_a.png": np.array([[255, 0], [0, 0]], dtype=np.uint8),
            "logical_b.png": np.array([[0, 0], [0, 255]], dtype=np.uint8),
            "structural.png": np.array([[0, 7], [0, 0]], dtype=np.uint8)}
        for name, array in self.masks.items():
            Image.fromarray(array).save(self.root / name)
        self.items = [
            dict(path="test/good/0.png", label=0, defect_type="good", mask_paths=[], orig_hw=(2, 4)),
            dict(path="test/logical/1.png", label=1, defect_type="logical_anomalies",
                 mask_paths=["logical_a.png", "logical_b.png"], orig_hw=(4, 2)),
            dict(path="test/structural/2.png", label=1, defect_type="structural_anomalies",
                 mask_paths=["structural.png"], orig_hw=(2, 4))]
        self.dev = [dict(path=f"dev/good/{i}.png", label=0, defect_type="", mask_paths=[], orig_hw=(2, 4)) for i in range(2)]
        self.maps = torch.tensor([[[0, 0], [0, 0]], [[0, 1], [1, 2]], [[2, 0], [0, 1]]], dtype=torch.float32)
        self.dev_maps = torch.zeros((2, 2, 2), dtype=torch.float32)
        self.scores = {r: np.array([0.2, 0.8, 0.4], dtype=np.float32) for r in evaluate.SUPPORTED_RULES}
        self.dev_scores = {r: np.array([0.0, 0.4], dtype=np.float32) for r in evaluate.SUPPORTED_RULES}
        self.ev._MASK_CACHE.clear()

    def evaluate(self, items=None, maps=None, dev=None, dev_maps=None, scores=None, dev_scores=None):
        return self.ev.evaluate_all(self.items if items is None else items, self.dev if dev is None else dev,
            self.maps if maps is None else maps, self.dev_maps if dev_maps is None else dev_maps,
            self.scores if scores is None else scores, self.dev_scores if dev_scores is None else dev_scores,
            self.root, self.torch.device("cpu"))

    def pixel_reference(self, items, maps):
        labels, scores = [], []
        for item, amap in zip(items, maps):
            h, w = item["orig_hw"]
            union = np.zeros((h, w), dtype=np.uint8)
            for path in item["mask_paths"]:
                with self.Image.open(self.root / path) as mask:
                    union |= (np.asarray(mask.resize((w, h), self.Image.Resampling.NEAREST)) > 0).astype(np.uint8)
            labels.extend(union.ravel().tolist())
            # Independent enumeration of align_corners=False bilinear interpolation.
            arr = amap.numpy()
            sh, sw = arr.shape
            for row in range(h):
                yy = max(0.0, min(sh - 1.0, (row + 0.5) * sh / h - 0.5))
                y0, y1 = int(np.floor(yy)), min(int(np.floor(yy)) + 1, sh - 1)
                wy = yy - y0
                for col in range(w):
                    xx = max(0.0, min(sw - 1.0, (col + 0.5) * sw / w - 0.5))
                    x0, x1 = int(np.floor(xx)), min(int(np.floor(xx)) + 1, sw - 1)
                    wx = xx - x0
                    scores.append((1-wy)*((1-wx)*arr[y0,x0]+wx*arr[y0,x1]) + wy*((1-wx)*arr[y1,x0]+wx*arr[y1,x1]))
        labels = np.array(labels, dtype=np.uint8)
        scores = np.array(scores, dtype=np.float32)
        return reference_check(self, labels, scores), labels

    def test_rectangles_zero_masks_union_and_full_resolution(self):
        result = self.ev.pixel_metrics(self.items, self.maps, self.root, self.torch.device("cpu"))
        expected, labels = self.pixel_reference(self.items, self.maps)
        self.assertEqual(result["n_pixels"], 24)
        self.assertEqual(result["n_positive_pixels"], 6)
        self.assertEqual(int(labels.sum()), 6)
        np.testing.assert_allclose([result["pixel_auroc"], result["pixel_ap"]], expected, rtol=0, atol=1e-12)

    def test_nearest_masks_stay_binary(self):
        mask = self.ev._get_mask(self.root / "structural.png", (3, 5))
        with self.Image.open(self.root / "structural.png") as original:
            expected = (np.asarray(original.resize((5, 3), self.Image.Resampling.NEAREST)) > 0).astype(np.uint8)
        np.testing.assert_array_equal(mask, expected)
        self.assertTrue(set(np.unique(mask)).issubset({0, 1}))

    def test_threshold_linear_and_strict_greater(self):
        threshold = self.ev.threshold_from_dev(np.array([0.0, 1.0, 2.0]))
        self.assertAlmostEqual(threshold, 1.9, places=14)
        stats = self.ev.test_threshold_stats([0, 1, 0, 1], [threshold, threshold, threshold+1, threshold+1],
                                            ["good", "a", "good", "b"], threshold)
        self.assertEqual(stats["normal_fpr"], 0.5)
        self.assertEqual(stats["anomaly_recall"], 0.5)
        self.assertEqual(stats["per_defect_recall"], {"a": 0.0, "b": 1.0})

    def test_image_helpers_match_reference_and_reject_missing_class(self):
        expected = reference_check(self, [0, 1, 1], self.scores["max"])
        self.assertAlmostEqual(self.ev.image_auroc([0, 1, 1], self.scores["max"]), expected[0], places=12)
        self.assertAlmostEqual(self.ev.image_ap([0, 1, 1], self.scores["max"]), expected[1], places=12)
        for fn in [self.ev.image_auroc, self.ev.image_ap]:
            with self.assertRaises(ValueError): fn([1, 1], [0, 1])

    def test_loco_groups_are_separate_and_include_normals(self):
        result = self.evaluate()
        self.assertEqual(set(result["groups"]), set(self.ev.LOCO_GROUPS))
        for group, index in [("logical_anomalies", 1), ("structural_anomalies", 2)]:
            entry = result["groups"][group]
            self.assertEqual((entry["n_good"], entry["n_anomaly"]), (1, 1))
            self.assertEqual(entry["pixel"]["n_pixels"], 16)
            expected = reference_check(self, [0, 1], self.scores["max"][[0, index]])
            np.testing.assert_allclose([entry["image"]["max"]["image_auroc"], entry["image"]["max"]["image_ap"]], expected, rtol=0, atol=1e-12)
            pixel, _ = self.pixel_reference([self.items[0], self.items[index]], self.maps[[0, index]])
            np.testing.assert_allclose([entry["pixel"]["pixel_auroc"], entry["pixel"]["pixel_ap"]], pixel, rtol=0, atol=1e-12)

    def test_missing_or_unknown_loco_group_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluate(items=self.items[:2], maps=self.maps[:2], scores={r:v[:2] for r,v in self.scores.items()})
        items = copy.deepcopy(self.items)
        items.append(dict(path="test/other.png", label=1, defect_type="other", mask_paths=["structural.png"], orig_hw=(2,4)))
        with self.assertRaises(ValueError):
            self.evaluate(items=items, maps=self.torch.cat([self.maps,self.maps[:1]]), scores={r:np.append(v,1) for r,v in self.scores.items()})
        items = copy.deepcopy(self.items)
        for item in items: item["path"] = "mvtec_loco/synthetic/" + item["path"]
        items[1]["defect_type"], items[2]["defect_type"] = "unknown_a", "unknown_b"
        with self.assertRaises(ValueError): self.evaluate(items=items)

    def test_ordinary_ad_has_no_loco_groups(self):
        items = copy.deepcopy(self.items)
        items[1]["defect_type"], items[2]["defect_type"] = "scratch", "crack"
        result = self.evaluate(items=items)
        self.assertNotIn("groups", result)

    def test_four_and_five_rules_and_metadata(self):
        full = self.evaluate()
        self.assertEqual(tuple(full["image"]), self.ev.SUPPORTED_RULES)
        self.assertEqual(full["metric_policy"]["version"], "tc2_gpu_tie_grouped")
        self.assertEqual(full["metric_policy"]["percentile_method"], "linear")
        old_rules = [r for r in self.ev.SUPPORTED_RULES if r != "native"]
        four = self.evaluate(scores={r:self.scores[r] for r in old_rules}, dev_scores={r:self.dev_scores[r] for r in old_rules})
        self.assertEqual(set(four["image"]), set(old_rules))
        self.assertEqual(four["pixel"], full["pixel"])
        json.dumps(full, allow_nan=False)

    def test_test_scores_cannot_change_dev_threshold(self):
        before = self.evaluate()
        changed = self.evaluate(scores={r:values*1000 for r,values in self.scores.items()})
        for rule in self.scores:
            self.assertEqual(before["image"][rule]["threshold_95pct"], changed["image"][rule]["threshold_95pct"])

    def test_evaluation_preserves_inputs_and_permutation(self):
        maps = self.maps.clone()
        before = {r:v.copy() for r,v in self.scores.items()}
        for values in self.scores.values(): values.flags.writeable = False
        result = self.evaluate()
        idx = [2, 0, 1]
        permuted = self.evaluate(items=[self.items[i] for i in idx], maps=self.maps[idx], scores={r:v[idx] for r,v in self.scores.items()})
        self.assertEqual(result, permuted)
        self.assertTrue(self.torch.equal(self.maps, maps))
        for rule in before: np.testing.assert_array_equal(before[rule], self.scores[rule])

    def test_development_integrity_and_overlap(self):
        dev = copy.deepcopy(self.dev);dev[0]["path"] = self.items[0]["path"]
        with self.assertRaises(ValueError): self.evaluate(dev=dev)
        dev = copy.deepcopy(self.dev);dev[0]["label"] = 1
        with self.assertRaises(ValueError): self.evaluate(dev=dev)
        with self.assertRaises(ValueError): self.evaluate(dev=[], dev_maps=self.dev_maps[:0])

    def test_score_rules_counts_and_nonfinite_values(self):
        cases = [{r:v[:2] for r,v in self.scores.items()},
                 {"unknown":np.zeros(3)}, {},
                 {r:np.array([0,np.nan,1]) for r in self.scores},
                 {r:np.array([0,np.inf,1]) for r in self.scores}]
        for scores in cases:
            with self.subTest(case=str(scores)), self.assertRaises(ValueError): self.evaluate(scores=scores)
        with self.assertRaises(ValueError): self.evaluate(dev_scores={"max":np.zeros(2)})
        with self.assertRaises(ValueError): self.ev.threshold_from_dev([])
        for p in [-1, 101, np.nan]:
            with self.assertRaises(ValueError): self.ev.threshold_from_dev([0,1],p)

    def test_bad_maps_and_item_metadata(self):
        for maps in [self.maps[:2], self.maps.unsqueeze(1), self.maps.to(self.torch.int64)]:
            with self.assertRaises(ValueError): self.evaluate(maps=maps)
        for bad in [float('nan'), float('inf')]:
            maps=self.maps.clone();maps[0,0,0]=bad
            with self.assertRaises(ValueError): self.evaluate(maps=maps)
        for field,value in [("orig_hw",(0,4)),("orig_hw",(2.5,4)),("label",2),
                            ("path","../escape.png"),("mask_paths",["../escape.png"])]:
            items=copy.deepcopy(self.items);items[1][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): self.evaluate(items=items)
        for index,masks in [(0,["structural.png"]),(1,[])]:
            items=copy.deepcopy(self.items);items[index]["mask_paths"]=masks
            with self.assertRaises(ValueError): self.evaluate(items=items)
        items=copy.deepcopy(self.items);items[1]["path"]=items[0]["path"]
        with self.assertRaises(ValueError): self.evaluate(items=items)
        for field in ["path","orig_hw","mask_paths","label","defect_type"]:
            items=copy.deepcopy(self.items);del items[1][field]
            with self.subTest(missing=field), self.assertRaises(ValueError): self.evaluate(items=items)


def contract(full):
    protocol = ROOT / "configs/tc2_gpu/protocol.json"
    if sha(protocol) != PROTOCOL_HASH:
        raise ValueError("Frozen protocol hash differs")
    data = json.loads(protocol.read_text(encoding="utf-8"))
    for item in data["data"]["frozen_manifests"]:
        path = (ROOT / item["path"]).resolve()
        if not path.is_relative_to(ROOT / "manifests") or sha(path) != item["file_sha256"]:
            raise ValueError("Frozen manifest hash differs")
    result = {"protocol_sha256":PROTOCOL_HASH,"frozen_manifests_verified":8,"python":sys.version,
              "numpy":np.__version__,"device":"cpu","gpu_requested":False,"slurm_job_id":os.environ.get("SLURM_JOB_ID")}
    if full:
        require_current_acceptance(ROOT, "metrics")
        if platform.system() != "Linux" or not os.environ.get("SLURM_JOB_ID", "").isdigit():
            raise RuntimeError("Full acceptance must run in a Linux SLURM compute job")
        setup = json.loads((ROOT / "configs/tc2_gpu/setup.json").read_text(encoding="utf-8"))
        if ROOT != Path(setup["remote"]["setup_root"]) or Path(sys.prefix) != Path(setup["remote"]["conda_environment_prefix"]):
            raise RuntimeError("Use the verified TC2 staging root and dedicated environment")
        if os.environ.get("SLURM_JOB_PARTITION") != setup["remote"]["partition"]:
            raise RuntimeError("Partition differs from verified setup")
        def setup_record(relative):
            primary = ROOT / "run/setup_tc2_gpu" / relative
            return primary
        previous = setup_record("last_check_all_job.txt").read_text().strip()
        if not previous.isdigit(): raise RuntimeError("Invalid step-2 job ID")
        ready = json.loads(setup_record(f"job_{previous}_all/setup_status.json").read_text())
        if not ready["step_2_complete"]: raise RuntimeError("Step 2 has not passed")
        for entry in ready["environment_export"]["files"]:
            if sha(ROOT / Path(entry["path"]).name) != entry["sha256"]:
                raise RuntimeError("Actual environment lock changed")
        versions = {name:metadata.version(name) for name in ("numpy","scikit-learn","torch","torchvision","pillow")}
        expected = {"numpy":"1.26.4","scikit-learn":"1.7.2","torch":"2.11.0+cu128","torchvision":"0.26.0+cu128","pillow":"12.3.0"}
        if versions != expected or sys.version_info[:2] != (3,10):
            raise RuntimeError("Acceptance environment differs from the approved versions")
        result["packages"] = versions
        result["step_2_job_id"] = previous
    return result


def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("core","full"),default="core")
    parser.add_argument("--output-dir",required=True,type=Path)
    args=parser.parse_args()
    OUTPUT=args.output_dir.resolve()
    allowed=(ROOT/"run/validation_tc2_gpu").resolve()
    if OUTPUT==allowed or not OUTPUT.is_relative_to(allowed): parser.error("Use a new directory strictly under run/validation_tc2_gpu")
    if OUTPUT.exists(): parser.error("Output directory already exists; use a new check ID")
    OUTPUT.mkdir(parents=True)
    status={"mode":args.mode,"step_3_complete":False,"status":"failed","checked_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        status["runtime"]=contract(args.mode=="full")
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(CoreTests)
        if args.mode=="full":
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceTests))
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(EvaluationTests))
        result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
        passed=result.wasSuccessful() and not result.skipped and (args.mode=="core" or REFERENCE["cases"]>0)
        status.update(tests_run=result.testsRun, failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
            reference=dict(REFERENCE),status="passed" if passed else "failed",
            step_3_complete=args.mode=="full" and passed)
        status["failure_details"]=[{"test":test.id(),"traceback":trace} for test,trace in result.failures+result.errors]
    except Exception as error:
        status["error"]=type(error).__name__+": "+str(error)
    status["source_hashes"]={p:sha(ROOT/p) for p in ["src/metric_core.py","src/evaluate.py","src/data.py","tests/test_metrics_tc2_gpu.py","scripts/slurm/check_tc2_gpu_metrics.sh"] if (ROOT/p).exists()}
    (OUTPUT/"setup_status.json").write_text(json.dumps(status,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(status,indent=2,allow_nan=False))
    return 0 if status["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
