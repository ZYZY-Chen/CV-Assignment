# -*- coding: utf-8 -*-
"""
scoring.py — 图像级异常分数聚合规则（手册第 5 页 I1/I2）
========================================================

PatchCore 原生图像分数 = 异常图最大值；I1 预注册改进 = top 1% 像素均值；
另保留 top 0.1%、top 5% 用于 q 敏感性分析（I2，不增加 fit）。

所有规则均只对异常图（连续像素分数）操作，像素级指标不受这些规则影响。
"""
from __future__ import annotations

import math
from typing import Dict

import torch

# 预注册的聚合规则：q 为取均值的像素比例；max 即原生最大值
RULES = ("max", "top_0.001", "top_0.01", "top_0.05")
# 正式改进预指定 q=0.01
IMPROVEMENT_RULE = "top_0.01"
_Q = {"top_0.001": 0.001, "top_0.01": 0.01, "top_0.05": 0.05}


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
