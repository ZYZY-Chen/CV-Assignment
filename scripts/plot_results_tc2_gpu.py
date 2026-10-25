"""Render immutable TC2 GPU analysis tables with Python and Matplotlib only.

Plotting is deliberately lazy: importing this module never requires Matplotlib,
Torch, a model, or a GPU. Rendering requires the accepted TC2 CPU environment.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import textwrap

import numpy as np

METHODS = ("padim", "patchcore")
LABELS = {"padim": "PaDiM", "patchcore": "PatchCore"}
COLORS = {"padim": "#3E6C96", "patchcore": "#BD6D36"}
RULE_LABELS = {"native": "Native", "max": "Map maximum", "top_0.001": "Top 0.1%", "top_0.01": "Top 1%", "top_0.05": "Top 5%"}
RULE_COLORS = {"native": "#58616A", "max": "#9A7BA8", "top_0.01": "#27877F"}
CATEGORIES = ("bottle", "cable", "capsule", "screw", "tile", "wood")
METRIC_LABELS = {"image_auroc": "Image AUROC", "pixel_ap": "Pixel AP", "pixel_auroc": "Pixel AUROC", "normal_fpr": "Normal false positive rate", "anomaly_recall": "Anomaly recall"}


def _extended(path):
    path = Path(path).absolute()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(path))
    return path


def _inside(directory, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Plot inputs must use relative POSIX paths")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
        raise ValueError("Plot input leaves the analysis directory")
    root = _extended(directory)
    path = root.joinpath(*relative.parts)
    for parent in (path, *path.parents):
        attributes = parent.lstat().st_file_attributes if os.name == "nt" and parent.exists() else 0
        if parent.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise ValueError("Plot input may not traverse a symbolic link")
        if parent == root:
            return path
    raise ValueError("Plot input leaves the analysis directory")


def _sha(path):
    value = hashlib.sha256()
    with _extended(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def _write(path, value):
    path = _extended(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n")


def _finite(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Plot value must be finite: " + field)
    return float(value)


def _native(rows):
    return [row for row in rows if row.get("score_rule", "native") == "native"]


def _group(rows, fields):
    result = defaultdict(list)
    for row in rows:
        result[tuple(row[field] for field in fields)].append(row)
    return result


def _mean_sd(values):
    values = np.asarray(values, dtype=np.float64)
    if values.shape != (3,) or not np.isfinite(values).all():
        raise ValueError("A variability bar requires exactly three finite run seeds")
    return float(values.mean()), float(values.std(ddof=1))


def _backend():
    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError("Matplotlib is required for full TC2 CPU figure validation; plotting is incomplete") from error
    matplotlib.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"],
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 9, "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "figure.titlesize": 11,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "text.usetex": False,
        "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": 0.7,
        "legend.frameon": False, "savefig.dpi": 300})
    return plt


def _grid(plt, rows=1, columns=2, height=None, bottom=0.22):
    fig, axes = plt.subplots(rows, columns, figsize=(7.2, height or 2.9 * rows), squeeze=False)
    fig.subplots_adjust(left=0.105, right=0.97, bottom=bottom, top=0.84, wspace=0.36, hspace=0.48)
    return fig, axes


def _labels(axes):
    for index, axis in enumerate(np.asarray(axes, dtype=object).reshape(-1)):
        axis.text(-0.08, 1.08, chr(ord("a") + index), transform=axis.transAxes,
                  fontsize=9, fontweight="bold", ha="left", va="bottom")


def require_matplotlib_panel_alignment(fig, axes, *, image_plate=False, diagram=False):
    """Measure final plot areas and enforce 1.5-point comparable-panel bounds."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    grid = np.asarray(axes, dtype=object)
    if grid.ndim != 2:
        raise ValueError("Alignment requires an explicit rectangular axes grid")
    records = []
    for index, axis in enumerate(grid.reshape(-1)):
        bbox = axis.get_window_extent(renderer=renderer).transformed(fig.dpi_scale_trans.inverted())
        values = [float(value * 72) for value in (bbox.x0, bbox.y0, bbox.width, bbox.height)]
        records.append({"panel": index, "x_pt": values[0], "y_pt": values[1], "width_pt": values[2], "height_pt": values[3]})
    tolerance = 1.5
    checks = []
    if not diagram:
        for row in range(grid.shape[0]):
            values = records[row * grid.shape[1]:(row + 1) * grid.shape[1]]
            for field in ("y_pt", "width_pt", "height_pt"):
                delta = max(value[field] for value in values) - min(value[field] for value in values)
                checks.append({"group": "row_" + str(row), "field": field, "difference_pt": delta})
                if delta > tolerance:
                    raise ValueError("Final figure panels are misaligned: row " + str(row) + "/" + field)
            if len(values) > 2:
                gutters = [right["x_pt"] - left["x_pt"] - left["width_pt"] for left, right in zip(values, values[1:])]
                delta = max(gutters) - min(gutters)
                checks.append({"group": "row_" + str(row), "field": "repeated_gutter", "difference_pt": delta})
                if delta > tolerance:
                    raise ValueError("Final figure panel gutters differ")
        if not image_plate:
            for column in range(grid.shape[1]):
                values = records[column::grid.shape[1]]
                for field in ("x_pt", "width_pt", "height_pt"):
                    delta = max(value[field] for value in values) - min(value[field] for value in values)
                    checks.append({"group": "column_" + str(column), "field": field, "difference_pt": delta})
                    if delta > tolerance:
                        raise ValueError("Final figure panels are misaligned: column " + str(column) + "/" + field)
    for index, left in enumerate(records):
        for right in records[index + 1:]:
            overlap_x = min(left["x_pt"] + left["width_pt"], right["x_pt"] + right["width_pt"]) - max(left["x_pt"], right["x_pt"])
            overlap_y = min(left["y_pt"] + left["height_pt"], right["y_pt"] + right["height_pt"]) - max(left["y_pt"], right["y_pt"])
            if overlap_x > tolerance and overlap_y > tolerance:
                raise ValueError("Final plot areas overlap")
    return {"status": "not_applicable" if diagram or grid.size == 1 else "passed", "tolerance_pt": tolerance,
            "panels": records, "checks": checks, "measured_after_final_draw": True,
            "exemptions": ["Method diagram has one free-positioned canvas"] if diagram else
                (["Image rows preserve each original image aspect ratio; column-height comparison between different cases is not applicable"] if image_plate else [])}


