"""CPU checks for the approved figure revision; --full requires all 15 renders."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tc2_gpu_provenance import historical_config, historical_sha
OUTPUT = None
FULL = False
FULL_RENDERED = False
FROZEN = {
    "configs/analysis_tc2_gpu.json": "9E6E20069F5E3C1F6ED5F739077D79D8556357C5C92501C822AD3E03BFB537B9",
    "scripts/analyze_results_tc2_gpu.py": "CC6B3FDC5518BEA45E1F4E9571BC1D318EADEA6340D3D75DA9FC5E649B3A3552",
    "scripts/plot_results_tc2_gpu.py": "C4AD7E9B6BB2D6D6428099EC255EBAE5BA624CD0B4F636D4CC7468C096F867B5",
    "scripts/collect_analysis_tc2_gpu.py": "23364A7E72E99AD6D02302A525523AD92B0A2300195BAF98861D88DDA2E8B98E",
    "scripts/slurm/analysis_tc2_gpu.sh": "8351E365AFE6FD996743E46DA13D6E7A9E40D6028B52C9612BDE5B0EFE4DC139",
    "tests/test_analysis_tc2_gpu.py": "168104960F564D6622564527FBCE3753FB9EEACA0EB4AB4C41209A312331521A",
    "docs/TC2_GPU_ANALYSIS.md": "F897C75659CC31BF98BB89E95AA4E3AEA241AA40FAC59CEDE85518119CA5F57C",
}
FIGURES = {"F1_methods", "baseline_comparison", "F3_hyperparameters", "F3_components", "F3_fewshot",
           "F4_improvement", "F4_q_sensitivity", "F4_score_distributions", "F4_defect_size", "F5_resources",
           "loco_extension", *("F2_cases_%02d" % number for number in range(1, 5))}


def local(path):
    path = Path(path).absolute()
    if sys.platform == "win32" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(path))
    return path


def sha(path):
    return hashlib.sha256(local(path).read_bytes()).hexdigest().upper()


def load(name, relative):
    """Use private names so preserved and revision collectors cannot alias modules."""
    path = local(ROOT / relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT / "scripts"))
revision = load("_figure_revision_test_driver", "scripts/revise_figures_tc2_gpu.py")
collector = load("_figure_revision_test_collector", "scripts/collect_figure_revision_tc2_gpu.py")


def temporary(test):
    target = local(tempfile.mkdtemp(prefix="fixture_", dir=OUTPUT)).resolve()
    expected_parent = local(OUTPUT).resolve()
    if target.parent != expected_parent or not target.name.startswith("fixture_"):
        raise ValueError("Fixture cleanup must remain inside the fresh test output directory")
    def cleanup():
        # Resolve and check the exact absolute directory immediately before removal.
        literal = local(target)
        info = literal.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Refusing fixture cleanup through a link or reparse point")
        checked = literal.resolve()
        if checked.parent != expected_parent or not checked.name.startswith("fixture_"):
            raise ValueError("Refusing fixture cleanup outside the fresh test output directory")
        shutil.rmtree(local(checked))
    test.addCleanup(cleanup)
    return target


def json_write(path, value):
    path = local(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def pdf_bytes(size=7, compressed=False, content=None):
    """A complete, tiny PDF lets the scanner check real content streams offline."""
    stream = content if content is not None else ("BT /F1 %s Tf 10 10 Td (Readable label) Tj ET" % size).encode("ascii")
    payload = zlib.compress(stream) if compressed else stream
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length " + str(len(payload)).encode("ascii") + (b" /Filter /FlateDecode" if compressed else b"") + b" >>\nstream\n" + payload + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    result = bytearray(b"%PDF-1.4\n"); positions = [0]
    for number, item in enumerate(objects, 1):
        positions.append(len(result))
        result.extend(("%d 0 obj\n" % number).encode("ascii") + item + b"\nendobj\n")
    start = len(result)
    result.extend(("xref\n0 %d\n0000000000 65535 f \n" % len(positions)).encode("ascii"))
    for position in positions[1:]:
        result.extend(("%010d 00000 n \n" % position).encode("ascii"))
    result.extend(("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(positions), start)).encode("ascii"))
    return bytes(result)


def source_snapshot():
    """Verify archived acceptance identities independently of current source identities."""
    preserved = load("_figure_revision_test_original_collector", "scripts/collect_analysis_tc2_gpu.py")
    design = historical_config(ROOT, "experiments")
    protected = {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **preserved.OLD_SOURCES}
    if len(protected) != 44:
        raise AssertionError("The historical scientific, pilot and experiment source set must contain 44 files")
    expected = {**protected, **FROZEN}
    actual = {name: historical_sha(ROOT, name) for name in expected}
    if actual != expected:
        raise AssertionError("At least one of the 51 archived sources differs from its accepted fingerprint")
    if sha(ROOT / "scripts/plot_results_tc2_gpu.py") != FROZEN["scripts/plot_results_tc2_gpu.py"]:
        raise AssertionError("The current numerical plotting implementation changed")
    return actual


class SourceAndDataTests(unittest.TestCase):
    def test_all_51_accepted_sources_still_match_their_fingerprints(self):
        self.assertEqual(len(source_snapshot()), 51)

    def test_exact_rows_accept_unchanged_and_reject_numeric_reorder_and_membership_edits(self):
        original = [{"category": "wood", "mean": 0.9685594, "std": 0.0027205, "seed": 17},
                    {"category": "tile", "mean": -0.000982872, "std": None, "seed": 53}]
        revision.assert_source_rows(original, copy.deepcopy(original))
        changed = copy.deepcopy(original); changed[0]["mean"] += 1e-14
        changed_membership = copy.deepcopy(original); changed_membership[0]["category"] = "bottle"
        for value in (changed, original[::-1], original[:1], original + [original[0]], changed_membership):
            with self.subTest(value=value), self.assertRaises(ValueError):
                revision.assert_source_rows(original, value)

    def test_exact_rows_reject_nonfinite_numbers(self):
        for number in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(number=number), self.assertRaises((ValueError, TypeError)):
                revision.assert_source_rows([{"score": 1.0}], [{"score": number}])

    def test_configuration_is_valid_and_binds_the_accepted_input(self):
        config = json.loads(local(ROOT / "configs/tc2_gpu/figure_revision.json").read_text(encoding="utf-8"))
        revision.validate_config(config)
        text = json.dumps(config)
        self.assertIn("6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C", text)
        self.assertIn("figure_revision", text)
        bad = copy.deepcopy(config); bad["unapproved_extra_policy"] = True
        with self.assertRaises(ValueError):
            revision.validate_config(bad)

    def test_imports_do_not_load_torch_or_matplotlib(self):
        self.assertNotIn("torch", sys.modules)
        if not FULL:
            self.assertNotIn("matplotlib.pyplot", sys.modules)


class FontTests(unittest.TestCase):
    def test_real_plain_and_flate_pdf_streams_pass_at_the_seven_point_floor(self):
        root = temporary(self)
        for compressed in (False, True):
            path = root / ("compressed.pdf" if compressed else "plain.pdf")
            path.write_bytes(pdf_bytes(7, compressed))
            result = revision.pdf_font_audit(path, minimum_pt=7)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["minimum_glyph_pt"], 7)

    def test_actual_small_glyphs_are_rejected_even_when_main_text_is_eight_point(self):
        root = temporary(self)
        content = b"BT /F1 8 Tf (Axis title) Tj /F1 5.25 Tf (2) Tj ET"
        for compressed in (False, True):
            path = root / ("compressed.pdf" if compressed else "plain.pdf")
            path.write_bytes(pdf_bytes(compressed=compressed, content=content))
            with self.subTest(compressed=compressed), self.assertRaises(ValueError):
                revision.pdf_font_audit(path, minimum_pt=7)

    def test_missing_text_and_invalid_pdf_are_refused(self):
        root = temporary(self)
        for number, content in enumerate((pdf_bytes(content=b"q 1 0 0 1 0 0 cm Q"), b"not a PDF")):
            path = root / ("bad%d.pdf" % number); path.write_bytes(content)
            with self.subTest(number=number), self.assertRaises(ValueError):
                revision.pdf_font_audit(path, minimum_pt=7)


class GeometryTests(unittest.TestCase):
    """Exercise the final rendered-bounds gate without installing Matplotlib locally."""
    class Artist:
        def __init__(self, bounds, text=""):
            self.bounds, self.text = bounds, text
        def get_window_extent(self, _renderer):
            return SimpleNamespace(**dict(zip(("x0", "y0", "x1", "y1"), self.bounds)))
        def get_visible(self):
            return True
        def get_text(self):
            return self.text

    def figure(self, texts=(), boxes=()):
        class Size:
            def __mul__(self, factor):
                return [7.2 * factor, 4.5 * factor]
        canvas = SimpleNamespace(draw=lambda: None, get_renderer=lambda: object())
        figure = SimpleNamespace(canvas=canvas, dpi=72, get_size_inches=lambda: Size(),
                                 _revision_diagram_boxes=list(boxes), _revision_diagram_routes=[])
        axis = self.Artist([50, 110, 450, 270])
        axis.title = self.Artist([60, 280, 200, 295], "Panel title")
        axis.texts = list(texts); axis.axison = False
        return figure, [[axis]]

    def test_legend_note_and_panel_bands_have_measured_clearance(self):
        figure, axes = self.figure()
        result = revision.require_clearance(figure, axes, [self.Artist([100, 65, 350, 80])], self.Artist([20, 20, 450, 40]))
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["measured_after_final_draw"])
        self.assertGreaterEqual(result["minimum_footer_clearance_pt"], 3)

    def test_legend_colliding_with_a_final_tick_label_is_rejected(self):
        figure, axes = self.figure([self.Artist([90, 80, 230, 96], "Long final tick")])
        with self.assertRaisesRegex(ValueError, "Footer collides"):
            revision.require_clearance(figure, axes, [self.Artist([100, 65, 350, 80])])

    def test_legend_note_overlap_and_page_overflow_are_rejected(self):
        figure, axes = self.figure()
        with self.assertRaisesRegex(ValueError, "bands overlap"):
            revision.require_clearance(figure, axes, [self.Artist([100, 65, 350, 80])], self.Artist([20, 82, 450, 95]))
        figure, axes = self.figure([self.Artist([10, -1, 30, 10], "Off-page label")])
        with self.assertRaisesRegex(ValueError, "leaves the page"):
            revision.require_clearance(figure, axes)

    def test_diagram_text_containment_uses_measured_box_bounds(self):
        outer = self.Artist([100, 140, 250, 190])
        inner = self.Artist([103, 145, 247, 185], "Frozen ImageNet weights")
        figure, axes = self.figure(boxes=[(outer, inner)])
        result = revision.require_clearance(figure, axes, diagram=True)
        self.assertEqual(len(result["diagram_text_containment"]), 1)
        inner.bounds = [95, 145, 247, 185]
        with self.assertRaisesRegex(ValueError, "does not fit"):
            revision.require_clearance(figure, axes, diagram=True)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        gate = patch.object(revision, "require_current_acceptance", return_value=None)
        gate.start(); self.addCleanup(gate.stop)

    ENVIRONMENT = {"SLURM_JOB_ID": "79867", "SLURM_CPUS_PER_TASK": "2", "SLURM_MEM_PER_NODE": "8192",
                   "SLURM_JOB_PARTITION": "MGPU-TC2", "SLURM_JOB_QOS": "normal", "CUDA_VISIBLE_DEVICES": "-1", "SLURM_GPUS": "0"}

    def fixture(self):
        root = temporary(self)
        original = root / ("run/tc2_gpu/summaries/analysis/" + "B" * 64)
        json_write(original / "tables.json", {"resources": [], "mask_areas": []})
        json_write(original / "cases.json", {"cases": []})
        for name in FIGURES:
            json_write(original / ("source_data/" + name + ".json"), {"rows": []})
        asset = original / "cases/001/image.png"; asset.parent.mkdir(parents=True); asset.write_bytes(b"Selected asset copied without interpretation\n")
        plan = {"identity": "A" * 64, "input_analysis": {"relative_path": original.relative_to(root).as_posix()},
                "input_artifacts": {"cases/001/image.png": sha(asset)}, "figure_revision_sources": {"synthetic_source_only": "C" * 64}}
        record = root / "run/validation_tc2_gpu/step8_figure_revision_job_79867"
        json_write(record / "plan.json", plan)
        state = {"schema_version": "1.0", "job_id": "79867", "identity": plan["identity"], "status": "running",
                 "phase": "tests", "output_relative": None, "new_fits": 0, "model_predict_calls": 0}
        json_write(record / "state.json", state)
        return root, original, record, plan

    def test_wrapper_test_state_reaches_render_once_preserves_inputs_and_refuses_retry(self):
        root, original, record, plan = self.fixture()
        before = {path.relative_to(original).as_posix(): sha(path) for path in original.rglob("*") if path.is_file()}
        plan_fingerprint = sha(record / "plan.json")
        class PlannedRenderStop(RuntimeError):
            pass
        def stop_at_render(_root, stage, context, source_data):
            self.assertEqual(Path(stage), record / "staging_output")
            self.assertEqual(sha(Path(stage) / "cases/001/image.png"), before["cases/001/image.png"])
            self.assertEqual(set(source_data), FIGURES)
            self.assertEqual(context["provenance"]["only_overrides"], ["_save", "_methods"])
            raise PlannedRenderStop("Synthetic renderer boundary; no rendering or scheduler execution")
        with patch.dict("os.environ", self.ENVIRONMENT, clear=True), patch.object(revision, "verify_plan") as verified, patch.object(revision, "render_revision", side_effect=stop_at_render) as render:
            with self.assertRaises(PlannedRenderStop):
                revision.run(root, "79867", plan)
            self.assertEqual(render.call_count, 1)
            verified.assert_called_once_with(root, plan)
            state = json.loads((record / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "failed")
            self.assertIn("Synthetic renderer boundary", state["error"])
            failed_fingerprint = sha(record / "state.json")
            with self.assertRaisesRegex(ValueError, "automatic retries"):
                revision.run(root, "79867", plan)
            self.assertEqual(render.call_count, 1)
            self.assertEqual(sha(record / "state.json"), failed_fingerprint)
        self.assertEqual(sha(record / "plan.json"), plan_fingerprint)
        self.assertEqual({name: sha(original / name) for name in before}, before)
        self.assertFalse((root / ("run/tc2_gpu/summaries/figure_revision/" + plan["identity"])).exists())

    def test_wrong_allocation_conflicting_wrapper_plan_and_existing_output_stop_before_render(self):
        for field, value in (("SLURM_GPUS", "1"), ("SLURM_CPUS_PER_TASK", "4"), ("SLURM_MEM_PER_NODE", "16384"), ("SLURM_JOB_ID", "79868")):
            root = temporary(self)
            environment = {**self.ENVIRONMENT, field: value}
            with self.subTest(field=field), patch.dict("os.environ", environment, clear=True), patch.object(revision, "verify_plan") as verified, patch.object(revision, "render_revision") as render:
                with self.assertRaises(ValueError):
                    revision.run(root, "79867", {"identity": "A" * 64})
                verified.assert_not_called(); render.assert_not_called()
                self.assertFalse((root / "run").exists())
        for conflict in ("wrapper_plan", "immutable_output"):
            root, _original, record, plan = self.fixture()
            if conflict == "wrapper_plan":
                json_write(record / "plan.json", {"identity": "D" * 64})
            else:
                (root / ("run/tc2_gpu/summaries/figure_revision/" + plan["identity"])).mkdir(parents=True)
            before = sha(record / "state.json")
            with self.subTest(conflict=conflict), patch.dict("os.environ", self.ENVIRONMENT, clear=True), patch.object(revision, "verify_plan"), patch.object(revision, "render_revision") as render:
                with self.assertRaises(ValueError):
                    revision.run(root, "79867", plan)
                render.assert_not_called()
            self.assertEqual(sha(record / "state.json"), before)
            self.assertFalse((record / "staging_output").exists())


class CollectionTests(unittest.TestCase):
    def setUp(self):
        gate = patch.object(collector, "require_current_acceptance", return_value=None)
        gate.start(); self.addCleanup(gate.stop)

    def snapshot(self):
        root = temporary(self)
        for name in sorted(collector.SOURCES):
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(local(ROOT / name).read_bytes() if name == "scripts/collect_figure_revision_tc2_gpu.py" else ("Synthetic pending source: " + name + "\n").encode("ascii"))
        exported = collector.export_archive(root, "79865", root / "snapshot")
        index_path = local(exported["index_path"])
        index = json.loads(index_path.read_text(encoding="utf-8"))
        return root, exported, index_path, index

    def test_collection_limits_are_the_approved_fixed_bounds(self):
        self.assertEqual(collector.LIMIT, 512 * 1024 * 1024)
        self.assertEqual(collector.MAX_MEMBERS, 512)
        self.assertEqual(collector.MAX_INDEX, 8 * 1024 * 1024)

    def test_pending_export_and_pinned_round_trip_do_not_claim_visual_acceptance(self):
        root, exported, index_path, index = self.snapshot()
        checked = collector.verify_index(index_path, exported["index_sha256"], "79865")
        self.assertTrue(checked["partial"])
        download = root / "download"; download.mkdir()
        archive = local(exported["directory"]) / "page_001.tar.gz"
        collector.verify_archive(archive, download / "page_001", index_path, expected_sha=index["pages"][0]["sha256"], job_id="79865")
        result = collector.verify_collection(index_path, download, "79865")
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["step_8_complete"])
        self.assertFalse(result["stage_complete"])
        self.assertFalse(result["visual_review_performed"])
        for expected, job in (("0" * 64, "79865"), (exported["index_sha256"], "79866")):
            with self.subTest(expected=expected, job=job), self.assertRaises(ValueError):
                collector.verify_index(index_path, expected, job)
        extra = download / "page_001/unexpected.json"; extra.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            collector.verify_collection(index_path, download, "79865")

    def test_index_rejects_duplicate_case_alias_extra_page_and_both_byte_limits(self):
        _root, _exported, _index_path, index = self.snapshot()
        variants = []
        duplicate = copy.deepcopy(index); duplicate["pages"][0]["files"].append(copy.deepcopy(duplicate["pages"][0]["files"][0])); variants.append(duplicate)
        case_alias = copy.deepcopy(index); alias = copy.deepcopy(case_alias["pages"][0]["files"][0]); alias["path"] = alias["path"].upper(); case_alias["pages"][0]["files"].append(alias); variants.append(case_alias)
        pages = copy.deepcopy(index); pages["page_count"] = 2; pages["pages"].append(copy.deepcopy(pages["pages"][0])); variants.append(pages)
        compressed = copy.deepcopy(index); compressed["pages"][0]["bytes"] = collector.LIMIT + 1; variants.append(compressed)
        decompressed = copy.deepcopy(index); decompressed["pages"][0]["files"][0]["size"] = collector.LIMIT; variants.append(decompressed)
        members = copy.deepcopy(index); members["pages"][0]["files"] = [copy.deepcopy(members["pages"][0]["files"][0]) for _ in range(collector.MAX_MEMBERS)]; variants.append(members)
        for number, value in enumerate(variants):
            with self.subTest(number=number), self.assertRaises(ValueError):
                collector._validate_index(value, "79865")

    def test_archive_rejects_duplicates_traversal_and_mixed_snapshots_before_publication(self):
        root, exported, _index_path, index = self.snapshot()
        with tarfile.open(local(exported["directory"]) / "page_001.tar.gz", "r:gz") as package:
            members = [(copy.copy(member), package.extractfile(member).read()) for member in package]
        for mode in ("duplicate", "traversal", "mixed_snapshot"):
            values = copy.deepcopy(members)
            if mode == "duplicate":
                values.append(copy.deepcopy(values[0]))
            elif mode == "traversal":
                member = tarfile.TarInfo("../outside.json"); values.append((member, b"{}"))
            else:
                for position, (member, data) in enumerate(values):
                    if member.name == collector.MANIFEST:
                        manifest = json.loads(data); manifest["export_id"] = "F" * 32
                        values[position] = (member, json.dumps(manifest).encode("utf-8"))
            archive = root / (mode + ".tar.gz")
            with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as package:
                for member, data in values:
                    member.size = len(data); package.addfile(member, io.BytesIO(data))
            modified = copy.deepcopy(index)
            modified["pages"][0]["bytes"] = archive.stat().st_size
            modified["pages"][0]["sha256"] = sha(archive)
            pinned_index = root / (mode + ".index.json"); json_write(pinned_index, modified)
            destination = root / ("rejected_" + mode)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                collector.verify_archive(archive, destination, pinned_index, job_id="79865")
            self.assertFalse(destination.exists(), "Rejected archive published a partial destination")

    def test_streaming_decompression_is_bounded_independently_of_declared_members(self):
        root, exported, _index_path, index = self.snapshot()
        archive = root / "padded.tar.gz"
        original = local(exported["directory"]) / "page_001.tar.gz"
        with gzip.open(original, "rb") as stream:
            raw = stream.read()
        # Legitimate zero tar padding can inflate far past the index member sum.
        maximum = max(20000, len(raw) + 1024)
        with gzip.open(archive, "wb") as stream:
            stream.write(raw + b"\0" * maximum)
        modified = copy.deepcopy(index)
        modified["pages"][0]["bytes"] = archive.stat().st_size
        modified["pages"][0]["sha256"] = sha(archive)
        pinned = root / "padded.index.json"; json_write(pinned, modified)
        destination = root / "rejected_padded"
        with patch.object(collector, "LIMIT", maximum), self.assertRaisesRegex(ValueError, "decompressed"):
            collector.verify_archive(archive, destination, pinned, job_id="79865")
        self.assertFalse(destination.exists())

    def test_relative_paths_reject_windows_absolute_and_traversal(self):
        for name in ("../escape", "/absolute", "a/../../escape", "a\\b", "C:/escape", "a//b", "./a"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                collector._relative(name)

    def test_tar_guard_rejects_links_extensions_and_concatenated_payload(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.XHDTYPE):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                member = tarfile.TarInfo("metadata.json"); member.type = kind; member.linkname = "outside"
                archive.addfile(member)
            payload = raw.getvalue()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                collector._tar_layout(io.BytesIO(payload), len(payload))
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            member = tarfile.TarInfo("metadata.json"); member.size = 2
            archive.addfile(member, io.BytesIO(b"{}"))
        payload = raw.getvalue() + b"another archive"
        with self.assertRaises(ValueError):
            collector._tar_layout(io.BytesIO(payload), len(payload))


def fixture_context(root):
    """Reuse frozen numerical fixtures, expanding only selected image assets to 16 cases."""
    fixtures = load("_figure_revision_test_frozen_fixtures", "tests/test_analysis_tc2_gpu.py")
    context = fixtures.synthetic_context(root)
    initial = context["cases"]
    import numpy as np
    from PIL import Image
    for number in range(3, 17):
        case = copy.deepcopy(initial[(number - 1) % 2])
        prefix = "cases/%03d" % number; directory = root / prefix; directory.mkdir(parents=True)
        image = np.full((80, 96, 3), 100 + number, dtype=np.uint8)
        mask = np.zeros((80, 96), dtype=np.uint8)
        if case["label"]:
            mask[30:35, 45:50] = 255
        Image.fromarray(image).save(directory / "image.png")
        Image.fromarray(mask).save(directory / "mask_union.png")
        case["case_id"] = "%03d" % number
        case["path"] = "mvtec_ad/bottle/synthetic_%03d.png" % number
        case["image_path"] = prefix + "/image.png"; case["mask_path"] = prefix + "/mask_union.png"
        for method in ("padim", "patchcore"):
            np.save(directory / (method + "_map.npy"), np.linspace(0, 2, 256 * 256, dtype=np.float32).reshape(256, 256), allow_pickle=False)
            case["maps"][method]["path"] = prefix + "/" + method + "_map.npy"
        json_write(directory / "case.json", case)
        initial.append(case)
    return context


class FullRenderTests(unittest.TestCase):
    def test_all_15_actual_png_pdf_renders_preserve_sources_assets_and_numerical_rows(self):
        global FULL_RENDERED
        from PIL import Image
        root = local(OUTPUT / "full_render_fixture"); root.mkdir()
        before_sources = source_snapshot()
        context = fixture_context(root)
        asset_hashes = {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file()}
        original_context = copy.deepcopy(context)
        plots = revision._plot()
        functions = {name: value for name, value in vars(plots).items() if callable(value)}
        expected_rows = {}
        plt = plots._backend()
        def capture(_plt, _output, name, fig, _axes, rows, _question, **_kwargs):
            if name in expected_rows:
                raise AssertionError("Frozen plot routines repeated a figure name")
            expected_rows[name] = copy.deepcopy(rows)
            _plt.close(fig)
            return {"name": name}
        with patch.object(plots, "_save", capture):
            plots._methods(plt, root)
            for routine in ("_baseline", "_ablation", "_components", "_fewshot", "_improvement", "_q_sensitivity", "_defect_size", "_resources", "_loco"):
                getattr(plots, routine)(plt, root, context["tables"])
            plots._distributions(plt, root, context)
            plots._cases(plt, root, context)
        self.assertEqual(set(expected_rows), FIGURES)
        manifest, invariance = revision.render_revision(ROOT, root, context, {name: {"rows": rows} for name, rows in expected_rows.items()})
        FULL_RENDERED = True
        self.assertEqual(len(invariance), 15)
        self.assertTrue(all(row["status"] == "identical" for row in invariance))
        self.assertEqual(manifest["figure_count"], 15)
        self.assertEqual({row["name"] for row in manifest["figures"]}, FIGURES)
        self.assertEqual(context, original_context)
        self.assertEqual(source_snapshot(), before_sources)
        self.assertEqual({name: sha(root / name) for name in asset_hashes}, asset_hashes)
        for name, value in functions.items():
            self.assertIs(getattr(plots, name), value, "Original plotting function was not restored: " + name)
        source_rows = {}
        for figure in manifest["figures"]:
            self.assertIn(figure["alignment_status"], ("passed", "not_applicable"))
            for name, spec in figure["files"].items():
                self.assertEqual(sha(root / name), spec["sha256"])
                self.assertEqual((root / name).stat().st_size, spec["bytes"])
            png = root / ("figures/" + figure["name"] + ".png")
            with Image.open(png) as image:
                image.verify()
            with Image.open(png) as image:
                self.assertGreater(min(image.size), 100)
                self.assertAlmostEqual(image.info["dpi"][0], 300, delta=0.1)
            pdf = root / ("figures/" + figure["name"] + ".pdf")
            self.assertEqual(revision.pdf_font_audit(pdf)["status"], "passed")
            qa = json.loads((root / ("qa/" + figure["name"] + ".alignment.json")).read_text(encoding="utf-8"))
            self.assertEqual(qa["clearance"]["status"], "passed")
            self.assertTrue(qa["clearance"]["measured_after_final_draw"])
            self.assertGreaterEqual(qa["actual_pdf_fonts"]["minimum_glyph_pt"], 7)
            if figure["name"] == "F1_methods":
                self.assertEqual(len(qa["clearance"]["diagram_text_containment"]), 6)
                routes = {row["route"] for row in qa["clearance"]["diagram_routes"]}
                self.assertIn("PaDiM to anomaly map and image scores", routes)
                self.assertIn("PatchCore to anomaly map and image scores", routes)
                self.assertEqual(len(routes), 5)
            source = json.loads((root / ("source_data/" + figure["name"] + ".json")).read_text(encoding="utf-8"))
            source_rows[figure["name"]] = source
            revision.assert_source_rows(expected_rows[figure["name"]], source["rows"])
        # Replay exact accepted rows through the revision gate without rendering again.
        for name, source in source_rows.items():
            revision.assert_source_rows(source["rows"], json.loads(json.dumps(source["rows"])))
        self.assertNotIn("torch", sys.modules)


def main():
    global OUTPUT, FULL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--full", action="store_true", help="Require all 15 real Matplotlib PNG/PDF renders; missing dependencies fail")
    args = parser.parse_args()
    OUTPUT = Path(args.output_dir).absolute(); FULL = args.full
    if OUTPUT.exists() or not OUTPUT.parent.is_dir():
        raise ValueError("Tests require a fresh output directory with an existing parent")
    local(OUTPUT).mkdir()
    classes = [SourceAndDataTests, FontTests, GeometryTests, LifecycleTests, CollectionTests] + ([FullRenderTests] if FULL else [])
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(value) for value in classes)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped and "torch" not in sys.modules
    report = {"status": "passed" if passed else "failed", "created_utc": datetime.now(timezone.utc).isoformat(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "full_requested": FULL, "full_plot_render_executed": FULL_RENDERED, "full_plot_render_passed": FULL_RENDERED and passed,
              "local_core_tests_passed": result.wasSuccessful(), "gpu_or_models_executed": False, "torch_imported": "torch" in sys.modules,
              "lifecycle_scheduler_environment_simulated": True, "actual_network_or_scheduler_connections": False,
              "figure_count_required": 15, "minimum_pdf_glyph_pt": 7, "preserved_source_count": 51,
              "source_hashes": {name: sha(ROOT / name) for name in ("scripts/revise_figures_tc2_gpu.py", "scripts/collect_figure_revision_tc2_gpu.py", "tests/test_figure_revision_tc2_gpu.py")},
              "render_scope": "All 15 real figure groups and 16 synthetic selected cases" if FULL else "Offline source, exact-row, PDF-font and archive guards; full rendering requires --full on TC2 CPU"}
    json_write(OUTPUT / "tests_summary.json", report)
    json_write(OUTPUT / "test_report.json", report)
    print(json.dumps(report, indent=2, allow_nan=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
