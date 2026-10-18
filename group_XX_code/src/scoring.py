# -*- coding: utf-8 -*-
"""
scoring.py — 图像级异常分数聚合规则（手册第 5 页 I1/I2）
========================================================

手册第 6 页：图像分数在 256×256 连续异常图上计算。
K = max(1, ceil(q × H × W))。正式改进 q=0.01；q=0.001 与 0.05 只做敏感性分析。
max 是该异常图的最大值（当前异常图已经是近邻加权分数）。
像素级指标不经过这些规则。
"""
from __future__ import annotations

import math
from typing import Dict

import torch
import torch.nn.functional as F

# 预注册的聚合规则：q 为取均值的像素比例；max 即原生最大值
RULES = ("max", "top_0.001", "top_0.01", "top_0.05")
# 正式改进预指定 q=0.01
IMPROVEMENT_RULE = "top_0.01"
IMAGE_SCORE_SIZE = 256
_Q = {"top_0.001": 0.001, "top_0.01": 0.01, "top_0.05": 0.05}


def to_image_score_grid(maps: torch.Tensor,
                        size: int = IMAGE_SCORE_SIZE) -> torch.Tensor:
    """把 patch 异常图双线性放到手册规定的 256×256。已是该尺寸则只转 float32。"""
    maps = maps.float()
    if maps.shape[-2:] == (size, size):
        return maps
    x = F.interpolate(maps.unsqueeze(1), size=(size, size),
                      mode="bilinear", align_corners=False)
    return x.squeeze(1)


def aggregate(amap: torch.Tensor, rule: str) -> float:
    """对单张异常图 (H,W) 聚合为图像分数。"""
    flat = amap.flatten()
    if rule == "max":
        return float(amap.max().item())
    if rule not in _Q:
        raise ValueError(f"未知聚合规则: {rule}")
    k = max(1, int(math.ceil(_Q[rule] * flat.numel())))
    topk = torch.topk(flat, k).values
    return float(topk.mean().item())


def aggregate_batch(amaps: torch.Tensor, rules=RULES) -> Dict[str, torch.Tensor]:
    """
    对一批异常图 (N,H,W) 返回 {rule: (N,) 分数}。
    """
    n, h, w = amaps.shape
    npix = h * w
    flat = amaps.reshape(n, npix)
    out: Dict[str, torch.Tensor] = {}
    out["max"] = flat.max(dim=1).values
    for rule in ("top_0.001", "top_0.01", "top_0.05"):
        k = max(1, int(math.ceil(_Q[rule] * npix)))
        topk = torch.topk(flat, k, dim=1).values
        out[rule] = topk.mean(dim=1)
    return {r: out[r] for r in rules}