def _save(plt, output, name, fig, axes, rows, question, *, note="", image_plate=False, diagram=False):
    handles, labels = [], []
    for axis in np.asarray(axes, dtype=object).reshape(-1):
        legend = axis.get_legend()
        if legend is not None:
            values, names = axis.get_legend_handles_labels()
            for value, label in zip(values, names):
                if label not in labels:
                    handles.append(value); labels.append(label)
            legend.remove()
    for legend in list(fig.legends):
        for value, label in zip(legend.legend_handles, [text.get_text() for text in legend.get_texts()]):
            if label not in labels:
                handles.append(value); labels.append(label)
        legend.remove()
    if handles:
        fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.53, 0.125), ncol=min(5, len(handles)), fontsize=7.5)
    if note:
        fig.text(0.105, 0.035, textwrap.fill(note, 112), fontsize=7.5, va="bottom", ha="left")
    alignment = require_matplotlib_panel_alignment(fig, axes, image_plate=image_plate, diagram=diagram)
    for text in fig.findobj(match=lambda artist: hasattr(artist, "get_fontsize") and hasattr(artist, "get_text")):
        if text.get_visible() and text.get_text() and text.get_fontsize() < 7:
            raise ValueError("Figure text falls below the approved 7-point minimum")
    for folder in ("figures", "source_data", "qa"):
        _extended(Path(output) / folder).mkdir(parents=True, exist_ok=True)
    png, pdf = "figures/" + name + ".png", "figures/" + name + ".pdf"
    data, qa = "source_data/" + name + ".json", "qa/" + name + ".alignment.json"
    fig.savefig(_extended(Path(output) / png), dpi=300, facecolor="white")
    fig.savefig(_extended(Path(output) / pdf), format="pdf", facecolor="white", metadata={"Title": question, "Creator": "TC2 GPU analysis"})
    _write(Path(output) / data, {"question": question, "rows": rows, "note": note, "rendering_changes_metrics": False})
    _write(Path(output) / qa, alignment)
    plt.close(fig)
    return {"name": name, "question": question, "files": {path: {"sha256": _sha(Path(output) / path), "bytes": _extended(Path(output) / path).stat().st_size} for path in (png, pdf, data, qa)},
            "alignment_status": alignment["status"], "source_row_count": len(rows), "dpi": 300}


