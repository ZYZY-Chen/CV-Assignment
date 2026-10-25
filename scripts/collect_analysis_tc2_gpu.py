"""Bounded, streaming collection of the approved TC2 GPU analysis outputs."""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import tarfile
import tempfile
import uuid

sys_path = str(Path(__file__).resolve().parent)
import sys
sys.path.insert(0, sys_path)
from collect_tc2_gpu_pilot import (_extended, _plain, _job, _relative, _no_links,
    _inside, _sha, _bytes_sha, _json as _protected_json, _encode, _digest, _read_bounded, _tar_layout,
    _atomic_publish, PROTOCOL_SHA256, PHASE)

LIMIT = 512 * 1024 * 1024
MAX_PAGES = 32
MAX_MEMBERS = 512
MAX_INDEX = 8 * 1024 * 1024
CONFIG = "configs/analysis_tc2_gpu.json"
EXPERIMENT_CONFIG = "configs/experiments_tc2_gpu.json"
PROTOCOL = "configs/protocol_v2.json"
DESIGN_SHA256 = "669AE05044C9441FACC6571F4E5AB5176BB08276DF58CA2B0D941B514A55FB75"
HEX = r"[0-9A-F]{64}"
MANIFEST = "analysis_export_manifest.json"
RECEIPT = "page_verification.json"
SOURCES = {CONFIG, "scripts/analyze_results_tc2_gpu.py", "scripts/plot_results_tc2_gpu.py",
    "scripts/collect_analysis_tc2_gpu.py", "scripts/slurm/analysis_tc2_gpu.sh",
    "tests/test_analysis_tc2_gpu.py", "docs/TC2_GPU_ANALYSIS.md"}
OLD_SOURCES = {"configs/experiments_tc2_gpu.json": DESIGN_SHA256,
    "scripts/experiments_tc2_gpu.py": "F4896D83DED9EAACB72ED7A75B63F76CC3538E61D2FB90A88CF1945D36D0CBDA",
    "scripts/analyze_scores_tc2_gpu.py": "D1412F6743ECB6709EB82FF978DF4D8C37601371BE4E78C2329B9AAD1FF609F6",
    "scripts/slurm/experiments_tc2_gpu.sh": "C4D12CFBC8D7B0F799AD51E06826318C8A17210526EC63ED04CD4FF3AB13080E",
    "scripts/collect_experiments_tc2_gpu.py": "AC61772F65C9F2C4124761D2361E0A85E9F65DBCF4DF5BAB3E939B5111466010",
    "tests/test_experiments_tc2_gpu.py": "371072914FD83F1E4A803501A86965977BA12C1797EE44C178D0A843F8A2FFE5",
    "docs/TC2_GPU_EXPERIMENTS.md": "EBF7AD234A2346379CE5B7B80A76826A564F3ED7FF08DEB17CA362EC9E2FD47A"}
STAGES = ("B0", "H1", "H2", "C1", "I1_seed17", "R0", "C1R", "C2", "F1", "I1_all_seeds", "I2", "B0_LOCO")
CATEGORIES = {"mvtec_ad": ("bottle", "cable", "capsule", "screw", "tile", "wood"),
    "mvtec_loco": ("juice_bottle", "screw_bag")}
MANIFESTS = {"manifests/manifest_" + dataset + "_" + category + ".json"
    for dataset, categories in CATEGORIES.items() for category in categories}
JOB_FILES = {"setup_status.json", "resources.json", "analysis_inputs.json", "inputs.json", "analysis_sources.json", "plan.json",
    "tests.stdout.txt", "tests.stderr.txt", "tests/setup_status.json", "tests/test_report.json", "tests/tests_summary.json"}
TOP = {"inputs.json", "analysis_config.json", "provenance.json", "tables.json", "cases.json",
    "plot_manifest.json", "verification.json", "artifacts.sha256", "SUCCESS"}
REPEATED = TOP
FIGURE = r"(?:F[1-5]_[A-Za-z0-9_]{1,60}|baseline_comparison|loco_extension)"


def _json(data):
    value = _protected_json(data)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("Nonfinite numbers are unsupported in analysis metadata")
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


def _hex(value):
    if not isinstance(value, str) or re.fullmatch(HEX, value) is None:
        raise ValueError("Expected an uppercase SHA256 fingerprint")
    return value


def _provenance():
    protection = Path(__file__).with_name("collect_tc2_gpu_pilot.py")
    _no_links(protection)
    protection_hash = "D8D3B072A6B769D81023AC0BE0770A24C999C822B5A63869992BFF084848DAC4"
    if _sha(protection) != protection_hash:
        raise ValueError("Preserved path and archive protection source differs")
    return {"schema_version": "1.0", "purpose": "tc2_gpu_analysis_collection_only",
        "collector_path": "scripts/collect_analysis_tc2_gpu.py", "collector_sha256": _sha(Path(__file__)),
        "path_protection_source_sha256": protection_hash}


def _analysis_path(value):
    _relative(value)
    if re.fullmatch(r"run/tc2_gpu/summaries/analysis/" + HEX, value) is None:
        raise ValueError("Analysis output must be an immutable canonical identity directory")
    return value


def _output_name(name):
    _relative(name)
    if name in TOP:
        return True
    patterns = (r"tables/[a-z][a-z0-9_]{0,63}\.csv", r"figures/" + FIGURE + r"\.(?:png|pdf)",
        r"source_data/" + FIGURE + r"\.json", r"qa/" + FIGURE + r"\.alignment\.json",
        r"cases/(?:00[1-9]|01[0-6])/(?:image\.png|mask_union\.png|padim_map\.npy|patchcore_map\.npy|case\.json)",
        r"cases/(?:00[1-9]|01[0-6])/masks/[0-9]{3}\.png")
    if not any(re.fullmatch(pattern, name) for pattern in patterns):
        raise ValueError("File is outside the declared analysis-output whitelist: " + name)
    return True


def _role(name, job_id, analysis_path):
    _relative(name)
    if name in {CONFIG, EXPERIMENT_CONFIG, PROTOCOL} | MANIFESTS:
        return "configuration"
    prefix = "run/validation_tc2_gpu/"
    if name in {prefix + "slurm-" + job_id + suffix for suffix in (".out", ".err")}:
        return "slurm_log"
    job_prefix = prefix + "step8_job_" + job_id + "/"
    if name.startswith(job_prefix):
        tail = name[len(job_prefix):]
        if tail in JOB_FILES:
            return "analysis_record"
        if PHASE.fullmatch(tail):
            return "phase_log"
    if analysis_path and name.startswith(analysis_path + "/"):
        _output_name(name[len(analysis_path) + 1:])
        return "published_analysis"
    raise ValueError("File is outside the analysis collection whitelist: " + name)


