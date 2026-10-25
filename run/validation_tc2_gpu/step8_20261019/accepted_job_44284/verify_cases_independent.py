"""Read-only, independent case/asset/plot-lineage audit of CPU analysis 44284.

This script never imports project analysis, model, or pixel-metric implementations.
It reads only frozen manifests and explicitly accepted step-7 archive locations.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
OUTPUT = Path(r"\\?\C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS\output\tc2_gpu_setup_20261019_220347_4dc4d911\remote\page_001\run\tc2_gpu\summaries\analysis\6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C")
AUDIT = ROOT / "run/validation_tc2_gpu/step8_20261019/accepted_job_44284"


def ext(path: Path | str) -> Path:
    value = str(path)
    return Path(value if value.startswith("\\\\?\\") else "\\\\?\\" + str(Path(value).absolute()))


def read(path: Path):
    return json.loads(ext(path).read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with ext(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def require(condition, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def main() -> dict:
    cases = read(OUTPUT / "cases.json")
    tables = read(OUTPUT / "tables.json")
    registry = read(OUTPUT / "inputs.json")
    candidates = cases["candidates"]
    selected = cases["cases"]
    candidate_by_path = {value["path"]: value for value in candidates}
    require(len(candidate_by_path) == len(candidates) == 1392, "Candidate paths repeat or are incomplete")
    require(len(selected) == 16 and len({value["path"] for value in selected}) == 16, "Selected case quota differs")

    accepted = read(ROOT / "run/validation_tc2_gpu/step7_20261019/setup_status.json")
    expected_stages = {value["stage_id"]: value for value in accepted["accepted_step_7_stages"]}
    pages_by_run = {}
    stage_sources = {}
    for stage in registry["stages"]:
        frozen = expected_stages[stage["stage_id"]]
        acceptance_path = ROOT / frozen["record"]
        require(sha(acceptance_path) == frozen["record_sha256"] == stage["acceptance_sha256"], "Stage acceptance record hash differs")
        value = read(acceptance_path)
        stage_sources[stage["stage_id"]] = value["source_directory"]
        for key, page in value.get("result_page_locations", {}).items():
            if key in pages_by_run:
                require(pages_by_run[key] == page, "Run appears under conflicting accepted pages")
            pages_by_run[key] = page

    manifests = {}
    manifest_images = {}
    expected_test_paths = set()
    expected_anomaly_paths = set()
    for cache in registry["caches"]:
        key = (cache["dataset"], cache["category"])
        relative = "manifests/manifest_%s_%s.json" % key
        require(sha(ROOT / relative) == registry["protected_sources"][relative], "A frozen manifest changed")
        manifest = read(ROOT / relative)
        manifests[key] = manifest
        for row in manifest["test"]["good"] + manifest["test"]["anomalies"]:
            require(row["path"] not in manifest_images, "Frozen test image repeated")
            manifest_images[row["path"]] = row
            expected_test_paths.add(row["path"])
        expected_anomaly_paths.update(row["path"] for row in manifest["test"]["anomalies"])
    require(set(candidate_by_path) == expected_test_paths, "The candidate register is not the complete frozen test set")

    area_by_path = {row["path"]: row for row in tables["mask_areas"]}
    require(len(area_by_path) == len(tables["mask_areas"]) == 982, "Mask area paths repeat or are incomplete")
    require(set(area_by_path) == expected_anomaly_paths, "Mask area register omits a frozen anomaly")
    area_summary = []
    for key, manifest in manifests.items():
        rows = [area_by_path[item["path"]] for item in manifest["test"]["anomalies"]]
        ordered = sorted(rows, key=lambda item: (item["area_fraction"], item["path"]))
        count = math.ceil(len(rows) / 4)
        expected_small = {item["path"] for item in ordered[:count]}
        expected_large = {item["path"] for item in ordered[-count:]}
        for item in rows:
            require(type(item["area_pixels"]) is int and 0 < item["area_pixels"] <= item["original_pixels"], "Original-mask area is invalid")
            require(item["area_fraction"] == item["area_pixels"] / item["original_pixels"], "Area fraction differs from its integer counts")
            expected = "small" if item["path"] in expected_small else "large" if item["path"] in expected_large else "middle"
            require(item["size_group"] == expected, "Area quartile does not use category-local ranks and path-order ties")
        area_summary.append({"dataset": key[0], "category": key[1], "anomaly_count": len(rows), "small_count": count, "large_count": count})

    baseline_records = [row for row in registry["results"] if row["configuration"]["stage"] in ("B0", "R0", "B0_LOCO")]
    records_needed = [row for row in baseline_records if row["configuration"]["run_seed"] == 17 or row["configuration"]["method"] == "patchcore"]
    score_lookup = {}
    samples_lookup = {}
    calibration = {}
    source_evidence = []
    selected_map_checks = []
    all_size_rows = {(row["category"], row["method"], row["run_seed"], row["score_rule"], row["size_group"]): row for row in tables["size_recall"]}
    size_rows_verified = 0
    for source in records_needed:
        cfg = source["configuration"]
        stage = cfg["stage"]
        base = ext(pages_by_run.get(source["run_key"], stage_sources[stage]))
        if source["run_key"] not in pages_by_run:
            matches = []
            for page in list((base / "remote").glob("page_*")) + list(base.glob("page_*")):
                if (page / source["path"] / "samples.json").is_file():
                    matches.append(page)
            require(len(matches) == 1, "Accepted source page is ambiguous or missing")
            base = matches[0]
        directory = base / source["path"]
        for name in ("samples.json", "metrics.json", "predictions.npz", "evidence.json"):
            require(sha(directory / name) == source["files"][name], "Accepted saved artifact hash differs: " + source["run_key"] + "/" + name)
        samples = read(directory / "samples.json")
        metrics = read(directory / "metrics.json")
        samples_lookup[source["identity_sha256"]] = samples
        for row in samples["test"]:
            if row["label"]:
                height, width = row["orig_hw"]
                require(area_by_path[row["path"]]["original_pixels"] == height * width, "Mask-area dimensions differ from accepted original image dimensions")
        with np.load(directory / "predictions.npz", allow_pickle=False) as archive:
            rules = ("native", "max", "top_0.01")
            for rule in rules:
                values = archive["test_score_" + rule]
                require(values.dtype == np.float32 and len(values) == len(samples["test"]) and np.isfinite(values).all(), "Saved image scores invalid")
                threshold = metrics["image"][rule]["threshold_95pct"]
                for sample, value in zip(samples["test"], values):
                    key = (cfg["dataset"], cfg["category"], cfg["method"], cfg["run_seed"], rule, sample["path"])
                    require(key not in score_lookup, "Baseline source score repeated")
                    score_lookup[key] = {"score": float(value), "threshold": threshold, "prediction": bool(float(value) > threshold), "label": sample["label"], "defect_type": sample["defect_type"], "identity": source["identity_sha256"]}
                if cfg["dataset"] == "mvtec_ad":
                    for size in ("small", "large"):
                        indices = [index for index, sample in enumerate(samples["test"]) if sample["path"] in area_by_path and area_by_path[sample["path"]]["size_group"] == size]
                        row = all_size_rows[(cfg["category"], cfg["method"], cfg["run_seed"], rule, size)]
                        require(row["n_images"] == len(indices) and row["recall"] == float(np.mean(values[indices] > threshold)), "Recorded size-group recall differs from accepted saved image scores")
                        size_rows_verified += 1
            matching_cases = [case for case in selected if case["source_result_ids"].get(cfg["method"]) == source["identity_sha256"]]
            if matching_cases:
                dev = archive["dev_maps"]
                require(dev.dtype == np.float32 and dev.shape[0] == len(samples["dev"]) and all(row["label"] == 0 for row in samples["dev"]) and np.isfinite(dev).all(), "Display calibration is not a finite normal-development map set")
                # The accepted TC2 NumPy 1.26 percentile interpolates FP32 input
                # in double precision. Explicit promotion keeps the independent
                # verifier equivalent when local NumPy is 2.x.
                expected_upper = float(np.percentile(dev.astype(np.float64), 99.5))
                if expected_upper <= 0:
                    expected_upper = 1.0
                calibration[source["identity_sha256"]] = expected_upper
                maps = archive["test_maps"]
                require(maps.dtype == np.float32 and maps.shape[0] == len(samples["test"]), "Source test maps invalid")
                index_by_path = {row["path"]: index for index, row in enumerate(samples["test"])}
                for case in matching_cases:
                    spec = case["maps"][cfg["method"]]
                    displayed = np.load(OUTPUT / spec["path"], allow_pickle=False)
                    require(displayed.shape == (256, 256) and displayed.dtype == np.float32 and np.isfinite(displayed).all(), "Exported selected map must be finite FP32 256x256")
                    require(np.array_equal(displayed, maps[index_by_path[case["path"]]]), "Selected map differs from accepted step-7 saved map")
                    require(spec["display_min"] == 0 and spec["display_max"] == expected_upper and spec["same_map_for_native_and_top_0.01"] is True, "Display calibration or shared-map declaration differs")
                    selected_map_checks.append({"case_id": case["case_id"], "method": cfg["method"], "source_identity": source["identity_sha256"], "sha256": sha(OUTPUT / spec["path"]), "normal_dev_percentile_99_5": expected_upper, "exact_saved_map_match": True})
        source_evidence.append({"run_key": source["run_key"], "directory": str(directory), "predictions_sha256": source["files"]["predictions.npz"], "samples_sha256": source["files"]["samples.json"], "metrics_sha256": source["files"]["metrics.json"]})
        print("Verified accepted scores/maps:", source["run_key"], flush=True)

    checked_points = 0

    def verify_point(point):
        nonlocal checked_points
        key = (point["dataset"], point["category"], point["method"], point["run_seed"], point["score_rule"], point["path"])
        source = score_lookup[key]
        for field in ("score", "threshold", "prediction", "label", "defect_type"):
            require(point[field] == source[field], "Case/distribution point differs from accepted score/threshold/label")
        require(point["result_identity_sha256"] == source["identity"] and point["role"] == "test", "Source result identity or role differs")
        checked_points += 1

    candidate_counts = collections.Counter()
    for row in candidates:
        frozen = manifest_images[row["path"]]
        require(row["label"] == frozen["label"], "Candidate label differs from manifest")
        require(row["defect_type"] == (frozen.get("defect_type") or "good"), "Candidate defect group differs from manifest")
        require(row["group"] == row["defect_type"], "Candidate group and defect_type differ")
        require(len(row["scores"]) == 3, "Candidate must preserve all three displayed score rules")
        require({(point["method"], point["score_rule"]) for point in row["scores"]} == {("padim", "native"), ("patchcore", "native"), ("patchcore", "top_0.01")}, "Candidate displayed rule set differs")
        for point in row["scores"]:
            require(point["path"] == row["path"] and point["run_seed"] == 17, "Candidate score path or seed differs")
            verify_point(point)
        failure = any(point["prediction"] != bool(row["label"]) for point in row["scores"])
        require(row["is_real_failure"] == failure and row["is_normal_false_positive"] == (row["label"] == 0 and failure), "Candidate failure/false-positive flag differs from real saved decisions")
        require(row["is_micro_hard_case"] == (area_by_path.get(row["path"], {}).get("size_group") == "small"), "Candidate small-mask flag differs from category-local quartile")
        require(row["selected"] == (row["path"] in {item["path"] for item in selected}), "Candidate selection flag differs")
        require((row["rejection_reason"] is None) == row["selected"], "Candidate rejection reason is not retained")
        for method in ("padim", "patchcore"):
            require(row["source_result_ids"][method] == next(point["result_identity_sha256"] for point in row["scores"] if point["method"] == method), "Candidate method source ID differs")
        candidate_counts[(row["dataset"], row["category"])] += 1

    expected_selection = []
    for key in manifests:
        current = [row for row in candidates if (row["dataset"], row["category"]) == key]
        if key[0] == "mvtec_loco":
            for group in ("logical_anomalies", "structural_anomalies"):
                within = [row for row in current if row["group"] == group]
                expected_selection.append(min(within, key=lambda row: (not row["is_real_failure"], not row["is_micro_hard_case"], row["path"]))["path"])
        else:
            first = min(current, key=lambda row: (not row["is_normal_false_positive"], not row["is_real_failure"], not row["is_micro_hard_case"], row["path"]))
            others = [row for row in current if row["path"] != first["path"]]
            second = min(others, key=lambda row: (not (row["is_micro_hard_case"] and row["is_real_failure"]), not row["is_micro_hard_case"], not row["is_real_failure"], row["path"]))
            expected_selection.extend((first["path"], second["path"]))
    require(set(expected_selection) == {row["path"] for row in selected}, "Actual selection differs from declared fixed quotas and priorities")
    require(len(selected_map_checks) == 32 and len(calibration) == 16, "Selected map/display calibration coverage incomplete")

    selected_assets = []
    raw_masks_checked = 0
    normal_cases = 0
    for position, row in enumerate(selected, 1):
        require(row["case_id"] == "%03d" % position, "Case numbering differs")
        require(read(OUTPUT / ("cases/" + row["case_id"] + "/case.json")) == row, "Per-case record differs from case register")
        candidate = candidate_by_path[row["path"]]
        require(all(row[field] == candidate[field] for field in ("dataset", "category", "group", "label", "is_real_failure", "is_normal_false_positive", "is_micro_hard_case", "scores", "source_result_ids")), "Selected case differs from its unfiltered candidate")
        expected_image = manifest_images[row["path"]]
        require(sha(OUTPUT / row["image_path"]) == row["raw_image_sha256"] == expected_image["sha256"], "Selected original image bytes differ from frozen manifest")
        with Image.open(OUTPUT / row["image_path"]) as im:
            width, height = im.size
        union = np.zeros((height, width), dtype=bool)
        require([{key: value for key, value in item.items() if key != "output_path"} for item in row["mask_sources"]] == expected_image.get("masks", []), "Selected case does not export all frozen mask references")
        for item in row["mask_sources"]:
            require(sha(OUTPUT / item["output_path"]) == item["sha256"], "Selected raw GT mask bytes differ from frozen manifest")
            with Image.open(OUTPUT / item["output_path"]) as mask:
                mask_value = np.asarray(mask.convert("L")) > 0
            require(mask_value.shape == union.shape, "Selected original GT dimensions differ from image")
            union |= mask_value
            raw_masks_checked += 1
        with Image.open(OUTPUT / row["mask_path"]) as mask:
            rendered_union = np.asarray(mask)
        require(rendered_union.shape == union.shape and set(np.unique(rendered_union)).issubset({0, 255}) and np.array_equal(rendered_union > 0, union), "Original-resolution union does not include every listed mask exactly")
        if row["label"]:
            area = area_by_path[row["path"]]
            require(area["area_pixels"] == int(union.sum()) and area["original_pixels"] == width * height, "Selected union area differs from complete size register")
        else:
            require(not union.any(), "Normal original image unexpectedly has positive truth")
            normal_cases += 1
        selected_assets.append({"case_id": row["case_id"], "category": row["category"], "group": row["group"], "image_sha256": row["raw_image_sha256"], "original_hw": [height, width], "raw_mask_count": len(row["mask_sources"]), "union_positive_pixels": int(union.sum()), "selection_reason": row["selection_reason"], "real_failure": row["is_real_failure"]})

    eligible_failures = sum(row["is_real_failure"] and row["eligible_under_group_quota"] for row in candidates)
    selected_failures = sum(row["is_real_failure"] for row in selected)
    require(eligible_failures == cases["real_failures_available"] == 644 and selected_failures == cases["real_failures_selected"] == 15, "Failure counts differ from actual saved predictions")
    require(selected_failures >= 2 and any(row["is_normal_false_positive"] for row in selected) and any(row["is_micro_hard_case"] and row["is_real_failure"] for row in selected), "Required failure, false-positive, or small-hard-case evidence absent")
    for key in manifests:
        values = [row for row in selected if (row["dataset"], row["category"]) == key]
        require(len(values) == 2, "Per-category selected case quota differs")
        if key[0] == "mvtec_loco":
            require({row["group"] for row in values} == {"logical_anomalies", "structural_anomalies"}, "LOCO case group quota differs")

    plot_cases = []
    for number in range(1, 5):
        source = read(OUTPUT / "source_data" / ("F2_cases_%02d.json" % number))
        require(source["rows"] == selected[(number - 1) * 4:number * 4] and source["rendering_changes_metrics"] is False, "Case figure source data does not exactly preserve exported cases")
        with Image.open(OUTPUT / "figures" / ("F2_cases_%02d.png" % number)) as image:
            require(image.size == (2160, 3330) and abs(image.info["dpi"][0] - 300) < 0.01, "Case figure resolution or DPI differs")
        plot_cases.extend(source["rows"])
    require(plot_cases == selected, "Case figure plates repeat or omit a selected case")

    distribution = read(OUTPUT / "source_data/F4_score_distributions.json")
    distribution_keys = set()
    for point in distribution["rows"]:
        verify_point(point)
        key = (point["dataset"], point["category"], point["method"], point["run_seed"], point["score_rule"], point["path"])
        require(key not in distribution_keys and point["dataset"] == "mvtec_ad" and point["method"] == "patchcore", "Descriptive distribution rows repeat or include the wrong dataset/method")
        distribution_keys.add(key)
    expected_distribution_keys = {key for key in score_lookup if key[0] == "mvtec_ad" and key[2] == "patchcore"}
    require(distribution_keys == expected_distribution_keys, "Descriptive pooled CDF does not preserve the full three-seed score set")
    require(distribution["rendering_changes_metrics"] is False and "not independent" in distribution["note"], "Pooled CDF independence limitation is omitted")

    size_plot = read(OUTPUT / "source_data/F4_defect_size.json")
    size_points = [row for row in size_plot["rows"] if "category" in row]
    expected_size_points = [row for row in tables["size_recall"] if row["method"] == "patchcore" and row["score_rule"] in ("native", "max", "top_0.01")]
    require(size_points == expected_size_points and len(size_points) == 108, "Size plot input rows differ from saved-score quartile calculations")
    summaries = [row for row in size_plot["rows"] if "mean_recall" in row]
    require(len(summaries) == 6, "Size-group display summaries incomplete")
    for row in summaries:
        per_seed = []
        for seed in (17, 29, 43):
            values = [item["recall"] for item in size_points if item["run_seed"] == seed and item["score_rule"] == row["score_rule"] and item["size_group"] == row["size_group"]]
            require(len(values) == 6, "Size macro must weight all six categories equally within a seed")
            per_seed.append(float(np.mean(values)))
        require(row["mean_recall"] == float(np.mean(per_seed)) and row["sample_sd"] == float(np.std(per_seed, ddof=1)) and row["categories_per_seed"] == [6, 6, 6], "Size display macro or sample SD differs")

    report = {
        "schema_version": "1.0", "status": "passed", "job_id": "44284", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_directory": str(OUTPUT), "cases_sha256": sha(OUTPUT / "cases.json"), "tables_sha256": sha(OUTPUT / "tables.json"),
        "frozen_manifests_verified": 8, "complete_candidate_count": len(candidates), "candidate_counts": [{"dataset": key[0], "category": key[1], "count": count} for key, count in candidate_counts.items()],
        "mask_area_register_count": len(area_by_path), "mask_area_register_quartiles": area_summary, "selected_count": len(selected), "selected_real_failures": selected_failures, "eligible_real_failures": eligible_failures,
        "selected_normal_false_positives": normal_cases, "selected_small_mask_real_failures": sum(row["is_micro_hard_case"] and row["is_real_failure"] for row in selected),
        "selected_original_images_sha_verified": 16, "selected_raw_gt_masks_sha_verified": raw_masks_checked, "original_resolution_unions_verified": 16,
        "selected_saved_maps_exactly_verified": len(selected_map_checks), "fixed_normal_dev_percentile_calibrations_verified": len(calibration), "display_percentile_independent_precision": "float64 interpolation, matching accepted TC2 NumPy 1.26 behavior for saved FP32 maps",
        "score_points_checked": checked_points, "independent_accepted_source_records_checked": len(source_evidence), "size_recall_rows_independently_recomputed": size_rows_verified,
        "case_plate_source_data_rows_verified": 16, "descriptive_cdf_source_points_verified": len(distribution_keys), "size_macro_summaries_verified": 6,
        "case_assets": selected_assets, "selected_map_checks": selected_map_checks, "accepted_source_evidence": source_evidence,
        "visual_review": {"F2_cases_01": "passed", "F2_cases_02": "passed", "F2_cases_03": "passed", "F2_cases_04": "passed", "method": "Original 2160x3330 PNGs inspected at original detail; all titles, four columns, row score/threshold annotations and footnotes visible without collision or clipping.", "display_rounding_note": "Case 011 rounds its distinct PatchCore native score and threshold to 1.49; the actual saved score is higher. Figure footnote explicitly identifies display rounding and full-precision source data."},
        "limitations": ["Original raw images/masks for nonselected anomalies are not present locally. All 982 area entries were checked for frozen anomaly membership, accepted original dimensions, integer fraction consistency, and deterministic category-local quartiles; actual mask-pixel areas were independently recomputed only for the 10 selected anomalous images.", "The selected 10 anomalous examples each have one listed GT mask. All listed masks were verified and unioned, but this selection does not independently exercise a multiple-mask LOCO example.", "Native PatchCore image scores were verified against accepted saved score vectors, not recomputed from original feature-bank neighborhoods.", "No pixel AUROC/AP metrics were recomputed. No feature cache, model fitting, prediction, SSH, or scheduler operation was performed.", "This audit covers F2 actual visual review and F4 case/score/size lineage. Root audit independently covers other plots and PDF typography; overall step-8 acceptance is separate."],
        "pixel_metrics_recomputed": False, "actual_tc2_connections": 0, "actual_model_calls": 0, "source_files_modified": [],
    }
    return report


if __name__ == "__main__":
    result = main()
    target = AUDIT / "cases_independent_verification.json"
    require(not target.exists(), "Audit output already exists")
    target.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: result[key] for key in ("status", "complete_candidate_count", "selected_count", "selected_saved_maps_exactly_verified", "score_points_checked", "descriptive_cdf_source_points_verified")}, indent=2))
