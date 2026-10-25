"""Record the separately reviewed step-8 acceptance and update English status."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(r"C:\Users\mhjv_\PycharmProjects\6129_assignment\group_XX_code")
COURSE = Path(r"C:\Users\mhjv_\Desktop\CharGPT projects\CA6129 COMPUTER VISION & APPLICATIONS")
AUDIT = ROOT / "run/validation_tc2_gpu/step8_figure_revision_20261019"
ACCEPTED = AUDIT / "accepted_job_44303"
RECEIVED = COURSE / "output/tc2_gpu_setup_20261019_223751_f596114b"
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
load = lambda path: json.loads(path.read_bytes())
def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2); stream.write("\n")

data = load(ACCEPTED / "independent_data_verification.json")
pdf = load(ACCEPTED / "pdf_layout_independent_verification.json")
render = load(ACCEPTED / "pdf_render_verification.json")
main = load(ACCEPTED / "main_figures_visual_review.json")
cases = load(ACCEPTED / "cases_visual_review.json")
collector = load(ACCEPTED / "collector_verification.json")
source_review = load(ACCEPTED / "source_preflight_resolution.json")
assert data["status"] == main["status"] == cases["status"] == "passed"
assert data["all_15_source_rows_type_order_and_canonical_bytes_identical"]
assert data["all_57_current_sources_match_pinned_fingerprints"]
assert data["case_asset_count"] == 90 and data["source_row_count"] == 6896
assert data["all_old_artifacts_preserved"] and data["all_payload_hashes_and_sizes_verified"]
assert pdf["status"] == "passed_with_explicit_pdfplumber_adapter"
assert pdf["all_actual_pdf_font_sizes_at_least_7pt"] and pdf["all_footer_bands_clear"]
assert pdf["all_supplemental_collision_checks_clear"]
assert pdf["minimum_actual_pdf_font_pt"] >= 7 - 1e-8
assert pdf["figures"]["F1_methods.pdf"]["method_diagram"]["both_method_outputs_connected"]
assert render["figure_count"] == 15 and render["all_pdfs_reopened"] and render["all_copies_byte_identical"]
assert main["figure_count"] == 11 and len(cases["plates"]) == 4
assert collector["stage_complete"] and not collector["partial"] and collector["file_count"] == 174
assert not source_review["unresolved_findings"]

index = load(RECEIVED / "figure-revision-index.json")
base = Path("\\\\?\\" + str(RECEIVED / "remote/page_001"))
job = base / "run/validation_tc2_gpu/step8_figure_revision_job_44303"
state = load(job / "state.json")
tests = load(job / "tests/tests_summary.json")
plan = load(job / "plan.json")
assert state["status"] == "passed" and state["identity"] == plan["identity"] == data["revision_identity"]
assert tests["status"] == "passed" and tests["tests_run"] == 22 and tests["full_plot_render_passed"]
terminal = (RECEIVED / "terminal.txt").read_text(encoding="utf-8")
assert re.search(r"(?m)^44303\s+.*COMPLETED\s+0:0\s+00:01:05\s+TC2N07\s+2\s+8G", terminal)

before = load(AUDIT / "before_scope.json")
for name, spec in before["sources"].items():
    path = ROOT / name
    assert sha(path) == spec["sha256"] and path.stat().st_mtime_ns == spec["mtime_ns"], name
for name, spec in before["historical_run_files"].items():
    path = ROOT / name
    assert path.stat().st_size == spec["bytes"] and path.stat().st_mtime_ns == spec["mtime_ns"], name
for name, fingerprint in {**plan["preserved_sources"], **plan["figure_revision_sources"]}.items():
    assert sha(ROOT / name) == fingerprint, name
helper = COURSE / "output/tc2_gpu_setup.ps1"
assert sha(helper) == load(AUDIT / "scope_verification.json")["helper_sha256"]

readme = ROOT / "README.md"
original = readme.read_bytes()
assert sha(readme) == "53D9650A99E2B99A7ACFD2F003F0639DB94CE1A247ABC99FCB1A616E8DC8F59F"
start = original.index(b"Step 8 remains pending final figure acceptance.")
end = original.index("\n## 数据集".encode("utf-8"), start)
replacement = """Step 8 completed on 2026-10-19. Analysis job 44284 finished as COMPLETED / 0:0 in 00:02:01 with all 29 full tests passing; its tables, selected cases and descriptive distributions passed independent verification. Figure revision job 44303 on TC2N07 then finished as COMPLETED / 0:0 in 00:01:05, using two CPUs, 8 GiB and zero GPUs. All 22 full revision tests passed, including actual synthetic rendering of fifteen figure groups. The complete collection returned 174 payload files with verified fingerprints.

