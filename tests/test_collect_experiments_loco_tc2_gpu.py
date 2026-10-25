"""Offline LOCO collector checks; synthetic bytes never authorize experiments."""
from __future__ import annotations

import ast
import argparse
from datetime import datetime, timezone
import io
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_experiments_loco_tc2_gpu as collector
import collect_experiments_tc2_gpu as original
from tc2_gpu_provenance import current_source_sha, historical_sha

OUTPUT = None

BASE_SHA256 = "AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010"
NOTE = "pixel is pooled auxiliary output; formal LOCO metrics are separate logical/structural groups"
GROUPS = ("logical_anomalies", "structural_anomalies")
IMAGE_FIELDS = {"image_auroc", "image_ap", "threshold_95pct", "normal_fpr", "anomaly_recall", "per_defect_recall"}


def samples(dataset="mvtec_loco"):
    def item(role, number, defect, size):
        return {"path": dataset + "/synthetic/" + role + "/" + defect + "/%03d.png" % number,
                "label": int(defect not in ("good", "")), "defect_type": defect, "mask_paths": [], "orig_hw": size}
    names = GROUPS if dataset == "mvtec_loco" else ("scratch", "crack")
    return {"fit": [item("train", n, "", [2, 3]) for n in range(2)],
            "dev": [item("validation", n, "", [2, 3]) for n in range(3)],
            "test": [item("test", 0, "good", [3, 4]), item("test", 1, "good", [2, 5]),
                     *[item("test", n, names[0], [4, 4]) for n in range(2)],
                     *[item("test", n, names[1], [5, 3]) for n in range(3)]]}


def metrics_for(items, loco=True, varied=False):
    test = items["test"]
    defects = sorted({item["defect_type"] for item in test if item["label"] == 1})
    count = {name: sum(item["defect_type"] == name for item in test) for name in defects}
    n_anomaly = sum(count.values())
    rec = {name: (0.5 if name == GROUPS[0] else 2 / 3) if varied else 0.0 for name in defects}
    if varied and not loco:
        rec = {"scratch": 0.5, "crack": 2 / 3}
    image = {}
    for position, rule in enumerate(sorted(collector.RULES)):
        image[rule] = {"image_auroc": 0.6 if varied else 0.5, "image_ap": 0.5,
                       "threshold_95pct": 1.25 + position, "normal_fpr": 0.5 if varied else 0.0,
                       "anomaly_recall": sum(count[name] * rec[name] for name in defects) / n_anomaly,
                       "per_defect_recall": dict(rec)}
    def pixel(rows):
        return {"pixel_auroc": 0.5, "pixel_ap": 0.5,
                "n_pixels": sum(row["orig_hw"][0] * row["orig_hw"][1] for row in rows),
                "n_positive_pixels": sum(row["label"] == 1 for row in rows)}
    value = {"image": image, "pixel": pixel(test), "metric_policy": copy.deepcopy(collector.METRIC_POLICY)}
    if loco:
        value.update(groups={}, pixel_note=NOTE)
        n_good = sum(item["label"] == 0 for item in test)
        for group in GROUPS:
            rows = [item for item in test if item["label"] == 0 or item["defect_type"] == group]
            grouped_image = {}
            for rule, pooled in image.items():
                grouped_image[rule] = {**pooled, "image_auroc": (0.75 if group == GROUPS[0] else 0.5) if varied else 0.5,
                                       "anomaly_recall": rec[group], "per_defect_recall": {group: rec[group]}}
            value["groups"][group] = {"n_good": n_good, "n_anomaly": count[group], "image": grouped_image, "pixel": pixel(rows)}
    return value


def configuration(dataset="mvtec_loco"):
    return {"dataset": dataset, "category": "juice_bottle" if dataset == "mvtec_loco" else "cable",
            "stage": "B0_LOCO" if dataset == "mvtec_loco" else "B0", "method": "padim"}


