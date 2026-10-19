"""Seeded, unique-index memory-bank sampling for the TC2 GPU protocol."""
from __future__ import annotations

import math
import torch
from anomaly_postprocess import fp32_arithmetic, fp32_tensor, integer, seed_value


def retained_count(size, ratio):
    size = integer(size, "pool size")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or not 0 < ratio <= 1:
        raise ValueError("ratio must be finite and in (0, 1]")
    return min(size, max(1, round(ratio * size)))


@torch.inference_mode()
def kcenter_coreset(bank, ratio, device="cuda", seed=0, *, chunk_size=16384, return_indices=False):
    """Exact greedy k-center in the original feature space, without repeated indices."""
    bank = fp32_tensor(bank, "feature pool", 2)
    count = retained_count(bank.shape[0], ratio)
    chunk_size = integer(chunk_size, "sampling chunk size")
    generator = torch.Generator(device="cpu").manual_seed(seed_value(seed))
    with fp32_arithmetic(device):
        bank = bank.to(device)
        current = int(torch.randint(len(bank), (1,), generator=generator).item())
        selected = []
        chosen = torch.zeros(len(bank), dtype=torch.bool, device=bank.device)
        nearest = torch.full((len(bank),), float("inf"), device=bank.device, dtype=torch.float32)
        for index in range(count):
            selected.append(current)
            chosen[current] = True
            if index + 1 == count:
                break
            for start in range(0, len(bank), chunk_size):
                block = bank[start:start + chunk_size]
                distances = (block - bank[current]).square().sum(dim=1)
                if not bool(torch.isfinite(distances).all()):
                    raise ValueError("Sampling distances overflowed FP32")
                nearest[start:start + len(block)] = torch.minimum(nearest[start:start + len(block)], distances)
            # Explicit exclusion handles duplicate vectors and all-zero distances.
            nearest.masked_fill_(chosen, -float("inf"))
            current = int(torch.argmax(nearest).item())
        indices = torch.tensor(selected, dtype=torch.long, device=bank.device)
        result = bank.index_select(0, indices)
    return (result, indices) if return_indices else result


@torch.inference_mode()
def random_subset(bank, n, device="cuda", seed=0, *, return_indices=False):
    """Uniform sampling without replacement, optionally returning pool indices."""
    bank = fp32_tensor(bank, "feature pool", 2)
    n = integer(n, "retained count")
    if n > len(bank):
        raise ValueError("Retained count exceeds the feature pool")
    generator = torch.Generator(device="cpu").manual_seed(seed_value(seed))
    with fp32_arithmetic(device):
        bank = bank.to(device)
        indices = torch.randperm(len(bank), generator=generator)[:n].to(bank.device)
        result = bank.index_select(0, indices)
    return (result, indices) if return_indices else result