def _methods(plt, output):
    from matplotlib.patches import FancyBboxPatch
    fig, axes = _grid(plt, 1, 1, height=4.1, bottom=0.15)
    axis = axes[0, 0]
    axis.set_xlim(0, 1); axis.set_ylim(0, 1); axis.axis("off")
    def box(x, y, width, height, text, color="#ECEFF2"):
        axis.add_patch(FancyBboxPatch((x, y), width, height, boxstyle="round,pad=0.012", linewidth=0.8, edgecolor="#59616A", facecolor=color))
        axis.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=9)
    def arrow(start, end):
        axis.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "linewidth": 1, "color": "#59616A"})
    box(0.02, 0.43, 0.20, 0.20, "RGB image\n256 x 256")
    box(0.29, 0.43, 0.22, 0.20, "ResNet18\nFrozen ImageNet weights")
    box(0.61, 0.71, 0.34, 0.19, "PaDiM\nPosition-wise Gaussian", "#DDE8F1")
    box(0.61, 0.37, 0.34, 0.19, "PatchCore\nRepresentative memory bank", "#F2E2D7")
    box(0.61, 0.03, 0.34, 0.19, "Image scores\nNative / maximum / top-q mean", "#DCEDE9")
    arrow((0.22, 0.53), (0.29, 0.53)); arrow((0.51, 0.55), (0.61, 0.80)); arrow((0.51, 0.49), (0.61, 0.46))
    arrow((0.78, 0.37), (0.78, 0.22))
    axis.text(0.02, 0.14, "Normal images fit each category.\nContinuous anomaly maps localize defects.\nTop-q changes image scores only.", fontsize=9, va="center")
    fig.suptitle("F1 | Two routes from frozen features to anomaly evidence", y=0.97)
    return _save(plt, output, "F1_methods", fig, axes, [], "How do the two frozen-feature methods differ?", diagram=True)


def _baseline(plt, output, tables):
    rows = _native(tables["baseline"])
    fig, axes = _grid(plt, 1, 2, height=3.7, bottom=0.23)
    for axis, metric in zip(axes[0], ("image_auroc", "pixel_ap")):
        for method, offset in zip(METHODS, (-0.12, 0.12)):
            means, deviations = [], []
            for category in CATEGORIES:
                matches = [row for row in rows if row["category"] == category and row["method"] == method]
                if {row["run_seed"] for row in matches} != {17, 29, 43} or len(matches) != 3:
                    raise ValueError("Baseline plot requires all six categories and three seeds")
                mean, sd = _mean_sd([row[metric] for row in matches]); means.append(mean); deviations.append(sd)
            axis.errorbar(means, np.arange(6) + offset, xerr=deviations, fmt="o", markersize=4,
                          capsize=2, color=COLORS[method], label=LABELS[method], linewidth=0.9)
        axis.set_yticks(np.arange(6), CATEGORIES); axis.invert_yaxis(); axis.set_xlabel(METRIC_LABELS[metric]); axis.grid(axis="x", alpha=0.2)
        axis.set_title("Detection" if metric == "image_auroc" else "Localization")
    axes[0, 0].legend(loc="lower left", bbox_to_anchor=(0, -0.37), ncol=2)
    _labels(axes); fig.suptitle("Baseline | Category differences under the same normal training budget", y=0.98)
    return _save(plt, output, "baseline_comparison", fig, axes, rows, "How do detection and localization differ by category?",
                 note="N=100; native image scores. Points show means and bars show sample SD across the same three run seeds (n=3, ddof=1). Classes remain separate.")


def _configuration_value(row, field):
    if field in row:
        return row[field]
    config = row.get("configuration", row.get("config", {}))
    if field in config:
        return config[field]
    for method in METHODS:
        if field in config.get(method, {}):
            return config[method][field]
    raise ValueError("Ablation row is missing the configuration field: " + field)


def _ablation(plt, output, tables):
    rows = _native(tables["ablations"])
    fig, axes = _grid(plt, 1, 2, height=3.4, bottom=0.25)
    for axis, stage, field, method, baseline, title in (
            (axes[0, 0], "H1", "n_dims", "padim", 100, "PaDiM dimensions"),
            (axes[0, 1], "H2", "coreset_ratio", "patchcore", 0.05, "PatchCore coreset ratio")):
        for category, marker, color in (("cable", "o", "#3E6C96"), ("screw", "s", "#BD6D36")):
            selected = [row for row in rows if row["category"] == category and row["method"] == method and row["run_seed"] == 17 and row.get("stage") in (stage, "B0")]
            points = sorted((_finite(_configuration_value(row, field), field), _finite(row["pixel_ap"], "pixel_ap")) for row in selected)
            if len(points) != 3 or baseline not in [point[0] for point in points]:
                raise ValueError("Hyperparameter figure is missing a predeclared setting or baseline")
            x = [point[0] * (100 if field == "coreset_ratio" else 1) for point in points]
            axis.plot(x, [point[1] for point in points], marker=marker, color=color, label=category, linewidth=1.2)
        axis.set_title(title); axis.set_xlabel("Retained dimensions" if field == "n_dims" else "Coreset fraction (%)"); axis.set_ylabel("Pixel AP"); axis.grid(alpha=0.2)
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=2)
    _labels(axes); fig.suptitle("F3 | Sensitivity to representation and memory budgets", y=0.98)
    return _save(plt, output, "F3_hyperparameters", fig, axes, rows, "How sensitive is localization to the predeclared resource settings?",
                 note="Seed 17 only; exploratory scans, with no variability bars. Baseline points are reused. All fixed settings are shown; no optimum is selected on test data.")


