"""PatchCore with separate one-neighbor pixel and weighted native image scores."""
from __future__ import annotations

from dataclasses import dataclass, field
import time
import torch
import torch.nn.functional as F
from anomaly_postprocess import feature_layers, fp32_arithmetic, fp32_tensor, integer, postprocess_anomaly_maps, seed_value
from sampling import kcenter_coreset, random_subset, retained_count
from scoring import aggregate_batch, TC2_GPU_RULES


@dataclass
class PatchCoreConfig:
    coreset_ratio: float = 0.05
    num_neighbors: int = 9
    sampling: str = "coreset"
    sampling_seed: int = 0
    chunk_size: int = 64
    query_chunk_size: int = 1024
    bank_chunk_size: int = 4096
    sampling_chunk_size: int = 16384


@dataclass
class PatchCoreModel:
    bank: torch.Tensor | None = None
    device: torch.device | None = None
    info: dict = field(default_factory=dict)


def _configuration(cfg):
    retained_count(1, cfg.coreset_ratio)
    seed_value(cfg.sampling_seed)
    if cfg.sampling not in ("coreset", "random"):
        raise ValueError("Sampling must be coreset or random")
    for name in ("num_neighbors", "chunk_size", "query_chunk_size", "bank_chunk_size", "sampling_chunk_size"):
        integer(getattr(cfg, name), name)


def compose_patch_features(feats):
    f2, f3 = feature_layers(feats, ("layer2", "layer3"))
    if f3.shape[-2] > f2.shape[-2] or f3.shape[-1] > f2.shape[-1]:
        raise ValueError("layer2 must be the highest-resolution PatchCore layer")
    with fp32_arithmetic(f2.device):
        p2 = F.avg_pool2d(f2, 3, stride=1, padding=1, count_include_pad=True)
        p3 = F.avg_pool2d(f3, 3, stride=1, padding=1, count_include_pad=True)
        p3 = F.interpolate(p3, size=f2.shape[-2:], mode="bilinear", align_corners=False)
        return torch.cat((p2, p3), dim=1)


@torch.inference_mode()
def fit_patchcore(feats, cfg, device="cuda"):
    _configuration(cfg)
    start = time.perf_counter()
    with fp32_arithmetic(device):
        x = compose_patch_features(feats).to(device)
        n, channels, h, w = x.shape
        pool = x.permute(0, 2, 3, 1).reshape(n * h * w, channels).contiguous()
        count = retained_count(len(pool), cfg.coreset_ratio)
        if cfg.sampling == "coreset":
            core, indices = kcenter_coreset(pool, cfg.coreset_ratio, device=x.device, seed=cfg.sampling_seed,
                                            chunk_size=cfg.sampling_chunk_size, return_indices=True)
        else:
            core, indices = random_subset(pool, count, device=x.device, seed=cfg.sampling_seed, return_indices=True)
        if x.device.type == "cuda":
            torch.cuda.synchronize(x.device)
        info = {"sampling": cfg.sampling, "coreset_ratio": cfg.coreset_ratio,
                "sampling_seed": cfg.sampling_seed, "memory_bank_full": len(pool),
                "memory_bank_kept": len(core), "retained_indices": indices.cpu().tolist(),
                "model_grid_hw": [h, w], "embedding_channels": channels,
                "feature_maps": [{"name": l, "channels": feats[l].shape[1], "height": feats[l].shape[2], "width": feats[l].shape[3]} for l in ("layer2", "layer3")],
                "support_neighbors": cfg.num_neighbors, "query_chunk_size": cfg.query_chunk_size,
                "bank_chunk_size": cfg.bank_chunk_size, "sampling_chunk_size": cfg.sampling_chunk_size,
                "image_chunk_size": cfg.chunk_size, "dtype": "float32", "distance_mode": "direct_euclidean",
                "fit_seconds": round(time.perf_counter() - start, 4)}
    return PatchCoreModel(core, core.device, info)