def _status(value, job_id):
    if not isinstance(value, dict) or value.get("job_id") != job_id:
        raise ValueError("Analysis snapshot job ID differs")
    if value.get("status") == "missing":
        if value != {"job_id": job_id, "status": "missing", "stage_id": "analysis", "step_8_complete": False}:
            raise ValueError("Missing analysis snapshot contains unexpected state")
        return value
    if value.get("mode") != "tc2_gpu_analysis" or value.get("stage_id") != "analysis":
        raise ValueError("Snapshot belongs to another workflow")
    if value.get("status") not in ("running", "passed", "failed") or type(value.get("step_8_complete")) is not bool:
        raise ValueError("Analysis status is invalid")
    if value["step_8_complete"] != (value["status"] == "passed"):
        raise ValueError("Analysis completion contradicts its execution state")
    if value.get("protocol_sha256") != PROTOCOL_SHA256 or value.get("results_count") != 66 or value.get("analysis_rows") != 108:
        raise ValueError("Analysis scope differs from the accepted experiment matrix")
    for key in ("inputs_sha256", "config_sha256"):
        _hex(value.get(key))
    sources = value.get("sources")
    if not isinstance(sources, dict) or set(sources) != SOURCES:
        raise ValueError("Analysis source set differs from the approved seven files")
    for fingerprint in sources.values():
        _hex(fingerprint)
    if sources[CONFIG] != value["config_sha256"]:
        raise ValueError("Analysis configuration and source fingerprints differ")
    if sources["scripts/collect_analysis_tc2_gpu.py"] != _provenance()["collector_sha256"]:
        raise ValueError("Collection code differs from the executed analysis source set")
    if value["step_8_complete"]:
        _analysis_path(value.get("analysis_path")); _hex(value.get("identity_sha256"))
        if value["analysis_path"].split("/")[-1] != value["identity_sha256"]:
            raise ValueError("Analysis path and content identity differ")
    return value


def _artifact_manifest(data):
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ValueError("Analysis artifact manifest is not UTF-8") from error
    result, folded = {}, set()
    for line in lines:
        match = re.fullmatch(r"(" + HEX + r")  (.+)", line)
        if not match:
            raise ValueError("Analysis artifact manifest has a malformed row")
        fingerprint, name = match.groups(); _output_name(name)
        if name in ("SUCCESS", "artifacts.sha256") or name.casefold() in folded:
            raise ValueError("Analysis artifact manifest repeats or includes reserved paths")
        result[name] = fingerprint; folded.add(name.casefold())
    if not TOP - {"SUCCESS", "artifacts.sha256"} <= set(result):
        raise ValueError("Published analysis is missing required metadata")
    if len(result) + 2 >= MAX_MEMBERS:
        raise ValueError("Published analysis exceeds the member bound")
    return result


def _registry(value, state, design):
    if not isinstance(value, dict) or value.get("protocol_sha256") != PROTOCOL_SHA256 or value.get("design_sha256") != DESIGN_SHA256:
        raise ValueError("Input registry belongs to another frozen protocol")
    if value.get("expected_total_fits") != 66 or value.get("expected_analysis_rows") != 108:
        raise ValueError("Input registry counts differ")
    if value.get("analysis_sources") != state["sources"]:
        raise ValueError("Registry source hashes differ from the executed analysis")
    if value.get("unique_pc_analysis_rows") != 90 or value.get("source_rows") != 108:
        raise ValueError("Registry source and deduplicated score-analysis counts differ")
    _hex(value.get("step7_acceptance_sha256"))
    if value.get("loco_collector_sha256") != "09AC7432F8F6BCE36F95EAEFF15D44A19F7852781A19FE65E5E573239E445967":
        raise ValueError("Registry LOCO acceptance collector fingerprint differs")
    protected = {**design["scientific_source_hashes"], **design["pilot_source_hashes"], **OLD_SOURCES}
    if len(protected) != 44 or value.get("protected_sources") != protected:
        raise ValueError("Input registry does not preserve all 44 accepted sources")
    lookup = {row["run_key"]: row["configuration"] for row in design["fits"]}
    results = value.get("results")
    if not isinstance(results, list) or len(results) != 66 or {row.get("run_key") for row in results} != set(lookup):
        raise ValueError("Input registry must contain each of the 66 frozen fit keys once")
    for row in results:
        if row.get("configuration") != lookup[row["run_key"]] or set(row.get("files", {})) != {"config.yaml", "samples.json", "predictions.npz", "metrics.json", "evidence.json", "validation.json", "artifacts.sha256", "SUCCESS"}:
            raise ValueError("A source result configuration or artifact set differs")
        identifier = _hex(row.get("identity_sha256"))
        if row.get("path") != "run/tc2_gpu/results/" + identifier:
            raise ValueError("Input registry result path differs from its identity")
        for fingerprint in row["files"].values():
            _hex(fingerprint)
    stages = value.get("stages")
    if not isinstance(stages, list) or [row.get("stage_id") for row in stages] != list(STAGES):
        raise ValueError("Input registry does not identify all twelve accepted stages")
    for row in stages:
        _job(row.get("job_id"))
        if row.get("status_path") != "run/validation_tc2_gpu/step7_job_" + row["job_id"] + "/setup_status.json":
            raise ValueError("An accepted stage status path differs")
        _relative(row.get("acceptance_record"))
        for name in ("status_sha256", "acceptance_sha256", "index_sha256"):
            _hex(row.get(name))
    analyses = value.get("analyses")
    if not isinstance(analyses, list) or [(row.get("stage_id"), row.get("rows")) for row in analyses] != [("I1_seed17", 18), ("I1_all_seeds", 54), ("I2", 36)]:
        raise ValueError("Input registry does not identify the 108 accepted score-analysis rows")
    for row in analyses:
        identifier = _hex(row.get("identity_sha256"))
        if row.get("path") != "run/tc2_gpu/summaries/" + row["stage_id"] + "/" + identifier or set(row.get("files", {})) != {"analysis.json", "analysis.csv", "evidence.json", "analysis.sha256", "SUCCESS"}:
            raise ValueError("A saved-score analysis path or artifact set differs")
        for fingerprint in row["files"].values():
            _hex(fingerprint)
    caches = value.get("caches")
    categories = {("mvtec_ad", name) for name in ("bottle", "cable", "capsule", "screw", "tile", "wood")}
    categories |= {("mvtec_loco", name) for name in ("juice_bottle", "screw_bag")}
    if not isinstance(caches, list) or len(caches) != 8 or {(row.get("dataset"), row.get("category")) for row in caches} != categories:
        raise ValueError("Input registry must identify the eight frozen category caches")
    for row in caches:
        _relative(row.get("path"))
        if not row["path"].startswith("run/tc2_gpu/feature_cache/") or set(row.get("files", {})) != {"metadata.json", "COMPLETE"}:
            raise ValueError("A source feature-cache path or metadata set differs")
        if set(row.get("layer_hashes", {})) != {"layer1", "layer2", "layer3"}:
            raise ValueError("A feature cache must bind all three frozen layers")
        for fingerprint in [*row["files"].values(), *row["layer_hashes"].values()]:
            _hex(fingerprint)