def _components(plt, output, tables):
    rows = _native(tables["ablations"])
    fig, axes = _grid(plt, 1, 2, height=3.6, bottom=0.25)
    source = []
    for position, category in enumerate(("cable", "screw")):
        deltas = []
        for seed in (17, 29, 43):
            matches = [row for row in rows if row["category"] == category and row["method"] == "patchcore" and row["run_seed"] == seed
                       and row.get("stage") in ("B0", "R0", "C1", "C1R")]
            selected = {str(_configuration_value(row, "sampling")): row for row in matches}
            if set(selected) != {"random", "coreset"}:
                raise ValueError("Sampling comparison requires matched coreset and random fits for all seeds")
            delta = selected["random"]["pixel_ap"] - selected["coreset"]["pixel_ap"]
            deltas.append(delta); source.append({"category": category, "run_seed": seed, "delta_pixel_ap_random_minus_coreset": delta})
        mean, sd = _mean_sd(deltas)
        axes[0, 0].scatter(np.full(3, position) + np.asarray([-0.07, 0, 0.07]), deltas, color="#9A7BA8", s=20)
        axes[0, 0].errorbar(position, mean, yerr=sd, color="#303941", marker="D", capsize=3, markersize=4)
    axes[0, 0].axhline(0, color="#72777C", linewidth=0.8); axes[0, 0].set_xticks([0, 1], ["cable", "screw"])
    axes[0, 0].set_ylabel("Pixel AP difference"); axes[0, 0].set_title("Random minus coreset (paired seeds)")
    layer_order = ("layer1+layer2+layer3", "layer2+layer3", "layer3")
    for category, color, marker in (("cable", "#3E6C96", "o"), ("screw", "#BD6D36", "s")):
        selected = [row for row in rows if row["method"] == "padim" and row["category"] == category and row["run_seed"] == 17 and row.get("stage") in ("B0", "C2")]
        lookup = {"+".join(_configuration_value(row, "layers")): row for row in selected}
        if set(lookup) != set(layer_order):
            raise ValueError("Layer comparison must retain all three fixed configurations")
        axes[0, 1].plot(range(3), [lookup[key]["pixel_ap"] for key in layer_order], marker=marker, color=color, label=category)
    axes[0, 1].set_xticks(range(3), ["1+2+3", "2+3", "3"]); axes[0, 1].set_xlabel("PaDiM layers (100 dimensions)"); axes[0, 1].set_ylabel("Pixel AP")
    axes[0, 1].set_title("Feature-layer configuration (seed 17)"); axes[0, 1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2)
    for axis in axes[0]: axis.grid(axis="y", alpha=0.2)
    _labels(axes); fig.suptitle("F3 | Controlled component comparisons", y=0.98)
    return _save(plt, output, "F3_components", fig, axes, rows + source, "What changes when sampling or feature layers are replaced?",
                 note="Sampling uses matched feature pools and bank counts; diamonds are paired mean +/- sample SD (n=3). Layer scans use one seed and carry no error bars; spatial scale also changes.")


def _fewshot(plt, output, tables):
    rows = _native(tables["ablations"])
    fig, axes = _grid(plt, 1, 2, height=3.3, bottom=0.25)
    for axis, category in zip(axes[0], ("cable", "screw")):
        for method in METHODS:
            selected = [row for row in rows if row["category"] == category and row["method"] == method and row["run_seed"] == 17 and row.get("stage") in ("B0", "F1")]
            values = {row["normal_train_n"]: row for row in selected}
            if set(values) != {20, 50, 100}:
                raise ValueError("Few-shot plot requires the full nested N=20/50/100 comparison")
            axis.plot([20, 50, 100], [values[n]["image_auroc"] for n in (20, 50, 100)], marker="o", color=COLORS[method], label=LABELS[method])
        axis.set_xticks([20, 50, 100]); axis.set_xlabel("Normal fitting images"); axis.set_ylabel("Image AUROC"); axis.set_title(category); axis.grid(alpha=0.2)
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2)
    _labels(axes); fig.suptitle("F3 | Detection as normal fitting data decreases", y=0.98)
    return _save(plt, output, "F3_fewshot", fig, axes, rows, "How does the normal-image budget affect detection?",
                 note="Seed 17; exploratory curves without SD. Both methods share the same ordered nested training lists. N=100 is reused from B0.")


