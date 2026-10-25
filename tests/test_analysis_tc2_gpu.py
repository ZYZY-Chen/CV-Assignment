"""Synthetic CPU analysis checks; --full additionally requires actual Matplotlib rendering."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_results_tc2_gpu as analysis
import plot_results_tc2_gpu as plots

OUTPUT = None


def temporary(test):
    value = tempfile.TemporaryDirectory(prefix="fixture_", dir=OUTPUT)
    target = Path(value.name).resolve()
    if target.parent != OUTPUT.resolve() or not target.name.startswith("fixture_"):
        raise ValueError("Fixture cleanup must stay inside the fresh test output directory")
    test.addCleanup(value.cleanup)
    return analysis.local(target)


def synthetic_records():
    design = analysis.read(ROOT / "configs/experiments_tc2_gpu.json")
    records = []
    for position, fit in enumerate(design["fits"]):
        cfg = copy.deepcopy(fit["configuration"])
        category_index = (analysis.CATS.index(cfg["category"]) if cfg["dataset"] == "mvtec_ad" else (0 if cfg["category"] == "juice_bottle" else 1))
        seed_index = analysis.SEEDS.index(cfg["run_seed"])
        base = 0.4 + category_index * 0.06 + seed_index * 0.01 + (0.015 if cfg["method"] == "patchcore" else 0)
        defects = ("logical_anomalies", "structural_anomalies") if cfg["dataset"] == "mvtec_loco" else ("scratch", "crack")
        group_samples = {"fit": [{"path": cfg["dataset"] + "/" + cfg["category"] + "/train/%03d.png" % n, "label": 0, "defect_type": "", "mask_paths": [], "orig_hw": [8, 8]} for n in range(cfg["normal_train_n"])],
                         "dev": [{"path": cfg["dataset"] + "/" + cfg["category"] + "/dev/%03d.png" % n, "label": 0, "defect_type": "", "mask_paths": [], "orig_hw": [8, 8]} for n in range(3 + category_index)],
                         "test": [{"path": cfg["dataset"] + "/" + cfg["category"] + "/test/%03d.png" % n, "label": int(n >= 2), "defect_type": "good" if n < 2 else defects[(n - 2) // 2], "mask_paths": [], "orig_hw": [8, 8]} for n in range(6)]}
        metric = {"image": {}, "pixel": {"pixel_auroc": 0.75, "pixel_ap": base - 0.1, "n_pixels": 384, "n_positive_pixels": 16}, "metric_policy": {}}
        for rule_index, rule in enumerate(analysis.RULES):
            metric["image"][rule] = {"image_auroc": base + rule_index * 0.006, "image_ap": base + rule_index * 0.004,
                                     "threshold_95pct": 1.25, "normal_fpr": 0.5 if rule == "native" else 0.0,
                                     "anomaly_recall": 0.5, "per_defect_recall": {defect: 0.5 for defect in defects}}
        if cfg["dataset"] == "mvtec_loco":
            metric["groups"] = {name: {"n_good": 2, "n_anomaly": 2, "image": copy.deepcopy(metric["image"]),
                                                "pixel": {"pixel_auroc": 0.7 + n * 0.1, "pixel_ap": base - 0.1 + n * 0.04, "n_pixels": 256, "n_positive_pixels": 8}}
                                for n, name in enumerate(defects)}
            for name, values in metric["groups"].items():
                for image in values["image"].values():
                    image["per_defect_recall"] = {name: 0.5}
        evidence = {"method_detail": {"memory_bank_kept": 17, "embedding_channels": 384, "model_grid_hw": [64, 64]},
                    "timings": {"fit_seconds": 1.0 + position / 100, "predict_seconds": 0.2 + position / 1000},
                    "gpu_peak_allocated_bytes": 1024 ** 2 * 100, "gpu_peak_reserved_bytes": 1024 ** 2 * 128,
                    "gpu_memory_scope": "synthetic cached-model fixture", "runtime": {"gpu": "NVIDIA A40", "device": "cuda"}}
        records.append({"run_key": fit["run_key"], "identity_sha256": analysis.digest({"synthetic_test_only": fit["run_key"]}),
                        "configuration": cfg, "metrics": metric, "samples": group_samples, "evidence": evidence})
    return records


def fixture_cases(root):
    cases = []
    for number in (1, 2):
        prefix = "cases/%03d" % number
        directory = analysis.inside(root, prefix); directory.mkdir(parents=True)
        image = np.full((80, 96, 3), 155, dtype=np.uint8)
        mask = np.zeros((80, 96), dtype=np.uint8)
        if number == 2:
            mask[30:35, 45:50] = 255
        Image.fromarray(image).save(directory / "image.png")
        Image.fromarray(mask).save(directory / "mask_union.png")
        case = {"case_id": "%03d" % number, "dataset": "mvtec_ad", "category": "bottle", "defect_type": "good" if number == 1 else "scratch",
                "path": "mvtec_ad/bottle/synthetic_%03d.png" % number, "label": number - 1,
                "selection_reason": "synthetic_plot_fixture", "source_result_ids": {"padim": "A" * 64, "patchcore": "B" * 64},
                "image_path": prefix + "/image.png", "mask_path": prefix + "/mask_union.png", "maps": {},
                "scores": [{"method": method, "score_rule": rule, "score": score, "threshold": threshold, "prediction": score > threshold}
                           for method, rule, score, threshold in (("padim", "native", 1.8, 1.25), ("patchcore", "native", 1.2, 1.25), ("patchcore", "top_0.01", 0.9, 0.7))]}
        for method in ("padim", "patchcore"):
            array = np.linspace(0, 2, 256 * 256, dtype=np.float32).reshape(256, 256)
            np.save(directory / (method + "_map.npy"), array, allow_pickle=False)
            case["maps"][method] = {"path": prefix + "/" + method + "_map.npy", "display_min": 0, "display_max": 1.5}
        analysis.write(directory / "case.json", case)
        cases.append(case)
    return cases


def synthetic_context(root):
    records = synthetic_records()
    tables = analysis.aggregate_tables(records)
    points = []
    for record in records:
        cfg = record["configuration"]
        if cfg["dataset"] != "mvtec_ad" or cfg["method"] != "patchcore" or cfg["stage"] not in ("B0", "R0"):
            continue
        for rule in analysis.RULES:
            for size in ("small", "large"):
                tables["size_recall"].append({"category": cfg["category"], "method": "patchcore", "run_seed": cfg["run_seed"],
                                               "score_rule": rule, "size_group": size, "n_images": 2, "recall": 0.5})
            for item in record["samples"]["test"]:
                points.append({"category": cfg["category"], "method": "patchcore", "run_seed": cfg["run_seed"], "score_rule": rule,
                               "role": "test", "path": item["path"], "label": item["label"], "score": 0.5 + item["label"] * 0.7 + cfg["run_seed"] / 1000,
                               "threshold": 1.25})
    return {"tables": tables, "cases": fixture_cases(root), "resources": tables["resources"], "score_distributions": points,
            "provenance": {"synthetic_fixture": True, "purpose": "offline tests; no actual experimental conclusions"}}


def fixture_output(root):
    tables = analysis.aggregate_tables(synthetic_records())
    analysis.write(root / "tables.json", tables)
    (root / "tables").mkdir()
    for name, rows in tables.items():
        analysis.write_csv(root / "tables" / (name + ".csv"), rows)
    cases = fixture_cases(root)
    analysis.write(root / "cases.json", {"cases": cases})
    analysis.write(root / "source_data/F1_methods.json", {"synthetic_fixture_only": True, "not_a_rendered_figure": True})
    plot_path = "source_data/F1_methods.json"
    plot_files = {plot_path: {"sha256": analysis.sha(root / plot_path), "bytes": (root / plot_path).stat().st_size}}
    analysis.write(root / "plot_manifest.json", {"status": "passed", "synthetic_fixture_only": True, "figure_count": 1,
                                                "figures": [{"name": "synthetic_metadata_validation", "alignment_status": "not_applicable", "files": plot_files}]})
    analysis.write(root / "inputs.json", {"synthetic_fixture_only": True})
    analysis.write(root / "analysis_config.json", {"synthetic_fixture_only": True})
    identity = {"inputs_sha256": analysis.sha(root / "inputs.json"), "analysis_config_sha256": analysis.sha(root / "analysis_config.json")}
    analysis.write(root / "provenance.json", {"identity": identity, "synthetic_fixture_only": True})
    files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    (root / "artifacts.sha256").write_text("".join(analysis.sha(analysis.inside(root, name)) + "  " + name + "\n" for name in files), encoding="utf-8", newline="\n")
    analysis.write(root / "SUCCESS", {"status": "passed", "namespace": "analysis", "identity_sha256": analysis.digest(identity), "artifacts_sha256": analysis.sha(root / "artifacts.sha256")})
    return tables, cases


def case_decisions(records, *, failures=True):
    areas, decisions = {}, {}
    for record in records:
        cfg = record["configuration"]
        if cfg["run_seed"] != 17 or cfg["stage"] not in ("B0", "B0_LOCO"):
            continue
        for index, item in enumerate(record["samples"]["test"]):
            if item["label"] == 1:
                areas[item["path"]] = {"size_group": "small" if index == 2 else "large" if index == 5 else "middle"}
            for rule in ("native", "top_0.01"):
                predicted = bool(item["label"])
                if failures and index in (0, 2, 5):
                    predicted = not predicted
                decisions[(cfg["dataset"], cfg["category"], item["path"], cfg["method"], rule)] = {
                    "path": item["path"], "label": item["label"], "prediction": predicted,
                    "score": 2.0 if predicted else 0.2, "threshold": 1.25,
                    "score_rule": rule, "result_identity_sha256": record["identity_sha256"]}
    return areas, decisions


def mask_fixture(root):
    """Four tiny anomalies; the first mask union has overlap across two files."""
    base = "mvtec_ad/bottle"
    def image(relative, value):
        target = analysis.inside(root, "datasets/" + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.full((8, 8, 3), value, dtype=np.uint8)).save(target)
        return {"path": relative, "sha256": analysis.sha(target)}
    dev = [image(base + "/dev/good.png", 10)]
    fit = [image(base + "/train/good.png", 20)]
    good = [image(base + "/test/good.png", 30)]
    anomalies = []
    for number, positive in enumerate((3, 4, 8, 32), 1):
        item = image(base + "/test/a%d.png" % number, 40 + number)
        values = []
        if number == 1:
            first = np.zeros((8, 8), dtype=np.uint8); first.flat[:2] = 255
            second = np.zeros((8, 8), dtype=np.uint8); second.flat[1:3] = 255
            values = [first, second]
        else:
            array = np.zeros((8, 8), dtype=np.uint8); array.flat[:positive] = 255; values = [array]
        masks = []
        for part, array in enumerate(values, 1):
            relative = base + "/masks/a%d_%d.png" % (number, part)
            path = analysis.inside(root, "datasets/" + relative); path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(array).save(path)
            masks.append({"path": relative, "sha256": analysis.sha(path)})
        anomalies.append({**item, "label": 1, "defect_type": "scratch", "masks": masks})
    manifest = {"dataset": "mvtec_ad", "category": "bottle", "dev": dev, "fit_pool": fit, "test": {"good": good, "anomalies": anomalies}}
    analysis.write(root / "manifests/manifest_mvtec_ad_bottle.json", manifest)
    entries = dev + fit + good + anomalies
    analysis.write(root / "cache_metadata/metadata.json", {"index": [{"path": row["path"], "orig_hw": [8, 8]} for row in entries]})
    registry = {"caches": [{"dataset": "mvtec_ad", "category": "bottle", "path": "cache_metadata"}]}
    return manifest, registry


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.records = synthetic_records()
        self.tables = analysis.aggregate_tables(self.records)

    def test_sample_standard_deviation_and_single_seed_boundary(self):
        value = analysis.mean_std([1, 2, 3])
        self.assertEqual((value["mean"], value["std"], value["ddof"], value["n"]), (2, 1, 1, 3))
        self.assertIsNone(analysis.mean_std([0.5])["std"])

    def test_nonfinite_boolean_empty_statistics_are_rejected(self):
        for values in ([], [True], [float("nan")], [float("inf")], ["0.5"]):
            with self.subTest(values=values), self.assertRaises((ValueError, TypeError)):
                analysis.mean_std(values)

    def test_macro_is_six_equal_classes_within_each_seed(self):
        for macro in self.tables["baseline_macro"]:
            source = [row for row in self.tables["baseline"] if all(row[key] == macro[key] for key in ("method", "score_rule", "run_seed"))]
            self.assertEqual(len(source), 6)
            self.assertEqual(macro["n_categories"], 6)
            for metric in analysis.METRICS:
                self.assertAlmostEqual(macro[metric], sum(row[metric] for row in source) / 6, places=14)

    def test_three_seed_summary_uses_seed_macros_with_ddof_one(self):
        for summary in self.tables["baseline_summary"]:
            source = [row for row in self.tables["baseline_macro"] if row["method"] == summary["method"] and row["score_rule"] == summary["score_rule"]]
            for metric in analysis.METRICS:
                expected = np.asarray([row[metric] for row in source])
                self.assertAlmostEqual(summary[metric + "_mean"], float(expected.mean()), places=14)
                self.assertAlmostEqual(summary[metric + "_std"], float(expected.std(ddof=1)), places=14)

    def test_unequal_image_counts_do_not_reweight_category_macros(self):
        changed = copy.deepcopy(self.records)
        target = next(record for record in changed if record["configuration"]["category"] == "wood")
        target["samples"]["test"] *= 5
        self.assertEqual(analysis.aggregate_tables(changed)["baseline_macro"], self.tables["baseline_macro"])

    def test_loco_groups_and_pooled_auxiliary_are_separate_from_ad_macros(self):
        self.assertEqual(len(self.tables["loco"]), 60)
        self.assertEqual({row["group"] for row in self.tables["loco"]}, {"pooled", "logical_anomalies", "structural_anomalies"})
        self.assertEqual({row["dataset"] for row in self.tables["baseline"]}, {"mvtec_ad"})
        self.assertEqual({row["category"] for row in self.tables["baseline"]}, set(analysis.CATS))

    def test_paired_improvement_matches_the_same_result_and_reference(self):
        lookup = {(row["result_identity_sha256"], row["score_rule"]): row for row in self.tables["baseline"]}
        self.assertEqual(len(self.tables["improvement"]), 90)
        for row in self.tables["improvement"]:
            for reference in ("native", "max"):
                native = lookup[(row["result_identity_sha256"], reference)]
                for metric in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall"):
                    self.assertAlmostEqual(row["delta_" + metric + "_vs_" + reference], row[metric] - native[metric], places=14)

    def test_checkpoint_rows_do_not_create_extra_pc_comparisons(self):
        self.assertEqual(len({(row["result_identity_sha256"], row["score_rule"]) for row in self.tables["improvement"]}), 90)
        self.assertEqual(len({row["result_identity_sha256"] for row in self.tables["improvement"]}), 18)
        self.assertEqual(len(self.tables["baseline"]), 180)

    def test_single_seed_scans_do_not_gain_fabricated_deviations(self):
        rows = [row for row in self.tables["ablations"] if row["stage"] in ("H1", "H2", "C2", "F1")]
        self.assertTrue(rows)
        self.assertTrue(all(row["run_seed"] == 17 and not any(key.endswith("_std") for key in row) for row in rows))

    def test_resource_latency_uses_dev_plus_test_and_declares_estimation(self):
        originals = {record["run_key"]: record for record in self.records}
        for row in self.tables["resources"]:
            source = originals[row["run_key"]]
            count = len(source["samples"]["dev"]) + len(source["samples"]["test"])
            self.assertEqual(row["prediction_image_count"], count)
            self.assertAlmostEqual(row["predict_ms_per_image"], source["evidence"]["timings"]["predict_seconds"] * 1000 / count)
            self.assertTrue(row["model_storage_estimated"])
            self.assertIn("cached", row["prediction_scope"])

    def test_padim_storage_includes_selected_int64_dimension_indices(self):
        originals = {record["run_key"]: record for record in self.records}
        for row in self.tables["resources"]:
            if row["method"] == "padim":
                source = originals[row["run_key"]]
                dimensions = source["configuration"]["padim"]["n_dims"]
                expected = 64 * 64 * (dimensions + dimensions * dimensions) * 4 + 8 * dimensions
                self.assertEqual(row["model_tensor_bytes"], expected)

    def test_missing_duplicate_scope_and_nonfinite_table_rows_are_rejected(self):
        for mutation in ("missing", "duplicate", "nonfinite"):
            changed = copy.deepcopy(self.tables)
            if mutation == "missing": changed["baseline"].pop()
            elif mutation == "duplicate": changed["image_metrics"][1] = copy.deepcopy(changed["image_metrics"][0])
            else: changed["baseline"][0]["image_auroc"] = float("nan")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                analysis.validate_tables(changed)


class OutputAndAssetTests(unittest.TestCase):
    def setUp(self):
        self.root = temporary(self)

    def test_output_csv_json_and_completion_hashes_roundtrip(self):
        fixture_output(self.root)
        self.assertEqual(analysis.verify_output(self.root)["status"], "passed")

    def test_changed_csv_or_unmanifested_output_is_refused(self):
        fixture_output(self.root)
        path = self.root / "tables/baseline.csv"
        path.write_bytes(path.read_bytes() + b"unexpected,row\n")
        with self.assertRaises(ValueError): analysis.verify_output(self.root)

    def test_changed_payload_or_completion_marker_is_refused(self):
        fixture_output(self.root)
        path = self.root / "cases/001/image.png"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError): analysis.verify_output(self.root)

    def test_paths_reject_parent_absolute_drive_and_backslash(self):
        for name in ("../secret", "/secret", "C:/secret", "cases\\001\\image.png", "./case", "cases//image.png"):
            with self.subTest(path=name), self.assertRaises(ValueError): analysis.inside(self.root, name)
        for name in ("../secret", "/secret", "C:/secret", "cases\\001\\image.png"):
            with self.subTest(plot_path=name), self.assertRaises(ValueError): plots._inside(self.root, name)

    def test_cases_preserve_original_truth_and_fixed_development_range(self):
        cases = fixture_cases(self.root)
        self.assertEqual(plots.validate_case_assets(self.root, cases)["status"], "passed")
        text = plots.case_score_annotation(cases[0])
        self.assertIn("PaDiM native", text); self.assertIn("PatchCore native", text); self.assertIn("PatchCore top 1%", text)
        self.assertIn("same PatchCore map", text)
        incorrect = copy.deepcopy(cases[0]); incorrect["scores"][0]["prediction"] = False
        with self.assertRaises(ValueError): plots.case_score_annotation(incorrect)
        changed = copy.deepcopy(cases); changed[1]["maps"]["padim"]["display_max"] = 2
        with self.assertRaises(ValueError): plots.validate_case_assets(self.root, changed)

    def test_case_duplicate_id_wrong_shape_nonfinite_and_dtype_are_refused(self):
        cases = fixture_cases(self.root)
        changed = copy.deepcopy(cases); changed[1]["case_id"] = changed[0]["case_id"]
        with self.assertRaises(ValueError): plots.validate_case_assets(self.root, changed)
        path = analysis.inside(self.root, cases[0]["maps"]["padim"]["path"])
        for array in (np.zeros((128, 128), dtype=np.float32), np.zeros((256, 256), dtype=np.float64), np.full((256, 256), np.nan, dtype=np.float32)):
            with self.subTest(shape=array.shape, dtype=str(array.dtype)):
                np.save(path, array, allow_pickle=False)
                with self.assertRaises(ValueError): plots.validate_case_assets(self.root, cases)

    def test_truth_must_be_binary_original_resolution(self):
        cases = fixture_cases(self.root)
        target = analysis.inside(self.root, cases[0]["mask_path"])
        for array in (np.zeros((40, 48), dtype=np.uint8), np.full((80, 96), 22, dtype=np.uint8)):
            Image.fromarray(array).save(target)
            with self.assertRaises(ValueError): plots.validate_case_assets(self.root, cases)


class RuntimeAndRegistryTests(unittest.TestCase):
    def test_registry_omission_or_wrong_design_fingerprint_is_refused(self):
        for count in (0, 65, 66):
            registry = {"protocol_sha256": analysis.PROTOCOL, "expected_total_fits": 66, "expected_analysis_rows": 108,
                        "results": [{} for _ in range(count)], "design_sha256": "0" * 64, "analysis_sources": {}}
            with self.subTest(count=count), self.assertRaises(ValueError):
                analysis.validate_registry(ROOT, registry)

    def test_compute_guard_refuses_missing_allocation_or_visible_gpu(self):
        config = {"resources": {"minimum_free_bytes": 0}}
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(ValueError):
            analysis.runtime_gate(ROOT, config, "79860")
        environment = {"SLURM_JOB_ID": "79860", "CUDA_VISIBLE_DEVICES": "0"}
        with patch.dict("os.environ", environment, clear=True), self.assertRaisesRegex(ValueError, "GPU"):
            analysis.runtime_gate(ROOT, config, "79860")

    def test_json_rejects_duplicate_keys_nonfinite_constants_and_overflow(self):
        root = temporary(self)
        path = root / "input.json"
        for content in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'):
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(ValueError): analysis.read(path)
        analysis.write(path, {"valid": [1, 0.1, {"nested": True}]})
        self.assertEqual(analysis.read(path), {"valid": [1, 0.1, {"nested": True}]})

    def test_windows_reparse_attribute_and_linked_paths_are_refused(self):
        root = temporary(self)
        class Reparse:
            parents = ()
            def exists(self): return True
            def lstat(self): return SimpleNamespace(st_file_attributes=1024)
            def is_symlink(self): return False
        with patch.object(analysis, "os", SimpleNamespace(name="nt")), patch.object(analysis, "local", return_value=Reparse()), self.assertRaises(ValueError):
            analysis.inside(root, "file.json")
        with patch.object(Path, "is_symlink", return_value=True), self.assertRaises(ValueError):
            analysis.inside(root, "file.json")


class CaseSelectionAndMaskTests(unittest.TestCase):
    def test_loco_quotas_and_all_candidates_and_real_failures_are_preserved(self):
        records = synthetic_records(); areas, decisions = case_decisions(records)
        cases, summary = analysis.select_cases(records, areas, decisions)
        self.assertEqual(len(cases), 16)
        self.assertEqual(len(summary["candidates"]), 48)
        self.assertGreaterEqual(summary["real_failures_available"], 2)
        self.assertGreaterEqual(summary["real_failures_selected"], 2)
        self.assertTrue(summary["normal_false_positive_selected"])
        self.assertTrue(summary["micro_hard_case_selected"])
        for category in ("juice_bottle", "screw_bag"):
            selected = [row for row in cases if row["dataset"] == "mvtec_loco" and row["category"] == category]
            self.assertEqual(len(selected), 2)
            self.assertEqual({row["group"] for row in selected}, {"logical_anomalies", "structural_anomalies"})
        for row in summary["candidates"]:
            self.assertTrue(row["source_result_ids"])
            self.assertTrue(all("score" in value and "threshold" in value for value in row["scores"]))
            if not row["selected"]:
                self.assertTrue(row["rejection_reason"])
        repeated, repeated_summary = analysis.select_cases(records, areas, decisions)
        self.assertEqual(cases, repeated); self.assertEqual(summary, repeated_summary)

    def test_failure_free_fixture_uses_explicit_controls_without_inventing_errors(self):
        records = synthetic_records(); areas, decisions = case_decisions(records, failures=False)
        cases, summary = analysis.select_cases(records, areas, decisions)
        self.assertEqual(summary["real_failures_available"], 0)
        self.assertEqual(summary["real_failures_selected"], 0)
        self.assertTrue(all(not row["is_real_failure"] and row["selection_fallback"] for row in cases))

    def test_original_union_area_and_quartile_ties_use_all_masks(self):
        root = temporary(self); manifest, registry = mask_fixture(root)
        areas, masks = analysis.masks_and_inputs(root, registry)
        ordered = manifest["test"]["anomalies"]
        self.assertEqual([areas[row["path"]]["area_pixels"] for row in ordered], [3, 4, 8, 32])
        self.assertEqual([areas[row["path"]]["size_group"] for row in ordered], ["small", "middle", "middle", "large"])
        self.assertEqual(len(masks[ordered[0]["path"]]), 2)
        self.assertEqual(areas[ordered[0]["path"]]["area_fraction"], 3 / 64)
        mask_path = analysis.inside(root, "datasets/" + ordered[0]["masks"][0]["path"])
        mask_path.write_bytes(mask_path.read_bytes() + b" ")
        with self.assertRaises(ValueError): analysis.masks_and_inputs(root, registry)

    def test_export_preserves_original_png_and_all_masks_and_same_scoring_map(self):
        root = temporary(self); manifest, registry = mask_fixture(root)
        areas, sources = analysis.masks_and_inputs(root, registry)
        item = manifest["test"]["anomalies"][0]
        records = []
        for method, identifier in (("padim", "A" * 64), ("patchcore", "B" * 64)):
            directory = root / ("saved_" + method); directory.mkdir()
            np.savez(directory / "predictions.npz", dev_maps=np.ones((2, 256, 256), dtype=np.float32), test_maps=np.full((1, 256, 256), 2, dtype=np.float32))
            records.append({"identity_sha256": identifier, "directory": directory, "samples": {"test": [{"path": item["path"]}]}})
        cases = [{"path": item["path"], "source_result_ids": {"padim": "A" * 64, "patchcore": "B" * 64}}]
        staging = root / "selected"; staging.mkdir()
        analysis.export_cases(root, staging, records, cases, sources)
        case = cases[0]
        self.assertEqual(analysis.sha(analysis.inside(staging, case["image_path"])), item["sha256"])
        self.assertEqual(len(case["mask_sources"]), 2)
        for mask in case["mask_sources"]:
            self.assertEqual(analysis.sha(analysis.inside(staging, mask["output_path"])), mask["sha256"])
        with Image.open(analysis.inside(staging, case["mask_path"])) as image:
            self.assertEqual(int((np.asarray(image) > 0).sum()), 3)
        for method in ("padim", "patchcore"):
            self.assertTrue(case["maps"][method]["same_map_for_native_and_top_0.01"])
            self.assertEqual(case["maps"][method]["display_max"], 1.0)


class CollectionTests(unittest.TestCase):
    def test_pending_collection_and_tamper_guards_without_models(self):
        import collect_analysis_tc2_gpu as collector
        root = temporary(self)
        for name in (collector.CONFIG, collector.EXPERIMENT_CONFIG, collector.PROTOCOL, *sorted(collector.MANIFESTS)):
            path = analysis.inside(root, name); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        (root / "tmp").mkdir()
        exported = collector.export_pages(root, "79862", root / "tmp/analysis-79862-pending")
        index_path = Path(exported["index_path"])
        collector.verify_index(index_path, exported["index_sha256"], "79862")
        local = root / "downloaded"; local.mkdir()
        for page in exported["pages"]:
            collector.verify_archive(Path(exported["directory"]) / page["name"], page["sha256"], "79862", local / ("page_%03d" % page["page_number"]), index_path)
        result = collector.verify_collection(index_path, local, "79862")
        self.assertFalse(result["step_8_complete"])
        with self.assertRaises(ValueError): collector.verify_index(index_path, "0" * 64, "79862")
        with self.assertRaises(ValueError): collector.verify_index(index_path, exported["index_sha256"], "79863")
        for bad in ("datasets/bottle.png", "feature_cache/layer1.npy", "cases/017/image.png", "cases/001/other.npy"):
            with self.subTest(path=bad), self.assertRaises(ValueError): collector._output_name(bad)


class FullRenderTests(unittest.TestCase):
    def test_all_quantitative_figures_and_two_case_plate_render(self):
        root = analysis.local(OUTPUT / "full_plot_fixture")
        root.mkdir()
        context = synthetic_context(root)
        before = {path.relative_to(root).as_posix(): analysis.sha(path) for path in root.rglob("*") if path.is_file()}
        manifest = plots.render_analysis(ROOT, root, context)
        self.assertEqual(manifest["status"], "passed")
        self.assertGreaterEqual(manifest["figure_count"], 12)
        for record in manifest["figures"]:
            self.assertIn(record["alignment_status"], ("passed", "not_applicable"))
            self.assertEqual(record["dpi"], 300)
            for name, spec in record["files"].items():
                self.assertEqual(analysis.sha(analysis.inside(root, name)), spec["sha256"])
                self.assertGreater(spec["bytes"], 0)
        self.assertEqual({name: analysis.sha(analysis.inside(root, name)) for name in before}, before)
        with self.assertRaises(ValueError): plots.render_analysis(ROOT, root, context)
        self.assertNotIn("torch", sys.modules)


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--full", action="store_true", help="Require actual Matplotlib rendering; absence is a failure")
    args = parser.parse_args()
    OUTPUT = Path(args.output_dir).absolute()
    if OUTPUT.exists() or not OUTPUT.parent.is_dir():
        raise ValueError("Tests require a fresh output directory with an existing parent")
    OUTPUT.mkdir()
    classes = [StatisticsTests, OutputAndAssetTests, RuntimeAndRegistryTests, CaseSelectionAndMaskTests, CollectionTests] + ([FullRenderTests] if args.full else [])
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(value) for value in classes)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"status": "passed" if result.wasSuccessful() and not result.skipped else "failed", "created_utc": datetime.now(timezone.utc).isoformat(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "full_requested": args.full, "full_plot_render_executed": args.full, "full_plot_render_passed": args.full and result.wasSuccessful() and not result.skipped,
              "local_core_tests_passed": result.wasSuccessful(), "gpu_or_models_executed": False, "torch_imported": "torch" in sys.modules,
              "source_hashes": {name: analysis.sha(ROOT / name) for name in ("scripts/analyze_results_tc2_gpu.py", "scripts/plot_results_tc2_gpu.py", "scripts/collect_analysis_tc2_gpu.py", "tests/test_analysis_tc2_gpu.py")},
              "render_scope": "All quantitative figure groups plus two synthetic case rows" if args.full else "Core, hash, path, CSV and asset validation only; rendering awaits the required full TC2 CPU checks"}
    analysis.write(OUTPUT / "tests_summary.json", report)
    analysis.write(OUTPUT / "test_report.json", report)
    print(json.dumps(report, indent=2, allow_nan=False))
    if not result.wasSuccessful() or result.skipped or "torch" in sys.modules:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
