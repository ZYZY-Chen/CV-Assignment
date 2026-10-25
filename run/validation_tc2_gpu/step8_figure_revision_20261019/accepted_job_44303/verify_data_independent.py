"""Read-only, standard-library audit of returned job 44303 data and sources."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

COURSE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS")
ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
CURRENT = COURSE / "output/tc2_gpu_setup_20261019_223751_f596114b"
OLD = COURSE / "output/tc2_gpu_setup_20261019_220347_4dc4d911"
ANALYSIS = "run/tc2_gpu/summaries/analysis/6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C"
REVISION = "run/tc2_gpu/summaries/figure_revision/F8FBEF088CF879DE093C89009081CAD00B4698BB99BC3A6A080C748AFA4AA636"
INDEX_SHA = "55E7243F960796B36546CDB4A3E380392AA3811348D8FD3F5DBFBD5CA40A4E8B"
ARCHIVE_SHA = "59B1A527CAC7B8482BDE36899C0782BA2D8814E307B68626320E5AC1AE1C63E3"
OLD_INDEX_SHA = "3450A62EDD4BEAAF026DD1EA5326CC827020219F6424FC0F744958FFE8D11079"
OLD_ARTIFACT_SHA = "1B5326EE8EB707E75BCD3F043B3479DCD8C6472ECB78FA770F0B2C618D5C33DA"
LIMIT = 536870912
FIGURES = {"F1_methods", "baseline_comparison", "F3_hyperparameters", "F3_components", "F3_fewshot",
           "F4_improvement", "F4_q_sensitivity", "F4_score_distributions", "F4_defect_size", "F5_resources",
           "loco_extension", *("F2_cases_%02d" % number for number in range(1, 5))}
REVISION_SOURCES = {
    "configs/figure_revision_tc2_gpu.json": "6E9B646F7063AA6EF91C8C8B1318245AAE60A95A984E5CF333BB00A6884A07FA",
    "docs/TC2_GPU_FIGURE_REVISION.md": "40282E2BFA821F913F7B2BD4BAD735B41167DD60810FECD7CC4BA2E9ED195421",
    "scripts/collect_figure_revision_tc2_gpu.py": "C01DBF89C7CFFEB9921F1DDD1BBE1C2BE35698FAF9AFCC4BD337D4F22C12A82B",
    "scripts/revise_figures_tc2_gpu.py": "D21C449E56FBA2D982537F7084458A1907023C9913C50D097E5F5E4E4D663C24",
    "scripts/slurm/figure_revision_tc2_gpu.sh": "0DA7BCC47E7193AB5CBDE71DD4BBC5C683B4D813F9E222A1BFCB25A78D290936",
    "tests/test_figure_revision_tc2_gpu.py": "6814B054A670DF15EBE010C5304FFD40ACE9F5CAD3F01D940FE0338D9269D2A5",
}


def ext(path):
    path = Path(path).absolute()
    return Path("\\\\?\\" + str(path)) if os.name == "nt" and not str(path).startswith("\\\\?\\") else path


def relative(name):
    assert isinstance(name, str) and name and "\\" not in name and ":" not in name and "\0" not in name
    assert not PurePosixPath(name).is_absolute() and PurePosixPath(name).as_posix() == name
    assert all(part not in ("", ".", "..") for part in name.split("/"))
    return name


def safe(root, name):
    path = ext(root) / relative(name)
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        assert not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
    return path


def sha(path):
    digest = hashlib.sha256()
    with ext(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def unique(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result
        result[key] = value
    return result


def read(path):
    value = json.loads(ext(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    canonical(value)
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def typed_equal(left, right):
    assert type(left) is type(right)
    if isinstance(left, dict):
        assert set(left) == set(right)
        for key in left:
            typed_equal(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for first, second in zip(left, right):
            typed_equal(first, second)
    else:
        assert left == right
        if isinstance(left, float):
            assert math.isfinite(left) and math.isfinite(right)


def manifest(directory, pinned=None):
    path = safe(directory, "artifacts.sha256")
    if pinned:
        assert sha(path) == pinned
    result = {}
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9A-F]{64})  (.+)", line)
        assert match
        fingerprint, name = match.groups(); relative(name)
        assert name not in ("artifacts.sha256", "SUCCESS") and name.casefold() not in {x.casefold() for x in result}
        assert sha(safe(directory, name)) == fingerprint
        result[name] = fingerprint
    actual = {path.relative_to(ext(directory)).as_posix() for path in ext(directory).rglob("*") if path.is_file()}
    assert actual == set(result) | {"artifacts.sha256", "SUCCESS"}
    return result


def payload(index, returned):
    records = {}
    for page in index["pages"]:
        for row in page["files"]:
            name = relative(row["path"])
            assert name.casefold() not in {x.casefold() for x in records}
            path = safe(returned, name)
            assert path.stat().st_size == row["size"] and sha(path) == row["sha256"]
            records[name] = row
    assert sorted(records) == index["all_artifact_paths"]
    return records


def main():
    index_path = CURRENT / "figure-revision-index.json"
    assert sha(index_path) == INDEX_SHA
    index = read(index_path)
    assert index["job_id"] == "44303" and index["page_count"] == 1 and index["partial"] is False and index["output_relative"] == REVISION
    returned = CURRENT / "remote/page_001"
    records = payload(index, returned)
    assert len(records) == 174
    page = index["pages"][0]
    archive = CURRENT / page["name"]
    assert sha(archive) == ARCHIVE_SHA == page["sha256"] and archive.stat().st_size == page["bytes"] <= LIMIT
    with gzip.open(ext(archive), "rb") as stream:
        raw = stream.read(LIMIT + 1)
    assert len(raw) <= LIMIT and len(raw) % 512 == 0
    offset = 0
    while True:
        header = raw[offset:offset + 512]
        assert len(header) == 512
        if header == b"\0" * 512:
            assert raw[offset + 512:offset + 1024] == b"\0" * 512 and not any(raw[offset + 1024:])
            break
        assert header[156:157] in (b"0", b"\0")
        field = header[124:136].rstrip(b"\0 ").lstrip(b" ")
        assert field and all(byte in b"01234567" for byte in field)
        offset += 512 + ((int(field, 8) + 511) // 512) * 512
        assert offset <= len(raw)
    seen = set(); export_manifest = None
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as package:
        for member in package:
            name = relative(member.name)
            assert name.casefold() not in seen and member.isfile() and not member.pax_headers
            seen.add(name.casefold()); assert len(seen) <= 512
            data = package.extractfile(member).read()
            if name == "figure_revision_export_manifest.json":
                export_manifest = json.loads(data, object_pairs_hook=unique)
            else:
                assert name in records and len(data) == records[name]["size"]
                assert hashlib.sha256(data).hexdigest().upper() == records[name]["sha256"]
    assert seen == {name.casefold() for name in records} | {"figure_revision_export_manifest.json"}
    expected_export = {key: value for key, value in index.items() if key not in ("pages", "all_artifact_paths")}
    expected_export.update(page_number=1, files=page["files"])
    assert export_manifest == expected_export

    old_index = read(OLD / "analysis-index.json")
    assert sha(OLD / "analysis-index.json") == OLD_INDEX_SHA
    old_records = payload(old_index, OLD / "remote/page_001")
    assert len(old_records) == 199
    original = OLD / "remote/page_001" / ANALYSIS
    revised = returned / REVISION
    old_artifacts = manifest(original, OLD_ARTIFACT_SHA)
    assert len(old_artifacts) == 174
    new_artifacts = manifest(revised)
    assert len(new_artifacts) == 157 and ext(revised / "SUCCESS").read_text(encoding="ascii") == sha(revised / "artifacts.sha256") + "\n"
    plan = read(revised / "plan.json")
    assert plan["identity"] == REVISION.split("/")[-1]
    assert hashlib.sha256(canonical({key: value for key, value in plan.items() if key != "identity"})).hexdigest().upper() == plan["identity"]
    assert plan["input_artifacts"] == old_artifacts
    inputs = read(original / "inputs.json")
    preserved = {**inputs["protected_sources"], **inputs["analysis_sources"]}
    assert len(inputs["protected_sources"]) == 44 and len(inputs["analysis_sources"]) == 7 and len(preserved) == 51
    assert plan["preserved_sources"] == preserved and plan["figure_revision_sources"] == REVISION_SOURCES
    for name, fingerprint in {**preserved, **REVISION_SOURCES}.items():
        assert sha(safe(ROOT, name)) == fingerprint
        if name in REVISION_SOURCES:
            assert sha(safe(returned, name)) == fingerprint
    table_case_hashes = {}
    for name in ("tables.json", "cases.json"):
        assert safe(original, name).read_bytes() == safe(revised, name).read_bytes()
        table_case_hashes[name] = sha(safe(original, name))
    old_assets = {path.relative_to(ext(original)).as_posix() for path in ext(original / "cases").rglob("*") if path.is_file()}
    new_assets = {path.relative_to(ext(revised)).as_posix() for path in ext(revised / "cases").rglob("*") if path.is_file()}
    assert old_assets == new_assets and len(old_assets) == 90
    asset_hashes = {}
    for name in sorted(old_assets):
        assert safe(original, name).read_bytes() == safe(revised, name).read_bytes()
        asset_hashes[name] = sha(safe(original, name))
    assert len(read(revised / "cases.json")["cases"]) == 16
    invariance = read(revised / "data_invariance.json")
    assert invariance["status"] == "passed" and invariance["copied_case_assets"] == asset_hashes
    assert all(invariance[key] == 0 for key in ("new_fits", "model_predict_calls", "new_statistics"))
    declared = {row["name"]: row for row in invariance["figures"]}
    assert set(declared) == FIGURES and len(invariance["figures"]) == 15
    figures = {}
    for name in sorted(FIGURES):
        old_rows = read(original / ("source_data/" + name + ".json"))["rows"]
        new_rows = read(revised / ("source_data/" + name + ".json"))["rows"]
        typed_equal(old_rows, new_rows)
        assert canonical(old_rows) == canonical(new_rows)
        fingerprint = hashlib.sha256(canonical(old_rows)).hexdigest().upper()
        assert plan["source_row_hashes"][name] == declared[name]["rows_sha256"] == fingerprint
        assert declared[name]["status"] == "identical" and declared[name]["source_row_count"] == len(new_rows)
        figures[name] = {"rows": len(new_rows), "rows_sha256": fingerprint, "typed_ordered_canonical_equal": True}
    tests = read(returned / "run/validation_tc2_gpu/step8_figure_revision_job_44303/tests/tests_summary.json")
    assert tests["tests_run"] == 22 and tests["status"] == "passed" and tests["full_plot_render_passed"] is True
    assert all(tests[key] == 0 for key in ("errors", "failures", "skipped"))
    state = read(returned / "run/validation_tc2_gpu/step8_figure_revision_job_44303/state.json")
    assert state == index["snapshot_status"] and state["status"] == "passed" and state["step_8_complete"] is False
    result = {"status": "passed", "created_utc": datetime.now(timezone.utc).isoformat(), "job_id": "44303",
              "revision_identity": plan["identity"], "index_sha256": INDEX_SHA, "archive_sha256": ARCHIVE_SHA,
              "archive_compressed_bytes": page["bytes"], "archive_decompressed_bytes": len(raw), "archive_regular_members": len(seen),
              "archive_limit_bytes": LIMIT, "archive_member_limit": 512, "duplicate_link_traversal_extension_and_trailing_payload_guards_passed": True,
              "payload_file_count": len(records), "all_payload_hashes_and_sizes_verified": True,
              "old_collection_payload_files_still_matching_pinned_index": len(old_records), "old_summary_artifact_files": len(old_artifacts) + 2,
              "old_artifacts_manifest_sha256": OLD_ARTIFACT_SHA, "all_old_artifacts_preserved": True,
              "new_summary_artifact_files": len(new_artifacts) + 2, "new_artifacts_manifest_sha256": sha(revised / "artifacts.sha256"),
              "current_preserved_source_count": len(preserved), "current_revision_source_count": len(REVISION_SOURCES),
              "all_57_current_sources_match_pinned_fingerprints": True, "current_preserved_source_hashes": preserved, "revision_source_hashes": REVISION_SOURCES,
              "tables_cases_byte_identical": table_case_hashes, "selected_case_count": 16, "case_asset_count": len(asset_hashes),
              "case_assets_byte_identical": asset_hashes, "case_selection_unchanged": True,
              "all_15_source_rows_type_order_and_canonical_bytes_identical": True, "source_row_count": sum(row["rows"] for row in figures.values()), "figures": figures,
              "new_fits": 0, "new_model_predict_calls": 0, "new_statistics": 0,
              "full_synthetic_tests_passed": 22, "formal_revision_publication_verified": True,
              "visual_review_performed_by_this_audit": False, "step_8_complete_set_by_this_audit": False,
              "audit_dependencies": "Python standard library only", "source_or_log_modifications": False,
              "actual_network_or_scheduler_connections": False, "new_render_or_model_calls": 0}
    target = Path(__file__).with_name("independent_data_verification.json")
    with ext(target).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write("\n")
    print(json.dumps({"status": "passed", "receipt": str(target), "receipt_sha256": sha(target),
                      "payload_files": len(records), "case_assets": len(asset_hashes), "source_rows": result["source_row_count"]}, indent=2))


if __name__ == "__main__":
    main()