def _improvement(plt, output, tables):
    rows = tables["improvement"]
    selected = [row for row in rows if row["score_rule"] == "top_0.01"]
    fig, axes = _grid(plt, 1, 2, height=3.9, bottom=0.25)
    plotted = []
    for axis, metric in zip(axes[0], ("image_auroc", "normal_fpr")):
        for reference, offset, color in (("native", -0.12, "#58616A"), ("max", 0.12, "#9A7BA8")):
            for position, category in enumerate(CATEGORIES):
                values = [row["delta_" + metric + "_vs_" + reference] * 100 for row in selected if row["category"] == category]
                mean, sd = _mean_sd(values)
                axis.errorbar(mean, position + offset, xerr=sd, marker="o", markersize=4, capsize=2, color=color, label=RULE_LABELS[reference] if position == 0 else None)
                plotted.append({"category": category, "metric": metric, "reference": reference, "mean_delta_pp": mean, "sample_sd_pp": sd, "n_seeds": 3})
        axis.axvline(0, color="#72777C", linewidth=0.8); axis.set_yticks(range(6), CATEGORIES); axis.invert_yaxis(); axis.grid(axis="x", alpha=0.2)
        axis.set_xlabel("Top 1% minus reference (percentage points)"); axis.set_title("Ranking: image AUROC" if metric == "image_auroc" else "Working point: normal false positives")
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=2)
    _labels(axes); fig.suptitle("F4 | Fixed top-1% aggregation against both controls", y=0.98)
    return _save(plt, output, "F4_improvement", fig, axes, selected + plotted, "Does fixed region aggregation change ranking and calibrated false positives?",
                 note="Paired differences use the same category, seed and saved maps (n=3 seeds; mean +/- sample SD). Lower FPR is better. Image scoring changes; pixel maps and pixel metrics remain identical.")


def _q_sensitivity(plt, output, tables):
    summary = [row for row in tables["baseline_summary"] if row["method"] == "patchcore"]
    lookup = {row["score_rule"]: row for row in summary}
    required = {"native", "max", "top_0.001", "top_0.01", "top_0.05"}
    if set(lookup) != required:
        raise ValueError("Sensitivity plot must include all five predeclared image-score rules")
    fig, axes = _grid(plt, 1, 2, height=3.4, bottom=0.27)
    q_rules = ("top_0.001", "top_0.01", "top_0.05")
    for axis, metric in zip(axes[0], ("image_auroc", "normal_fpr")):
        means = [lookup[rule][metric + "_mean"] for rule in q_rules]
        sd = [lookup[rule][metric + "_std"] for rule in q_rules]
        axis.errorbar([0.1, 1, 5], means, yerr=sd, color="#27877F", marker="o", capsize=3, label="Top-q mean")
        for rule, style in (("native", "--"), ("max", ":")):
            axis.axhline(lookup[rule][metric + "_mean"], color=RULE_COLORS[rule], linestyle=style, label=RULE_LABELS[rule])
        axis.set_xscale("log"); axis.set_xticks([0.1, 1, 5], ["0.1", "1", "5"]); axis.set_xlabel("Highest-scoring pixels q (%)")
        axis.set_ylabel(METRIC_LABELS[metric]); axis.grid(alpha=0.2)
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.29), ncol=3)
    _labels(axes); fig.suptitle("F4 | Sensitivity to the predeclared aggregation area", y=0.98)
    return _save(plt, output, "F4_q_sensitivity", fig, axes, summary, "How does the chosen aggregation area affect the six-class macro result?",
                 note="First average six categories within each seed, then summarize the three seed macros (sample SD, ddof=1). q=1% is fixed; q=0.1% and 5% are sensitivity controls, not selected optima.")


def _distributions(plt, output, context):
    rows = [row for row in context["score_distributions"] if row.get("role", "test") == "test" and row["score_rule"] in ("native", "max", "top_0.01")]
    fig, axes = _grid(plt, 2, 3, height=5.8, bottom=0.19)
    for axis, category in zip(axes.reshape(-1), CATEGORIES):
        for rule in ("native", "max", "top_0.01"):
            for label, style in ((0, "-"), (1, "--")):
                values = sorted(_finite(row["score"], "score") for row in rows if row["category"] == category and row["score_rule"] == rule and row["label"] == label)
                if not values:
                    raise ValueError("Score-distribution figure is missing a category, rule or label")
                axis.step(values, np.arange(1, len(values) + 1) / len(values), where="post", color=RULE_COLORS[rule], linestyle=style, linewidth=1)
        axis.set_title(category); axis.set_xlabel("Raw image score"); axis.set_ylabel("Empirical CDF"); axis.set_ylim(0, 1.03); axis.grid(alpha=0.15)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=RULE_COLORS[rule], label=RULE_LABELS[rule]) for rule in ("native", "max", "top_0.01")]
    handles += [Line2D([], [], color="#58616A", linestyle=style, label=name) for style, name in (("-", "Normal"), ("--", "Anomaly"))]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.52, 0.085), ncol=5, fontsize=7.5)
    _labels(axes); fig.suptitle("F4 | Score distributions across normal and anomalous products", y=0.97)
    return _save(plt, output, "F4_score_distributions", fig, axes, rows, "Which score distributions explain the changed working point?",
                 note="PatchCore baseline predictions; all three seeds shown as descriptive pooled CDFs. Images repeat across seeds and are not independent repetitions. Raw units may differ across rules and categories.")