def _publication_contract(meta, prefix, declared, registry, provenance):
    tables = _json(meta[prefix + "tables.json"])
    table_names = {"baseline", "baseline_macro", "baseline_summary", "category_summary", "improvement",
        "paired_improvement", "paired_improvement_summary", "sampling_paired", "sampling_summary", "ablations",
        "loco", "image_metrics", "pixel_metrics", "resources", "size_recall", "shared_extraction", "mask_areas"}
    if not isinstance(tables, dict) or set(tables) != table_names or any(not isinstance(rows, list) for rows in tables.values()):
        raise ValueError("The published statistical table set differs")
    expected_counts = {"baseline": 180, "baseline_macro": 30, "baseline_summary": 10,
        "improvement": 90, "image_metrics": 370, "pixel_metrics": 74, "loco": 60, "resources": 66, "shared_extraction": 8}
    if any(len(tables[name]) != count for name, count in expected_counts.items()):
        raise ValueError("Published analysis tables do not cover the complete frozen matrix")
    anomalies = {row["path"]: (dataset, category) for dataset, categories in CATEGORIES.items() for category in categories
        for row in _json(meta["manifests/manifest_" + dataset + "_" + category + ".json"])["test"]["anomalies"]}
    areas = tables["mask_areas"]
    if len(areas) != len(anomalies) or {row.get("path") for row in areas} != set(anomalies):
        raise ValueError("Mask-area statistics do not cover each frozen anomaly once")
    for row in areas:
        if (row.get("dataset"), row.get("category")) != anomalies[row["path"]] or type(row.get("area_pixels")) is not int or type(row.get("original_pixels")) is not int or not 0 <= row["area_pixels"] <= row["original_pixels"] or row["original_pixels"] <= 0:
            raise ValueError("Original-resolution union-mask counts are invalid")
        if row.get("area_fraction") != row["area_pixels"] / row["original_pixels"] or row.get("size_group") not in ("small", "middle", "large"):
            raise ValueError("Mask-area fraction or quartile group differs")
    caches = {(row["dataset"], row["category"]): row for row in registry["caches"]}
    if {(row.get("dataset"), row.get("category")) for row in tables["shared_extraction"]} != set(caches):
        raise ValueError("Shared extraction must be recorded once per accepted category")
    for row in tables["shared_extraction"]:
        cache = caches[(row["dataset"], row["category"])]
        if row.get("cache_path") != cache["path"] or row.get("metadata_sha256") != cache["files"]["metadata.json"]:
            raise ValueError("Shared extraction provenance differs from the accepted cache metadata")
    expected = set(TOP - {"SUCCESS", "artifacts.sha256"}) | {"tables/" + name + ".csv" for name in table_names}
    cases = _json(meta[prefix + "cases.json"])
    records = cases.get("cases")
    if cases.get("schema_version") != "1.0" or not isinstance(records, list) or len(records) != 16:
        raise ValueError("Case publication exceeds its selected-image scope")
    if cases.get("selection_policy") != _json(meta[CONFIG]).get("case_policy"):
        raise ValueError("Case selection policy differs from the approved configuration")
    by_id = {row["identity_sha256"]: row for row in registry["results"]}
    if any(sum(row.get("dataset") == dataset and row.get("category") == category for row in records) != 2
            for dataset, categories in CATEGORIES.items() for category in categories):
        raise ValueError("Selected cases must retain both examples for all eight frozen categories")
    for category in CATEGORIES["mvtec_loco"]:
        if {row.get("group") for row in records if row.get("dataset") == "mvtec_loco" and row.get("category") == category} != {"logical_anomalies", "structural_anomalies"}:
            raise ValueError("LOCO cases must retain one logical and one structural example")
    seen = set()
    for number, record in enumerate(records, 1):
        identifier = "%03d" % number; folder = "cases/" + identifier
        if record.get("case_id") != identifier or record.get("path") in seen:
            raise ValueError("Selected cases repeat or have nonsequential identities")
        seen.add(record.get("path"))
        dataset, category = record.get("dataset"), record.get("category")
        if dataset not in CATEGORIES or category not in CATEGORIES[dataset]:
            raise ValueError("Selected case belongs to another dataset")
        manifest = _json(meta["manifests/manifest_" + dataset + "_" + category + ".json"])
        found = [row for row in manifest["test"]["good"] + manifest["test"]["anomalies"] if row["path"] == record.get("path")]
        if len(found) != 1:
            raise ValueError("Selected case is absent from the frozen test split")
        source = found[0]; anomaly = source in manifest["test"]["anomalies"]
        defect = source.get("defect_type", "good")
        if record.get("raw_image_sha256") != source["sha256"] or type(record.get("label")) is not int or record["label"] != int(anomaly) or record.get("defect_type") != defect or record.get("group") != defect:
            raise ValueError("Selected case source fingerprint or label differs")
        if record.get("image_path") != folder + "/image.png" or record.get("mask_path") != folder + "/mask_union.png":
            raise ValueError("Selected image or union mask path differs")
        if declared.get(folder + "/image.png") != source["sha256"]:
            raise ValueError("Selected image copy differs from its frozen original")
        expected.update((folder + "/image.png", folder + "/mask_union.png", folder + "/case.json"))
        source_ids = record.get("source_result_ids")
        if not isinstance(source_ids, dict) or set(source_ids) != {"padim", "patchcore"}:
            raise ValueError("Selected cases require the paired baseline methods")
        maps = record.get("maps")
        if not isinstance(maps, dict) or set(maps) != set(source_ids):
            raise ValueError("Selected cases require exactly two continuous maps")
        for method, result_id in source_ids.items():
            result = by_id.get(result_id)
            if result is None:
                raise ValueError("Selected case references an unaccepted result")
            cfg = result["configuration"]
            if (cfg["dataset"], cfg["category"], cfg["method"], cfg["run_seed"], cfg["normal_train_n"], cfg["stage"]) != (dataset, category, method, 17, 100, "B0" if dataset == "mvtec_ad" else "B0_LOCO"):
                raise ValueError("Selected case does not use its fixed baseline pair")
            item = maps[method]; name = folder + "/" + method + "_map.npy"
            if item.get("path") != name or item.get("same_map_for_native_and_top_0.01") is not True or item.get("display_calibration") != "normal development maps, percentile 99.5":
                raise ValueError("Selected map or display calibration differs")
            if item.get("display_min") != 0 or not isinstance(item.get("display_max"), (int, float)) or isinstance(item.get("display_max"), bool) or not math.isfinite(item["display_max"]) or item["display_max"] <= 0:
                raise ValueError("Selected map display range is invalid")
            expected.add(name)
        scores = record.get("scores")
        if not isinstance(scores, list) or [(item.get("method"), item.get("score_rule")) for item in scores] != [("padim", "native"), ("patchcore", "native"), ("patchcore", "top_0.01")]:
            raise ValueError("Selected case decision coverage differs")
        for score in scores:
            method, rule = score["method"], score["score_rule"]
            expected_id = source_ids[method]
            references = [row for row in tables["image_metrics"] if row.get("result_identity_sha256") == expected_id and row.get("score_rule") == rule and row.get("group") == "pooled"]
            if len(references) != 1 or score.get("threshold") != references[0].get("threshold_95pct"):
                raise ValueError("Selected case threshold differs from its accepted normal-development rule")
            if any(score.get(key) != record.get(key) for key in ("dataset", "category", "path", "label", "defect_type")) or score.get("result_identity_sha256") != expected_id or score.get("run_seed") != 17:
                raise ValueError("Selected case decision refers to another sample or result")
            if isinstance(score.get("score"), bool) or not isinstance(score.get("score"), (int, float)) or not math.isfinite(score["score"]) or type(score.get("prediction")) is not bool or score["prediction"] != (score["score"] > score["threshold"]):
                raise ValueError("Selected case does not preserve its fixed strict threshold decision")
        failure = any(score["prediction"] != bool(record["label"]) for score in scores)
        if record.get("is_real_failure") is not failure or record.get("is_normal_false_positive") is not (failure and record["label"] == 0):
            raise ValueError("Selected failure-case labels contradict the saved decisions")
        masks = record.get("mask_sources")
        raw_masks = source.get("masks", [])
        if not isinstance(masks, list) or len(masks) != len(raw_masks):
            raise ValueError("Selected case omitted an original anomaly mask")
        for index, (mask, raw) in enumerate(zip(masks, raw_masks), 1):
            name = folder + "/masks/%03d.png" % index
            if mask != {**raw, "output_path": name} or declared.get(name) != raw["sha256"]:
                raise ValueError("Selected mask copy differs from its frozen original")
            expected.add(name)
    plots = _json(meta[prefix + "plot_manifest.json"])
    figures = plots.get("figures")
    if plots.get("status") != "passed" or not isinstance(figures, list) or not figures or plots.get("figure_count") != len(figures):
        raise ValueError("Published figure manifest is incomplete")
    if plots.get("plot_source_sha256") != provenance["identity"]["sources"]["scripts/plot_results_tc2_gpu.py"] or plots.get("input_provenance") != provenance or plots.get("metrics_changed_by_plotting") is not False:
        raise ValueError("Figure provenance differs from the executed analysis")
    names = []
    for figure in figures:
        name = figure.get("name")
        if not isinstance(name, str) or re.fullmatch(FIGURE, name) is None or name in names:
            raise ValueError("Figure identity is unsupported or repeated")
        names.append(name)
        if figure.get("dpi") != 300 or figure.get("alignment_status") not in ("passed", "not_applicable"):
            raise ValueError("Figure resolution or alignment did not pass")
        paths = {"figures/" + name + ".png", "figures/" + name + ".pdf", "source_data/" + name + ".json", "qa/" + name + ".alignment.json"}
        if not isinstance(figure.get("files"), dict) or set(figure["files"]) != paths:
            raise ValueError("A figure must include both exports, its source data and alignment evidence")
        for path, row in figure["files"].items():
            if row.get("sha256") != declared.get(path) or type(row.get("bytes")) is not int or not 0 < row["bytes"] <= LIMIT:
                raise ValueError("A figure artifact differs from its publication manifest")
        expected.update(paths)
    fixed = {"F1_methods", "baseline_comparison", "F3_hyperparameters", "F3_components", "F3_fewshot",
        "F4_improvement", "F4_q_sensitivity", "F4_score_distributions", "F4_defect_size", "F5_resources", "loco_extension"}
    expected_figures = fixed | {"F2_cases_%02d" % number for number in range(1, math.ceil(len(records) / 4) + 1)}
    if set(names) != expected_figures or set(declared) != expected:
        raise ValueError("Published analysis has missing or additional figure, case or table artifacts")
    return records


