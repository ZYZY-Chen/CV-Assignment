"""Revise accepted TC2 figures without accessing models or scientific inputs.

Only the frozen plotting module's shared export and method diagram functions are
replaced, temporarily, in this process. Numerical plotting functions are reused
byte-for-byte, and every resulting source-data row is compared exactly.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import zlib


import importlib.util as _import_util
_bootstrap_spec = _import_util.spec_from_file_location(
    "_tc2_gpu_bootstrap", Path(__file__).resolve().parents[1] / "_bootstrap.py")
_bootstrap = _import_util.module_from_spec(_bootstrap_spec)
_bootstrap_spec.loader.exec_module(_bootstrap)
ROOT = _bootstrap.configure(__file__)
from tc2_gpu_provenance import historical_sha, current_source_sha, require_current_acceptance
CONFIG = "configs/tc2_gpu/figure_revision.json"
FIGURES = ("F1_methods", "baseline_comparison", "F3_hyperparameters", "F3_components",
           "F3_fewshot", "F4_improvement", "F4_q_sensitivity", "F4_score_distributions",
           "F4_defect_size", "F5_resources", "loco_extension", "F2_cases_01",
           "F2_cases_02", "F2_cases_03", "F2_cases_04")
EXPECTED_SOURCES = (CONFIG, "scripts/tc2_gpu/analysis/revise_figures.py",
                    "scripts/tc2_gpu/collect/collect_figure_revision.py",
                    "scripts/tc2_gpu/slurm/run_figure_revision.sh",
                    "tests/test_figure_revision_tc2_gpu.py", "docs/experiment_history/implementation/STEP_08_FIGURE_REVISION.md",
    'scripts/__init__.py',
    'scripts/tc2_gpu/__init__.py',
    'scripts/tc2_gpu/_bootstrap.py',
    'src/tc2_gpu_provenance.py',
    'scripts/tc2_gpu/analysis/__init__.py',
    'scripts/tc2_gpu/collect/__init__.py',
    'scripts/tc2_gpu/collect/collect_pilot.py',
    'scripts/tc2_gpu/analysis/plot_results.py')
ANALYSIS_ID = "6077F6D3F5244ECB28EF67BECBE454E989C99246F285CD63C85DBEC8A6239B5C"
INPUT_SPEC = {"identity": ANALYSIS_ID, "relative_path": "run/tc2_gpu/summaries/analysis/" + ANALYSIS_ID,
              "artifacts_sha256": "1B5326EE8EB707E75BCD3F043B3479DCD8C6472ECB78FA770F0B2C618D5C33DA",
              "inputs_sha256": "59F8F62DA7E14B2F1710F8EBE43ABF2A64D42B3B2A878B5677607D7FE4C06454",
              "tables_sha256": "E92DDEB9DEF288C34664E0D91CC9F66AD1902FCA7FF96378F8935CEBB498C0F0",
              "cases_sha256": "83DBAE5C4C5B78AC27BC61A6208C3CA7DE3A0710DC7FE68E1C1E348201B01B27",
              "plot_manifest_sha256": "A3AC879DEB953BA15759AF5CFE4EDAA02B812BE9037118E561EFE3E36BBFB632"}
ANALYSIS_HASHES = {
    "configs/analysis_tc2_gpu.json": "9E6E20069F5E3C1F6ED5F739077D79D8556357C5C92501C822AD3E03BFB537B9",
    "scripts/analyze_results_tc2_gpu.py": "CC6B3FDC5518BEA45E1F4E9571BC1D318EADEA6340D3D75DA9FC5E649B3A3552",
    "scripts/plot_results_tc2_gpu.py": "C4AD7E9B6BB2D6D6428099EC255EBAE5BA624CD0B4F636D4CC7468C096F867B5",
    "scripts/collect_analysis_tc2_gpu.py": "23364A7E72E99AD6D02302A525523AD92B0A2300195BAF98861D88DDA2E8B98E",
    "scripts/slurm/analysis_tc2_gpu.sh": "8351E365AFE6FD996743E46DA13D6E7A9E40D6028B52C9612BDE5B0EFE4DC139",
    "tests/test_analysis_tc2_gpu.py": "168104960F564D6622564527FBCE3753FB9EEACA0EB4AB4C41209A312331521A",
    "docs/TC2_GPU_ANALYSIS.md": "F897C75659CC31BF98BB89E95AA4E3AEA241AA40FAC59CEDE85518119CA5F57C"}


def extended(path):
    path = Path(path).absolute()
    return Path("\\\\?\\" + str(path)) if os.name == "nt" and not str(path).startswith("\\\\?\\") else path


def inside(root, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Expected a relative POSIX path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
        raise ValueError("Path leaves the approved root")
    root = extended(root)
    target = root.joinpath(*relative.parts)
    for item in (target, *target.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
                raise ValueError("Links and reparse points are forbidden")
        if item == root:
            return target
    raise ValueError("Path leaves the approved root")


def sha(path):
    digest = hashlib.sha256()
    with extended(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated JSON key: " + key)
        result[key] = value
    return result


def load(path):
    value = json.loads(extended(path).read_text(encoding="utf-8"), object_pairs_hook=_unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    canonical(value)
    return value


def write(path, value):
    path = extended(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n")


def _state(path, value):
    temporary = extended(path).with_name("state.json.next")
    write(temporary, value)
    os.replace(temporary, extended(path))


def validate_config(config):
    if set(config) != {"schema_version", "display_name", "scope", "input_analysis", "new_sources", "layout", "policy", "collection_bounds"}:
        raise ValueError("Unexpected figure revision configuration key")
    if config.get("schema_version") != "1.0" or config.get("input_analysis", {}).get("identity") != ANALYSIS_ID:
        raise ValueError("Wrong accepted input analysis identity")
    if config["input_analysis"] != INPUT_SPEC:
        raise ValueError("Accepted input binding differs from job 44284")
    if config.get("new_sources") != list(EXPECTED_SOURCES):
        raise ValueError("Revision must publish exactly the approved current source files")
    expected_layout = {"dpi": 300, "minimum_pdf_glyph_pt": 7, "body_font_pt": 7.5,
                       "footer_gap_pt": 8, "outer_margin_pt": 8, "panel_alignment_tolerance_pt": 1.5,
                       "final_bound_clearance_pt": 3, "plain_numeric_log_ticks": True,
                       "measured_footer_bands": True, "diagram_text_containment": True}
    if config.get("layout") != expected_layout:
        raise ValueError("Layout/export settings differ from the approved revision")
    policy = config.get("policy", {})
    if set(policy) != {"figure_count", "exact_source_rows", "copy_selected_assets_unchanged", "only_plot_overrides",
                       "new_fits", "model_predict_calls", "new_statistics", "environment_installations", "post_download_visual_review_required"}:
        raise ValueError("Unexpected figure revision policy key")
    if (policy.get("figure_count") != 15 or policy.get("only_plot_overrides") != ["_save", "_methods"]
            or not policy.get("exact_source_rows") or not policy.get("copy_selected_assets_unchanged")
            or any(policy.get(key) != 0 for key in ("new_fits", "model_predict_calls", "new_statistics"))
            or policy.get("environment_installations") is not False
            or policy.get("post_download_visual_review_required") is not True):
        raise ValueError("Figure revision may not change the approved scientific scope")
    if config.get("collection_bounds") != {"compressed_archive_bytes": 536870912, "decompressed_archive_bytes": 536870912, "members": 512}:
        raise ValueError("Collection bounds differ from the approved limit")
    return config


def artifact_manifest(directory, *, expected_sha=None):
    directory = extended(directory)
    manifest = inside(directory, "artifacts.sha256")
    if expected_sha and sha(manifest) != expected_sha:
        raise ValueError("Artifact manifest fingerprint differs")
    records = {}
    for line in manifest.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([A-F0-9]{64})  (.+)", line)
        if not match or match[2] in records:
            raise ValueError("Invalid or repeated artifact manifest entry")
        target = inside(directory, match[2])
        if not target.is_file() or sha(target) != match[1]:
            raise ValueError("Artifact hash differs: " + match[2])
        records[match[2]] = match[1]
    if not records or len(records) > 510:
        raise ValueError("Artifact count is outside the approved collection bound")
    actual = set()
    for item in directory.rglob("*"):
        relative = item.relative_to(directory).as_posix()
        inside(directory, relative)
        if item.is_file():
            actual.add(relative)
        elif not item.is_dir():
            raise ValueError("Artifact tree contains a special filesystem object")
    if actual != set(records) | {"artifacts.sha256", "SUCCESS"}:
        raise ValueError("Unmanifested or missing artifact file")
    return records


def validate_input(root, config, analysis_root=None):
    spec = config["input_analysis"]
    original = extended(analysis_root) if analysis_root else inside(root, spec["relative_path"])
    records = artifact_manifest(original, expected_sha=spec["artifacts_sha256"])
    if load(original / "SUCCESS") != {"status": "passed", "namespace": "analysis", "job_id": "44284",
                                       "identity_sha256": ANALYSIS_ID, "artifacts_sha256": spec["artifacts_sha256"]}:
        raise ValueError("Accepted analysis completion marker differs from job 44284")
    for name, key in (("inputs.json", "inputs_sha256"), ("tables.json", "tables_sha256"),
                      ("cases.json", "cases_sha256"), ("plot_manifest.json", "plot_manifest_sha256")):
        if records.get(name) != spec[key]:
            raise ValueError("Accepted input binding differs: " + name)
    inputs = load(original / "inputs.json")
    protected = {**inputs["protected_sources"], **inputs["analysis_sources"]}
    if len(inputs["protected_sources"]) != 44 or inputs["analysis_sources"] != ANALYSIS_HASHES or len(protected) != 51:
        raise ValueError("Expected all 44 scientific and seven analysis sources")
    for name, expected in protected.items():
        if historical_sha(root, name) != expected:
            raise ValueError("Frozen source fingerprint differs: " + name)
    plot = load(original / "plot_manifest.json")
    if plot.get("status") != "passed" or plot.get("figure_count") != 15 or {item["name"] for item in plot["figures"]} != set(FIGURES):
        raise ValueError("Accepted analysis must contain exactly fifteen figure groups")
    if len(load(original / "cases.json")["cases"]) != 16:
        raise ValueError("Accepted selection must contain exactly sixteen cases")
    for name in FIGURES:
        if "source_data/" + name + ".json" not in records:
            raise ValueError("Accepted figure source data is missing")
    return original, protected, records


def build_plan(root, analysis_root=None):
    root = extended(root)
    config = validate_config(load(inside(root, CONFIG)))
    original, protected, records = validate_input(root, config, analysis_root)
    sources = {name: current_source_sha(root, name) for name in EXPECTED_SOURCES}
    plan = {"schema_version": "1.0", "workflow_id": "tc2_gpu", "scope": "figure_revision",
            "input_analysis": config["input_analysis"], "figure_revision_sources": sources,
            "preserved_sources": protected, "input_artifacts": records,
            "source_row_hashes": {name: hashlib.sha256(canonical(load(inside(original, "source_data/" + name + ".json"))["rows"])).hexdigest().upper() for name in FIGURES},
            "resources": {"partition": "MGPU-TC2", "qos": "normal", "nodes": 1, "tasks": 1,
                          "cpus": 2, "memory_mib": 8192, "time_limit": "00:15:00", "gpus": 0,
                          "new_fits": 0, "model_predict_calls": 0, "new_statistics": 0}}
    plan["identity"] = hashlib.sha256(canonical(plan)).hexdigest().upper()
    return plan


def verify_plan(root, plan, analysis_root=None):
    if build_plan(root, analysis_root) != plan:
        raise ValueError("Portable revision plan differs from current sources or accepted inputs")
    return plan


def assert_source_rows(original_rows, revised_rows):
    if canonical(original_rows) != canonical(revised_rows):
        raise ValueError("Rendering changed accepted source-data rows")
    return hashlib.sha256(canonical(original_rows)).hexdigest().upper()


def pdf_font_audit(path, minimum_pt=7.0):
    """Check actual PDF Tf glyph sizes, including reduced mathtext runs.

    Plain/Flate stream logic follows the dependency-free nature-figure PDF text
    audit; final visual review remains required for arbitrary PDF transforms.
    """
    data = extended(path).read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Expected an actual PDF document")
    cursor, sizes, streams = 0, [], 0
    while True:
        match = re.search(rb"stream\r?\n", data[cursor:])
        if not match:
            break
        start, payload_start = cursor + match.start(), cursor + match.end()
        end = data.find(b"endstream", payload_start)
        if end < 0:
            raise ValueError("PDF stream is incomplete")
        header = data[max(0, start - 2048):start]
        dictionary = header[header.rfind(b"<<"):]
        payload = data[payload_start:end]
        if b"/FlateDecode" in dictionary:
            try:
                payload = zlib.decompress(payload)
            except zlib.error as error:
                raise ValueError("PDF Flate stream cannot be audited") from error
        elif b"/Filter" in dictionary:
            raise ValueError("PDF uses an unsupported content filter")
        for font in re.finditer(rb"/[^\s/<>]+\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?)\s+Tf\b", payload):
            value = float(font[1])
            if value > 0:
                sizes.append(value)
        streams += 1
        cursor = end + 9
    if not sizes or min(sizes) < minimum_pt - 1e-8:
        raise ValueError("Actual PDF glyph size is missing or below the approved minimum")
    return {"status": "passed", "minimum_required_pt": minimum_pt, "minimum_glyph_pt": min(sizes),
            "text_font_operators": len(sizes), "streams": streams,
            "scope": "Actual plain/Flate PDF Tf operators; final-size visual inspection still required"}


_PLOT = None


def _plot():
    global _PLOT
    if _PLOT is None:
        path = Path(__file__).with_name("plot_results.py")
        spec = importlib.util.spec_from_file_location("_frozen_tc2_figure_plot", path)
        _PLOT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PLOT)
    return _PLOT


def _axes(axes):
    return [axis for row in axes for axis in row]


def _bbox(box, dpi):
    return [float(value * 72 / dpi) for value in (box.x0, box.y0, box.x1, box.y1)]


def _overlap(left, right, tolerance=0):
    return min(left[2], right[2]) - max(left[0], right[0]) > tolerance and min(left[3], right[3]) - max(left[1], right[1]) > tolerance


def _segment_hits_box(start, end, bounds):
    lower, upper = 0.0, 1.0
    for dimension in (0, 1):
        delta = end[dimension] - start[dimension]
        low, high = bounds[dimension], bounds[dimension + 2]
        if abs(delta) < 1e-12:
            if not low <= start[dimension] <= high:
                return False
        else:
            near, far = sorted(((low - start[dimension]) / delta, (high - start[dimension]) / delta))
            lower, upper = max(lower, near), min(upper, far)
            if lower > upper:
                return False
    return True


def _axis_texts(axis):
    values = [axis.title, *axis.texts]
    if axis.axison:
        values += [axis.xaxis.label, axis.yaxis.label, axis.xaxis.get_offset_text(), axis.yaxis.get_offset_text()]
        for dimension in (axis.xaxis, axis.yaxis):
            low, high = sorted(dimension.get_view_interval())
            for tick in dimension.get_major_ticks() + dimension.get_minor_ticks():
                if low - 1e-10 <= tick.get_loc() <= high + 1e-10:
                    values += [tick.label1, tick.label2]
    return [item for item in values if item.get_visible() and item.get_text()]


def require_clearance(fig, axes, legends=(), note_artist=None, *, image_plate=False, diagram=False):
    """Measure final footer separation, page containment and diagram boxes."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    axis_values = _axes(axes)
    body = []
    for index, axis in enumerate(axis_values):
        body.append({"kind": "plot_area", "panel": index, "bounds_pt": _bbox(axis.get_window_extent(renderer), fig.dpi)})
        body.extend({"kind": "text", "panel": index, "text": text.get_text(),
                     "bounds_pt": _bbox(text.get_window_extent(renderer), fig.dpi)} for text in _axis_texts(axis))
    footer = [{"kind": "legend", "bounds_pt": _bbox(legend.get_window_extent(renderer), fig.dpi)} for legend in legends]
    if note_artist is not None:
        footer.append({"kind": "note", "bounds_pt": _bbox(note_artist.get_window_extent(renderer), fig.dpi)})
    clearance = 3.0
    for item in footer:
        for other in body:
            expanded = [item["bounds_pt"][0], item["bounds_pt"][1] - clearance,
                        item["bounds_pt"][2], item["bounds_pt"][3] + clearance]
            if _overlap(expanded, other["bounds_pt"]):
                raise ValueError("Footer collides with a final plot label, tick or plot area")
    for i, left in enumerate(footer):
        for right in footer[i + 1:]:
            if _overlap([left["bounds_pt"][0], left["bounds_pt"][1] - clearance,
                         left["bounds_pt"][2], left["bounds_pt"][3] + clearance], right["bounds_pt"]):
                raise ValueError("Legend and note bands overlap")
    width, height = fig.get_size_inches() * 72
    for item in body + footer:
        x0, y0, x1, y1 = item["bounds_pt"]
        if x0 < -0.5 or y0 < -0.5 or x1 > width + 0.5 or y1 > height + 0.5:
            raise ValueError("Final rendered label or panel leaves the page: " + item.get("text", item["kind"]))
    diagram_records = []
    for patch, text in getattr(fig, "_revision_diagram_boxes", []):
        outer = _bbox(patch.get_window_extent(renderer), fig.dpi)
        inner = _bbox(text.get_window_extent(renderer), fig.dpi)
        if any((inner[0] < outer[0] + 2, inner[1] < outer[1] + 2,
                inner[2] > outer[2] - 2, inner[3] > outer[3] - 2)):
            raise ValueError("Diagram text does not fit inside its measured box")
        diagram_records.append({"text": text.get_text(), "box_bounds_pt": outer, "text_bounds_pt": inner})
    routes = getattr(fig, "_revision_diagram_routes", [])
    for route in routes:
        start, end = axis_values[0].transData.transform([route["start"], route["end"]]) * 72 / fig.dpi
        for record in diagram_records:
            bounds = record["text_bounds_pt"]
            if _segment_hits_box(start, end, [bounds[0] - 2, bounds[1] - 2, bounds[2] + 2, bounds[3] + 2]):
                raise ValueError("Diagram arrow crosses a measured text boundary")
    return {"status": "passed", "measured_after_final_draw": True, "minimum_footer_clearance_pt": clearance,
            "body": body, "footer": footer, "diagram_text_containment": diagram_records,
            "diagram_routes": routes, "diagram_arrow_text_clearance": "passed" if routes else "not_applicable",
            "image_plate_row_captions_preserved": bool(image_plate), "diagram": bool(diagram)}


