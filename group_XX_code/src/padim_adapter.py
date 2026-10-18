# -*- coding: utf-8 -*-
"""
padim_adapter.py — PaDiM（Defard 2021，PatchCore 同期的参数化基线）
=================================================================

锁定口径（手册第 3 页）：
  - 特征层：ResNet18 layer1+layer2+layer3（448 维），
    layer1(64×64)、layer2(32×32) 双线性对齐到 layer3 的 16×16
  - 维度随机选择：从 448 维中随机选 100 维（H1 消融：50/200）；
    选择结果由 run seed 决定，维度索引随证据落盘
  - 建模：逐空间位置（共 256 个）拟合正常图的多元高斯
    N(μ_p, Σ_p)，协方差做单位矩阵正则化（ε=0.01）
  - 异常图：每个 patch 到该位置高斯的马氏距离
  - FP32 全程计算

马氏距离越大 → 该位置出现“正常分布之外”的特征 → 异常。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Dict, List

import numpy as np
import torch
import torch.nn.functional as F


@dataclass
class PaDiMConfig:
    n_dims: int = 100          # 随机选择的维度（H1: 50/200）
    eps: float = 0.01          # 协方差单位正则
    dims_seed: int = 17        # 维度随机选择种子（= run seed，随证据记录）
    layers: tuple = ("layer1", "layer2", "layer3")  # C2 会改成 layer2+3 或仅 layer3


@dataclass
class PaDiMModel:
    means: torch.Tensor           # (256, d)
    inv_covs: torch.Tensor        # (256, d, d)
    dim_indices: torch.Tensor     # (d,) 选中的维度索引
    eps: float
    info: dict = field(default_factory=dict)


def compose_full_features(feats: Dict[str, torch.Tensor],
                          layers: tuple = ("layer1", "layer2", "layer3"),
                          grid: int = 16) -> torch.Tensor:
    """
    按给定层顺序拼到 16×16。缺层直接报错，不静默跳过。
    基线是 layer1+2+3（448 维）；C2 为 layer2+3 或仅 layer3。
    空间尺寸不同的层用双线性对齐（连续特征，允许双线性）。
    """
    if not layers:
        raise ValueError("PaDiM 层列表为空")
    aligned = []
    for name in layers:
        if name not in feats:
            raise KeyError(
                f"PaDiM 配置要求特征层 {name}，本次载入的特征里没有该层")
        f = feats[name]
        if f.shape[-2:] != (grid, grid):
            f = F.interpolate(f, size=(grid, grid), mode="bilinear",
                              align_corners=False)
        aligned.append(f)
    return torch.cat(aligned, dim=1)


def _select_dims(total: int, n_dims: int, seed: int,
                 device: torch.device) -> torch.Tensor:
    """从 total 维中随机选 n_dims 维（排序保存，保证可复现）。"""
    g = torch.Generator(device="cpu").manual_seed(seed)
    perm = torch.randperm(total, generator=g)[:n_dims].sort().values
    return perm.to(device)


def fit_padim(feats: Dict[str, torch.Tensor], cfg: PaDiMConfig,
              device: torch.device) -> PaDiMModel:
    """对 256 个空间位置分别拟合正则化多元高斯。"""
    t0 = time.perf_counter()
    layers = tuple(cfg.layers)
    x = compose_full_features(feats, layers).to(torch.float32)
    n, total, h, w = x.shape
    if cfg.n_dims > total:
        raise ValueError(f"n_dims={cfg.n_dims} 超过拼接后的通道数 {total}")
    p = h * w
    dims = _select_dims(total, cfg.n_dims, cfg.dims_seed, device)
    x = x.index_select(1, dims).permute(0, 2, 3, 1).reshape(n, p, -1)  # (N,P,d)

    means = x.mean(dim=0)                                                  # (P,d)
    xc = x - means.unsqueeze(0)
    cov = torch.einsum("npd,npe->pde", xc, xc) / max(n - 1, 1)           # (P,d,d)
    eye = torch.eye(cfg.n_dims, device=device, dtype=cov.dtype)
    cov = cov + cfg.eps * eye
    inv_covs = torch.linalg.inv(cov)
    if device.type == "cuda":
        torch.cuda.synchronize()
    info = {"n_fit_images": n, "n_positions": int(p),
            "layers": list(layers),
            "feature_maps": [
                {"name": name,
                 "channels": int(feats[name].shape[1]),
                 "height": int(feats[name].shape[2]),
                 "width": int(feats[name].shape[3])}
                for name in layers],
            "total_dims": int(total), "n_dims": int(cfg.n_dims),
            "eps": cfg.eps, "dims_seed": cfg.dims_seed,
            "fit_seconds": round(time.perf_counter() - t0, 4)}
    return PaDiMModel(means=means, inv_covs=inv_covs, dim_indices=dims,
                      eps=cfg.eps, info=info)


def anomaly_maps_padim(model: PaDiMModel, feats: Dict[str, torch.Tensor],
                       cfg: PaDiMConfig) -> torch.Tensor:
    """逐位置马氏距离异常图：(N,16,16)。"""
    x = compose_full_features(feats, tuple(cfg.layers)).to(torch.float32)
    n, _, h, w = x.shape
    p = h * w
    x = x.index_select(1, model.dim_indices).permute(0, 2, 3, 1).reshape(n, p, -1)
    delta = x - model.means.unsqueeze(0)                               # (N,P,d)
    maha = torch.einsum("npd,pde,npe->np", delta, model.inv_covs, delta)
    return maha.reshape(n, h, w)