def _png_size(path):
    with path.open("rb") as stream:
        header = stream.read(33)
    if len(header) != 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[8:16] != b"\x00\x00\x00\rIHDR":
        raise ValueError("Analysis PNG has an invalid header")
    width, height = struct.unpack(">II", header[16:24])
    if not 0 < width <= 16384 or not 0 < height <= 16384 or width * height > 64 * 1024 * 1024:
        raise ValueError("Analysis PNG exceeds its bounded display pixel scope")
    return width, height


def _selected_map(path):
    with path.open("rb") as stream:
        if stream.read(6) != b"\x93NUMPY":
            raise ValueError("Selected continuous map is not an NPY file")
        version = stream.read(2)
        if version == b"\x01\x00":
            length_data = stream.read(2)
            if len(length_data) != 2:
                raise ValueError("Truncated NPY header")
            length = struct.unpack("<H", length_data)[0]
        elif version in (b"\x02\x00", b"\x03\x00"):
            length_data = stream.read(4)
            if len(length_data) != 4:
                raise ValueError("Truncated NPY header")
            length = struct.unpack("<I", length_data)[0]
        else:
            raise ValueError("Unsupported selected-map NPY version")
        if length > 4096:
            raise ValueError("Selected-map NPY header is oversized")
        try:
            header = ast.literal_eval(stream.read(length).decode("utf-8" if version == b"\x03\x00" else "latin1"))
        except (SyntaxError, ValueError, UnicodeError) as error:
            raise ValueError("Selected-map NPY header is invalid") from error
        if not isinstance(header, dict) or set(header) != {"descr", "fortran_order", "shape"} or header["descr"] != "<f4" or header["fortran_order"] is not False or header["shape"] != (256, 256):
            raise ValueError("Only selected FP32 256x256 maps may be exported; feature caches are excluded")
        remaining = 256 * 256 * 4
        while remaining:
            block = stream.read(min(65536, remaining))
            if not block or len(block) % 4:
                raise ValueError("Selected-map array data is truncated")
            if any(not math.isfinite(value[0]) for value in struct.iter_unpack("<f", block)):
                raise ValueError("Selected-map values must be finite")
            remaining -= len(block)
        if stream.read(1):
            raise ValueError("Selected-map file contains trailing or additional array data")


