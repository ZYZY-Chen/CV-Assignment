# -*- coding: utf-8 -*-
"""
feature_cache.py — 冻结 ResNet18 特征提取与每类一次性缓存
=========================================================

设计原则（手册第 3、5 页）：
  - 骨干 ResNet18（ImageNet 预训练）全程 eval、冻结，不做任何训练；
  - 每个类别只提取一次 layer1/layer2/layer3 特征，之后：
      * PaDiM（layer1+2+3）与 PatchCore（layer2+3）直接共用；
      * 100/50/20 不同子集只是在缓存中选行；
      * 三个 run seed 复用同一缓存（子集由 manifest 决定，特征与 seed 无关）。
  - 特征以 float16 存盘（fp16 仅用于存储；建模时在内存中按 fp32 计算）。
  - 缓存与 manifest 的 split_hash 绑定：划分变动时自动判定为缓存失效。

缓存文件：run/feature_cache/cache_<dataset>_<category>.npz
  key 形如 "layer1/mvtec_ad/bottle/train/good/000.png"
  每个 key 对应 fp16 数组：layer1 (64,64,64)、layer2 (128,32,32)、layer3 (256,16,16)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
import torch
import torch.nn as nn
from torchvision.models import resnet18, ResNet18_Weights

from data import ManifestDataset

LAYERS = ("layer1", "layer2", "layer3")
CACHE_VERSION = "1.0"


class ResNet18FeatureExtractor(nn.Module):
    """输出 layer1–3 特征（保留原始 patch 网格，不做额外池化）。"""

    def __init__(self):
        super().__init__()
        backbone = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        self.stem = nn.Sequential(
            backbone.conv1, backbone.bn1, backbone.relu, backbone.maxpool)
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        for p in self.parameters():
            p.requires_grad_(False)
        self.eval()

    @torch.inference_mode()
    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        x = self.stem(x)
        f1 = self.layer1(x)
        f2 = self.layer2(f1)
        f3 = self.layer3(f2)
        return {"layer1": f1, "layer2": f2, "layer3": f3}


# ---------------------------------------------------------------------------
# 特征形状常量（256×256 输入）
# ---------------------------------------------------------------------------
FEATURE_SHAPES = {
    "layer1": (64, 64, 64),
    "layer2": (128, 32, 32),
    "layer3": (256, 16, 16),
}


def cache_path(out_dir: str | Path, dataset: str, category: str) -> Path:
    return Path(out_dir) / f"cache_{dataset}_{category}.npz"


def is_cache_valid(npz_path: Path, expected_split_hash: str) -> bool:
    """缓存存在且 split_hash 与 manifest 一致才算有效。"""
    if not npz_path.is_file():
        return False
    try:
        with np.load(npz_path, allow_pickle=False) as z:
            if "__meta__" not in z.files:
                return False
            meta = json.loads(str(z["__meta__"].item()))
        return meta.get("split_hash") == expected_split_hash
    except Exception:
        return False


@torch.inference_mode()
def extract_and_cache(manifest, datasets_root: str | Path, out_dir: str | Path,
                      device: str = "cuda", batch_size: int = 8,
                      num_workers: int = 2, force: bool = False,
                      warmup_batches: int = 20) -> Dict[str, object]:
    """
    提取一个类别的全部图片特征（dev+fit_pool+test），写入 npz 缓存。
    返回计时与张量信息（供 run 证据记录）。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    npz = cache_path(out_dir, manifest.dataset, manifest.category)
    if not force and is_cache_valid(npz, manifest.split_hash):
        return {"status": "cached", "path": str(npz), "split_hash": manifest.split_hash}

    if device == "cuda" and not torch.cuda.is_available():
        print("[feature_cache] CUDA 不可用，回退 CPU。")
        device = "cpu"
    device = torch.device(device)

    items = manifest.all_image_items()
    ds = ManifestDataset(datasets_root, items)
    loader = torch.utils.data.DataLoader(
        ds, batch_size=batch_size, shuffle=False, num_workers=num_workers,
        pin_memory=(device.type == "cuda"),
        persistent_workers=(num_workers > 0))

    extractor = ResNet18FeatureExtractor().to(device).eval()
    # 存储：{layer: {path: np.float16 array}}
    store: Dict[str, Dict[str, np.ndarray]] = {l: {} for l in LAYERS}

    # 计时：前 warmup_batches 个 batch 只用于预热（不计时），手册要求 20 次预热
    t_start = None
    n_processed = 0
    n_warmup = 0
    warmup_wall = 0.0
    t_all = time.perf_counter()
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        if t_start is None and n_warmup >= warmup_batches:
            if device.type == "cuda":
                torch.cuda.synchronize()
            t_start = time.perf_counter()
        if device.type == "cuda":
            torch.cuda.synchronize()
        feats = extractor(images)
        if n_warmup < warmup_batches:
            n_warmup += 1
        for layer in LAYERS:
            arr = feats[layer].half().cpu().numpy()
            for i, p in enumerate(batch["path"]):
                store[layer][p] = arr[i]
        n_processed += images.shape[0]
    if device.type == "cuda":
        torch.cuda.synchronize()
    wall = time.perf_counter() - t_all
    timed_wall = time.perf_counter() - t_start if t_start is not None else wall

    # 校验：每张图三个层都齐全
    expected_paths = [it["path"] for it in items]
    for layer in LAYERS:
        missing = [p for p in expected_paths if p not in store[layer]]
        if missing:
            raise RuntimeError(f"{layer} 缺 {len(missing)} 张图特征，例如 {missing[:2]}")

    meta = {
        "cache_version": CACHE_VERSION,
        "dataset": manifest.dataset,
        "category": manifest.category,
        "split_hash": manifest.split_hash,
        "image_size": 256,
        "backbone": "ResNet18_ImageNet_V1",
        "layers": list(LAYERS),
        "dtype": "float16",
        "n_images": len(expected_paths),
        "torch_version": torch.__version__,
        "device": str(torch.cuda.get_device_name(0)) if device.type == "cuda" else "cpu",
    }
    save_kwargs = {"__meta__": np.asarray(json.dumps(meta, ensure_ascii=False))}
    for layer in LAYERS:
        for p in expected_paths:
            save_kwargs[f"{layer}/{p}"] = store[layer][p]
    np.savez_compressed(npz, **save_kwargs)

    size_mb = npz.stat().st_size / 1e6
    timed_per_img = timed_wall / max(1, n_processed - n_warmup * batch_size)
    return {
        "status": "extracted",
        "path": str(npz),
        "split_hash": manifest.split_hash,
        "n_images": n_processed,
        "wall_seconds": round(wall, 2),
        "timed_seconds_after_warmup": round(timed_wall, 2),
        "seconds_per_image_timed": round(timed_per_img, 4),
        "cache_mb": round(size_mb, 1),
        "device": meta["device"],
    }


def load_features(npz_path: str | Path, paths: Sequence[str],
                  layers: Sequence[str] = LAYERS,
                  dtype: torch.dtype = torch.float32) -> Dict[str, torch.Tensor]:
    """
    从缓存按给定图片路径读取特征，返回 {layer: Tensor (N, C, H, W)}。
    路径顺序严格按传入顺序（与 manifest 子集一致）。
    """
    out = {l: [] for l in layers}
    with np.load(npz_path, allow_pickle=False) as z:
        for layer in layers:
            for p in paths:
                key = f"{layer}/{p}"
                if key not in z.files:
                    raise KeyError(f"缓存中没有 {key}（缓存与 manifest 是否匹配？）")
                out[layer].append(torch.from_numpy(z[key].astype(np.float32)
                                                   if dtype == torch.float32
                                                   else z[key]))
    return {l: torch.stack(out[l]).to(dtype) for l in layers}
