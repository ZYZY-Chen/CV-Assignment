"""PaDiM under the frozen TC2 GPU Experiment Protocol."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
import torch
import torch.nn.functional as F
from anomaly_postprocess import feature_layers, fp32_arithmetic, fp32_tensor, integer, postprocess_anomaly_maps, seed_value
from scoring import aggregate_batch, TC2_GPU_RULES


@dataclass
class PaDiMConfig:
    n_dims: int = 100
    eps: float = 0.01
    dims_seed: int = 17
    layers: tuple = ("layer1", "layer2", "layer3")
    position_chunk_size: int = 256


@dataclass
class PaDiMModel:
    means: torch.Tensor
    inv_covs: torch.Tensor
    dim_indices: torch.Tensor
    eps: float
    info: dict = field(default_factory=dict)


def _configuration(cfg):
    integer(cfg.n_dims, "selected dimensions")
    integer(cfg.position_chunk_size, "position chunk size")
    seed_value(cfg.dims_seed)
    if isinstance(cfg.eps, bool) or not math.isfinite(cfg.eps) or cfg.eps != 0.01:
        raise ValueError("The frozen PaDiM regularization is 0.01")
    layers = tuple(cfg.layers)
    if not layers or len(set(layers)) != len(layers) or any(l not in ("layer1", "layer2", "layer3") for l in layers):
        raise ValueError("Select distinct supported PaDiM layers")
    return layers


def compose_full_features(feats, layers=("layer1", "layer2", "layer3"), grid=None):
    """Nearest-neighbor alignment to the highest selected spatial resolution."""
    arrays = feature_layers(feats, tuple(layers))
    target = max((tuple(t.shape[-2:]) for t in arrays), key=lambda hw: hw[0] * hw[1])
    if any(t.shape[-2] > target[0] or t.shape[-1] > target[1] for t in arrays):
        raise ValueError("Selected feature grids have no highest-resolution layer")
    if grid is not None and (integer(grid, "grid"), grid) != target:
        raise ValueError("An explicit grid must equal the highest selected resolution")
    with fp32_arithmetic(arrays[0].device):
        return torch.cat([t if tuple(t.shape[-2:]) == target else F.interpolate(t, size=target, mode="nearest") for t in arrays], dim=1)


def _select_dims(total, n_dims, seed, device):
    n_dims = integer(n_dims, "selected dimensions")
    if n_dims > total:
        raise ValueError("Selected dimensions exceed concatenated channels")
    generator = torch.Generator(device="cpu").manual_seed(seed_value(seed))
    return torch.randperm(total, generator=generator)[:n_dims].sort().values.to(device)


@torch.inference_mode()
def fit_padim(feats, cfg, device):
    layers = _configuration(cfg)
    start = time.perf_counter()
    with fp32_arithmetic(device):
        x = compose_full_features(feats, layers).to(device)
        n, total, h, w = x.shape
        if n < 2:
            raise ValueError("Sample covariance requires at least two fitting images")
        dims = _select_dims(total, cfg.n_dims, cfg.dims_seed, x.device)
        x = x.index_select(1, dims).permute(0, 2, 3, 1).reshape(n, h * w, cfg.n_dims)
        means = x.mean(dim=0)
        inverses = torch.empty((h * w, cfg.n_dims, cfg.n_dims), dtype=torch.float32, device=x.device)
        identity = torch.eye(cfg.n_dims, device=x.device, dtype=torch.float32)
        for first in range(0, h * w, cfg.position_chunk_size):
            centered = x[:, first:first + cfg.position_chunk_size] - means[first:first + cfg.position_chunk_size]
            covariance = torch.einsum("npd,npe->pde", centered, centered) / (n - 1)
            covariance = covariance + cfg.eps * identity
            fp32_tensor(covariance, "regularized covariance", 3)
            inverses[first:first + len(covariance)] = torch.linalg.inv(covariance)
        fp32_tensor(inverses, "inverse covariances", 3)
        fp32_tensor(means, "means", 2)
        if x.device.type == "cuda":
            torch.cuda.synchronize(x.device)
        info = {"n_fit_images": n, "n_positions": h * w, "layers": list(layers),
                "feature_maps": [{"name": l, "channels": feats[l].shape[1], "height": feats[l].shape[2], "width": feats[l].shape[3]} for l in layers],
                "model_grid_hw": [h, w], "total_dims": total, "n_dims": cfg.n_dims,
                "dim_indices": dims.cpu().tolist(), "eps": cfg.eps, "dims_seed": cfg.dims_seed,
                "position_chunk_size": cfg.position_chunk_size, "dtype": "float32",
                "patch_score": "square_root_mahalanobis", "fit_seconds": round(time.perf_counter() - start, 4)}
    return PaDiMModel(means, inverses, dims, cfg.eps, info)


def _patch_maps(model, feats, cfg):
    layers = _configuration(cfg)
    means = fp32_tensor(model.means, "fitted means", 2)
    inverses = fp32_tensor(model.inv_covs, "fitted inverse covariances", 3)
    dims = model.dim_indices
    if (not isinstance(dims, torch.Tensor) or dims.dtype != torch.long or dims.ndim != 1
            or len(dims) != cfg.n_dims or dims.device != means.device or inverses.device != means.device):
        raise ValueError("Invalid fitted dimension indices or model devices")
    if model.info.get("layers") != list(layers) or model.eps != cfg.eps or model.info.get("dims_seed") != cfg.dims_seed:
        raise ValueError("Inference configuration differs from the fitted PaDiM model")
    with fp32_arithmetic(means.device):
        x = compose_full_features(feats, layers).to(means.device)
        n, channels, h, w = x.shape
        actual = [{"name": l, "channels": feats[l].shape[1], "height": feats[l].shape[2], "width": feats[l].shape[3]} for l in layers]
        if actual != model.info.get("feature_maps") or model.info.get("model_grid_hw") != [h, w]:
            raise ValueError("Inference feature shapes differ from the fitted model")
        if means.shape != (h * w, cfg.n_dims) or inverses.shape != (h * w, cfg.n_dims, cfg.n_dims):
            raise ValueError("Invalid fitted PaDiM tensor shapes")
        if bool((dims < 0).any()) or bool((dims >= channels).any()) or not torch.equal(dims, dims.unique(sorted=True)):
            raise ValueError("Fitted dimensions must be sorted, distinct, and in range")
        x = x.index_select(1, dims).permute(0, 2, 3, 1).reshape(n, h * w, cfg.n_dims)
        result = torch.empty((n, h * w), dtype=torch.float32, device=means.device)
        for first in range(0, h * w, cfg.position_chunk_size):
            delta = x[:, first:first + cfg.position_chunk_size] - means[first:first + cfg.position_chunk_size]
            inverse = inverses[first:first + cfg.position_chunk_size]
            quadratic = torch.einsum("npd,pde,npe->np", delta, inverse, delta)
            fp32_tensor(quadratic, "Mahalanobis quadratic form", 2)
            result[:, first:first + len(inverse)] = quadratic.clamp_min(0).sqrt()
    return result.reshape(n, h, w)


@torch.inference_mode()
def predict_padim(model, feats, cfg):
    maps = postprocess_anomaly_maps(_patch_maps(model, feats, cfg))
    native = maps.amax(dim=(1, 2))
    return {"anomaly_maps": maps, "image_scores": aggregate_batch(maps, TC2_GPU_RULES, native_scores=native)}


@torch.inference_mode()
def anomaly_maps_padim(model, feats, cfg):
    """Map-only compatibility wrapper returning final FP32 256x256 maps."""
    return predict_padim(model, feats, cfg)["anomaly_maps"]
