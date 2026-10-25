# -*- coding: utf-8 -*-
"""V2 per-category metrics: grouped ties, normal-dev thresholds and LOCO groups."""
from __future__ import annotations

import operator
from pathlib import Path, PurePosixPath
from typing import Dict, Sequence
import numpy as np
import torch
import torch.nn.functional as F
from metric_core import METRIC_POLICY_VERSION, binary_auroc_ap, binary_inputs, finite_scores

SUPPORTED_RULES = ("native", "max", "top_0.001", "top_0.01", "top_0.05")
LOCO_GROUPS = ("logical_anomalies", "structural_anomalies")
_MASK_CACHE: dict[str, np.ndarray] = {}


def _relative_path(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(name + " must be a nonempty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError(name + " must stay inside the dataset root")
    return path.as_posix()


def _size(value):
    try:
        if len(value) != 2 or any(isinstance(v, (bool, np.bool_)) for v in value):
            raise ValueError("orig_hw must contain two positive integers")
        height, width = (operator.index(v) for v in value)
    except (TypeError, KeyError) as error:
        raise ValueError("orig_hw must contain two positive integers") from error
    if height <= 0 or width <= 0:
        raise ValueError("orig_hw must contain two positive integers")
    return height, width


def _items(items, role):
    if not items:
        raise ValueError(role + " items are empty")
    paths = []
    for item in items:
        required = {"path", "label", "defect_type", "mask_paths", "orig_hw"}
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(role + " item is missing required metadata")
        paths.append(_relative_path(item["path"], role + " image path"))
        _size(item["orig_hw"])
        label, masks, defect = item["label"], item["mask_paths"], item["defect_type"]
        if label not in (0, 1):
            raise ValueError("image labels must be 0 or 1")
        if not isinstance(masks, (list, tuple)):
            raise ValueError("mask_paths must be a list or tuple")
        for mask in masks:
            _relative_path(mask, "mask path")
        if not isinstance(defect, str):
            raise ValueError("defect_type must be a string")
        if role == "dev":
            if label != 0 or masks or defect not in ("", "good"):
                raise ValueError("development samples must all be normal and mask-free")
        elif label == 0:
            if masks or defect != "good":
                raise ValueError("normal test samples must be good and mask-free")
        elif not masks or not defect or defect == "good":
            raise ValueError("anomalous test samples need an anomaly type and masks")
    if len(set(paths)) != len(paths):
        raise ValueError(role + " contains duplicate image paths")
    return set(paths)


def _maps(maps, count):
    if not isinstance(maps, torch.Tensor) or maps.ndim != 3:
        raise ValueError("maps must be a tensor shaped (N,H,W)")
    if maps.shape[0] != count or min(maps.shape[1:]) <= 0 or not maps.is_floating_point():
        raise ValueError("map counts or dimensions do not match the samples")
    maps = maps.detach().to(device="cpu", dtype=torch.float32)
    if not torch.isfinite(maps).all().item():
        raise ValueError("maps contain NaN or infinity")
    return maps


def _rules(test_scores, dev_scores, n_test, n_dev):
    if not isinstance(test_scores, dict) or not isinstance(dev_scores, dict):
        raise ValueError("image scores must be dictionaries")
    if not test_scores or set(test_scores) != set(dev_scores) or not set(test_scores).issubset(SUPPORTED_RULES):
        raise ValueError("test/dev scoring rules must be the same nonempty supported set")
    for name, count, collection in [("test", n_test, test_scores), ("dev", n_dev, dev_scores)]:
        for rule, values in collection.items():
            if finite_scores(values, name + " " + rule).size != count:
                raise ValueError(name + " score counts do not match samples")
    return [rule for rule in SUPPORTED_RULES if rule in test_scores]


def _loco_groups(items):
    types = {item["defect_type"] for item in items}
    groups = set(LOCO_GROUPS) & types
    if not groups:
        return ()
    if groups != set(LOCO_GROUPS) or "good" not in types or types - {"good", *LOCO_GROUPS}:
        raise ValueError("LOCO requires normal, logical and structural groups without other anomaly groups")
    return LOCO_GROUPS


def _get_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    height, width = _size(size)
    key = f"{path.resolve()}|{height}x{width}"
    hit = _MASK_CACHE.get(key)
    if hit is None:
        from data import load_mask
        hit = (load_mask([path], size=(height, width)).numpy() > 0).astype(np.uint8)
        _MASK_CACHE[key] = hit
    return hit


def _pixel_auroc_ap(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    return binary_auroc_ap(labels, scores)


def image_auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    return binary_auroc_ap(labels, scores)[0]


def image_ap(labels: np.ndarray, scores: np.ndarray) -> float:
    return binary_auroc_ap(labels, scores)[1]


def upsample_maps(maps: torch.Tensor, size: tuple[int, int]) -> torch.Tensor:
    """Resize continuous maps only; no smoothing or display normalization."""
    count = maps.shape[0] if isinstance(maps, torch.Tensor) and maps.ndim else 0
    maps = _maps(maps, count)
    return F.interpolate(maps.unsqueeze(1), size=_size(size), mode="bilinear", align_corners=False).squeeze(1)


def pixel_metrics(test_items: Sequence[dict], maps: torch.Tensor,
                  datasets_root: Path, device: torch.device) -> Dict[str, float]:
    _items(test_items, "test")
    maps = _maps(maps, len(test_items))
    binary_inputs([it["label"] for it in test_items], np.zeros(len(test_items), dtype=np.float32))
    root = Path(datasets_root).resolve()
    total = sum(_size(it["orig_hw"])[0] * _size(it["orig_hw"])[1] for it in test_items)
    scores, labels = np.empty(total, dtype=np.float32), np.empty(total, dtype=np.uint8)
    offset = n_pos = 0
    for i, item in enumerate(test_items):
        height, width = _size(item["orig_hw"])
        n_pix = height * width
        scores[offset:offset + n_pix] = upsample_maps(maps[i:i + 1], (height, width))[0].numpy().reshape(-1)
        lab = np.zeros(n_pix, dtype=np.uint8)
        for relative in item["mask_paths"]:
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError("mask path resolves outside the dataset root")
            lab |= _get_mask(path, (height, width)).reshape(-1)
        labels[offset:offset + n_pix] = lab
        n_pos += int(lab.sum(dtype=np.int64))
        offset += n_pix
    auroc, ap = _pixel_auroc_ap(labels, scores)
    return {"pixel_auroc": auroc, "pixel_ap": ap, "n_pixels": total, "n_positive_pixels": n_pos}


def threshold_from_dev(dev_scores: np.ndarray, percentile: float = 95.0) -> float:
    scores = finite_scores(dev_scores, "development scores")
    if not np.isfinite(percentile) or not 0 <= percentile <= 100:
        raise ValueError("percentile must be finite and within [0,100]")
    return float(np.percentile(scores, percentile, method="linear"))


def test_threshold_stats(labels: np.ndarray, scores: np.ndarray,
                         defect_types: Sequence[str], thr: float) -> dict:
    labels, scores = binary_inputs(labels, scores)
    if len(defect_types) != labels.size or not all(isinstance(t, str) for t in defect_types):
        raise ValueError("defect types must match the labels")
    if any((y == 0) != (t == "good") for y, t in zip(labels, defect_types)):
        raise ValueError("defect types disagree with normal/anomalous labels")
    if not np.isfinite(thr):
        raise ValueError("threshold must be finite")
    prediction = scores > thr
    normal, anomaly = labels == 0, labels == 1
    return {"threshold_95pct": float(thr), "normal_fpr": float(prediction[normal].mean()),
            "anomaly_recall": float(prediction[anomaly].mean()),
            "per_defect_recall": {dt: float(prediction[np.array([t == dt for t in defect_types])].mean())
                                  for dt in sorted(set(defect_types) - {"good"})}}


def group_metrics(test_items: Sequence[dict], test_maps: torch.Tensor,
                  image_scores_test: Dict[str, np.ndarray], image_scores_dev: Dict[str, np.ndarray],
                  datasets_root: Path, device: torch.device) -> dict | None:
    _items(test_items, "test")
    groups = _loco_groups(test_items)
    if not groups:
        return None
    maps = _maps(test_maps, len(test_items))
    n_dev = len(next(iter(image_scores_dev.values()))) if image_scores_dev else 0
    rules = _rules(image_scores_test, image_scores_dev, len(test_items), n_dev)
    types = [it["defect_type"] for it in test_items]
    good_idx = [i for i, t in enumerate(types) if t == "good"]
    out = {}
    for group in groups:
        idx = good_idx + [i for i, t in enumerate(types) if t == group]
        items = [test_items[i] for i in idx]
        labels = np.array([it["label"] for it in items], dtype=np.uint8)
        defects = [it["defect_type"] for it in items]
        entry = {"n_good": len(good_idx), "n_anomaly": len(idx) - len(good_idx), "image": {}}
        for rule in rules:
            scores = np.asarray(image_scores_test[rule])[idx]
            auc, ap = binary_auroc_ap(labels, scores)
            entry["image"][rule] = {"image_auroc": auc, "image_ap": ap,
                **test_threshold_stats(labels, scores, defects, threshold_from_dev(image_scores_dev[rule]))}
        entry["pixel"] = pixel_metrics(items, maps[idx], datasets_root, device)
        out[group] = entry
    return out


def evaluate_all(test_items: Sequence[dict], dev_items: Sequence[dict],
                 test_maps: torch.Tensor, dev_maps: torch.Tensor,
                 image_scores_test: Dict[str, np.ndarray], image_scores_dev: Dict[str, np.ndarray],
                 datasets_root: Path, device: torch.device) -> dict:
    _MASK_CACHE.clear()
    test_paths, dev_paths = _items(test_items, "test"), _items(dev_items, "dev")
    if test_paths & dev_paths:
        raise ValueError("development and test paths overlap")
    test_maps, dev_maps = _maps(test_maps, len(test_items)), _maps(dev_maps, len(dev_items))
    rules = _rules(image_scores_test, image_scores_dev, len(test_items), len(dev_items))
    _loco_groups(test_items)
    labels = np.array([it["label"] for it in test_items], dtype=np.uint8)
    defects = [it["defect_type"] for it in test_items]
    metrics = {"image": {}, "pixel": None,
        "metric_policy": {"version": METRIC_POLICY_VERSION, "ties": "equal-score threshold groups",
                          "threshold_percentile": 95.0, "percentile_method": "linear", "decision": "score > threshold",
                          "pixel_scope": "all pixels at original resolution"}}
    for rule in rules:
        scores = image_scores_test[rule]
        auc, ap = binary_auroc_ap(labels, scores)
        metrics["image"][rule] = {"image_auroc": auc, "image_ap": ap,
            **test_threshold_stats(labels, scores, defects, threshold_from_dev(image_scores_dev[rule]))}
    metrics["pixel"] = pixel_metrics(test_items, test_maps, datasets_root, device)
    grouped = group_metrics(test_items, test_maps, image_scores_test, image_scores_dev, datasets_root, device)
    if grouped:
        metrics["groups"] = grouped
        metrics["pixel_note"] = "pixel is pooled auxiliary output; formal LOCO metrics are separate logical/structural groups"
    return metrics
