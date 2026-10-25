# -*- coding: utf-8 -*-
"""
evaluate.py — 统一评估指标（手册第 6 页）
=========================================

  - 图像 AUROC：按类别计算（正常 vs 异常），报告各聚合规则
  - 像素 AUROC / 像素 AP：异常图双线性恢复到原图分辨率后逐像素比对；
    正常图使用全零掩膜；按类别整体计算（六类再在汇总阶段宏平均）
  - 阈值：只用正常开发集各规则分数的第 95 百分位（预校准），
    再在官方测试集上报告正常图误报率、异常召回率（分缺陷类型）
  - AUPRO 为可选指标（后续单独实现）

注意：本模块不做任何“按测试集选最优阈值/F1”的操作。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score, average_precision_score

from scoring import RULES

# 批量实验中同一类别的掩膜被反复读取，进程内缓存（键：掩膜路径）
_MASK_CACHE: dict[str, torch.Tensor] = {}


def _get_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    """掩膜缩放到 (H, W) 后返回 uint8 的 0/1 数组，避免整图 float32 占内存。"""
    height, width = int(size[0]), int(size[1])
    key = f"{path}|{height}x{width}"
    hit = _MASK_CACHE.get(key)
    if hit is None:
        from data import load_mask
        hit = (load_mask([path], size=(height, width)).numpy() > 0).astype(np.uint8)
        _MASK_CACHE[key] = hit
    return hit


def _pixel_auroc_ap(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """二分类 AUROC / AP。只保留一份 float32 分数和排序下标，不把分数转成 float64。"""
    labels = np.ascontiguousarray(labels, dtype=np.uint8)
    scores = np.ascontiguousarray(scores, dtype=np.float32)
    n_pos = int(labels.sum())
    n = int(labels.size)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("像素评估需要同时有正常像素和异常像素")
    order = np.argsort(scores, kind="quicksort")
    del scores
    y = labels[order]
    del order, labels
    pos = np.flatnonzero(y)
    del y
    pos_f = pos.astype(np.float64, copy=False)
    sum_ranks = float(pos_f.sum()) + n_pos
    auroc = (sum_ranks - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    retrieved = n - pos[::-1]
    tp = np.arange(1, n_pos + 1, dtype=np.float64)
    ap = float(np.mean(tp / retrieved))
    return float(auroc), ap


def image_auroc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    if len(np.unique(labels)) < 2:
        return None
    return float(roc_auc_score(labels, scores))


def image_ap(labels: np.ndarray, scores: np.ndarray) -> float | None:
    if len(np.unique(labels)) < 2:
        return None
    return float(average_precision_score(labels, scores))


def upsample_maps(maps: torch.Tensor, size: tuple[int, int]) -> torch.Tensor:
    """16×16 patch 异常图 → 原图分辨率，双线性（仅用于连续异常图）。"""
    x = maps.unsqueeze(1).float()
    x = F.interpolate(x, size=size, mode="bilinear", align_corners=False)
    return x.squeeze(1)


def pixel_metrics(test_items: Sequence[dict], maps: torch.Tensor,
                  datasets_root: Path, device: torch.device) -> Dict[str, float]:
    """
    像素级 AUROC / AP（每张图恢复到自己的原图分辨率；正常图掩膜为全 0）。
    test_items 与 maps 顺序一致，maps 为 (N,16,16)。
    LOCO 同一类别里有 800×1600 和转置尺寸，所以按图处理，不把掩膜缩成正方形。
    """
    total = 0
    for it in test_items:
        total += int(it["orig_hw"][0]) * int(it["orig_hw"][1])
    scores = np.empty(total, dtype=np.float32)
    labels = np.empty(total, dtype=np.uint8)
    offset = 0
    n_pos = 0
    for i, it in enumerate(test_items):
        height, width = int(it["orig_hw"][0]), int(it["orig_hw"][1])
        n_pix = height * width
        amap = upsample_maps(maps[i:i + 1].float(), (height, width))[0]
        scores[offset:offset + n_pix] = amap.reshape(-1).numpy()
        lab = np.zeros(n_pix, dtype=np.uint8)
        for p in it["mask_paths"]:
            lab |= _get_mask(Path(datasets_root) / p, (height, width)).reshape(-1)
        labels[offset:offset + n_pix] = lab
        n_pos += int(lab.sum())
        offset += n_pix
    auroc, ap = _pixel_auroc_ap(labels, scores)
    return {
        "pixel_auroc": auroc,
        "pixel_ap": ap,
        "n_pixels": int(total),
        "n_positive_pixels": n_pos,
    }


def threshold_from_dev(dev_scores: np.ndarray, percentile: float = 95.0) -> float:
    """正常开发集分数的第 P 百分位（统一校准规则，5% 名义误报率）。"""
    return float(np.percentile(dev_scores, percentile))


def test_threshold_stats(labels: np.ndarray, scores: np.ndarray,
                         defect_types: Sequence[str], thr: float) -> dict:
    labels = np.asarray(labels)
    scores = np.asarray(scores)
    normal = labels == 0
    anomaly = labels == 1
    stats = {
        "threshold_95pct": float(thr),
        "normal_fpr": float((scores[normal] > thr).mean()),
        "anomaly_recall": float((scores[anomaly] > thr).mean()),
        "per_defect_recall": {},
    }
    for dt in sorted(set(defect_types) - {"good"}):
        sel = np.array([d == dt for d in defect_types])
        if sel.any():
            stats["per_defect_recall"][dt] = float((scores[sel] > thr).mean())
    return stats


LOCO_GROUPS = ("logical_anomalies", "structural_anomalies")


def group_metrics(test_items: Sequence[dict], test_maps: torch.Tensor,
                  image_scores_test: Dict[str, np.ndarray],
                  image_scores_dev: Dict[str, np.ndarray],
                  datasets_root: Path, device: torch.device) -> dict | None:
    """LOCO：正常图分别对逻辑异常、结构异常计算图像和像素指标。

    两类异常不放进同一次 AUROC。MVTec 没有这两组名字时返回 None。
    """
    defect_types = [it["defect_type"] for it in test_items]
    groups = [g for g in LOCO_GROUPS if g in defect_types]
    if len(groups) < 2:
        return None
    good_idx = [i for i, d in enumerate(defect_types) if d == "good"]
    out = {}
    for g in groups:
        idx = good_idx + [i for i, d in enumerate(defect_types) if d == g]
        sub_items = [test_items[i] for i in idx]
        sub_maps = test_maps[idx]
        sub_labels = np.array([test_items[i]["label"] for i in idx], dtype=int)
        sub_defects = [defect_types[i] for i in idx]
        entry = {
            "n_good": len(good_idx),
            "n_anomaly": len(idx) - len(good_idx),
            "image": {},
        }
        for rule in RULES:
            scores = np.asarray(image_scores_test[rule])[idx]
            entry["image"][rule] = {
                "image_auroc": image_auroc(sub_labels, scores),
                "image_ap": image_ap(sub_labels, scores),
            }
            thr = threshold_from_dev(image_scores_dev[rule])
            entry["image"][rule].update(
                test_threshold_stats(sub_labels, scores, sub_defects, thr))
        entry["pixel"] = pixel_metrics(sub_items, sub_maps, datasets_root, device)
        out[g] = entry
    return out


def evaluate_all(test_items: Sequence[dict], dev_items: Sequence[dict],
                 test_maps: torch.Tensor, dev_maps: torch.Tensor,
                 image_scores_test: Dict[str, np.ndarray],
                 image_scores_dev: Dict[str, np.ndarray],
                 datasets_root: Path, device: torch.device) -> dict:
    """汇总图像级（多规则）、像素级、阈值统计。"""
    _MASK_CACHE.clear()
    labels = np.array([it["label"] for it in test_items], dtype=int)
    defect_types = [it["defect_type"] for it in test_items]
    metrics = {"image": {}, "pixel": None}
    for rule in RULES:
        metrics["image"][rule] = {
            "image_auroc": image_auroc(labels, image_scores_test[rule]),
            "image_ap": image_ap(labels, image_scores_test[rule]),
        }
        thr = threshold_from_dev(image_scores_dev[rule])
        metrics["image"][rule].update(
            test_threshold_stats(labels, image_scores_test[rule],
                                 defect_types, thr))
    metrics["pixel"] = pixel_metrics(test_items, test_maps, datasets_root, device)
    grouped = group_metrics(test_items, test_maps, image_scores_test,
                            image_scores_dev, datasets_root, device)
    if grouped:
        metrics["groups"] = grouped
        metrics["pixel_note"] = (
            "pixel 是全部测试图混在一起的结果；"
            "LOCO 的正式像素指标看 groups 里分开的 logical / structural"
        )
    return metrics