def _defect_size(plt, output, tables):
    rows = [row for row in tables["size_recall"] if row["method"] == "patchcore" and row["score_rule"] in ("native", "max", "top_0.01")]
    fig, axes = _grid(plt, 1, 2, height=3.5, bottom=0.27)
    displayed = []
    for axis, size_group in zip(axes[0], ("small", "large")):
        axis.set_title(size_group.capitalize() + " defects")
        for position, rule in enumerate(("native", "max", "top_0.01")):
            seed_values = []
            coverage = []
            for seed in (17, 29, 43):
                selected = [row for row in rows if row["run_seed"] == seed and row["size_group"] == size_group and row["score_rule"] == rule and row["n_images"] > 0]
                coverage.append(len(selected))
                if selected:
                    seed_values.append(float(np.mean([row["recall"] for row in selected])))
            if seed_values:
                mean, sd = _mean_sd(seed_values)
                axis.errorbar(position, mean, yerr=sd, marker="o", capsize=3, color=RULE_COLORS[rule])
                displayed.append({"size_group": size_group, "score_rule": rule, "mean_recall": mean, "sample_sd": sd, "categories_per_seed": coverage})
            else:
                axis.text(position, 0.5, "No cases", ha="center", fontsize=7.5)
                displayed.append({"size_group": size_group, "score_rule": rule, "categories_per_seed": coverage, "empty_group": True})
        axis.set_xticks(range(3), [RULE_LABELS[rule] for rule in ("native", "max", "top_0.01")]); axis.set_ylabel("Category-macro anomaly recall"); axis.set_ylim(-0.04, 1.06); axis.grid(axis="y", alpha=0.2)
    _labels(axes); fig.suptitle("F4 | Defect-size boundary of image-score aggregation", y=0.98)
    return _save(plt, output, "F4_defect_size", fig, axes, rows + displayed, "Does aggregation behave differently for small and larger defects?",
                 note="Fixed original-mask area groups; only nonempty category groups enter each macro (coverage recorded in source data). Mean +/- sample SD across three seeds; no pixel-level pseudo-replication.")


def _resources(plt, output, tables):
    rows = [row for row in tables["resources"] if row["dataset"] == "mvtec_ad"]
    if not rows or not all(math.isfinite(row["predict_ms_per_image"]) and row["predict_ms_per_image"] > 0
                           and math.isfinite(row["model_tensor_bytes"]) and row["model_tensor_bytes"] > 0 for row in rows):
        raise ValueError("Log-scale resource inputs must all be finite and strictly positive")
    metrics = {row["run_key"]: row for row in _native(tables["baseline"] + tables["ablations"])}
    fig, axes = _grid(plt, 1, 2, height=3.4, bottom=0.28)
    plotted = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        for axis, field, scale in ((axes[0, 0], "predict_ms_per_image", 1), (axes[0, 1], "model_tensor_bytes", 1 / 1024 ** 2)):
            values, accuracy = [], []
            for row in selected:
                value = _finite(row[field], field) * scale
                if value <= 0:
                    raise ValueError("Resource logarithmic axes require positive measurements")
                values.append(value); accuracy.append(metrics[row["run_key"]]["image_auroc"])
            axis.scatter(values, accuracy, color=COLORS[method], s=20, alpha=0.7, label=LABELS[method], linewidths=0)
        plotted.extend({**row, "image_auroc": metrics[row["run_key"]]["image_auroc"]} for row in selected)
    for axis in axes[0]:
        axis.set_xscale("log"); axis.set_ylabel("Native image AUROC"); axis.grid(alpha=0.2)
    axes[0, 0].set_xlabel("Cached-feature prediction (ms / image)"); axes[0, 1].set_xlabel("Estimated model tensor storage (MiB)")
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.31), ncol=2)
    _labels(axes); fig.suptitle("F5 | Accuracy and the cost of the recorded cached workflow", y=0.98)
    return _save(plt, output, "F5_resources", fig, axes, plotted, "What latency and model-state costs accompany the measured accuracy?",
                 note="Each dot is an AD fit on the accepted A40 protocol. Cached-feature prediction excludes shared extraction and is not end-to-end latency. Tensor storage is an explicit metadata-based estimate, not a serialized checkpoint size.")