def _check_assets(directory, rows, metadata, state):
    if not state["step_8_complete"]:
        return
    prefix = state["analysis_path"] + "/"
    cases = _json(metadata[prefix + "cases.json"])["cases"]
    by_case = {row["case_id"]: row for row in cases}
    tables = _json(metadata[prefix + "tables.json"])
    plots = _json(metadata[prefix + "plot_manifest.json"])
    figure_files = {name: row for figure in plots["figures"] for name, row in figure["files"].items()}
    for name in rows:
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix):]; path = _inside(directory, name)
        if relative in TOP:
            continue
        if relative in figure_files and path.stat().st_size != figure_files[relative]["bytes"]:
            raise ValueError("Figure size differs from its rendering manifest")
        if relative.endswith(".png"):
            _png_size(path)
        elif relative.endswith(".npy"):
            _selected_map(path)
        elif relative.endswith(".pdf"):
            with path.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise ValueError("Published figure is not a PDF")
        elif relative.startswith("tables/"):
            table = relative[len("tables/"):-len(".csv")]
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream); expected = tables[table]
                for row in expected:
                    actual = next(reader, None)
                    if actual is None or set(actual) != set(row):
                        raise ValueError("CSV and JSON table fields or row counts differ")
                    for key, value in row.items():
                        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) if isinstance(value, (dict, list)) or value is None else str(value)
                        if actual[key] != text:
                            raise ValueError("CSV and JSON table values differ")
                if next(reader, None) is not None:
                    raise ValueError("CSV table contains additional rows")
        elif relative.startswith("cases/") and relative.endswith("/case.json"):
            if _json(_read_bounded(path, MAX_INDEX)) != by_case[relative.split("/")[1]]:
                raise ValueError("Per-case and selected-case metadata differ")
        elif relative.startswith("qa/"):
            record = _json(_read_bounded(path, MAX_INDEX))
            figure = next(row for row in plots["figures"] if relative in row["files"])
            if record.get("status") != figure["alignment_status"]:
                raise ValueError("Alignment receipt differs from its figure manifest")
        elif relative.startswith("source_data/"):
            record = _json(_read_bounded(path, MAX_INDEX))
            figure = next(row for row in plots["figures"] if relative in row["files"])
            if record.get("rendering_changes_metrics") is not False or record.get("question") != figure["question"] or not isinstance(record.get("rows"), list) or len(record["rows"]) != figure["source_row_count"]:
                raise ValueError("Figure source data differs from its rendering receipt")


def _metadata(meta, snapshot, job_id):
    """Validate small, repeated metadata without loading images or map arrays."""
    state = _status(snapshot, job_id)
    if _bytes_sha(meta[CONFIG]) != (state.get("config_sha256") or _bytes_sha(meta[CONFIG])):
        raise ValueError("Exported analysis configuration differs")
    if _bytes_sha(meta[PROTOCOL]) != PROTOCOL_SHA256 or _bytes_sha(meta[EXPERIMENT_CONFIG]) != DESIGN_SHA256:
        raise ValueError("Frozen protocol or experiment design bytes differ")
    design = _json(meta[EXPERIMENT_CONFIG])
    for name in MANIFESTS:
        if _bytes_sha(meta[name]) != design["scientific_source_hashes"][name]:
            raise ValueError("Frozen input manifest bytes differ")
    if state["status"] == "missing":
        return
    status_name = "run/validation_tc2_gpu/step8_job_" + job_id + "/setup_status.json"
    if _json(meta[status_name]) != state:
        raise ValueError("Exported execution record and snapshot differ")
    input_names = ["run/validation_tc2_gpu/step8_job_" + job_id + "/" + name for name in ("inputs.json", "analysis_inputs.json")]
    for inputs_name in input_names:
        if inputs_name not in meta:
            continue
        if _bytes_sha(meta[inputs_name]) != state["inputs_sha256"]:
            raise ValueError("Copied input registry fingerprint differs")
        _registry(_json(meta[inputs_name]), state, _json(meta[EXPERIMENT_CONFIG]))
    if not state["step_8_complete"]:
        return
    prefix = state["analysis_path"] + "/"
    for name in TOP:
        if prefix + name not in meta:
            raise ValueError("Final analysis metadata must travel on every page")
    registry_bytes = meta[prefix + "inputs.json"]
    if _bytes_sha(registry_bytes) != state["inputs_sha256"] or meta[prefix + "analysis_config.json"] != meta[CONFIG]:
        raise ValueError("Published analysis input or configuration bytes differ")
    registry = _json(registry_bytes)
    _registry(registry, state, design)
    provenance = _json(meta[prefix + "provenance.json"])
    identity = provenance.get("identity")
    expected = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "stage": "analysis", "job_id": job_id,
        "protocol_sha256": PROTOCOL_SHA256, "design_sha256": DESIGN_SHA256, "inputs_sha256": state["inputs_sha256"],
        "analysis_config_sha256": state["config_sha256"], "sources": state["sources"]}
    if identity != expected or _digest(identity) != state["identity_sha256"]:
        raise ValueError("Published analysis identity is not bound to its executed inputs")
    marker = {"status": "passed", "namespace": "analysis", "job_id": job_id,
        "identity_sha256": state["identity_sha256"], "artifacts_sha256": _bytes_sha(meta[prefix + "artifacts.sha256"])}
    if _json(meta[prefix + "SUCCESS"]) != marker:
        raise ValueError("Published analysis completion marker differs")
    declared = _artifact_manifest(meta[prefix + "artifacts.sha256"])
    for name in TOP - {"SUCCESS", "artifacts.sha256"}:
        if _bytes_sha(meta[prefix + name]) != declared[name]:
            raise ValueError("Repeated analysis metadata differs from its publication manifest")
    verification = _json(meta[prefix + "verification.json"])
    if verification.get("status") != "passed" or verification.get("result_count") != 66 or verification.get("analysis_rows") != 108 or verification.get("unique_pc_analysis_rows") != 90:
        raise ValueError("Published analysis has not passed its own verification")
    if any(verification.get(name) is not True for name in ("tables_verified", "figures_verified", "source_artifacts_verified")) or verification.get("pixel_metrics_recomputed") is not False:
        raise ValueError("Published analysis verification scope differs")
    if provenance.get("source_artifacts_verified") is not True or provenance.get("pixel_metrics_recomputed") is not False:
        raise ValueError("Analysis provenance makes a different verification claim")
    cases = _publication_contract(meta, prefix, declared, registry, provenance)
    if verification.get("case_count") != len(cases):
        raise ValueError("Verification and selected-case counts differ")


def _file_record(root, name, job_id, analysis_path, snapshots=None):
    path = (snapshots or {}).get(name, _inside(root, name))
    if not path.is_file():
        raise ValueError("A declared snapshot file is absent")
    size = path.stat().st_size
    if size > LIMIT:
        raise ValueError("One artifact exceeds the unchanged 512 MiB page limit")
    return {"path": name, "size": size, "sha256": _sha(path), "role": _role(name, job_id, analysis_path)}


def _metadata_bytes(root, names, snapshots=None):
    return {name: _read_bounded((snapshots or {}).get(name, _inside(root, name)), MAX_INDEX) for name in names}


def _rows(rows, job_id, analysis_path):
    if not isinstance(rows, list) or len(rows) >= MAX_MEMBERS:
        raise ValueError("Invalid analysis collection member count")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256", "role"}:
            raise ValueError("Invalid collection file record fields")
        name = _relative(row["path"])
        if name.casefold() in seen or type(row["size"]) is not int or not 0 <= row["size"] <= LIMIT:
            raise ValueError("Duplicate or oversized collection artifact")
        seen.add(name.casefold()); _hex(row["sha256"])
        if row["role"] != _role(name, job_id, analysis_path):
            raise ValueError("Collection member role differs")
    return {row["path"]: row for row in rows}