def _wrapped_note(fig, note, width_in, font_pt=7.5):
    from matplotlib.font_manager import FontProperties
    renderer = fig.canvas.get_renderer()
    font = FontProperties(family="DejaVu Sans", size=font_pt)
    limit = width_in * fig.dpi
    lines, line = [], ""
    for word in note.split():
        candidate = (line + " " + word).strip()
        if line and renderer.get_text_width_height_descent(candidate, font, False)[0] > limit:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return "\n".join(lines)


def _final_layout(fig, axes, note, image_plate=False):
    """Add measured footer space while preserving absolute plot-area sizes."""
    axis_values = _axes(axes)
    handles, labels = [], []
    for axis in axis_values:
        legend = axis.get_legend()
        if legend is not None:
            values, names = axis.get_legend_handles_labels()
            for handle, label in zip(values, names):
                if label not in labels:
                    handles.append(handle); labels.append(label)
            legend.remove()
    for legend in list(fig.legends):
        for handle, label in zip(legend.legend_handles, [text.get_text() for text in legend.get_texts()]):
            if label not in labels:
                handles.append(handle); labels.append(label)
        legend.remove()
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    width, old_height = map(float, fig.get_size_inches())
    left = 0.14 if image_plate else 0.38
    note_artist = fig.text(left / width, 8 / 72 / old_height,
                           _wrapped_note(fig, note, width - 2 * left), fontsize=7.5,
                           ha="left", va="bottom", linespacing=1.25) if note else None
    fig.canvas.draw()
    note_height = note_artist.get_window_extent(renderer).height / fig.dpi if note_artist else 0
    cursor = 8 / 72 + note_height + (8 / 72 if note else 0)
    legend_artist = None
    if handles:
        for columns in range(min(5, len(handles)), 0, -1):
            if legend_artist is not None:
                legend_artist.remove()
            legend_artist = fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, cursor / old_height),
                                       ncol=columns, fontsize=7.5, borderaxespad=0, handlelength=1.8,
                                       columnspacing=1.5, labelspacing=0.7)
            fig.canvas.draw()
            if legend_artist.get_window_extent(renderer).width / fig.dpi <= width - 2 * left:
                break
        else:
            raise ValueError("Legend cannot fit inside the approved figure width")
        cursor += legend_artist.get_window_extent(renderer).height / fig.dpi + 8 / 72
    body_bottom = min(axis.get_tightbbox(renderer).y0 / fig.dpi for axis in axis_values)
    shift = max(0.0, cursor + 4 / 72 - body_bottom)
    old_positions = [axis.get_position().frozen() for axis in axis_values]
    figure_texts = [(text, text.get_position()) for text in fig.texts if text is not note_artist]
    new_height = old_height + shift
    fig.set_size_inches(width, new_height, forward=True)
    for axis, position in zip(axis_values, old_positions):
        axis.set_position([position.x0, (position.y0 * old_height + shift) / new_height,
                           position.width, position.height * old_height / new_height])
    for text, (x, y) in figure_texts:
        text.set_position((x, (y * old_height + shift) / new_height))
    if note_artist:
        note_artist.set_position((left / width, 8 / 72 / new_height))
    if legend_artist:
        legend_artist.set_bbox_to_anchor((0.5, (8 / 72 + note_height + (8 / 72 if note else 0)) / new_height))
    fig.canvas.draw()
    return ([legend_artist] if legend_artist else []), note_artist