The approved [figure revision supplement](docs/TC2_GPU_FIGURE_REVISION.md) uses the independent [CPU revision driver](scripts/revise_figures_tc2_gpu.py), [configuration](configs/figure_revision_tc2_gpu.json), [collector](scripts/collect_figure_revision_tc2_gpu.py), [wrapper](scripts/slurm/figure_revision_tc2_gpu.sh) and [tests](tests/test_figure_revision_tc2_gpu.py). It imports the frozen plotting module and overrides only shared layout/export and the methods diagram. Independent checks confirmed exact equality of all 6,896 ordered source-data rows across fifteen groups, byte-identical tables and case registries, and all 90 assets for the unchanged sixteen selected cases. All 51 protected source files and six pinned revision files matched their fingerprints; original analysis outputs and historical logs remain unchanged. No new fit, model prediction or scientific analysis was introduced.

All fifteen original 300 dpi PNGs and independently rendered PDF pages passed visual review. Actual PDF text is selectable and uses embedded TrueType-backed fonts; the smallest glyph is 7.5 pt. Measured page-footer separation, axes alignment, methods-diagram text containment and both output routes passed. Supplemental PDF geometry checks used an explicitly documented pdfplumber adapter because PyMuPDF was unavailable; the record does not claim a standard fitz CLI pass. Existing-case display rounding remains documented and does not change full-precision decisions.

Accepted revised figures use `run/tc2_gpu/summaries/figure_revision/F8FBEF088CF879DE093C89009081CAD00B4698BB99BC3A6A080C748AFA4AA636/`. See the [final step-8 status](run/validation_tc2_gpu/step8_figure_revision_20261019/setup_status.json) and [independent acceptance](run/validation_tc2_gpu/step8_figure_revision_20261019/accepted_job_44303/verification.json). The original analysis namespace is retained. The helper's RunFigureRevision/CollectFigureRevision actions preserve the bounded single-archive workflow; accepted job 44303 requires no resubmission or further collection. Report writing and step 9 have not started.
""".encode("utf-8")
updated = original[:start] + replacement + original[end:]
chinese = lambda raw: [line for line in raw.decode("utf-8").splitlines() if re.search(r"[\u4e00-\u9fff]", line)]
assert chinese(original) == chinese(updated)
assert updated[:start] == original[:start] and updated[start + len(replacement):] == original[end:]
(ACCEPTED / "README.before_acceptance.md").write_bytes(original)

evidence_names = ["collector_verification.json", "independent_data_verification.json",
                  "pdf_render_verification.json", "pdf_layout_independent_verification.json",
                  "main_figures_visual_review.json", "cases_visual_review.json",
                  "source_preflight_resolution.json"]
evidence = {name: sha(ACCEPTED / name) for name in evidence_names}
result = {
    "schema_version": "1.0", "status": "accepted", "step_8_complete": True,
    "accepted_at_utc": datetime.now(timezone.utc).isoformat(), "analysis_job_id": "44284",
    "figure_revision_job_id": "44303", "job_state": "COMPLETED", "exit_code": "0:0",
    "elapsed": "00:01:05", "node": "TC2N07", "cpus": 2, "memory_mib": 8192,
    "gpus": 0, "batch_max_rss_kib": 819780, "identity": plan["identity"],
    "summary_relative": index["output_relative"], "collection_directory": str(RECEIVED),
    "index_sha256": data["index_sha256"], "archive_sha256": data["archive_sha256"],
    "payload_files_verified": 174, "full_tests_passed": 22,
    "source_data_groups_identical": 15, "ordered_source_data_rows_identical": 6896,
    "case_assets_byte_identical": 90, "selected_cases_unchanged": 16,
    "tables_and_cases_byte_identical": True, "preserved_sources_verified": 51,
    "revision_sources_verified": 6, "preexisting_source_files_preserved": len(before["sources"]),
    "historical_run_files_preserved": len(before["historical_run_files"]),
    "actual_pngs_and_pdf_pages_visually_reviewed": 15,
    "minimum_actual_pdf_glyph_pt": 7.5, "editable_embedded_truetype_pdf_text": True,
    "footer_and_diagram_gates_passed": True,
    "pdf_collision_extractor": "pdfplumber adapter with independent geometry core",
    "standard_fitz_cli_passed": False,
    "pdf_qa_limitations": pdf["limitations"],
    "existing_case_011_rounding_note": "Displayed score/threshold both round to 1.49; unchanged full-precision decision and explanatory footer remain accepted.",
    "new_fits": 0, "model_predict_calls": 0, "new_statistics": 0,
    "evidence_sha256": evidence, "frozen_source_sha256": plan["preserved_sources"],
    "revision_source_sha256": plan["figure_revision_sources"],
    "old_evidence_preserved": True, "existing_chinese_readme_preserved": True,
    "report_writing_started": False, "automatic_next_step": False,
}
write_new(ACCEPTED / "verification.json", result)
readme.write_bytes(updated)
status = {key: value for key, value in result.items()
          if key not in ("evidence_sha256", "frozen_source_sha256", "revision_source_sha256", "pdf_qa_limitations")}
status.update(verification_path="accepted_job_44303/verification.json",
              verification_sha256=sha(ACCEPTED / "verification.json"), readme_sha256=sha(readme))
write_new(AUDIT / "setup_status.json", status)
print(json.dumps({"status": "accepted", "step_8_complete": True, "job_id": "44303",
                  "verification_sha256": sha(ACCEPTED / "verification.json"), "readme_sha256": sha(readme)}))