class MetricValidationTests(unittest.TestCase):
    def setUp(self):
        self.samples = samples()
        self.cfg = configuration()
        self.metrics = metrics_for(self.samples, varied=True)

    def validate(self, metric=None, sample=None, cfg=None):
        return collector._validate_result_metrics(self.metrics if metric is None else metric,
                                                 self.cfg if cfg is None else cfg,
                                                 self.samples if sample is None else sample)

    def rejects(self, mutate):
        value = copy.deepcopy(self.metrics)
        mutate(value)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            self.validate(value)

    def test_complete_loco_schema_and_original_pixel_totals(self):
        self.validate()
        self.assertEqual(self.metrics["pixel"]["n_pixels"], 99)
        self.assertEqual(self.metrics["groups"][GROUPS[0]]["pixel"]["n_pixels"], 54)
        self.assertEqual(self.metrics["groups"][GROUPS[1]]["pixel"]["n_pixels"], 67)
        self.assertEqual(set(self.metrics["image"]["native"]), IMAGE_FIELDS)

    def test_ad_schema_remains_exactly_three_top_level_fields(self):
        sample = samples("mvtec_ad")
        value = metrics_for(sample, loco=False, varied=True)
        self.assertEqual(set(value), {"image", "pixel", "metric_policy"})
        self.validate(value, sample, configuration("mvtec_ad"))

    def test_ad_rejects_loco_only_fields(self):
        sample = samples("mvtec_ad")
        for extra in ("groups", "pixel_note"):
            with self.subTest(field=extra):
                value = metrics_for(sample, loco=False)
                value[extra] = {} if extra == "groups" else NOTE
                with self.assertRaises(ValueError):
                    self.validate(value, sample, configuration("mvtec_ad"))

    def test_loco_requires_groups_and_exact_pixel_note(self):
        for field in ("groups", "pixel_note"):
            with self.subTest(field=field):
                self.rejects(lambda value: value.pop(field))
        for bad in ("", "pooled is the formal metric", None, 3):
            with self.subTest(note=bad):
                self.rejects(lambda value: value.__setitem__("pixel_note", bad))

    def test_missing_extra_and_renamed_groups_are_refused(self):
        self.rejects(lambda value: value["groups"].pop(GROUPS[0]))
        self.rejects(lambda value: value["groups"].__setitem__("unexpected", copy.deepcopy(value["groups"][GROUPS[0]])))
        self.rejects(lambda value: value["groups"].__setitem__("logical", value["groups"].pop(GROUPS[0])))

    def test_group_objects_require_exact_fields(self):
        for field in ("n_good", "n_anomaly", "image", "pixel"):
            with self.subTest(field=field):
                self.rejects(lambda value: value["groups"][GROUPS[0]].pop(field))
        self.rejects(lambda value: value["groups"][GROUPS[0]].__setitem__("extra", True))

    def test_group_sample_counts_must_be_exact_nonboolean_integers(self):
        for field in ("n_good", "n_anomaly"):
            for bad in (-1, 0, 1, 2.0, True, "2", None):
                with self.subTest(field=field, bad=bad):
                    self.rejects(lambda value: value["groups"][GROUPS[0]].__setitem__(field, bad))

    def test_loco_samples_require_both_anomaly_groups_and_good_images(self):
        for defect in ("good", *GROUPS):
            with self.subTest(removed=defect):
                changed = copy.deepcopy(self.samples)
                changed["test"] = [row for row in changed["test"] if row["defect_type"] != defect]
                with self.assertRaises((ValueError, KeyError)):
                    self.validate(sample=changed)

    def test_sample_label_and_defect_disagreement_is_refused(self):
        for position, field, bad in ((0, "label", 1), (2, "label", 0), (2, "defect_type", "other"), (0, "label", True)):
            with self.subTest(position=position, field=field):
                changed = copy.deepcopy(self.samples)
                changed["test"][position][field] = bad
                with self.assertRaises((ValueError, KeyError)):
                    self.validate(sample=changed)

    def test_all_five_image_rules_are_required_pooled_and_grouped(self):
        for group in (None, *GROUPS):
            with self.subTest(group=group):
                self.rejects(lambda value: (value["image"] if group is None else value["groups"][group]["image"]).pop("native"))
                self.rejects(lambda value: (value["image"] if group is None else value["groups"][group]["image"]).__setitem__("top_0.02", copy.deepcopy(value["image"]["max"])))

    def test_metric_policy_is_exact(self):
        for name in self.metrics["metric_policy"]:
            with self.subTest(field=name):
                self.rejects(lambda value: value["metric_policy"].pop(name))
        self.rejects(lambda value: value["metric_policy"].__setitem__("decision", "score >= threshold"))
        self.rejects(lambda value: value["metric_policy"].__setitem__("extra", True))

    def test_image_metric_fields_are_exact(self):
        for field in IMAGE_FIELDS:
            with self.subTest(field=field):
                self.rejects(lambda value: value["image"]["native"].pop(field))
        self.rejects(lambda value: value["image"]["native"].__setitem__("n_images", 7))

    def test_nonfinite_boolean_and_string_image_metrics_are_refused(self):
        for field in IMAGE_FIELDS - {"per_defect_recall"}:
            for bad in (float("nan"), float("inf"), float("-inf"), True, "0.5", None):
                with self.subTest(field=field, bad=repr(bad)):
                    self.rejects(lambda value: value["image"]["native"].__setitem__(field, bad))

    def test_probability_metrics_require_unit_interval(self):
        for field in ("image_auroc", "image_ap", "normal_fpr", "anomaly_recall"):
            for bad in (-0.01, 1.01):
                with self.subTest(field=field, bad=bad):
                    self.rejects(lambda value: value["image"]["native"].__setitem__(field, bad))

    def test_frozen_auroc_ap_endpoint_roundoff_is_preserved(self):
        for boundary in (-2.220446049250313e-16, 1.0000000000000002):
            with self.subTest(boundary=boundary):
                value = metrics_for(self.samples)
                for entry in [value, *value["groups"].values()]:
                    for metric in entry["image"].values():
                        metric["image_auroc"] = boundary
                        metric["image_ap"] = boundary
                    entry["pixel"]["pixel_auroc"] = boundary
                    entry["pixel"]["pixel_ap"] = boundary
                self.validate(value)

    def test_auroc_ap_values_beyond_frozen_roundoff_tolerance_are_refused(self):
        for bad in (-2e-12, 1 + 2e-12):
            for field in ("image_auroc", "image_ap"):
                with self.subTest(bad=bad, field=field):
                    self.rejects(lambda value: value["image"]["native"].__setitem__(field, bad))
            for field in ("pixel_auroc", "pixel_ap"):
                with self.subTest(bad=bad, field=field):
                    self.rejects(lambda value: value["pixel"].__setitem__(field, bad))

    def test_rate_and_recall_ranges_do_not_use_auroc_ap_roundoff_tolerance(self):
        for field in ("normal_fpr", "anomaly_recall"):
            with self.subTest(field=field):
                self.rejects(lambda value: value["image"]["native"].__setitem__(field, 1.0000000000000002))
        self.rejects(lambda value: value["image"]["native"]["per_defect_recall"].__setitem__(GROUPS[0], 1.0000000000000002))

    def test_unbounded_json_integer_metrics_are_refused_cleanly(self):
        for field in ("image_auroc", "threshold_95pct"):
            with self.subTest(field=field):
                self.rejects(lambda value: value["image"]["native"].__setitem__(field, 10 ** 1000))

    def test_group_image_metrics_also_require_finite_numeric_values(self):
        for bad in (float("nan"), float("inf"), True, "0.75", -0.1, 1.1):
            with self.subTest(bad=repr(bad)):
                self.rejects(lambda value: value["groups"][GROUPS[0]]["image"]["max"].__setitem__("image_auroc", bad))

    def test_per_defect_recall_keys_and_values_are_exact(self):
        self.rejects(lambda value: value["image"]["native"]["per_defect_recall"].pop(GROUPS[1]))
        self.rejects(lambda value: value["image"]["native"]["per_defect_recall"].__setitem__("other", 0.5))
        self.rejects(lambda value: value["groups"][GROUPS[0]]["image"]["native"]["per_defect_recall"].__setitem__(GROUPS[1], 0.5))
        for bad in (float("nan"), True, "0.5", -0.1, 1.1):
            with self.subTest(bad=repr(bad)):
                self.rejects(lambda value: value["image"]["native"]["per_defect_recall"].__setitem__(GROUPS[0], bad))

    def test_rates_must_correspond_to_integer_sample_counts(self):
        self.rejects(lambda value: value["image"]["native"].__setitem__("normal_fpr", 0.1))
        self.rejects(lambda value: value["image"]["native"].__setitem__("anomaly_recall", 0.1))
        self.rejects(lambda value: value["image"]["native"]["per_defect_recall"].__setitem__(GROUPS[0], 0.1))

    def test_pooled_recall_matches_weighted_per_defect_recall(self):
        self.rejects(lambda value: value["image"]["native"].__setitem__("anomaly_recall", 0.4))

    def test_group_thresholds_and_normal_false_positive_rates_match_pooled(self):
        for field, bad in (("threshold_95pct", 99.0), ("normal_fpr", 1.0)):
            with self.subTest(field=field):
                self.rejects(lambda value: value["groups"][GROUPS[0]]["image"]["native"].__setitem__(field, bad))

    def test_group_recall_matches_the_pooled_per_defect_value(self):
        def mutate(value):
            group = value["groups"][GROUPS[0]]["image"]["native"]
            group["anomaly_recall"] = 1.0
            group["per_defect_recall"][GROUPS[0]] = 1.0
        self.rejects(mutate)

    def test_pooled_auroc_matches_weighted_group_auroc(self):
        self.rejects(lambda value: value["image"]["native"].__setitem__("image_auroc", 0.9))

    def test_pixel_fields_are_exact_for_pooled_and_groups(self):
        for group in (None, *GROUPS):
            with self.subTest(group=group):
                self.rejects(lambda value: (value["pixel"] if group is None else value["groups"][group]["pixel"]).pop("n_positive_pixels"))
                self.rejects(lambda value: (value["pixel"] if group is None else value["groups"][group]["pixel"]).__setitem__("resized", True))

    def test_pixel_counts_follow_original_dimensions_and_group_membership(self):
        for group in (None, *GROUPS):
            with self.subTest(group=group):
                self.rejects(lambda value: (value["pixel"] if group is None else value["groups"][group]["pixel"]).__setitem__("n_pixels", 256 * 256 * 7))

    def test_pixel_count_types_and_ranges_are_strict(self):
        for field in ("n_pixels", "n_positive_pixels"):
            for bad in (True, 1.0, "1", None, -1, 0, 10000):
                with self.subTest(field=field, bad=bad):
                    self.rejects(lambda value: value["pixel"].__setitem__(field, bad))

    def test_pixel_probability_values_are_finite_nonboolean_unit_values(self):
        for field in ("pixel_auroc", "pixel_ap"):
            for bad in (float("nan"), float("inf"), True, "0.5", -0.1, 1.1):
                with self.subTest(field=field, bad=repr(bad)):
                    self.rejects(lambda value: value["pixel"].__setitem__(field, bad))

    def test_group_positive_pixels_cannot_exceed_group_anomaly_pixels(self):
        self.rejects(lambda value: value["groups"][GROUPS[0]]["pixel"].__setitem__("n_positive_pixels", 33))

    def test_pooled_positive_pixels_are_sum_of_two_anomaly_groups(self):
        self.rejects(lambda value: value["pixel"].__setitem__("n_positive_pixels", 6))

    def test_invalid_original_dimensions_are_refused(self):
        for bad in ([0, 3], [-1, 3], [True, 3], [2.0, 3], [2], "2x3"):
            with self.subTest(size=bad):
                changed = copy.deepcopy(self.samples)
                changed["test"][0]["orig_hw"] = bad
                with self.assertRaises((ValueError, TypeError, KeyError)):
                    self.validate(sample=changed)