def _loco(plt, output, tables):
    rows = _native(tables["loco"])
    fig, axes = _grid(plt, 2, 2, height=5.8, bottom=0.18)
    groups = ("logical_anomalies", "structural_anomalies")
    for column, category in enumerate(("juice_bottle", "screw_bag")):
        for row_index, metric in enumerate(("image_auroc", "pixel_ap")):
            axis = axes[row_index, column]
            for method, offset in zip(METHODS, (-0.08, 0.08)):
                values = []
                for group in groups:
                    selected = [item for item in rows if item["category"] == category and item["method"] == method and item["group"] == group]
                    if len(selected) != 1:
                        raise ValueError("LOCO figure requires one result for each method/category/anomaly group")
                    values.append(selected[0][metric])
                axis.plot(np.arange(2) + offset, values, "o-", color=COLORS[method], label=LABELS[method], markersize=4)
            axis.set_xticks([0, 1], ["Logical", "Structural"]); axis.set_ylabel(METRIC_LABELS[metric]); axis.set_title(category); axis.grid(alpha=0.2)
    axes[1, 0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2)
    _labels(axes); fig.suptitle("LOCO | Separate logical and structural anomaly evidence", y=0.97)
    return _save(plt, output, "loco_extension", fig, axes, rows, "How do the methods transfer to the two distinct LOCO anomaly groups?",
                 note="Extension only: seed 17, N=100, one fit per method/category. No SD is assigned. LOCO remains separate from the six-class AD macro; pooled LOCO pixel metrics are auxiliary.")


def validate_case_assets(output, cases):
    """Read-only validation also used by CPU tests without Matplotlib."""
    from PIL import Image
    if not isinstance(cases, list) or not 1 <= len(cases) <= 16:
        raise ValueError("The approved display subset must contain between one and sixteen cases")
    seen, calibration = set(), {}
    for case in cases:
        if case["case_id"] in seen:
            raise ValueError("Repeated display case ID")
        seen.add(case["case_id"])
        with Image.open(_inside(output, case["image_path"])) as image, Image.open(_inside(output, case["mask_path"])) as mask:
            if image.size != mask.size or image.width < 1 or image.height < 1:
                raise ValueError("Display image and original union-mask dimensions differ")
            mask_values = np.asarray(mask)
            if mask_values.ndim != 2 or not set(np.unique(mask_values)).issubset({0, 1, 255}):
                raise ValueError("Display truth must be an original-resolution binary union mask")
        if set(case["maps"]) != set(METHODS):
            raise ValueError("Every display case requires both methods")
        for method in METHODS:
            spec = case["maps"][method]
            values = np.load(_inside(output, spec["path"]), allow_pickle=False)
            if values.dtype != np.float32 or values.shape != (256, 256) or not np.isfinite(values).all():
                raise ValueError("Display anomaly maps must be finite FP32 at the frozen 256 resolution")
            minimum = _finite(spec["display_min"], "display_min")
            maximum = _finite(spec["display_max"], "display_max")
            if minimum != 0 or maximum <= minimum:
                raise ValueError("Display ranges must use zero and the fixed normal-development calibration")
            source = case["source_result_ids"][method] if isinstance(case["source_result_ids"], dict) else case["category"]
            key = (case["dataset"], case["category"], method, source)
            if key in calibration and calibration[key] != (minimum, maximum):
                raise ValueError("A source model may not change display range between images")
            calibration[key] = (minimum, maximum)
    return {"status": "passed", "cases": len(cases), "calibrations": len(calibration), "map_precision": "float32", "truth_resolution": "original"}


def case_score_annotation(case):
    """Format saved image decisions; score rounding is confined to display text."""
    lookup = {}
    for point in case.get("scores", []):
        key = (point["method"], point["score_rule"])
        if key in lookup:
            raise ValueError("A display case repeats an image-score decision")
        score, threshold = _finite(point["score"], "case_score"), _finite(point["threshold"], "case_threshold")
        if type(point["prediction"]) is not bool or point["prediction"] != (score > threshold):
            raise ValueError("Displayed decision differs from its saved score and threshold")
        lookup[key] = "%s: %.3g / threshold %.3g -> %s" % (
            LABELS[point["method"]] + (" top 1%" if point["score_rule"] == "top_0.01" else " native"),
            score, threshold, "anomaly" if point["prediction"] else "normal")
    required = (("padim", "native"), ("patchcore", "native"), ("patchcore", "top_0.01"))
    if set(lookup) != set(required):
        raise ValueError("A display case requires PaDiM native and both PatchCore image-score decisions")
    return lookup[required[0]] + " | " + lookup[required[1]] + "\n" + lookup[required[2]] + " (same PatchCore map)"


