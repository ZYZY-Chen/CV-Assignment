# -*- coding: utf-8 -*-
"""
sampling.py — 记忆库采样策略（PatchCore C1 对照实验的核心）
==========================================================

- kcenter_coreset：PatchCore 原生贪心 k-center coreset（默认 0.05）
- random_subset ：不放回均匀随机采样（C1 对照组，与 coreset 保持相同点数）

两种采样输出数量必须相同，随机采样记录种子，保证可复现。
"""
from __future__ import annotations

import torch


def kcenter_coreset(bank: torch.Tensor, ratio: float,
                    device: torch.device | str = "cuda",
                    seed: int = 0) -> torch.Tensor:
    """
    贪心 k-center coreset 选择。
    bank: (M, D)；返回 (p, D) 的 coreset 张量，p = round(ratio * M)。
    """
    device = torch.device(device)
    bank = bank.to(device)
    m = bank.shape[0]
    p = max(1, round(ratio * m))
    p = min(p, m)

    g = torch.Generator(device="cpu").manual_seed(seed)
    first = int(torch.randint(m, (1,), generator=g).item())

    selected = [first]
    min_dist = torch.full((m,), float("inf"), device=device, dtype=bank.dtype)
    for _ in range(p - 1):
        # 新选中点到全部样本的距离（平方距离足以决定 argmax）
        d = ((bank - bank[selected[-1]].unsqueeze(0)) ** 2).sum(dim=1)
        torch.minimum(min_dist, d, out=min_dist)
        nxt = int(torch.argmax(min_dist).item())
        selected.append(nxt)
        min_dist[nxt] = 0.0  # 防止重复选中
    return bank[torch.tensor(selected, device=device)]


def random_subset(bank: torch.Tensor, n: int,
                  device: torch.device | str = "cuda",
                  seed: int = 0) -> torch.Tensor:
    """不放回均匀随机采样 n 个点（C1 对照）。"""
    device = torch.device(device)
    bank = bank.to(device)
    m = bank.shape[0]
    n = min(n, m)
    g = torch.Generator(device="cpu").manual_seed(seed)
    idx = torch.randperm(m, generator=g)[:n]
    return bank[idx.to(device)]