def _tar_size(rows, manifest_bytes):
    length = sum(512 + ((row["size"] + 511) // 512) * 512 for row in rows)
    length += 512 + ((len(manifest_bytes) + 511) // 512) * 512 + 1024
    return ((length + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE


def _write_page(root, target, rows, manifest, snapshots=None):
    encoded = _encode(manifest)
    if _tar_size(rows, encoded) > LIMIT:
        raise ValueError("Page exceeds the unchanged decompressed 512 MiB bound")
    with target.open("xb") as destination:
        with gzip.GzipFile(fileobj=destination, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.USTAR_FORMAT) as package:
                for row in rows:
                    path = (snapshots or {}).get(row["path"], _inside(root, row["path"]))
                    if path.stat().st_size != row["size"] or _sha(path) != row["sha256"]:
                        raise ValueError("Source artifact changed while collecting")
                    info = tarfile.TarInfo(row["path"]); info.size = row["size"]; info.mode = 0o600
                    with path.open("rb") as source:
                        package.addfile(info, source)
                info = tarfile.TarInfo(MANIFEST); info.size = len(encoded); info.mode = 0o600
                package.addfile(info, io.BytesIO(encoded))
        destination.flush(); os.fsync(destination.fileno())
    if target.stat().st_size > LIMIT:
        raise ValueError("Compressed page exceeds the unchanged 512 MiB bound")
    for row in rows:
        if _sha((snapshots or {}).get(row["path"], _inside(root, row["path"]))) != row["sha256"]:
            raise ValueError("Source artifact changed during collection")


def export_pages(root, job_id, directory):
    if not Path(directory).is_absolute():
        raise ValueError("Export directory must be absolute")
    parent = _extended(directory).parent
    _no_links(parent)
    with tempfile.TemporaryDirectory(prefix="analysis-snapshot-", dir=parent) as temporary:
        return _export_pages(root, job_id, directory, _extended(temporary))


def _export_pages(root, job_id, directory, snapshot_root):
    job_id = _job(job_id)
    if not Path(directory).is_absolute():
        raise ValueError("Export directory must be absolute")
    root, directory = _extended(root), _extended(directory)
    _no_links(root); _no_links(directory)
    if not root.is_dir() or not directory.parent.is_dir() or directory.exists():
        raise ValueError("Export requires a fresh directory and existing parent")
    status_name = "run/validation_tc2_gpu/step8_job_" + job_id + "/setup_status.json"
    status_path = _inside(root, status_name)
    status_bytes = _read_bounded(status_path, MAX_INDEX) if status_path.is_file() else None
    state = _status(_json(status_bytes), job_id) if status_bytes else {"job_id": job_id, "status": "missing", "stage_id": "analysis", "step_8_complete": False}
    if status_bytes:
        for name, expected in state["sources"].items():
            if _sha(_inside(root, name)) != expected:
                raise ValueError("An approved analysis source changed before collection")
    analysis_path = state.get("analysis_path") if state["step_8_complete"] else None
    common = {CONFIG, EXPERIMENT_CONFIG, PROTOCOL} | MANIFESTS
    for suffix in (".out", ".err"):
        name = "run/validation_tc2_gpu/slurm-" + job_id + suffix
        if _inside(root, name).is_file():
            common.add(name)
    if status_bytes:
        for path in status_path.parent.iterdir():
            _no_links(path)
            if path.is_file() and (path.name in JOB_FILES or PHASE.fullmatch(path.name)):
                common.add(status_path.parent.relative_to(root).as_posix() + "/" + path.name)
        for tail in JOB_FILES:
            name = status_path.parent.relative_to(root).as_posix() + "/" + tail
            if _inside(root, name).is_file():
                common.add(name)
    outputs = []
    if state["step_8_complete"]:
        path = _inside(root, _analysis_path(analysis_path))
        declared = _artifact_manifest(_read_bounded(_inside(path, "artifacts.sha256"), MAX_INDEX))
        expected = set(declared) | {"artifacts.sha256", "SUCCESS"}
        actual = set()
        for entry in path.rglob("*"):
            _no_links(entry)
            if entry.is_file():
                actual.add(entry.relative_to(path).as_posix())
        if actual != expected:
            raise ValueError("Published analysis contains missing or undeclared artifacts")
        for name in declared:
            if _sha(_inside(path, name)) != declared[name]:
                raise ValueError("Published analysis artifact differs from its manifest")
        common.update(analysis_path + "/" + name for name in REPEATED)
        outputs = sorted(analysis_path + "/" + name for name in expected - REPEATED)
    snapshots = {}
    for name in common:
        if not name.startswith("run/validation_tc2_gpu/"):
            continue
        source, target = _inside(root, name), _inside(snapshot_root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as destination:
            if name == status_name:
                destination.write(status_bytes)
            else:
                copied = 0
                with source.open("rb") as original:
                    for block in iter(lambda: original.read(1024 * 1024), b""):
                        copied += len(block)
                        if copied > LIMIT:
                            raise ValueError("A live analysis record exceeds its collection bound")
                        destination.write(block)
        snapshots[name] = target
    metadata_names = sorted(name for name in common if name in {CONFIG, EXPERIMENT_CONFIG, PROTOCOL} | MANIFESTS
        or (name.startswith("run/validation_tc2_gpu/") and name[len(status_path.parent.relative_to(root).as_posix()) + 1:] in JOB_FILES and name.endswith(".json"))
        or (analysis_path and name.startswith(analysis_path + "/") and name[len(analysis_path) + 1:] in TOP))
    metadata = _metadata_bytes(root, metadata_names, snapshots)
    if status_bytes:
        metadata[status_name] = status_bytes
    _metadata(metadata, state, job_id)
    registry_name = analysis_path + "/inputs.json" if analysis_path else None
    if registry_name:
        for name, expected in _json(metadata[registry_name])["protected_sources"].items():
            if _sha(_inside(root, name)) != expected:
                raise ValueError("A protected experiment source changed before collection")
    common_rows = [_file_record(root, name, job_id, analysis_path, snapshots) for name in sorted(common)]
    if status_bytes:
        next(row for row in common_rows if row["path"] == status_name).update(size=len(status_bytes), sha256=_bytes_sha(status_bytes))
    output_rows = [_file_record(root, name, job_id, analysis_path) for name in outputs]
    _check_assets(root, {row["path"]: row for row in common_rows + output_rows}, metadata, state)
    export_id = uuid.uuid4().hex.upper(); created = datetime.now(timezone.utc).isoformat()
    base = {"schema_version": "1.0", "export_id": export_id, "job_id": job_id, "stage_id": "analysis",
        "analysis_path": analysis_path, "snapshot_status": state, "snapshot_sha256": _digest(state),
        "partial": not state["step_8_complete"], "collector_provenance": _provenance(), "created_utc": created}
    groups, current = [], []
    for row in output_rows:
        candidate = common_rows + current + [row]
        provisional = {**base, "page_number": MAX_PAGES, "page_count": MAX_PAGES, "files": candidate}
        if len(candidate) + 1 > MAX_MEMBERS or _tar_size(candidate, _encode(provisional)) > LIMIT:
            if not current:
                raise ValueError("A complete analysis artifact exceeds the unchanged page bound")
            groups.append(current); current = []
        current.append(row)
    groups.append(current)
    if len(groups) > MAX_PAGES:
        raise ValueError("Analysis collection exceeds its 32-page bound")
    directory.mkdir()
    pages = []
    for number, group in enumerate(groups, 1):
        rows = common_rows + group
        manifest = {**base, "page_number": number, "page_count": len(groups), "files": rows}
        name = "page_%03d.tar.gz" % number; target = directory / name
        _write_page(root, target, rows, manifest, snapshots)
        pages.append({"name": name, "page_number": number, "sha256": _sha(target), "bytes": target.stat().st_size,
            "files": rows})
    index = {**base, "page_count": len(pages), "pages": pages,
        "all_artifact_paths": sorted(set(common) | set(outputs)), "config_sha256": _bytes_sha(metadata[CONFIG]),
        "protocol_sha256": PROTOCOL_SHA256, "inputs_sha256": state.get("inputs_sha256")}
    encoded = _encode(index)
    if len(encoded) > MAX_INDEX:
        raise ValueError("Analysis index exceeds its metadata bound")
    index_path = directory / "index.json"
    with index_path.open("xb") as stream:
        stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    return {"job_id": job_id, "directory": _plain(directory), "index_path": _plain(index_path),
        "index_sha256": _sha(index_path), "pages": pages, "page_count": len(pages), "partial": index["partial"],
        "stage_id": "analysis", "stage_complete": state["step_8_complete"], "step_8_complete": state["step_8_complete"],
        "collector_provenance": index["collector_provenance"]}


def _validate_index(value, job_id):
    if not isinstance(value, dict) or value.get("schema_version") != "1.0" or value.get("job_id") != job_id or value.get("stage_id") != "analysis" or re.fullmatch(r"[0-9A-F]{32}", value.get("export_id", "")) is None:
        raise ValueError("Analysis collection index identity differs")
    state = _status(value.get("snapshot_status"), job_id)
    if value.get("snapshot_sha256") != _digest(state) or value.get("partial") != (not state["step_8_complete"]) or value.get("collector_provenance") != _provenance():
        raise ValueError("Analysis index snapshot or collector fingerprint differs")
    path = value.get("analysis_path")
    if state["step_8_complete"]:
        if path != state["analysis_path"]:
            raise ValueError("Analysis index output directory differs")
    elif path is not None:
        raise ValueError("An incomplete snapshot must not export analysis outputs")
    pages = value.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES or value.get("page_count") != len(pages):
        raise ValueError("Analysis page count exceeds its bound")
    union, page_hashes = {}, set()
    for number, page in enumerate(pages, 1):
        if not isinstance(page, dict) or set(page) != {"name", "page_number", "sha256", "bytes", "files"} or page.get("name") != "page_%03d.tar.gz" % number or page.get("page_number") != number:
            raise ValueError("Analysis pages are not a bounded sequential layout")
        _hex(page["sha256"])
        if page["sha256"] in page_hashes or type(page["bytes"]) is not int or not 0 < page["bytes"] <= LIMIT:
            raise ValueError("Analysis page is repeated or oversized")
        page_hashes.add(page["sha256"])
        rows = _rows(page["files"], job_id, path)
        for name, row in rows.items():
            if name in union and union[name] != row:
                raise ValueError("Repeated analysis metadata has different bytes")
            union[name] = row
    if value.get("all_artifact_paths") != sorted(union) or not ({CONFIG, EXPERIMENT_CONFIG, PROTOCOL} | MANIFESTS) <= set(union):
        raise ValueError("Analysis index artifact coverage differs")
    if value.get("protocol_sha256") != PROTOCOL_SHA256 or union[CONFIG]["sha256"] != value.get("config_sha256"):
        raise ValueError("Analysis index protocol or configuration differs")
    if state["status"] != "missing" and (value.get("config_sha256") != state["config_sha256"] or value.get("inputs_sha256") != state["inputs_sha256"]):
        raise ValueError("Analysis index and execution input fingerprints differ")
    return value


def _index(path, job_id):
    path = _extended(path); _no_links(path)
    return _validate_index(_json(_read_bounded(path, MAX_INDEX)), _job(job_id))


def verify_index(path, expected_sha, job_id):
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", expected_sha) or _sha(path) != expected_sha.upper():
        raise ValueError("Analysis index SHA256 differs")
    value = _index(path, job_id)
    return {"status": "verified", "job_id": _job(job_id), "stage_id": "analysis", "index_sha256": _sha(path),
        "page_count": value["page_count"], "pages": value["pages"], "partial": value["partial"],
        "stage_complete": False, "step_8_complete": False, "remote_stage_complete": value["snapshot_status"]["step_8_complete"]}


def _check_manifest(manifest, index, page):
    fields = ("schema_version", "export_id", "job_id", "stage_id", "analysis_path", "snapshot_status",
        "snapshot_sha256", "partial", "collector_provenance", "created_utc", "page_count")
    if any(manifest.get(key) != index.get(key) for key in fields) or manifest.get("page_number") != page["page_number"] or manifest.get("files") != page["files"]:
        raise ValueError("Analysis page belongs to another index, source or snapshot")


def _metadata_from_directory(directory, rows, index):
    path = index["analysis_path"]
    names = {name for name in rows if name in {CONFIG, EXPERIMENT_CONFIG, PROTOCOL} | MANIFESTS
        or ("/step8_job_" in name and name.rsplit("/", 1)[-1] in JOB_FILES)
        or (path and name.startswith(path + "/") and name[len(path) + 1:] in TOP)}
    return _metadata_bytes(directory, names)


def verify_archive(archive, expected_sha, job_id, destination, index_path):
    job_id = _job(job_id); archive, destination = _extended(archive), _extended(destination)
    _no_links(archive); _no_links(destination)
    index = _index(index_path, job_id)
    if not isinstance(expected_sha, str) or re.fullmatch(r"[0-9A-Fa-f]{64}", expected_sha) is None:
        raise ValueError("Expected analysis archive fingerprint is invalid")
    matches = [page for page in index["pages"] if page["sha256"] == expected_sha.upper()]
    if len(matches) != 1:
        raise ValueError("Analysis archive does not identify one index page")
    page = matches[0]
    if not archive.is_file() or archive.stat().st_size != page["bytes"] or _sha(archive) != expected_sha.upper():
        raise ValueError("Analysis archive bytes or fingerprint differ")
    if destination.exists() or not destination.parent.is_dir():
        raise ValueError("Analysis extraction requires a fresh destination")
    expected = _rows(page["files"], job_id, index["analysis_path"])
    with tempfile.TemporaryDirectory(prefix="analysis-verified-", dir=destination.parent) as temporary:
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
                        raise ValueError("Analysis archive exceeds the decompressed 512 MiB bound")
                    raw.write(block)
            raw.seek(0); _tar_layout(raw, length)
            observed, total, manifest_bytes = set(), 0, None
            with tarfile.open(fileobj=raw, mode="r:") as package:
                for item in package:
                    name = _relative(item.name)
                    if name.casefold() in observed or len(observed) >= MAX_MEMBERS or not item.isfile() or item.pax_headers or item.size < 0 or item.size > LIMIT - total:
                        raise ValueError("Duplicate, linked, extended or oversized analysis archive member")
                    observed.add(name.casefold()); total += item.size
                    stream = package.extractfile(item)
                    if stream is None:
                        raise ValueError("Unreadable analysis member")
                    if name == MANIFEST:
                        if item.size > MAX_INDEX:
                            raise ValueError("Analysis page manifest is too large")
                        manifest_bytes = stream.read(item.size + 1)
                        if len(manifest_bytes) != item.size:
                            raise ValueError("Truncated analysis manifest")
                        continue
                    if name not in expected or item.size != expected[name]["size"]:
                        raise ValueError("Undeclared or differently sized analysis member")
                    target = _inside(staging, name); target.parent.mkdir(parents=True, exist_ok=True)
                    digest, copied = hashlib.sha256(), 0
                    with target.open("xb") as output:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            copied += len(block)
                            if copied > item.size:
                                raise ValueError("Analysis member exceeds its declared size")
                            digest.update(block); output.write(block)
                    if copied != item.size or digest.hexdigest().upper() != expected[name]["sha256"]:
                        raise ValueError("Analysis member fingerprint differs")
            if manifest_bytes is None or observed != {name.casefold() for name in expected} | {MANIFEST.casefold()}:
                raise ValueError("Analysis archive is incomplete")
            _check_manifest(_json(manifest_bytes), index, page)
            metadata = _metadata_from_directory(staging, expected, index)
            _metadata(metadata, index["snapshot_status"], job_id)
            _check_assets(staging, expected, metadata, index["snapshot_status"])
            with (staging / MANIFEST).open("xb") as stream:
                stream.write(manifest_bytes)
        receipt = {"status": "verified", "job_id": job_id, "export_id": index["export_id"],
            "page_number": page["page_number"], "index_sha256": _sha(index_path), "archive_sha256": expected_sha.upper(),
            "manifest_sha256": _bytes_sha(manifest_bytes), "file_count": len(expected),
            "collector_provenance": index["collector_provenance"], "stage_complete": False, "step_8_complete": False}
        with (staging / RECEIPT).open("xb") as stream:
            stream.write(_encode(receipt))
        # Exclusive creation preserves any destination created by another process.
        destination.mkdir()
        for name in [*expected, MANIFEST, RECEIPT]:
            target = _inside(destination, name); target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_publish(_inside(staging, name), target)
    return {**receipt, "destination": _plain(destination), "partial": index["partial"],
        "remote_stage_complete": index["snapshot_status"]["step_8_complete"], "raw_dataset_exported": False,
        "feature_cache_arrays_exported": False}


def verify_collection(index_path, directory, job_id):
    job_id = _job(job_id); directory = _extended(directory); _no_links(directory)
    index = _index(index_path, job_id); union = {}
    for page in index["pages"]:
        base = _inside(directory, "page_%03d" % page["page_number"])
        receipt = _json(_read_bounded(_inside(base, RECEIPT), MAX_INDEX))
        required = {"status": "verified", "job_id": job_id, "export_id": index["export_id"],
            "page_number": page["page_number"], "index_sha256": _sha(index_path), "archive_sha256": page["sha256"],
            "collector_provenance": index["collector_provenance"]}
        if any(receipt.get(key) != value for key, value in required.items()):
            raise ValueError("Analysis collection is missing a matching page receipt")
        manifest_bytes = _read_bounded(_inside(base, MANIFEST), MAX_INDEX)
        if _bytes_sha(manifest_bytes) != receipt.get("manifest_sha256"):
            raise ValueError("Verified analysis page manifest changed")
        manifest = _json(manifest_bytes); _check_manifest(manifest, index, page)
        expected = _rows(page["files"], job_id, index["analysis_path"])
        observed = set()
        for path in base.rglob("*"):
            _no_links(path)
            if path.is_file():
                observed.add(path.relative_to(base).as_posix())
        if observed != set(expected) | {MANIFEST, RECEIPT}:
            raise ValueError("Analysis collection page contains missing or extra files")
        for name, row in expected.items():
            target = _inside(base, name)
            if target.stat().st_size != row["size"] or _sha(target) != row["sha256"]:
                raise ValueError("An extracted analysis file changed after verification")
            union[name] = row
        metadata = _metadata_from_directory(base, expected, index)
        _metadata(metadata, index["snapshot_status"], job_id)
        _check_assets(base, expected, metadata, index["snapshot_status"])
    if sorted(union) != index["all_artifact_paths"]:
        raise ValueError("Analysis collection does not contain every indexed output")
    state = index["snapshot_status"]
    if state["step_8_complete"]:
        path = state["analysis_path"]
        first = _inside(directory, "page_001")
        declared = _artifact_manifest(_read_bounded(_inside(first, path + "/artifacts.sha256"), MAX_INDEX))
        expected_outputs = {path + "/" + name for name in {*declared, "artifacts.sha256", "SUCCESS"}}
        actual_outputs = {name for name in union if name.startswith(path + "/")}
        if actual_outputs != expected_outputs:
            raise ValueError("Final analysis collection omits a published artifact")
        for name, digest in declared.items():
            if union[path + "/" + name]["sha256"] != digest:
                raise ValueError("Collected analysis and publication fingerprints differ")
    return {"status": "verified", "job_id": job_id, "stage_id": "analysis", "index_sha256": _sha(index_path),
        "page_count": len(index["pages"]), "file_count": len(union), "partial": index["partial"],
        "stage_complete": state["step_8_complete"], "step_8_complete": state["step_8_complete"],
        "results_count": 66 if state["step_8_complete"] else 0, "analysis_rows": 108 if state["step_8_complete"] else 0,
        "completion_scope": "approved_analysis_outputs_only", "raw_dataset_exported": False,
        "feature_cache_arrays_exported": False, "post_download_visual_review_required": True,
        "visual_review_performed": False, "collector_provenance": index["collector_provenance"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest="action", required=True)
    export = commands.add_parser("export")
    for name in ("root", "job-id", "directory"):
        export.add_argument("--" + name, required=True)
    index = commands.add_parser("verify-index")
    for name in ("index", "sha256", "job-id"):
        index.add_argument("--" + name, required=True)
    archive = commands.add_parser("verify")
    for name in ("archive", "sha256", "job-id", "destination", "index"):
        archive.add_argument("--" + name, required=True)
    collection = commands.add_parser("verify-collection")
    for name in ("index", "directory", "job-id"):
        collection.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if args.action == "export":
        value = export_pages(args.root, args.job_id, args.directory)
    elif args.action == "verify-index":
        value = verify_index(args.index, args.sha256, args.job_id)
    elif args.action == "verify":
        value = verify_archive(args.archive, args.sha256, args.job_id, args.destination, args.index)
    else:
        value = verify_collection(args.index, args.directory, args.job_id)
    print(json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
