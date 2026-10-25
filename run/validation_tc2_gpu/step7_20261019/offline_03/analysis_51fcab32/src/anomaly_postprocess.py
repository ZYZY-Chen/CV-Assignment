"""Shared FP32 validation and fixed TC2 GPU anomaly-map postprocessing."""
from __future__ import annotations

from contextlib import contextmanager
import operator

import torch
import torch.nn.functional as F


def integer(value, name, minimum=1):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    try:
        result = operator.index(value)
    except TypeError as error:
        raise ValueError(f"{name} must be an integer >= {minimum}") from error
    if result < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return result


def seed_value(value):
    value = integer(value, "seed", 0)
    if value >= 2**63:
        raise ValueError("seed must be less than 2**63")
    return value


def fp32_tensor(value, name, ndim):
    if (not isinstance(value, torch.Tensor) or value.ndim != ndim
            or value.dtype != torch.float32 or any(size <= 0 for size in value.shape)):
        raise ValueError(f"{name} must be a nonempty {ndim}D FP32 tensor")
    if not bool(torch.isfinite(value).all()):
        raise ValueError(f"{name} contains nonfinite values")
    return value


def feature_layers(feats, layers):
    if not isinstance(feats, dict) or not layers or len(set(layers)) != len(layers):
        raise ValueError("Provide a feature dictionary and distinct selected layers")
    arrays = []
    for name in layers:
        if name not in feats:
            raise ValueError(f"Missing required feature layer: {name}")
        tensor = fp32_tensor(feats[name], name, 4)
        if arrays and (tensor.shape[0] != arrays[0].shape[0] or tensor.device != arrays[0].device):
            raise ValueError("Selected feature layers must share batch size and device")
        arrays.append(tensor)
    return arrays


@contextmanager
def fp32_arithmetic(device):
    device = torch.device(device)
    if device.type not in ("cpu", "cuda"):
        raise ValueError("Only CPU and CUDA execution are supported")
    if device.type == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but unavailable; CPU fallback is forbidden")
        if torch.backends.cuda.matmul.allow_tf32 or torch.backends.cudnn.allow_tf32:
            raise RuntimeError("Disable matmul and cuDNN TF32 before algorithm execution")
    with torch.autocast(device_type=device.type, enabled=False):
        yield


@torch.inference_mode()
def postprocess_anomaly_maps(patch_maps):
    """Bilinear 256x256 resize, then a unit-sum sigma=4 Gaussian, once."""
    patch_maps = fp32_tensor(patch_maps, "patch_maps", 3)
    with fp32_arithmetic(patch_maps.device):
        maps = F.interpolate(patch_maps.unsqueeze(1), size=(256, 256), mode="bilinear", align_corners=False)
        coordinates = torch.arange(-16, 17, device=maps.device, dtype=torch.float32)
        kernel = torch.exp(-coordinates.square() / 32.0)
        kernel = kernel / kernel.sum()
        maps = F.conv2d(F.pad(maps, (16, 16, 0, 0), mode="reflect"), kernel.reshape(1, 1, 1, 33))
        maps = F.conv2d(F.pad(maps, (0, 0, 16, 16), mode="reflect"), kernel.reshape(1, 1, 33, 1))
    return fp32_tensor(maps[:, 0], "final_anomaly_maps", 3)
