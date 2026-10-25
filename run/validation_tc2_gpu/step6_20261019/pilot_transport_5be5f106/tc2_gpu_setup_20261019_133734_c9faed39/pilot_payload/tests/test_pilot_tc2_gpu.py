"""Offline pilot integration checks; fixtures never qualify as formal acceptance."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = None
sys.path.insert(0, str(ROOT / "src"))
import tc2_gpu_protocol as protocol


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


pilot = module("pilot_tc2_gpu_offline", "scripts/pilot_tc2_gpu.py")
collector = module("collect_tc2_gpu_pilot_offline", "scripts/collect_tc2_gpu_pilot.py")


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def passed(count):
    return {"tests_run": count, "failures": 0, "errors": 0, "skipped": 0,
            "passed": True, "failure_details": []}


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.root = OUTPUT / ("case_" + uuid.uuid4().hex[:10])
        self.root.mkdir()
        self.design = {"run_keys": ["B0_bottle_padim_seed17_N100", "B0_bottle_patchcore_seed17_N100"],
                       "workflow_acceptance_job_id": "44012"}
        self.calls = []
        self.records = []
        self.fit_counts = {}
        self.identifiers = {key: character * 64 for key, character in zip(self.design["run_keys"], "AB")}

    def fake(self, action, args):
        self.calls.append((action, list(args)))
        if action == "extract":
            return {"status": "extracted", "path": str(self.root / "run/tc2_gpu/feature_cache/mvtec_ad/bottle" / ("C" * 64)),
                    "identity": {"namespace": "formal"}}
        if action == "run":
            key = args[args.index("--run-key") + 1]
            count = self.fit_counts.get(key, 0)
            self.fit_counts[key] = count + 1
            identifier = self.identifiers[key]
            return {"status": "completed" if count == 0 else "skipped", "namespace": "formal",
                    "path": str(self.root / "run/tc2_gpu/results" / identifier), "identity_sha256": identifier}
        if action == "verify":
            path = args[args.index("--result") + 1]
            return {"status": "passed", "namespace": "formal", "path": path,
                    "identity_sha256": Path(path).name}
        raise AssertionError("Unexpected invocation: " + action)

    def record(self, phase, payload):
        self.records.append((phase, copy.deepcopy(payload)))

    def exercise(self, transform=None, fail_at=None):
        def invoke(action, args):
            result = self.fake(action, args)
            if fail_at == len(self.calls):
                raise RuntimeError("Injected subprocess failure")
            return transform(action, args, result, len(self.calls)) if transform else result
        return pilot.perform_steps(self.design, invoke, self.record)

    def gate_fixture(self):
        hashes = {}
        for number in range(31):
            name = "src/frozen_" + str(number) + ".py"
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Frozen fixture " + str(number) + "\n", encoding="utf-8")
            hashes[name] = sha(path)
        self.design["workflow_source_hashes"] = hashes
        pointer = self.root / "run/validation_tc2_gpu/last_check_workflow_job.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("44012\n", encoding="utf-8")
        status = {"mode": "full", "status": "passed", "step_5_complete": True,
                  "source_hashes": hashes, "core": passed(16), "gpu": passed(4),
                  "metric_regression": {**passed(24), "mode": "full", "status": "passed", "step_3_complete": True},
                  "algorithm_regression": {"mode": "full", "status": "passed", "step_4_complete": True,
                                           "cpu": passed(19), "gpu": passed(2)}}
        destination = self.root / "run/validation_tc2_gpu/step5_job_44012/setup_status.json"
        write_json(destination, status)
        return destination, status, pointer

    def test_frozen_design_selects_only_two_real_bottle_B0_fits(self):
        design = pilot.load_design(ROOT)
        self.assertEqual(len(design["run_keys"]), 2)
        plan = protocol.build_plan(ROOT)
        configurations = {row["run_key"]: row["configuration"] for row in plan["fits"]}
        selected = [configurations[key] for key in design["run_keys"]]
        self.assertEqual([cfg["method"] for cfg in selected], ["padim", "patchcore"])
        for cfg in selected:
            self.assertEqual((cfg["stage"], cfg["dataset"], cfg["category"], cfg["run_seed"], cfg["normal_train_n"]),
                             ("B0", "mvtec_ad", "bottle", 17, 100))

    def test_sequence_fits_each_method_then_verifies_saved_outputs_before_reuse(self):
        result = self.exercise()
        first, second = self.design["run_keys"]
        self.assertEqual(self.calls, [
            ("extract", ["--dataset", "mvtec_ad", "--category", "bottle"]),
            ("run", ["--run-key", first]),
            ("verify", ["--result", str(self.root / "run/tc2_gpu/results" / self.identifiers[first])]),
            ("run", ["--run-key", second]),
            ("verify", ["--result", str(self.root / "run/tc2_gpu/results" / self.identifiers[second])]),
            ("run", ["--run-key", first]), ("run", ["--run-key", second])])
        self.assertEqual([phase for phase, _ in self.records],
                         ["extract", "padim_run", "padim_verify", "patchcore_run", "patchcore_verify", "padim_reuse", "patchcore_reuse"])
        self.assertEqual([row["run_key"] for row in result["results"]], self.design["run_keys"])
        self.assertEqual([row["reuse"]["status"] for row in result["results"]], ["skipped", "skipped"])

    def test_existing_complete_cache_and_initial_results_are_reusable(self):
        def transform(action, args, value, count):
            if action == "extract":
                value["status"] = "cached"
            elif action == "run":
                value["status"] = "skipped"
            return value
        self.assertEqual(len(self.exercise(transform)["results"]), 2)

    def test_subprocess_failure_stops_without_starting_next_stage(self):
        for stage in (1, 2, 3, 4, 5, 6, 7):
            with self.subTest(stage=stage):
                self.calls.clear(); self.records.clear(); self.fit_counts.clear()
                with self.assertRaisesRegex(RuntimeError, "Injected subprocess failure"):
                    self.exercise(fail_at=stage)
                self.assertEqual(len(self.calls), stage)
                self.assertEqual(len(self.records), stage - 1)

    def test_incomplete_or_validation_cache_cannot_start_fit(self):
        for change in ({"status": "failed"}, {"identity": {"namespace": "validation"}}):
            with self.subTest(change=change):
                self.calls.clear(); self.records.clear(); self.fit_counts.clear()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.exercise(lambda action, args, value, count: {**value, **change} if count == 1 else value)
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(self.records, [])

    def test_nonformal_or_failed_fit_cannot_proceed_to_saved_verification(self):
        for change in ({"status": "failed"}, {"namespace": "validation"}):
            with self.subTest(change=change):
                self.calls.clear(); self.records.clear(); self.fit_counts.clear()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.exercise(lambda action, args, value, count: {**value, **change} if count == 2 else value)
                self.assertEqual(len(self.calls), 2)
                self.assertEqual([phase for phase, _ in self.records], ["extract"])

    def test_verification_requires_passed_formal_matching_path_and_identity(self):
        for change in ({"status": "failed"}, {"namespace": "validation"},
                       {"identity_sha256": "D" * 64}, {"path": str(self.root / "run/tc2_gpu/results" / ("D" * 64))}):
            with self.subTest(change=change):
                self.calls.clear(); self.records.clear(); self.fit_counts.clear()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.exercise(lambda action, args, value, count: {**value, **change} if count == 3 else value)
                self.assertEqual(len(self.calls), 3)

    def test_reuse_must_skip_same_result_without_a_new_fit(self):
        for change in ({"status": "completed"}, {"identity_sha256": "D" * 64},
                       {"path": str(self.root / "run/tc2_gpu/results" / ("D" * 64))}, {"namespace": "validation"}):
            with self.subTest(change=change):
                self.calls.clear(); self.records.clear(); self.fit_counts.clear()
                with self.assertRaises((ValueError, RuntimeError)):
                    self.exercise(lambda action, args, value, count: {**value, **change} if count == 6 else value)
                self.assertEqual(len(self.calls), 6)

    def test_gate_accepts_complete_unchanged_workflow(self):
        self.gate_fixture()
        self.assertIsInstance(pilot.accepted_workflow(self.root, self.design), dict)

    def test_gate_rejects_missing_or_different_workflow_pointer(self):
        _, _, pointer = self.gate_fixture()
        for text in ("44013\n", "../44012\n", ""):
            with self.subTest(pointer=text):
                pointer.write_text(text, encoding="utf-8")
                with self.assertRaises((ValueError, RuntimeError, FileNotFoundError)):
                    pilot.accepted_workflow(self.root, self.design)
        pointer.unlink()
        with self.assertRaises((ValueError, RuntimeError, FileNotFoundError)):
            pilot.accepted_workflow(self.root, self.design)

    def test_gate_rejects_failed_partial_or_core_only_acceptance(self):
        destination, status, _ = self.gate_fixture()
        for change in ({"status": "failed"}, {"mode": "core"}, {"step_5_complete": False}):
            with self.subTest(change=change):
                write_json(destination, {**status, **change})
                with self.assertRaises((ValueError, RuntimeError)):
                    pilot.accepted_workflow(self.root, self.design)

    def test_gate_rejects_failed_skipped_or_missing_regression_tests(self):
        destination, status, _ = self.gate_fixture()
        paths = [("core",), ("gpu",), ("metric_regression",), ("algorithm_regression", "cpu"), ("algorithm_regression", "gpu")]
        for fields in paths:
            for change in ({"failures": 1}, {"errors": 1}, {"skipped": 1}, {"tests_run": 0}):
                with self.subTest(fields=fields, change=change):
                    altered = copy.deepcopy(status)
                    target = altered
                    for field in fields:
                        target = target[field]
                    target.update(change)
                    write_json(destination, altered)
                    with self.assertRaises((ValueError, RuntimeError)):
                        pilot.accepted_workflow(self.root, self.design)

    def test_gate_rejects_changed_current_source_bytes(self):
        self.gate_fixture()
        source = self.root / next(iter(self.design["workflow_source_hashes"]))
        source.write_text("# Changed fixture\n", encoding="utf-8")
        with self.assertRaises((ValueError, RuntimeError)):
            pilot.accepted_workflow(self.root, self.design)

    def test_gate_rejects_explicitly_failed_nested_acceptance(self):
        destination, status, _ = self.gate_fixture()
        cases = [("core", "passed", False), ("gpu", "passed", False),
                 ("metric_regression", "status", "failed"), ("metric_regression", "step_3_complete", False),
                 ("algorithm_regression", "status", "failed"), ("algorithm_regression", "step_4_complete", False)]
        for section, key, value in cases:
            with self.subTest(section=section, key=key):
                changed = copy.deepcopy(status)
                changed[section][key] = value
                write_json(destination, changed)
                with self.assertRaises((ValueError, RuntimeError)):
                    pilot.accepted_workflow(self.root, self.design)

    def test_gate_rejects_different_accepted_source_fingerprint(self):
        destination, status, _ = self.gate_fixture()
        status = copy.deepcopy(status)
        status["source_hashes"][next(iter(status["source_hashes"]))] = "0" * 64
        write_json(destination, status)
        with self.assertRaises((ValueError, RuntimeError)):
            pilot.accepted_workflow(self.root, self.design)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.root = OUTPUT / ("archive_" + uuid.uuid4().hex[:10])
        self.root.mkdir()

    def make_archive(self, members):
        path = self.root / (uuid.uuid4().hex + ".tar.gz")
        with tarfile.open(path, "w:gz") as archive:
            for name, data, kind in members:
                item = tarfile.TarInfo(name)
                if kind == "symlink":
                    item.type = tarfile.SYMTYPE; item.linkname = "../../outside"
                    archive.addfile(item)
                elif kind == "hardlink":
                    item.type = tarfile.LNKTYPE; item.linkname = "../../outside"
                    archive.addfile(item)
                else:
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
        return path

    def pending_fixture(self):
        record = {"job_id": "12345", "mode": "real_data_pilot", "status": "running",
                  "step_6_complete": False, "cache": None, "results": []}
        prefix = self.root / "run/validation_tc2_gpu/step6_job_12345"
        write_json(prefix / "setup_status.json", record)
        log = prefix / "phase_01_preflight.stdout.txt"
        log.write_text("Pending synthetic fixture\n", encoding="utf-8")
        return prefix, record, log

    def completed_fixture(self):
        """Byte-evidence fixture only: no image, NumPy array, model or GPU work."""
        config = json.loads((ROOT / "configs/pilot_tc2_gpu.json").read_text(encoding="utf-8"))
        write_json(self.root / "configs/pilot_tc2_gpu.json", config)
        images = [{"path": "fixture/" + str(i) + ".png", "sha256": "A" * 64} for i in range(292)]
        identity = {"format": "tc2_gpu_fp32_npy_1", "namespace": "formal", "protocol_sha256": protocol.PROTOCOL_SHA256,
                    "dataset": "mvtec_ad", "category": "bottle", "dtype": "float32", "images": images,
                    "extraction_sources": {name: config["workflow_source_hashes"][name] for name in protocol.CACHE_SOURCES}}
        cache_id = digest(identity)
        cache_name = "run/tc2_gpu/feature_cache/mvtec_ad/bottle/" + cache_id
        cache_dir = self.root / cache_name
        layers = {name: {"dtype": "float32", "shape": [292, *shape], "sha256": "B" * 64}
                  for name, shape in protocol.SHAPES.items()}
        metadata = {"identity": identity, "cache_id": cache_id,
                    "index": [{"path": row["path"], "orig_hw": [2, 2]} for row in images], "layers": layers}
        write_json(cache_dir / "metadata.json", metadata)
        write_json(cache_dir / "COMPLETE", {"status": "complete", "cache_id": cache_id,
                                            "metadata_sha256": sha(cache_dir / "metadata.json")})
        cache_fingerprint = {"cache_id": cache_id, "metadata_sha256": sha(cache_dir / "metadata.json"),
                             "layer_hashes": {name: entry["sha256"] for name, entry in layers.items()}}
        samples = {"fit": images[:100], "dev": images[100:142], "test": images[142:225]}
        results = []
        for fit in config["fits"]:
            cfg = fit["configuration"]
            result_identity = {"namespace": "formal", "protocol_sha256": protocol.PROTOCOL_SHA256,
                               "configuration": cfg, "sources": {name: config["workflow_source_hashes"][name]
                                                                    for name in protocol.SOURCE_FILES},
                               "samples_sha256": digest(samples), "cache": cache_fingerprint}
            identifier = digest(result_identity)
            name = "run/tc2_gpu/results/" + identifier
            target = self.root / name
            write_json(target / "config.yaml", cfg)
            write_json(target / "samples.json", samples)
            (target / "predictions.npz").write_bytes(b"Offline byte-evidence fixture; contains no scientific predictions.\n")
            write_json(target / "metrics.json", {})
            write_json(target / "evidence.json", {"identity": result_identity, "cache_identity": identity})
            write_json(target / "validation.json", {"status": "passed", "identity_sha256": identifier,
                "metric_abs_tolerance": 1e-12, "prediction_dtype": "float32", "saved_metric_reproduction": True})
            artifacts = ["config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json"]
            (target / "artifacts.sha256").write_text("".join(sha(target / item) + "  " + item + "\n" for item in artifacts), encoding="utf-8")
            write_json(target / "SUCCESS", {"status": "passed", "namespace": "formal", "identity_sha256": identifier,
                                             "artifacts_sha256": sha(target / "artifacts.sha256")})
            results.append({"method": cfg["method"], "run_key": fit["run_key"], "path": name})
        record = {"job_id": "12345", "mode": "real_data_pilot", "status": "passed", "step_6_complete": True,
                  "cache": {"path": cache_name}, "results": results}
        write_json(self.root / "run/validation_tc2_gpu/step6_job_12345/setup_status.json", record)
        return record

    def test_completed_byte_evidence_roundtrip_contains_results_and_cache_hashes_only(self):
        record = self.completed_fixture()
        archive = self.root / "completed.tar.gz"
        collector.export_archive(self.root, "12345", archive)
        destination = self.root / "completed_download"
        result = collector.verify_archive(archive, sha(archive), "12345", destination)
        self.assertFalse(result["partial"])
        self.assertTrue(result["step_6_complete"])
        for row in record["results"]:
            self.assertEqual(sha(destination / row["path"] / "predictions.npz"), sha(self.root / row["path"] / "predictions.npz"))
        self.assertTrue((destination / record["cache"]["path"] / "metadata.json").is_file())
        self.assertEqual(list(destination.rglob("*.npy")), [])

    def test_completed_snapshot_rejects_missing_success_marker(self):
        record = self.completed_fixture()
        (self.root / record["results"][0]["path"] / "SUCCESS").unlink()
        archive = self.root / "missing_success.tar.gz"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.export_archive(self.root, "12345", archive)
        self.assertFalse(archive.exists())

    def test_resealed_artifacts_cannot_hide_a_failed_validation_report(self):
        record = self.completed_fixture()
        target = self.root / record["results"][0]["path"]
        report = json.loads((target / "validation.json").read_text(encoding="utf-8"))
        report["saved_metric_reproduction"] = False
        write_json(target / "validation.json", report)
        names = [row.split(None, 1)[1] for row in (target / "artifacts.sha256").read_text().splitlines()]
        (target / "artifacts.sha256").write_text("".join(sha(target / name) + "  " + name + "\n" for name in names), encoding="utf-8")
        marker = json.loads((target / "SUCCESS").read_text(encoding="utf-8"))
        marker["artifacts_sha256"] = sha(target / "artifacts.sha256")
        write_json(target / "SUCCESS", marker)
        archive = self.root / "resealed_failed_validation.tar.gz"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.export_archive(self.root, "12345", archive)
        self.assertFalse(archive.exists())

    def test_pending_roundtrip_preserves_bytes_and_cannot_qualify_step_six(self):
        prefix, _, log = self.pending_fixture()
        before = {path.name: (sha(path), path.stat().st_mtime_ns) for path in prefix.iterdir()}
        archive = self.root / "pending.tar.gz"
        exported = collector.export_archive(self.root, "12345", archive)
        self.assertTrue(exported["partial"])
        self.assertFalse(exported["step_6_complete"])
        destination = self.root / "download"
        verified = collector.verify_archive(archive, sha(archive), "12345", destination)
        self.assertTrue(verified["partial"])
        self.assertFalse(verified["step_6_complete"])
        self.assertEqual(sha(destination / log.relative_to(self.root)), sha(log))
        self.assertEqual(before, {path.name: (sha(path), path.stat().st_mtime_ns) for path in prefix.iterdir()})

    def test_missing_status_snapshot_is_partial_and_does_not_invent_success(self):
        archive = self.root / "missing_status.tar.gz"
        collector.export_archive(self.root, "12345", archive)
        result = collector.verify_archive(archive, sha(archive), "12345", self.root / "missing_download")
        self.assertTrue(result["partial"])
        self.assertFalse(result["step_6_complete"])
        self.assertEqual(result["pilot_status"], "missing")

    def test_incomplete_record_cannot_claim_completed_without_cache_and_results(self):
        prefix, record, _ = self.pending_fixture()
        record.update(status="passed", step_6_complete=True)
        write_json(prefix / "setup_status.json", record)
        archive = self.root / "invalid_complete.tar.gz"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.export_archive(self.root, "12345", archive)
        self.assertFalse(archive.exists())

    def test_content_tamper_is_refused_even_with_correct_new_archive_hash(self):
        self.pending_fixture()
        archive = self.root / "before_tamper.tar.gz"
        collector.export_archive(self.root, "12345", archive)
        with tarfile.open(archive, "r:gz") as reader:
            members = [(item.name, reader.extractfile(item).read(), "file") for item in reader.getmembers()]
        altered = [(name, b"Modified after collection\n" if name.endswith(".stdout.txt") else data, kind)
                   for name, data, kind in members]
        tampered = self.make_archive(altered)
        destination = self.root / "tampered_download"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.verify_archive(tampered, sha(tampered), "12345", destination)
        self.assertFalse(destination.exists())

    def test_matching_new_content_manifest_cannot_authorize_unlisted_payload(self):
        self.pending_fixture()
        archive = self.root / "before_reseal.tar.gz"
        collector.export_archive(self.root, "12345", archive)
        with tarfile.open(archive, "r:gz") as reader:
            members = [(item.name, reader.extractfile(item).read(), "file") for item in reader.getmembers()]
        data = b"unexpected output\n"
        extra = "run/validation_tc2_gpu/step6_job_12345/unexpected.txt"
        changed = []
        for name, body, kind in members:
            if name == "pilot_export_manifest.json":
                manifest = json.loads(body)
                manifest["files"].append({"path": extra, "size": len(data),
                                          "sha256": hashlib.sha256(data).hexdigest().upper(), "role": "phase_log"})
                body = json.dumps(manifest).encode("utf-8")
            changed.append((name, body, kind))
        changed.append((extra, data, "file"))
        resealed = self.make_archive(changed)
        destination = self.root / "resealed_download"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.verify_archive(resealed, sha(resealed), "12345", destination)
        self.assertFalse(destination.exists())

    def test_bounded_snapshot_limits_apply_before_extraction(self):
        self.pending_fixture()
        archive = self.root / "bounded.tar.gz"
        collector.export_archive(self.root, "12345", archive)
        destination = self.root / "oversized_download"
        with patch.object(collector, "LIMIT", 32):
            with self.assertRaises((ValueError, RuntimeError)):
                collector.verify_archive(archive, sha(archive), "12345", destination)
        self.assertFalse(destination.exists())

    def test_archive_hash_mismatch_is_refused_without_extraction(self):
        archive = self.make_archive([("manifest.json", b"{}", "file")])
        destination = self.root / "download"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.verify_archive(archive, "0" * 64, "12345", destination)
        self.assertFalse(destination.exists())

    def test_archive_traversal_absolute_and_windows_paths_are_refused(self):
        for name in ("../outside.txt", "/absolute.txt", "C:/drive.txt", "run\\backslash.txt", "run/../outside.txt"):
            with self.subTest(path=name):
                archive = self.make_archive([(name, b"untrusted", "file")])
                destination = self.root / uuid.uuid4().hex
                with self.assertRaises((ValueError, RuntimeError)):
                    collector.verify_archive(archive, sha(archive), "12345", destination)
                self.assertFalse(destination.exists())
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_archive_symbolic_and_hard_links_are_refused(self):
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                archive = self.make_archive([("run/link", b"", kind)])
                destination = self.root / uuid.uuid4().hex
                with self.assertRaises((ValueError, RuntimeError)):
                    collector.verify_archive(archive, sha(archive), "12345", destination)
                self.assertFalse(destination.exists())

    def test_duplicate_member_names_are_refused(self):
        archive = self.make_archive([("manifest.json", b"{}", "file"), ("manifest.json", b"{}", "file")])
        destination = self.root / "duplicate"
        with self.assertRaises((ValueError, RuntimeError)):
            collector.verify_archive(archive, sha(archive), "12345", destination)
        self.assertFalse(destination.exists())


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
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(PilotTests),
                               unittest.defaultTestLoader.loadTestsFromTestCase(CollectorTests)])
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    (OUTPUT / "offline_tests.txt").write_text(text, encoding="utf-8")
    status = {"mode": "offline", "status": "passed" if result.wasSuccessful() and not result.skipped else "failed",
              "step_6_complete": False, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "actual_model_calls": 0, "actual_tc2_connections": 0,
              "actual_slurm_submissions": 0,
              "failure_details": [{"test": test.id(), "traceback": trace} for test, trace in result.failures + result.errors],
              "source_hashes": {name: sha(ROOT / name) for name in ["scripts/pilot_tc2_gpu.py", "scripts/collect_tc2_gpu_pilot.py",
                                                                  "configs/pilot_tc2_gpu.json", "tests/test_pilot_tc2_gpu.py"]}}
    write_json(OUTPUT / "setup_status.json", status)
    print(text)
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
