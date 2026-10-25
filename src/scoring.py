"""Image aggregation on final continuous maps; native scores are method-specific."""
from __future__ import annotations

import math
import torch
import torch.nn.functional as F
from anomaly_postprocess import fp32_arithmetic, fp32_tensor, integer

RULES = ("max", "top_0.001", "top_0.01", "top_0.05")
TC2_GPU_RULES = ("native",) + RULES
IMPROVEMENT_RULE = "top_0.01"
IMAGE_SCORE_SIZE = 256
_Q = {"top_0.001": 0.001, "top_0.01": 0.01, "top_0.05": 0.05}


def to_image_score_grid(maps, size=IMAGE_SCORE_SIZE):
    """Legacy resize helper only; never apply smoothing a second time."""
    if not isinstance(maps, torch.Tensor):
        raise ValueError("maps must be a tensor")
    maps = fp32_tensor(maps.float(), "maps", 3)
    size = integer(size, "image score size")
    if maps.shape[-2:] == (size, size):
        return maps
    with fp32_arithmetic(maps.device):
        return F.interpolate(maps.unsqueeze(1), size=(size, size), mode="bilinear", align_corners=False)[:, 0]


def aggregate(amap, rule, *, native_score=None):
    amap = fp32_tensor(amap, "anomaly map", 2)
    native = None if native_score is None else torch.as_tensor(native_score, device=amap.device, dtype=torch.float32).reshape(-1)
    return float(aggregate_batch(amap.unsqueeze(0), rules=(rule,), native_scores=native)[rule][0].item())


def aggregate_batch(amaps, rules=RULES, *, native_scores=None):
    """Keep the four-rule default; require explicit native values for five rules."""
    amaps = fp32_tensor(amaps, "anomaly maps", 3)
    rules = tuple(rules)
    if not rules or len(set(rules)) != len(rules) or any(rule not in TC2_GPU_RULES for rule in rules):
        raise ValueError("Scoring rules must be a nonempty distinct supported set")
    n, h, w = amaps.shape
    if "native" in rules:
        native_scores = fp32_tensor(native_scores, "native scores", 1)
        if native_scores.shape != (n,) or native_scores.device != amaps.device:
            raise ValueError("Native scores must match the map batch and device")
    out = {}
    with fp32_arithmetic(amaps.device):
        flat = amaps.reshape(n, h * w)
        for rule in rules:
            if rule == "native":
                out[rule] = native_scores
            elif rule == "max":
                out[rule] = flat.max(dim=1).values
            else:
                count = max(1, math.ceil(_Q[rule] * h * w))
                out[rule] = flat.topk(count, dim=1).values.mean(dim=1)
    return out