def _cases(plt, output, context):
    from PIL import Image
    cases = context["cases"]
    validate_case_assets(output, cases)
    results = []
    for start in range(0, len(cases), 4):
        selected = cases[start:start + 4]
        fig, axes = _grid(plt, len(selected), 4, height=2.55 * len(selected) + 0.90, bottom=0.19)
        fig.subplots_adjust(left=0.02, right=0.99, bottom=0.19, top=0.90, wspace=0.05, hspace=0.70)
        for row_index, case in enumerate(selected):
            image = np.asarray(Image.open(_inside(output, case["image_path"])).convert("RGB"))
            mask = np.asarray(Image.open(_inside(output, case["mask_path"]))) > 0
            height, width = mask.shape
            axes[row_index, 0].imshow(image)
            axes[row_index, 1].imshow(mask, cmap="gray", vmin=0, vmax=1)
            for column, method in enumerate(METHODS, 2):
                axis = axes[row_index, column]
                spec = case["maps"][method]
                amap = np.load(_inside(output, spec["path"]), allow_pickle=False)
                axis.imshow(image)
                axis.imshow(amap, cmap="magma", vmin=spec["display_min"], vmax=spec["display_max"], alpha=0.57,
                            extent=(-0.5, width - 0.5, height - 0.5, -0.5), interpolation="bilinear")
                if mask.any() and not mask.all():
                    axis.contour(mask.astype(np.uint8), levels=[0.5], colors=["#25BFC6"], linewidths=0.5)
                axis.set_title(LABELS[method] + "\n0 to %.3g" % spec["display_max"], fontsize=8)
            axes[row_index, 0].set_title("Image | " + case["category"], fontsize=8)
            axes[row_index, 1].set_title("Union truth", fontsize=8)
            for axis in axes[row_index]:
                axis.set_xlim(-0.5, width - 0.5); axis.set_ylim(height - 0.5, -0.5); axis.axis("off")
            text = str(case["case_id"]) + " | " + case["defect_type"] + " | " + str(case["selection_reason"])
            text = textwrap.fill(text, 104) + "\n" + case_score_annotation(case)
            axes[row_index, 0].text(0, -0.13, text, transform=axes[row_index, 0].transAxes, fontsize=7.5, va="top", linespacing=1.2)
        fig.suptitle("F2 | Traceable localization and boundary cases", y=0.985)
        results.append(_save(plt, output, "F2_cases_%02d" % (start // 4 + 1), fig, axes, selected,
            "Where do the methods localize defects or produce image-level mistakes?", image_plate=True,
            note="Original union truth and fixed development-calibrated heatmaps. Image scores, thresholds and decisions are shown below each row (rounded for display; full precision in source data). PatchCore native and top 1% share one unchanged map."))
    return results


def render_analysis(root, output, context):
    """Write PNG/PDF, exact plot inputs, measured alignment, and a hash manifest."""
    root, output = Path(root).absolute(), _extended(output)
    if not output.is_dir() or (output / "plot_manifest.json").exists():
        raise ValueError("Plot rendering requires a fresh staging output directory")
    required = {"baseline", "baseline_macro", "baseline_summary", "ablations", "improvement", "loco", "size_recall", "resources"}
    tables = context.get("tables")
    if not isinstance(tables, dict) or not required.issubset(tables):
        raise ValueError("Plot context is missing an approved analysis table")
    plt = _backend()
    figures = [_methods(plt, output), _baseline(plt, output, tables), _ablation(plt, output, tables),
               _components(plt, output, tables), _fewshot(plt, output, tables), _improvement(plt, output, tables),
               _q_sensitivity(plt, output, tables), _distributions(plt, output, context),
               _defect_size(plt, output, tables), _resources(plt, output, tables), _loco(plt, output, tables)]
    figures.extend(_cases(plt, output, context))
    result = {"schema_version": "1.0", "status": "passed", "backend": "python_matplotlib", "dpi": 300,
              "pdf_fonttype": 42, "minimum_text_pt": 7, "figure_count": len(figures), "figures": figures,
              "plot_source_sha256": _sha(Path(__file__)), "input_provenance": context.get("provenance", {}),
              "metrics_changed_by_plotting": False, "post_download_visual_review_required": True,
              "pdf_text_collision_audit": "pending_post_download_review"}
    _write(output / "plot_manifest.json", result)
    return result