def layout_and_save(plt, output, name, fig, axes, rows, question, *, note="", image_plate=False, diagram=False):
    from matplotlib.ticker import FuncFormatter, NullFormatter
    for axis in _axes(axes):
        if axis.get_xscale() == "log":
            axis.xaxis.set_minor_formatter(NullFormatter())
        if name == "F5_resources":
            axis.xaxis.set_major_formatter(FuncFormatter(lambda value, position: format(value, ".6g")))
    legends, note_artist = _final_layout(fig, axes, note, image_plate)
    alignment = _plot().require_matplotlib_panel_alignment(fig, axes, image_plate=image_plate, diagram=diagram)
    clearance = require_clearance(fig, axes, legends, note_artist, image_plate=image_plate, diagram=diagram)
    for text in fig.findobj(match=lambda artist: hasattr(artist, "get_fontsize") and hasattr(artist, "get_text")):
        if text.get_visible() and text.get_text() and text.get_fontsize() < 7:
            raise ValueError("Visible text falls below the approved minimum")
    output = extended(output)
    for folder in ("figures", "source_data", "qa"):
        inside(output, folder).mkdir(parents=True, exist_ok=True)
    names = ("figures/" + name + ".png", "figures/" + name + ".pdf", "source_data/" + name + ".json", "qa/" + name + ".alignment.json")
    fig.savefig(inside(output, names[0]), dpi=300, facecolor="white")
    fig.savefig(inside(output, names[1]), format="pdf", facecolor="white",
                metadata={"Title": question, "Creator": "TC2 GPU figure revision"})
    fonts = pdf_font_audit(inside(output, names[1]))
    from PIL import Image
    with Image.open(inside(output, names[0])) as image:
        image.verify()
    write(inside(output, names[2]), {"question": question, "rows": rows, "note": note, "rendering_changes_metrics": False})
    write(inside(output, names[3]), {**alignment, "clearance": clearance, "actual_pdf_fonts": fonts,
                                   "rendered_png_reopened": True})
    plt.close(fig)
    return {"name": name, "question": question,
            "files": {path: {"sha256": sha(inside(output, path)), "bytes": inside(output, path).stat().st_size} for path in names},
            "alignment_status": alignment["status"], "clearance_status": "passed", "font_status": "passed",
            "source_row_count": len(rows), "dpi": 300}