class FrozenDerivationTests(unittest.TestCase):
    def test_historical_and_current_collector_fingerprints_are_separate(self):
        self.assertEqual(historical_sha(ROOT, "scripts/collect_experiments_tc2_gpu.py"), BASE_SHA256)
        actual = current_source_sha(ROOT, "scripts/collect_experiments_tc2_gpu.py")
        self.assertEqual(collector.BASE_COLLECTOR_SHA256, actual)
        self.assertNotEqual(actual, BASE_SHA256)

    def test_security_bounds_and_whitelists_are_preserved(self):
        for name in ("LIMIT", "MAX_PAGES", "MAX_MEMBERS", "MAX_INDEX", "ARTIFACTS", "RESULT_FILES", "MANIFESTS", "SCIENCE_SOURCES", "CACHE_SOURCES"):
            with self.subTest(name=name):
                self.assertEqual(getattr(collector, name), getattr(original, name))

    def test_provenance_binds_actual_derivative_and_preserved_source_bytes(self):
        provenance = collector._collection_provenance()
        self.assertEqual(provenance["base_collector_sha256"], current_source_sha(ROOT, "scripts/collect_experiments_tc2_gpu.py"))
        expected = hashlib.sha256((ROOT / "scripts/collect_experiments_loco_tc2_gpu.py").read_bytes()).hexdigest().upper()
        self.assertEqual(provenance["collector_sha256"], expected)
        self.assertEqual(provenance["purpose"], "B0_LOCO_collection_only")

    def test_semantic_change_is_limited_to_dataset_conditioned_metric_validation(self):
        def semantic_source(path):
            source = path.read_text(encoding="utf-8")
            function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == "_semantic")
            return ast.get_source_segment(source, function)
        before = semantic_source(ROOT / "scripts/collect_experiments_tc2_gpu.py")
        after = semantic_source(ROOT / "scripts/collect_experiments_loco_tc2_gpu.py")
        start = before.index('        if set(metrics) != ')
        end = before.index('    analysis_records = ', start)
        expected = before[:start] + '        _validate_result_metrics(metrics, cfg, samples)\n' + before[end:]
        self.assertEqual(ast.dump(ast.parse(after), include_attributes=False), ast.dump(ast.parse(expected), include_attributes=False))

    def test_core_path_hash_runtime_and_final_chain_checks_are_unchanged(self):
        def definitions(path):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        before = definitions(ROOT / "scripts/collect_experiments_tc2_gpu.py")
        after = definitions(ROOT / "scripts/collect_experiments_loco_tc2_gpu.py")
        for name in ("_hex", "_result_path", "_cache_path", "_analysis_path", "_design", "_status", "_chain_evidence", "_runtime", "_expected_samples", "_artifact_manifest", "_tar_size", "_read_files", "_write_page"):
            with self.subTest(function=name):
                self.assertEqual(after[name], before[name])

    def test_collector_and_test_are_standard_library_only(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("numpy", sys.modules)
        for relative in ("scripts/collect_experiments_loco_tc2_gpu.py", "tests/test_collect_experiments_loco_tc2_gpu.py"):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertTrue(imported.isdisjoint({"numpy", "torch", "torchvision", "PIL"}))

    def test_cli_help_has_no_runtime_or_network_dependency(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/collect_experiments_loco_tc2_gpu.py"), "--help"],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verify-collection", result.stdout)


def put(root, name, value):
    target = collector._inside(root, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(value if isinstance(value, bytes) else collector._encode(value))
    return target


def build_loco_fixture(root):
    """Use real frozen lists and synthetic metadata; never load images or arrays."""
    design_bytes = (ROOT / collector.CONFIG).read_bytes()
    design = json.loads(design_bytes)
    put(root, collector.CONFIG, design_bytes)
    (root / "tmp").mkdir()
    for name in collector.MANIFESTS:
        put(root, name, (ROOT / name).read_bytes())
    job = "79861"
    software = {"python": "3.10.22", "numpy": "1.26.4", "torch": "2.11.0+cu128"}
    runtime = {"device": "cuda", **design["expected_hardware"], "tf32": False, "autocast": False,
               "software": software, "slurm_job_id": job}
    state = {"mode": "formal_experiment_stage", "stage_id": "B0_LOCO", "job_id": job, "status": "running",
             "stage_complete": False, "step_7_complete": False, "design_sha256": collector._bytes_sha(design_bytes),
             "experiment_sources": {name: collector._bytes_sha(name.encode()) for name in collector.EXPERIMENT_SOURCES},
             "runtime": runtime, "caches": [], "results": [], "analyses": [], "phases": []}
    caches = {}
    for fit in [row for row in design["fits"] if row["configuration"]["stage"] == "B0_LOCO"]:
        key, cfg = fit["run_key"], fit["configuration"]
        category = cfg["category"]
        if category not in caches:
            frozen_name = "manifests/manifest_mvtec_loco_" + category + ".json"
            frozen = json.loads((ROOT / frozen_name).read_bytes())
            images = [{"path": row["path"], "sha256": row["sha256"]} for row in frozen["dev"] + frozen["fit_pool"] + frozen["test"]["good"] + frozen["test"]["anomalies"]]
            identity = {"namespace": "formal", "protocol_sha256": collector.PROTOCOL_SHA256, "dtype": "float32",
                        "format": "tc2_gpu_fp32_npy_1", "dataset": "mvtec_loco", "category": category, "images": images,
                        "manifest_sha256": design["scientific_source_hashes"][frozen_name], "split_hash": frozen["split_hash"],
                        "extraction_sources": {name: design["scientific_source_hashes"][name] for name in collector.CACHE_SOURCES},
                        "software": software, "hardware": design["expected_hardware"]}
            identifier = collector._digest(identity)
            path = "run/tc2_gpu/feature_cache/mvtec_loco/" + category + "/" + identifier
            n = len(images)
            meta = {"identity": identity, "cache_id": identifier,
                    "index": [{"path": row["path"], "orig_hw": [2, 3]} for row in images],
                    "layers": {layer: {"dtype": "float32", "shape": shape, "sha256": "A" * 64}
                               for layer, shape in {"layer1": [n, 64, 64, 64], "layer2": [n, 128, 32, 32], "layer3": [n, 256, 16, 16]}.items()}}
            metadata_path = put(root, path + "/metadata.json", meta)
            put(root, path + "/COMPLETE", {"status": "complete", "cache_id": identifier, "metadata_sha256": collector._sha(metadata_path)})
            fingerprint = {"cache_id": identifier, "metadata_sha256": collector._sha(metadata_path),
                           "layer_hashes": {name: row["sha256"] for name, row in meta["layers"].items()}}
            state["caches"].append({"path": path, "identity": identity, "metadata_sha256": fingerprint["metadata_sha256"], "layer_hashes": fingerprint["layer_hashes"]})
            caches[category] = (identity, fingerprint, frozen)
        cache_identity, fingerprint, frozen = caches[category]
        groups = collector._expected_samples(frozen, cfg)
        for group in groups.values():
            for row in group:
                row["orig_hw"] = [2, 3]
        identity = {"namespace": "formal", "protocol_sha256": collector.PROTOCOL_SHA256, "configuration": cfg,
                    "manifest_sha256": cache_identity["manifest_sha256"], "split_hash": frozen["split_hash"],
                    "raw_inputs_sha256": collector._digest({"images": cache_identity["images"], "masks": [mask for row in frozen["test"]["anomalies"] for mask in row["masks"]]}),
                    "samples_sha256": collector._digest(groups), "cache": fingerprint,
                    "sources": {name: design["scientific_source_hashes"][name] for name in collector.SCIENCE_SOURCES},
                    "software": software, "hardware": design["expected_hardware"]}
        identifier = collector._digest(identity)
        path = "run/tc2_gpu/results/" + identifier
        values = {"config.yaml": cfg, "samples.json": groups, "predictions.npz": b"SYNTHETIC COLLECTOR FIXTURE ONLY; NO MODEL OR NUMPY ARRAYS\n",
                  "metrics.json": metrics_for(groups), "evidence.json": {"identity": identity, "cache_identity": cache_identity, "runtime": runtime},
                  "validation.json": {"status": "passed", "identity_sha256": identifier, "metric_abs_tolerance": 1e-12,
                                      "prediction_dtype": "float32", "saved_metric_reproduction": True}}
        for name, value in values.items():
            put(root, path + "/" + name, value)
        manifest_bytes = "".join(collector._sha(root / path / name) + "  " + name + "\n" for name in collector.ARTIFACTS).encode()
        put(root, path + "/artifacts.sha256", manifest_bytes)
        put(root, path + "/SUCCESS", {"status": "passed", "namespace": "formal", "identity_sha256": identifier,
                                      "artifacts_sha256": collector._bytes_sha(manifest_bytes)})
        state["results"].append({"run_key": key, "path": path, "identity_sha256": identifier, "verified": True, "run_status": "completed",
                                 **{name: cfg[name] for name in ("method", "dataset", "category", "run_seed", "normal_train_n")}})
    put(root, "run/validation_tc2_gpu/step7_job_" + job + "/setup_status.json", state)
    return state


class PagedCollectionTests(unittest.TestCase):
    def setUp(self):
        if OUTPUT is None:
            raise RuntimeError("Use --output-dir to keep generated fixtures inside validation")
        fixture_base = OUTPUT / "s"
        fixture_base.mkdir(exist_ok=True)
        target = Path(tempfile.mkdtemp(prefix="c", dir=fixture_base)).resolve()
        if target.parent != fixture_base.resolve() or not target.name.startswith("c"):
            raise ValueError("Temporary fixtures must stay inside the approved validation sandbox")
        self.root = collector._extended(target)
        self.state = build_loco_fixture(self.root)

    def test_valid_loco_export_index_all_pages_and_collection_roundtrip(self):
        job = self.state["job_id"]
        exported = collector.export_pages(self.root, job, self.root / ("tmp/experiments-" + job + "-synthetic"), "B0_LOCO")
        self.assertEqual(exported["page_count"], 2)
        self.assertTrue(exported["partial"])
        index_path = Path(exported["index_path"])
        verified_index = collector.verify_index(index_path, exported["index_sha256"], job)
        self.assertEqual(verified_index["job_id"], job)
        local = self.root / "downloaded"
        local.mkdir()
        for page in exported["pages"]:
            collector.verify_archive(Path(exported["directory"]) / page["name"], page["sha256"], job,
                                     local / ("page_%03d" % page["page_number"]), index_path)
        complete = collector.verify_collection(index_path, local, job)
        self.assertEqual(complete["result_count"], 4)
        self.assertFalse(complete["stage_complete"])
        self.assertFalse(complete["step_7_complete"])
        self.assertIn("collector_provenance", json.loads(index_path.read_bytes()))
        for field in ("base_collector_sha256", "collector_sha256", "purpose"):
            changed = json.loads(index_path.read_bytes())
            changed["collector_provenance"][field] = "0" * 64
            with self.subTest(provenance_field=field), self.assertRaises(ValueError):
                collector._validate_index(changed, job)
        receipt_path = local / "page_001" / collector.RECEIPT
        receipt = json.loads(receipt_path.read_bytes())
        receipt["collector_provenance"]["collector_sha256"] = "0" * 64
        receipt_path.write_bytes(collector._encode(receipt))
        with self.assertRaisesRegex(ValueError, "matching verification receipt"):
            collector.verify_collection(index_path, local, job)
        with self.assertRaises((ValueError, FileNotFoundError)):
            collector.verify_collection(index_path, self.root, job)

    def test_realistic_loco_payload_is_rejected_by_frozen_original_schema(self):
        job = self.state["job_id"]
        with self.assertRaisesRegex(ValueError, "metric policy or five image rules"):
            original.export_pages(self.root, job, self.root / ("tmp/experiments-" + job + "-original"), "B0_LOCO")

    def test_loco_collector_refuses_an_ad_public_export(self):
        with self.assertRaises(ValueError):
            collector.export_pages(self.root, self.state["job_id"], self.root / ("tmp/experiments-" + self.state["job_id"] + "-wrongstage"), "B0")

    def test_changed_metric_bytes_cannot_pass_artifact_validation(self):
        path = self.root / self.state["results"][0]["path"] / "metrics.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            collector.export_pages(self.root, self.state["job_id"], self.root / ("tmp/experiments-" + self.state["job_id"] + "-changed"), "B0_LOCO")


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    OUTPUT = args.output_dir.absolute()
    allowed = (ROOT / "run/validation_tc2_gpu").resolve()
    if OUTPUT.exists() or OUTPUT.resolve() == allowed or not OUTPUT.resolve().is_relative_to(allowed):
        parser.error("Use a fresh directory strictly inside run/validation_tc2_gpu")
    OUTPUT.mkdir(parents=True)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    (OUTPUT / "offline_tests.txt").write_text(text, encoding="utf-8")
    status = {"mode": "offline", "status": "passed" if result.wasSuccessful() and not result.skipped else "failed",
              "step_7_complete": False, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "actual_model_calls": 0, "actual_tc2_connections": 0,
              "actual_slurm_submissions": 0, "torch_imported": "torch" in sys.modules,
              "failure_details": [{"test": test.id(), "traceback": trace} for test, trace in result.failures + result.errors],
              "source_hashes": {name: current_source_sha(ROOT, name) for name in
                               ("scripts/collect_experiments_loco_tc2_gpu.py", "scripts/collect_experiments_tc2_gpu.py",
                                "tests/test_collect_experiments_loco_tc2_gpu.py")}}
    (OUTPUT / "setup_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(text)
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