@torch.inference_mode()
def nearest_neighbors(queries, bank, count=1, *, query_chunk_size=1024, bank_chunk_size=4096):
    """Exact chunked Euclidean search; equal distances retain lower bank indices."""
    queries = fp32_tensor(queries, "queries", 2)
    bank = fp32_tensor(bank, "memory bank", 2)
    if queries.shape[1] != bank.shape[1] or queries.device != bank.device:
        raise ValueError("Queries and memory bank must share channels and device")
    count = min(integer(count, "neighbor count"), len(bank))
    query_chunk_size = integer(query_chunk_size, "query chunk size")
    bank_chunk_size = integer(bank_chunk_size, "bank chunk size")
    values = torch.empty((len(queries), count), device=bank.device, dtype=torch.float32)
    locations = torch.empty((len(queries), count), device=bank.device, dtype=torch.long)
    with fp32_arithmetic(bank.device):
        for first in range(0, len(queries), query_chunk_size):
            q = queries[first:first + query_chunk_size]
            best = torch.full((len(q), count), float("inf"), device=bank.device, dtype=torch.float32)
            indices = torch.full((len(q), count), len(bank), device=bank.device, dtype=torch.long)
            for offset in range(0, len(bank), bank_chunk_size):
                block = bank[offset:offset + bank_chunk_size]
                distances = torch.cdist(q, block, p=2, compute_mode="donot_use_mm_for_euclid_dist")
                fp32_tensor(distances, "Euclidean distances", 2)
                if count == 1:
                    current, local = distances.min(dim=1)
                    replace = current < best[:, 0]
                    best[:, 0] = torch.where(replace, current, best[:, 0])
                    indices[:, 0] = torch.where(replace, local + offset, indices[:, 0])
                else:
                    candidates = torch.cat((best, distances), dim=1)
                    candidate_indices = torch.cat((indices, torch.arange(offset, offset + len(block), device=bank.device).expand(len(q), -1)), dim=1)
                    order = torch.argsort(candidates, dim=1, stable=True)[:, :count]
                    best = candidates.gather(1, order)
                    indices = candidate_indices.gather(1, order)
            values[first:first + len(q)] = best
            locations[first:first + len(q)] = indices
    return values, locations


def _native_scores(points, distances, locations, bank, cfg):
    scores = torch.empty(len(points), dtype=torch.float32, device=bank.device)
    count = min(cfg.num_neighbors, len(bank))
    for image in range(len(points)):
        patch = int(distances[image].argmax().item())
        reference = int(locations[image, patch].item())
        _, candidates = nearest_neighbors(bank[reference:reference + 1], bank, count,
                                          query_chunk_size=cfg.query_chunk_size, bank_chunk_size=cfg.bank_chunk_size)
        others = candidates[0][candidates[0] != reference][:count - 1]
        support = torch.cat((torch.tensor([reference], device=bank.device, dtype=torch.long), others))
        test_point = points[image, patch:patch + 1]
        support_distances = torch.cdist(test_point, bank[support], p=2, compute_mode="donot_use_mm_for_euclid_dist")[0]
        fp32_tensor(support_distances, "support distances", 1)
        weight = 1.0 - torch.softmax(support_distances, dim=0)[0]
        scores[image] = weight * distances[image, patch]
    return fp32_tensor(scores, "native image scores", 1)


@torch.inference_mode()
def predict_patchcore(model, feats, cfg):
    _configuration(cfg)
    bank = fp32_tensor(model.bank, "fitted memory bank", 2)
    if model.device is None:
        raise ValueError("The fitted memory-bank device is missing")
    declared = torch.device(model.device)
    if declared.type != bank.device.type or (declared.index is not None and declared.index != bank.device.index):
        raise ValueError("Model device and memory-bank device disagree")
    with fp32_arithmetic(bank.device):
        x = compose_patch_features(feats).to(bank.device)
        n, channels, h, w = x.shape
        if channels != bank.shape[1]:
            raise ValueError("Inference embedding channels differ from the memory bank")
        actual = [{"name": l, "channels": feats[l].shape[1], "height": feats[l].shape[2], "width": feats[l].shape[3]} for l in ("layer2", "layer3")]
        if model.info and (model.info.get("feature_maps") != actual or model.info.get("model_grid_hw") != [h, w]
                           or model.info.get("support_neighbors") != cfg.num_neighbors):
            raise ValueError("Inference shapes or support configuration differ from the fitted model")
        points = x.permute(0, 2, 3, 1).reshape(n, h * w, channels)
        patch_maps = torch.empty((n, h, w), device=bank.device, dtype=torch.float32)
        native = torch.empty(n, device=bank.device, dtype=torch.float32)
        for first in range(0, n, cfg.chunk_size):
            block = points[first:first + cfg.chunk_size]
            distances, locations = nearest_neighbors(block.reshape(-1, channels), bank,
                    query_chunk_size=cfg.query_chunk_size, bank_chunk_size=cfg.bank_chunk_size)
            distances = distances.reshape(len(block), h * w)
            locations = locations.reshape(len(block), h * w)
            patch_maps[first:first + len(block)] = distances.reshape(len(block), h, w)
            native[first:first + len(block)] = _native_scores(block, distances, locations, bank, cfg)
        maps = postprocess_anomaly_maps(patch_maps)
        scores = aggregate_batch(maps, TC2_GPU_RULES, native_scores=native)
    return {"anomaly_maps": maps, "image_scores": scores}


@torch.inference_mode()
def anomaly_maps(model, feats, cfg):
    """Map-only compatibility wrapper returning final FP32 256x256 maps."""
    return predict_patchcore(model, feats, cfg)["anomaly_maps"]