def methods_diagram(plt, output):
    from matplotlib.patches import FancyBboxPatch
    fig, axes = plt.subplots(1, 1, figsize=(7.2, 4.5), squeeze=False)
    fig.subplots_adjust(left=0.035, right=0.965, bottom=0.13, top=0.86)
    axis = axes[0, 0]
    axis.set_xlim(0, 1); axis.set_ylim(0, 1); axis.axis("off")
    fig._revision_diagram_boxes = []
    fig._revision_diagram_routes = []
    def box(x, y, width, height, text, color="#ECEFF2"):
        patch = FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.009", linewidth=0.8, edgecolor="#59616A", facecolor=color)
        axis.add_patch(patch)
        label = axis.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=8, linespacing=1.3)
        fig._revision_diagram_boxes.append((patch, label))
    def arrow(start, end, route):
        axis.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "linewidth": 1, "color": "#59616A", "shrinkA": 1.5, "shrinkB": 2})
        fig._revision_diagram_routes.append({"route": route, "start": list(start), "end": list(end)})
    box(0.01, 0.40, 0.17, 0.20, "RGB image\n256 x 256")
    box(0.25, 0.38, 0.22, 0.24, "ResNet18\nFrozen ImageNet\nweights")
    box(0.55, 0.66, 0.20, 0.25, "PaDiM\nPosition-wise\nGaussian", "#DDE8F1")
    box(0.55, 0.10, 0.20, 0.25, "PatchCore\nRepresentative\nmemory bank", "#F2E2D7")
    box(0.81, 0.65, 0.18, 0.27, "Anomaly map\nImage scores:\nNative / maximum /\ntop-q mean", "#DCEDE9")
    box(0.81, 0.09, 0.18, 0.27, "Anomaly map\nImage scores:\nNative / maximum /\ntop-q mean", "#DCEDE9")
    arrow((0.19, 0.50), (0.24, 0.50), "RGB to frozen features")
    arrow((0.48, 0.56), (0.54, 0.77), "Frozen features to PaDiM")
    arrow((0.48, 0.44), (0.54, 0.23), "Frozen features to PatchCore")
    arrow((0.76, 0.785), (0.80, 0.785), "PaDiM to anomaly map and image scores")
    arrow((0.76, 0.225), (0.80, 0.225), "PatchCore to anomaly map and image scores")
    fig.suptitle("F1 | Two routes from frozen features to anomaly evidence", y=0.97)
    return layout_and_save(plt, output, "F1_methods", fig, axes, [], "How do the two frozen-feature methods differ?", diagram=True,
                           note="Normal images fit each category. Both methods produce continuous anomaly maps and image scores. Top-q aggregation changes image scores only.")


