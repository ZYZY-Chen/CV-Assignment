# -*- coding: utf-8 -*-
"""
patchcore_adapter.py — PatchCore 基线（手册第 3 页）
====================================================

固定配置（B0）：
  - 特征层：layer2 + layer3（ResNet18）
  - layer2 做 3×3 局部邻域平均聚合后对齐到 layer3 的 16×16 网格，拼接为 384 维
  - 记忆库：全部训练 patch 特征 → coreset 0.05（贪心 k-center）
  - 异常分数：PatchCore 原生加权近邻（Roth 2022）——
    s(x) = w(x) · mean_{k=1..9} d(x, m_k)，w(x) = 1 - exp(-d(x, m_1)/2)
    其中 d(x, m_1) 为最近邻距离。该权重在存在极近邻时抑制分数，
    避免 coreset 稀疏区域（如图像四角）仅凭远邻距离造成假阳性。
  - 异常图：16×16 patch 分数，评估时双线性恢复到原图
对照组：sampling='random' 时用等数量随机采样（C1）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict

import torch
import torch.nn.functional as F

from sampling import kcenter_coreset, random_subset


@dataclass
class PatchCoreConfig:
    coreset_ratio: float = 0.05
    num_neighbors: int = 9
    sampling: str = "coreset"     # "coreset" 或 "random"
    sampling_seed: int = 0
    chunk_size: int = 64          # 近邻打分时的图像分块，避免显存尖峰


@dataclass
class PatchCoreModel:
    bank: torch.Tensor | None = None
    device: torch.device | None = None
    info: Dict[str, object] = field(default_factory=dict)


def compose_patch_features(feats: Dict[str, torch.Tensor]) -> torch.Tensor:
    """
    layer2/layer3 特征 → 拼接的 patch 特征 (N, 384, 16, 16)。
    layer2 先做 3×3 邻域平均，再以 stride 2 对齐到 16×16。
    """
    f2, f3 = feats["layer2"], feats["layer3"]
    agg = F.avg_pool2d(f2, kernel_size=3, stride=1, padding=1)
    agg = agg[:, :, ::2, ::2]
    # 防御：网格必须严格对齐
    if agg.shape[-2:] != f3.shape[-2:]:
        agg = F.adaptive_avg_pool2d(agg, f3.shape[-2:])
    return torch.cat([agg, f3], dim=1)  # (N, 384, 16, 16)


def fit_patchcore(feats: Dict[str, torch.Tensor], cfg: PatchCoreConfig,
                  device: torch.device | str = "cuda") -> PatchCoreModel:
    """从训练特征建立记忆库。"""
    device = torch.device(device)
    t0 = time.perf_counter()
    x = compose_patch_features(feats).to(device)
    n, c, h, w = x.shape
    bank = x.permute(0, 2, 3, 1).reshape(n * h * w, c).contiguous()  # (M, 384)
    m_full = bank.shape[0]
    if cfg.sampling == "coreset":
        core = kcenter_coreset(bank, cfg.coreset_ratio,
                               device=device, seed=cfg.sampling_seed)
    elif cfg.sampling == "random":
        p = max(1, round(cfg.coreset_ratio * m_full))
        core = random_subset(bank, p, device=device, seed=cfg.sampling_seed)
    else:
        raise ValueError(f"未知采样方式: {cfg.sampling}")
    if device.type == "cuda":
        torch.cuda.synchronize()
    fit_seconds = time.perf_counter() - t0
    return PatchCoreModel(
        bank=core, device=device,
        info={"sampling": cfg.sampling,
              "coreset_ratio": cfg.coreset_ratio,
              "memory_bank_full": m_full,
              "memory_bank_kept": int(core.shape[0]),
              "fit_seconds": round(fit_seconds, 4)})


@torch.inference_mode()
def anomaly_maps(model: PatchCoreModel, feats: Dict[str, torch.Tensor],
                 cfg: PatchCoreConfig) -> torch.Tensor:
    """
    返回每张图的 patch 异常图 (N, 16, 16)（欧氏距离，k 近邻均值）。
    """
    x = compose_patch_features(feats).to(model.device)
    n, c, h, w = x.shape
    pts = x.permute(0, 2, 3, 1).reshape(n, h * w, c)        # (N, 256, 384)
    bank = model.bank                                       # (B, 384)
    k = min(cfg.num_neighbors, bank.shape[0])
    maps = torch.empty((n, h, w), device=model.device, dtype=bank.dtype)
    # 单块距离矩阵上限 256MB，避免全记忆库一次 cdist 打满内存或显存。
    bytes_per_image = (h * w) * bank.shape[0] * bank.element_size()
    safe_chunk = max(1, (256 * 1024 * 1024) // max(bytes_per_image, 1))
    step = max(1, min(cfg.chunk_size, safe_chunk))
    for s in range(0, n, step):
        q = pts[s:s + step]                                 # (b, 256, 384)
        b = q.shape[0]
        dist = torch.cdist(q, bank.unsqueeze(0).expand(b, -1, -1))
        topk, _ = dist.topk(k, dim=2, largest=False)       # (b, 256, k)
        d1 = topk[..., :1]                                  # 最近邻距离
        weight = 1.0 - torch.exp(-d1 / 2.0)                 # 原生权重 w*
        score = (weight * topk.mean(dim=2, keepdim=True)).squeeze(-1)
        maps[s:s + b] = score.reshape(b, h, w)
    if model.device.type == "cuda":
        torch.cuda.synchronize()
    return maps
