"""Offline stage and analysis checks; synthetic fixtures never authorize experiments."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = None
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import tc2_gpu_protocol as protocol


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


experiments = module("experiments_tc2_gpu_offline", "scripts/experiments_tc2_gpu.py")
analysis = module("analyze_scores_tc2_gpu_offline", "scripts/analyze_scores_tc2_gpu.py")


def write_json(path, value):
    path = analysis.local_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")


def fresh(prefix):
    if OUTPUT is None:
        raise RuntimeError("Run this file with --output-dir to keep fixtures inside validation")
    path = OUTPUT / (prefix + "_" + uuid.uuid4().hex[:8])
    path.mkdir()
    return path


def completed_record(design, stage, index, previous=None):
    spec = experiments.stage_spec(design, stage)
    return {"mode": "formal_experiment_stage", "stage_id": stage, "job_id": str(50000 + index),
            "status": "passed", "stage_complete": True, "step_7_complete": False,
            "predecessor": previous, "design_sha256": "A" * 64, "experiment_sources": {"offline": "B" * 64},
            "results": [{"run_key": key, "verified": True, "run_status": "completed"} for key in spec["run_keys"]],
            "analyses": [{"stage_id": stage, "status": "passed", "rows": spec["expected_rows"]}]
                        if spec["kind"] == "analysis" else []}


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.root = fresh("config")
        self.design = experiments.load_design(ROOT)

    def test_frozen_matrix_has_66_unique_fits_and_only_64_new_fits(self):
        fits = self.design["fits"]
        self.assertEqual(len(fits), 66)
        self.assertEqual(len({row["run_key"] for row in fits}), 66)
        self.assertEqual(sum(row["configuration"]["dataset"] == "mvtec_ad" for row in fits), 62)
        self.assertEqual(sum(row["configuration"]["dataset"] == "mvtec_loco" for row in fits), 4)
        self.assertEqual(sum(row["planned_new_fits"] for row in self.design["stages"]), 64)
        self.assertEqual(fits, protocol.build_plan(ROOT)["fits"])
        self.assertEqual([row["run_key"] for row in self.design["accepted_pilot_results"]], list(experiments.pilot.RUN_KEYS))

    def test_stage_dependencies_and_allocations_match_approved_order(self):
        self.assertEqual([row["stage_id"] for row in self.design["stages"]], list(experiments.STAGES))
        previous = None
        cumulative = 0
        for spec, fit_count in zip(self.design["stages"], experiments.FIT_COUNTS):
            with self.subTest(stage=spec["stage_id"]):
                self.assertEqual(spec["predecessor"], previous)
                previous = spec["stage_id"]
                self.assertEqual(len(spec["run_keys"]), fit_count)
                cumulative += fit_count
                self.assertEqual(spec["expected_cumulative_fits"], cumulative)
                resource = spec["resources"]
                self.assertEqual((resource["partition"], resource["qos"], resource["cpus_per_task"]), ("MGPU-TC2", "normal", 2))
                self.assertEqual((resource["gpus"], resource["memory_gib"], resource["time_limit"]),
                                 (1, 24, "02:00:00") if spec["kind"] == "fit" else (0, 8, "00:15:00"))

    def test_analysis_sources_and_rows_are_exactly_18_54_36(self):
        configurations = {row["run_key"]: row["configuration"] for row in self.design["fits"]}
        for stage, count, seeds in (("I1_seed17", 18, {17}), ("I1_all_seeds", 54, {17, 29, 43}), ("I2", 36, {17, 29, 43})):
            with self.subTest(stage=stage):
                spec = experiments.stage_spec(self.design, stage)
                self.assertEqual(spec["expected_rows"], count)
                self.assertEqual(spec["score_rules"], list(analysis.STAGE_RULES[stage]))
                source = [configurations[key] for key in spec["source_run_keys"]]
                self.assertEqual({row["run_seed"] for row in source}, seeds)
                self.assertEqual({row["method"] for row in source}, {"patchcore"})
                self.assertLessEqual({row["stage"] for row in source}, {"B0", "R0"})
                self.assertEqual(len(source), 6 if stage == "I1_seed17" else 18)

    def test_changed_matrix_resources_order_or_analysis_scope_is_refused(self):
        variants = []
        value = copy.deepcopy(self.design); value["fits"][0]["configuration"]["run_seed"] = 0; variants.append(value)
        value = copy.deepcopy(self.design); value["stages"][0]["resources"]["memory_gib"] = 30; variants.append(value)
        value = copy.deepcopy(self.design); value["stages"][1], value["stages"][2] = value["stages"][2], value["stages"][1]; variants.append(value)
        value = copy.deepcopy(self.design); value["stages"][4]["source_run_keys"] = value["stages"][4]["source_run_keys"][:-1]; variants.append(value)
        for index, changed in enumerate(variants):
            with self.subTest(variant=index):
                path = self.root / (str(index) + ".json")
                write_json(path, changed)
                with self.assertRaises(ValueError):
                    experiments.load_design(ROOT, path)

    def test_plan_cli_is_read_only_and_does_not_import_torch(self):
        formal = ROOT / "run/tc2_gpu"
        before = formal.exists()
        output = io.StringIO()
        with patch.object(sys, "argv", ["experiments_tc2_gpu.py", "plan", "--root", str(ROOT)]), patch.object(sys, "stdout", output):
            experiments.main()
        planned = json.loads(output.getvalue())
        self.assertEqual((planned["fits"], planned["new_fits"]), (66, 64))
        self.assertEqual(formal.exists(), before)
        self.assertNotIn("torch", sys.modules)


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.root = fresh("orchestrate")
        self.design = experiments.load_design(ROOT)
        self.calls = []
        self.emitted = []

    def invoke(self, action, arguments):
        self.calls.append((action, list(arguments)))
        if action == "extract":
            return {"status": "cached", "identity": {"namespace": "formal"}, "path": str(self.root / "cache")}
        if action == "run":
            key = arguments[1]
            identity = protocol.digest(key)
            return {"status": "completed", "namespace": "formal", "path": str(self.root / ("run/tc2_gpu/results/" + identity)), "identity_sha256": identity}
        if action == "verify":
            path = Path(arguments[1])
            return {"status": "passed", "namespace": "formal", "path": str(path.absolute()), "identity_sha256": path.name}
        raise AssertionError("Unexpected action")

    def emit(self, kind, value):
        self.emitted.append((kind, value))

    def run_stage(self, stage="B0", invoke=None):
        return experiments.perform_fits(self.design, experiments.stage_spec(self.design, stage), invoke or self.invoke, self.emit, root=self.root)

    def test_b0_extracts_six_categories_once_and_never_refits_pilot(self):
        before = copy.deepcopy(self.design["accepted_pilot_results"])
        self.run_stage()
        caches = [args for action, args in self.calls if action == "extract"]
        runs = [args[1] for action, args in self.calls if action == "run"]
        verified = [args for action, args in self.calls if action == "verify"]
        self.assertEqual(len(caches), 6)
        self.assertEqual(len({tuple(args) for args in caches}), 6)
        self.assertEqual(len(runs), 10)
        self.assertTrue(set(runs).isdisjoint(experiments.pilot.RUN_KEYS))
        self.assertEqual(len(verified), 12)
        results = [value for kind, value in self.emitted if kind == "result"]
        self.assertEqual([value["run_key"] for value in results], experiments.stage_spec(self.design, "B0")["run_keys"])
        self.assertEqual(sum(value["accepted_pilot_reuse"] for value in results), 2)
        self.assertEqual(self.design["accepted_pilot_results"], before)
        self.assertTrue(all(Path(value["run"]["path"]).is_absolute() for value in results))

    def test_multiple_fit_variants_share_one_extraction_per_category(self):
        self.run_stage("F1")
        spec = experiments.stage_spec(self.design, "F1")
        configurations = {row["run_key"]: row["configuration"] for row in self.design["fits"]}
        expected = {(configurations[key]["dataset"], configurations[key]["category"]) for key in spec["run_keys"]}
        caches = [tuple(args[1::2]) for action, args in self.calls if action == "extract"]
        self.assertEqual(set(caches), expected)
        self.assertEqual(len(caches), len(expected))
        self.assertEqual(sum(action == "run" for action, _ in self.calls), 8)

    def test_extraction_failure_stops_before_any_fit(self):
        def invoke(action, arguments):
            if action == "extract" and sum(name == "extract" for name, _ in self.calls) == 1:
                self.calls.append((action, list(arguments)))
                return {"status": "failed", "identity": {"namespace": "formal"}}
            return self.invoke(action, arguments)
        with self.assertRaises(RuntimeError):
            self.run_stage(invoke=invoke)
        self.assertEqual([action for action, _ in self.calls], ["extract", "extract"])
        self.assertEqual([kind for kind, _ in self.emitted], ["cache"])

    def test_fit_failure_stops_all_later_fits(self):
        def invoke(action, arguments):
            if action == "run":
                self.calls.append((action, list(arguments)))
                return {"status": "failed", "namespace": "formal"}
            return self.invoke(action, arguments)
        with self.assertRaises(RuntimeError):
            self.run_stage(invoke=invoke)
        self.assertEqual(sum(action == "run" for action, _ in self.calls), 1)
        self.assertEqual(sum(action == "verify" for action, _ in self.calls), 2)
        self.assertEqual(sum(kind == "result" for kind, _ in self.emitted), 2)

    def test_wrong_verification_identity_stops_before_new_fits(self):
        def invoke(action, arguments):
            result = self.invoke(action, arguments)
            if action == "verify":
                result["identity_sha256"] = "0" * 64
            return result
        with self.assertRaises(RuntimeError):
            self.run_stage(invoke=invoke)
        self.assertEqual(sum(action == "run" for action, _ in self.calls), 0)
        self.assertEqual(sum(kind == "result" for kind, _ in self.emitted), 0)

    def test_foreign_cache_namespace_is_refused(self):
        def invoke(action, arguments):
            result = self.invoke(action, arguments)
            if action == "extract":
                result["identity"]["namespace"] = "validation"
            return result
        with self.assertRaises(RuntimeError):
            self.run_stage(invoke=invoke)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.emitted)


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.root = fresh("dependency")
        self.design = experiments.load_design(ROOT)
        self.source_hashes = {"offline": "B" * 64}

    def chain(self, through):
        previous = None
        rows = []
        for index, stage in enumerate(experiments.STAGES[:experiments.STAGES.index(through) + 1]):
            value = completed_record(self.design, stage, index, previous)
            directory = self.root / ("run/validation_tc2_gpu/step7_job_" + value["job_id"])
            write_json(directory / "setup_status.json", value)
            pointer = self.root / ("run/validation_tc2_gpu/last_experiments_" + stage + "_job.txt")
            pointer.write_text(value["job_id"] + "\n", encoding="utf-8")
            previous = {"stage_id": stage, "job_id": value["job_id"], "status_sha256": analysis.sha(directory / "setup_status.json")}
            rows.append((value, directory))
        return rows

    def predecessors(self, stage):
        return experiments.predecessors(self.root, stage, self.design, self.source_hashes, "A" * 64)

    def test_latest_valid_predecessor_chain_is_verified(self):
        self.chain("H1")
        with patch.object(experiments, "verify_artifacts", side_effect=lambda root, value, design, **kwargs: value) as verify:
            completed, previous = self.predecessors("H2")
        self.assertEqual([value["stage_id"] for value in completed], ["B0", "H1"])
        self.assertEqual(previous["stage_id"], "H1")
        self.assertEqual(verify.call_count, 16)

    def test_latest_failed_job_never_falls_back_to_older_success(self):
        rows = self.chain("B0")
        old = rows[0][1] / "setup_status.json"
        before = analysis.sha(old)
        failed = copy.deepcopy(rows[0][0]); failed.update(job_id="59999", status="failed", stage_complete=False)
        write_json(self.root / "run/validation_tc2_gpu/step7_job_59999/setup_status.json", failed)
        pointer = self.root / "run/validation_tc2_gpu/last_experiments_B0_job.txt"
        pointer.write_text("59999\n", encoding="utf-8")
        with patch.object(experiments, "verify_artifacts") as verify, self.assertRaises(RuntimeError):
            self.predecessors("H1")
        verify.assert_not_called()
        self.assertEqual(pointer.read_text().strip(), "59999")
        self.assertEqual(analysis.sha(old), before)

    def test_missing_latest_job_does_not_fall_back(self):
        self.chain("B0")
        pointer = self.root / "run/validation_tc2_gpu/last_experiments_B0_job.txt"
        pointer.write_text("59998\n", encoding="utf-8")
        with patch.object(experiments, "verify_artifacts"), self.assertRaises(FileNotFoundError):
            self.predecessors("H1")

    def test_changed_predecessor_link_is_refused(self):
        rows = self.chain("H1")
        changed = rows[1][0]
        changed["predecessor"]["status_sha256"] = "F" * 64
        write_json(rows[1][1] / "setup_status.json", changed)
        with patch.object(experiments, "verify_artifacts"), self.assertRaises(RuntimeError):
            self.predecessors("H2")

    def test_changed_source_snapshot_is_refused(self):
        rows = self.chain("B0")
        changed = rows[0][0]
        changed["experiment_sources"]["offline"] = "C" * 64
        write_json(rows[0][1] / "setup_status.json", changed)
        with patch.object(experiments, "verify_artifacts"), self.assertRaises(RuntimeError):
            self.predecessors("H1")

    def test_incomplete_previous_analysis_blocks_later_stage(self):
        rows = self.chain("I1_seed17")
        changed = rows[-1][0]
        changed["analyses"] = []
        write_json(rows[-1][1] / "setup_status.json", changed)
        with patch.object(experiments, "verify_artifacts"), self.assertRaises(RuntimeError):
            self.predecessors("R0")


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.root = fresh("publication")
        self.incoming = self.root / "tmp/incoming"
        self.incoming.mkdir(parents=True)
        self.record = self.root / "run/validation_tc2_gpu/experiments_stage_offline"
        self.record.parent.mkdir(parents=True)
        for name in experiments.FILES:
            target = self.incoming / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        (self.incoming / "experiments.sha256").write_text("".join(analysis.sha(self.incoming / name).lower() + "  " + name + "\n" for name in experiments.FILES), encoding="utf-8")

    def test_lowercase_transport_hashes_publish_exactly_seven_new_files(self):
        with patch.object(experiments, "preflight", return_value={"status": "passed"}) as preflight:
            value = experiments.publish(self.root, self.incoming, "B0", self.record)
        self.assertEqual((value["status"], value["files"]), ("published", 7))
        preflight.assert_called_once()
        for name in experiments.FILES:
            self.assertEqual(analysis.sha(self.root / name), analysis.sha(self.incoming / name))
        self.assertFalse((self.root / "configs/tc2_setup.json").exists())
        self.assertTrue((self.record / "experiments.sha256").is_file())

    def test_conflicting_source_is_preserved_before_publication(self):
        target = self.root / "scripts/experiments_tc2_gpu.py"
        target.parent.mkdir(parents=True)
        target.write_text("Existing conflicting source\n", encoding="utf-8")
        before = analysis.sha(target)
        with patch.object(experiments, "preflight") as preflight, self.assertRaises(ValueError):
            experiments.publish(self.root, self.incoming, "B0", self.record)
        preflight.assert_not_called()
        self.assertEqual(analysis.sha(target), before)
        self.assertFalse(self.record.exists())
        self.assertFalse((self.root / experiments.FILES[0]).exists())

    def test_extra_payload_member_is_refused_without_publication(self):
        path = self.incoming / "experiments.sha256"
        path.write_text(path.read_text() + "F" * 64 + "  configs/tc2_setup.json\n", encoding="utf-8")
        with patch.object(experiments, "preflight") as preflight, self.assertRaises(ValueError):
            experiments.publish(self.root, self.incoming, "B0", self.record)
        preflight.assert_not_called()
        self.assertFalse(self.record.exists())
        self.assertFalse((self.root / experiments.FILES[0]).exists())

    def test_local_gpu_entry_is_refused_before_output_creation(self):
        with patch.object(experiments.platform, "system", return_value="Windows"), patch.dict(os.environ, {"SLURM_JOB_ID": ""}), self.assertRaises(RuntimeError):
            experiments.run_stage(self.root, "B0")
        self.assertFalse((self.root / "run/validation_tc2_gpu/step7_job_").exists())
        self.assertFalse((self.root / "run/tc2_gpu").exists())


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.design = experiments.load_design(ROOT)

    def state(self, stage):
        completed = [completed_record(self.design, value, index) for index, value in enumerate(experiments.STAGES[:experiments.STAGES.index(stage)])]
        current = completed_record(self.design, stage, experiments.STAGES.index(stage))
        current.update(status="running", stage_complete=False, preflight={"completed_stages": completed})
        return current

    def test_core_standard_and_full_checkpoints_require_22_62_66_fits(self):
        for stage, count, expected in (("I1_seed17", 22, [True, False, False]), ("I2", 62, [True, True, False]), ("B0_LOCO", 66, [True, True, True])):
            with self.subTest(stage=stage):
                state = self.state(stage)
                experiments.complete_state(state, self.design)
                self.assertEqual(state["cumulative_fits"], count)
                self.assertEqual([value["complete"] for value in state["checkpoints"]], expected)
                self.assertEqual(state["step_7_complete"], stage == "B0_LOCO")
                self.assertTrue(state["stage_complete"])

    def test_each_checkpoint_refuses_missing_required_analysis(self):
        for stage in ("I1_seed17", "I2", "B0_LOCO"):
            with self.subTest(stage=stage):
                state = self.state(stage)
                if stage == "I1_seed17":
                    state["analyses"] = []
                else:
                    next(row for row in state["preflight"]["completed_stages"] if row["stage_id"] == "I1_seed17")["analyses"] = []
                with self.assertRaises(RuntimeError):
                    experiments.complete_state(state, self.design)
                self.assertFalse(state["stage_complete"])

    def test_duplicate_or_missing_fit_never_marks_complete(self):
        for duplicate in (True, False):
            with self.subTest(duplicate=duplicate):
                state = self.state("B0_LOCO")
                if duplicate:
                    state["results"][-1] = dict(state["results"][0])
                else:
                    state["results"].pop()
                with self.assertRaises(RuntimeError):
                    experiments.complete_state(state, self.design)
                self.assertFalse(state["step_7_complete"])

    def test_failed_analysis_and_unverified_fit_never_mark_checkpoint(self):
        for kind in ("analysis", "fit"):
            with self.subTest(kind=kind):
                state = self.state("I2")
                if kind == "analysis":
                    state["analyses"][0]["status"] = "failed"
                else:
                    state["preflight"]["completed_stages"][0]["results"][0]["verified"] = False
                with self.assertRaises(RuntimeError):
                    experiments.complete_state(state, self.design)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.root = fresh("analysis")
        self.design = experiments.load_design(ROOT)

    def prepare(self):
        for name in {*self.design["scientific_source_hashes"], analysis.DESIGN_FILE, analysis.ANALYSIS_FILE}:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def records(self, stage):
        spec = experiments.stage_spec(self.design, stage)
        return [{"run_key": key, "path": "run/tc2_gpu/results/" + protocol.digest(key), "identity_sha256": protocol.digest(key)}
                for key in spec["source_run_keys"]]

    def source(self, root, record, design):
        cfg = next(row["configuration"] for row in design["fits"] if row["run_key"] == record["run_key"])
        image = {rule: analysis.image_metrics([0, 0, 1, 1], [0.0, 0.1, 0.2, 0.3], [0.0, 0.1], ["good", "good", "crack", "dent"])
                 for rule in protocol.RULES}
        return {"source": {**record, "configuration": cfg, "artifacts_sha256": "A" * 64,
                           "artifact_hashes": {name: "B" * 64 for name in analysis.RESULT_ARTIFACTS},
                           "cache_metadata": {"path": "run/tc2_gpu/feature_cache/mvtec_ad/" + cfg["category"] + "/" + "C" * 64,
                                              "metadata_sha256": "D" * 64, "complete_sha256": "E" * 64}},
                "image": image, "pixel_reference": {"path": record["path"] + "/metrics.json", "sha256": "F" * 64,
                "field": "pixel", "recomputed_by_analysis": False}, "n_dev": 2, "n_good": 2, "n_anomaly": 2}

    def test_percentile_matches_accepted_numpy_126_across_local_versions(self):
        score = analysis.np.asarray([0.5, 1.25, 2.0], dtype=analysis.np.float32)
        self.assertAlmostEqual(analysis.normal_dev_threshold(score), 1.925, places=14)
        self.assertEqual(analysis.normal_dev_threshold(analysis.np.asarray([1.25], dtype=analysis.np.float32)), 1.25)

    def test_grouped_ties_and_strict_threshold_decision(self):
        value = analysis.image_metrics([0, 0, 1, 1], [0.0, 0.95, 0.95, 1.0], [0.0, 1.0], ["good", "good", "crack", "dent"])
        self.assertEqual(value["image_auroc"], 0.875)
        self.assertAlmostEqual(value["image_ap"], 5 / 6)
        self.assertEqual(value["threshold_95pct"], 0.95)
        self.assertEqual(value["normal_fpr"], 0.0)
        self.assertEqual(value["anomaly_recall"], 0.5)
        self.assertEqual(value["per_defect_recall"], {"crack": 0.0, "dent": 1.0})

    def test_nonfinite_empty_or_one_class_scores_are_refused(self):
        for scores, dev, labels in (([0.0, float("nan")], [0.0], [0, 1]), ([0.0, 1.0], [], [0, 1]), ([0.0, 1.0], [0.0], [0, 0])):
            with self.subTest(scores=scores, labels=labels), self.assertRaises(ValueError):
                analysis.image_metrics(labels, scores, dev, ["good", "dent"])

    def test_all_three_stages_publish_exact_rows_and_preserve_reuse(self):
        self.prepare()
        with patch.object(analysis, "verify_source_result", side_effect=self.source):
            for stage, count in (("I1_seed17", 18), ("I1_all_seeds", 54), ("I2", 36)):
                with self.subTest(stage=stage):
                    parent = self.root / ("run/tc2_gpu/summaries/" + stage)
                    value = analysis.analyze(self.root, stage, self.records(stage), parent)
                    directory = self.root / value["path"]
                    self.assertEqual((value["status"], value["reuse"], value["rows"]), ("passed", "created", count))
                    self.assertEqual({path.name for path in directory.iterdir()}, {*analysis.ANALYSIS_ARTIFACTS, "analysis.sha256", "SUCCESS"})
                    self.assertEqual(analysis.verify_analysis(self.root, directory, stage)["status"], "passed")
                    before = {path.name: (analysis.sha(path), path.stat().st_mtime_ns) for path in directory.iterdir()}
                    self.assertEqual(analysis.analyze(self.root, stage, self.records(stage), parent)["reuse"], "skipped")
                    self.assertEqual(before, {path.name: (analysis.sha(path), path.stat().st_mtime_ns) for path in directory.iterdir()})
        self.assertNotIn("torch", sys.modules)

    def test_missing_analysis_source_is_refused_before_output_creation(self):
        self.prepare()
        parent = self.root / "run/tc2_gpu/summaries/I1_seed17"
        with patch.object(analysis, "verify_source_result", side_effect=self.source), self.assertRaises(ValueError):
            analysis.analyze(self.root, "I1_seed17", self.records("I1_seed17")[:-1], parent)
        self.assertFalse(parent.exists())

    def test_unknown_analysis_lock_is_preserved(self):
        self.prepare()
        stage = "I1_seed17"
        parent = self.root / ("run/tc2_gpu/summaries/" + stage)
        with patch.object(analysis, "verify_source_result", side_effect=self.source):
            _, value = analysis._assemble(self.root, stage, self.records(stage))
            lock = parent / ("." + value["identity_sha256"] + ".lock")
            write_json(lock, {"owner": "unknown"})
            before = analysis.sha(lock)
            with self.assertRaises(RuntimeError):
                analysis.analyze(self.root, stage, self.records(stage), parent)
            self.assertEqual(analysis.sha(lock), before)
            self.assertFalse((parent / value["identity_sha256"]).exists())

    def test_resealed_analysis_corruption_is_refused_without_overwrite(self):
        self.prepare()
        stage = "I1_seed17"
        parent = self.root / ("run/tc2_gpu/summaries/" + stage)
        with patch.object(analysis, "verify_source_result", side_effect=self.source):
            value = analysis.analyze(self.root, stage, self.records(stage), parent)
            directory = self.root / value["path"]
            data = analysis.read(directory / "analysis.json")
            data["rows"][0]["image_auroc"] = 0.0
            write_json(directory / "analysis.json", data)
            (directory / "analysis.csv").write_text(analysis._csv(data), encoding="utf-8", newline="\n")
            (directory / "analysis.sha256").write_text("".join(analysis.sha(directory / name) + "  " + name + "\n" for name in analysis.ANALYSIS_ARTIFACTS), encoding="utf-8")
            marker = analysis.read(directory / "SUCCESS")
            marker["analysis_manifest_sha256"] = analysis.sha(directory / "analysis.sha256")
            write_json(directory / "SUCCESS", marker)
            before = {path.name: analysis.sha(path) for path in directory.iterdir()}
            for recompute in (False, True):
                with self.subTest(recompute=recompute), self.assertRaises(ValueError):
                    analysis.verify_analysis(self.root, directory, recompute=recompute)
            with self.assertRaises(ValueError):
                analysis.analyze(self.root, stage, self.records(stage), parent)
            self.assertEqual(before, {path.name: analysis.sha(path) for path in directory.iterdir()})

    def test_failed_analysis_keeps_partial_and_has_no_success_marker(self):
        self.prepare()
        stage = "I1_seed17"
        parent = self.root / ("run/tc2_gpu/summaries/" + stage)
        with patch.object(analysis, "verify_source_result", side_effect=self.source), patch.object(analysis, "_csv", side_effect=RuntimeError("Injected offline serialization failure")):
            with self.assertRaises(RuntimeError):
                analysis.analyze(self.root, stage, self.records(stage), parent)
        partials = list(parent.glob(".*.partial.*"))
        self.assertEqual(len(partials), 1)
        self.assertTrue((partials[0] / "FAILED.json").is_file())
        self.assertFalse((partials[0] / "SUCCESS").exists())
        self.assertFalse(list(parent.glob("*.lock")))


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    OUTPUT = args.output_dir.absolute()
    allowed = (ROOT / "run/validation_tc2_gpu").resolve()
    if OUTPUT == allowed or OUTPUT.exists() or not OUTPUT.resolve().is_relative_to(allowed):
        parser.error("Use a fresh directory strictly under run/validation_tc2_gpu")
    OUTPUT.mkdir(parents=True)
    stream = io.StringIO()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        for cls in (ConfigurationTests, OrchestrationTests, DependencyTests, PublicationTests, CompletionTests, AnalysisTests))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    (OUTPUT / "offline_tests.txt").write_text(text, encoding="utf-8")
    status = {"mode": "offline", "status": "passed" if result.wasSuccessful() and not result.skipped and "torch" not in sys.modules else "failed",
              "step_7_complete": False, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "torch_imported": "torch" in sys.modules, "actual_model_calls": 0, "actual_tc2_connections": 0, "actual_slurm_submissions": 0,
              "failure_details": [{"test": test.id(), "traceback": trace} for test, trace in result.failures + result.errors],
              "source_hashes": {name: analysis.sha(ROOT / name) for name in experiments.FILES if (ROOT / name).is_file()}}
    write_json(OUTPUT / "setup_status.json", status)
    print(text)
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