def render_revision(root, output, context, original_source_data=None):
    plot = _plot()
    original_save, original_methods = plot._save, plot._methods
    try:
        plot._save, plot._methods = layout_and_save, methods_diagram
        manifest = plot.render_analysis(root, output, context)
    finally:
        plot._save, plot._methods = original_save, original_methods
    if manifest["figure_count"] != 15 or {item["name"] for item in manifest["figures"]} != set(FIGURES):
        raise ValueError("Revision must produce exactly the original fifteen figure groups")
    records = []
    if original_source_data is not None:
        for name in FIGURES:
            original = original_source_data[name]
            revised = load(inside(output, "source_data/" + name + ".json"))
            fingerprint = assert_source_rows(original["rows"], revised["rows"])
            records.append({"name": name, "rows_sha256": fingerprint, "source_row_count": len(revised["rows"]), "status": "identical"})
    return manifest, records


def verify_output(output, expected_identity=None):
    output = extended(output)
    records = artifact_manifest(output)
    plan = load(inside(output, "plan.json"))
    identity = plan.pop("identity", None)
    if identity != hashlib.sha256(canonical(plan)).hexdigest().upper() or (expected_identity and identity != expected_identity):
        raise ValueError("Output plan identity differs")
    plan["identity"] = identity
    if plan.get("input_analysis") != INPUT_SPEC or set(plan.get("figure_revision_sources", {})) != set(EXPECTED_SOURCES):
        raise ValueError("Output plan does not bind the approved input and six source files")
    if sha(inside(output, "figure_revision_config.json")) != plan["figure_revision_sources"][CONFIG]:
        raise ValueError("Output configuration differs from the six-source revision plan")
    validate_config(load(inside(output, "figure_revision_config.json")))
    if set(plan.get("source_row_hashes", {})) != set(FIGURES):
        raise ValueError("Output plan is missing accepted source-data row hashes")
    if sha(inside(output, "tables.json")) != INPUT_SPEC["tables_sha256"] or sha(inside(output, "cases.json")) != INPUT_SPEC["cases_sha256"]:
        raise ValueError("Copied tables or selected cases differ from the accepted input")
    for name, expected in plan["input_artifacts"].items():
        if name.startswith("cases/") and records.get(name) != expected:
            raise ValueError("Copied selected case asset differs from the accepted input")
    verification = load(inside(output, "verification.json"))
    if verification.get("status") != "passed" or verification.get("identity") != identity or verification.get("figure_count") != 15:
        raise ValueError("Output verification is incomplete")
    success = inside(output, "SUCCESS").read_text(encoding="ascii").strip()
    if success != sha(inside(output, "artifacts.sha256")):
        raise ValueError("Output completion fingerprint differs")
    manifest = load(inside(output, "plot_manifest.json"))
    if manifest.get("figure_count") != 15 or {item["name"] for item in manifest["figures"]} != set(FIGURES):
        raise ValueError("Revised output is missing figure groups")
    provenance = manifest.get("input_provenance", {})
    if (provenance.get("input_analysis_identity") != ANALYSIS_ID
            or provenance.get("figure_revision_identity") != identity
            or provenance.get("figure_revision_sources") != plan["figure_revision_sources"]
            or provenance.get("only_overrides") != ["_save", "_methods"]):
        raise ValueError("Rendered manifest source binding differs from the revision plan")
    for figure in manifest["figures"]:
        for name, spec in figure["files"].items():
            if records.get(name) != spec["sha256"] or inside(output, name).stat().st_size != spec["bytes"]:
                raise ValueError("Figure manifest differs from artifact fingerprint")
        qa = load(inside(output, "qa/" + figure["name"] + ".alignment.json"))
        if qa.get("clearance", {}).get("status") != "passed" or qa.get("actual_pdf_fonts", {}).get("status") != "passed":
            raise ValueError("Figure layout or typography gate is incomplete")
        pdf_font_audit(inside(output, "figures/" + figure["name"] + ".pdf"))
        from PIL import Image
        with Image.open(inside(output, "figures/" + figure["name"] + ".png")) as image:
            image.verify()
    invariance = load(inside(output, "data_invariance.json"))
    if (invariance.get("status") != "passed" or len(invariance.get("figures", [])) != 15
            or {item.get("name") for item in invariance.get("figures", [])} != set(FIGURES)
            or any(invariance.get(key) != 0 for key in ("new_fits", "model_predict_calls", "new_statistics"))):
        raise ValueError("Data invariance evidence is incomplete")
    for entry in invariance["figures"]:
        revised = load(inside(output, "source_data/" + entry["name"] + ".json"))
        if (hashlib.sha256(canonical(revised["rows"])).hexdigest().upper() != entry["rows_sha256"]
                or entry["rows_sha256"] != plan["source_row_hashes"][entry["name"]]):
            raise ValueError("Revised source data no longer matches its invariant rows")
    return {"status": "passed", "identity": identity, "figure_count": 15, "artifact_files": len(records),
            "post_download_visual_review_required": True}


