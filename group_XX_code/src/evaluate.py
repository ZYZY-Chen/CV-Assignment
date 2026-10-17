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
    像素级 AUROC / AP（原图分辨率；正常图掩膜为全 0）。
    test_items 与 maps 顺序一致，maps 为 (N,16,16)。
    """
    # 延迟导入，避免掩膜读取逻辑分叉
    from data import load_mask
    all_scores, all_labels = [], []
    for i, it in enumerate(test_items):
        h, w = it["orig_hw"]
        amap = upsample_maps(maps[i:i + 1].float(), (h, w))[0]
        if it["mask_paths"]:
            mask = load_mask([Path(datasets_root) / p for p in it["mask_paths"]],
                             size=h)
        else:
            mask = torch.zeros((h, w), dtype=torch.float32)
        all_scores.append(amap.flatten().cpu().numpy())
        all_labels.append(mask.flatten().numpy())
    # 逐图拼接前做一次 z 对齐（每张图各自的绝对量纲由近邻距离决定，
    # 像素 AUROC 按“类内所有像素”统一计算，不做逐图归一化）
    s = np.concatenate(all_scores)
    y = np.concatenate(all_labels).astype(np.uint8)
    return {
        "pixel_auroc": float(roc_auc_score(y, s)),
        "pixel_ap": float(average_precision_score(y, s)),
        "n_pixels": int(y.size),
        "n_positive_pixels": int(y.sum()),
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


def evaluate_all(test_items: Sequence[dict], dev_items: Sequence[dict],
                 test_maps: torch.Tensor, dev_maps: torch.Tensor,
                 image_scores_test: Dict[str, np.ndarray],
                 image_scores_dev: Dict[str, np.ndarray],
                 datasets_root: Path, device: torch.device) -> dict:
    """汇总图像级（多规则）、像素级、阈值统计。"""
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
    return metrics