def run(root, job_id, plan):
    require_current_acceptance(root, "figure_revision")
    if not re.fullmatch(r"[1-9][0-9]*", str(job_id)) or os.environ.get("SLURM_JOB_ID") != str(job_id):
        raise ValueError("Figure rendering requires its assigned scheduler job")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in ("-1", "") or os.environ.get("SLURM_GPUS") not in (None, "", "0"):
        raise ValueError("Figure revision requires a CPU-only allocation")
    if (os.environ.get("SLURM_CPUS_PER_TASK") != "2" or os.environ.get("SLURM_MEM_PER_NODE") != "8192"
            or os.environ.get("SLURM_JOB_PARTITION") != "MGPU-TC2" or os.environ.get("SLURM_JOB_QOS", "normal") != "normal"):
        raise ValueError("Figure revision allocation differs from the approved CPU resources")
    verify_plan(root, plan)
    root = extended(root)
    record = inside(root, "run/validation_tc2_gpu/step8_figure_revision_job_" + str(job_id))
    record.mkdir(parents=True, exist_ok=True)
    relative = "run/tc2_gpu/summaries/figure_revision/" + plan["identity"]
    if (record / "plan.json").exists() and load(record / "plan.json") != plan:
        raise ValueError("Existing wrapper plan differs from this figure revision")
    if (record / "state.json").exists():
        previous = load(record / "state.json")
        if (previous.get("job_id") != str(job_id) or previous.get("identity") != plan["identity"]
                or previous.get("status") != "running" or previous.get("phase") != "tests"
                or previous.get("output_relative") is not None
                or previous.get("new_fits") != 0 or previous.get("model_predict_calls") != 0):
            raise ValueError("Job revision already attempted rendering; automatic retries are forbidden")
    final = inside(root, relative)
    if final.exists():
        raise ValueError("Immutable figure revision output already exists")
    stage = inside(record, "staging_output")
    stage.mkdir()
    if not (record / "plan.json").exists():
        write(record / "plan.json", plan)
    state = {"schema_version": "1.0", "job_id": str(job_id), "identity": plan["identity"],
             "status": "running", "phase": "render", "output_relative": relative,
             "step_8_complete": False, "new_fits": 0, "model_predict_calls": 0, "new_statistics": 0}
    _state(record / "state.json", state)
    try:
        original = inside(root, plan["input_analysis"]["relative_path"])
        for name in ("tables.json", "cases.json"):
            shutil.copyfile(inside(original, name), inside(stage, name))
        copied = {}
        for name, expected in plan["input_artifacts"].items():
            if name.startswith("cases/"):
                destination = inside(stage, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(inside(original, name), destination)
                if sha(destination) != expected:
                    raise ValueError("Selected case asset changed while copying")
                copied[name] = expected
        tables, cases = load(stage / "tables.json"), load(stage / "cases.json")["cases"]
        source_data = {name: load(inside(original, "source_data/" + name + ".json")) for name in FIGURES}
        context = {"tables": tables, "cases": cases, "resources": tables["resources"],
                   "mask_areas": tables["mask_areas"], "score_distributions": source_data["F4_score_distributions"]["rows"],
                   "provenance": {"input_analysis_identity": ANALYSIS_ID, "figure_revision_identity": plan["identity"],
                                  "figure_revision_sources": plan["figure_revision_sources"],
                                  "only_overrides": ["_save", "_methods"]}}
        manifest, invariance = render_revision(root, stage, context, source_data)
        verify_plan(root, plan)
        write(stage / "plan.json", plan)
        shutil.copyfile(inside(root, CONFIG), stage / "figure_revision_config.json")
        write(stage / "data_invariance.json", {"status": "passed", "figures": invariance,
              "copied_case_assets": copied, "tables_sha256": sha(stage / "tables.json"),
              "cases_sha256": sha(stage / "cases.json"), "new_fits": 0, "model_predict_calls": 0, "new_statistics": 0})
        write(stage / "verification.json", {"status": "passed", "identity": plan["identity"], "figure_count": manifest["figure_count"],
              "all_51_frozen_sources_preserved": True, "all_original_artifacts_preserved": True,
              "all_source_rows_identical": True, "all_png_reopened": True, "all_pdf_glyph_sizes_at_least_7pt": True,
              "all_final_layout_gates_passed": True, "post_download_visual_review_required": True})
        files = sorted(item for item in stage.rglob("*") if item.is_file())
        with (stage / "artifacts.sha256").open("x", encoding="ascii", newline="\n") as stream:
            for item in files:
                stream.write(sha(item) + "  " + item.relative_to(stage).as_posix() + "\n")
        (stage / "SUCCESS").write_text(sha(stage / "artifacts.sha256") + "\n", encoding="ascii", newline="\n")
        verify_output(stage, plan["identity"])
        final.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(final)
        state["status"] = "passed"
        state["phase"] = "render_complete_visual_review_pending"
        _state(record / "state.json", state)
    except Exception as error:
        state["status"] = "failed"
        state["error"] = str(error)
        _state(record / "state.json", state)
        raise
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "preflight", "run"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        if name == "plan":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--analysis-root", type=Path)
        else:
            command.add_argument("--plan", type=Path, required=True)
            if name == "run":
                command.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = build_plan(args.root, args.analysis_root)
        write(args.output, result)
    elif args.command == "preflight":
        result = verify_plan(args.root, load(args.plan))
    else:
        result = run(args.root, args.job_id, load(args.plan))
    print(json.dumps({"status": "passed", "command": args.command, "identity": result["identity"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
