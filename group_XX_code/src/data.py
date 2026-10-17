# -*- coding: utf-8 -*-
"""
data.py — CA6129 小组项目：manifest 驱动的数据加载器
=====================================================

协议要点（与手册第 2 页一致）：
  - 输入统一转 RGB、resize 到 256×256（图像双线性）、ImageNet 均值方差归一化；
  - 不做随机增强、不做中心裁剪；
  - 掩膜 resize 一律最近邻（NEAREST），然后二值化；LOCO 一图多掩膜时取并集；
  - 正常图返回全 0 掩膜；
  - 同时返回原始分辨率，供评估时把连续异常图双线性恢复到原图尺寸。

数据单元（dict）：
  image       : float32 Tensor (3, 256, 256)
  mask        : float32 Tensor (256, 256)，0/1 二值
  label       : int，0=正常，1=异常
  path        : str，相对 datasets 根目录的路径
  defect_type : str，正常图为 ""
  orig_size   : (H, W) 原图尺寸
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms

IMAGE_SIZE = 256
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# 图像：双线性；掩膜：最近邻（严禁双线性）
IMAGE_RESAMPLE = Image.BILINEAR
MASK_RESAMPLE = Image.NEAREST


# ---------------------------------------------------------------------------
# Manifest 读取与条目组织
# ---------------------------------------------------------------------------
class Manifest:
    """对一个类别的 manifest JSON 的只读封装。"""

    def __init__(self, manifest_path: str | Path, datasets_root: str | Path):
        self.manifest_path = Path(manifest_path)
        self.datasets_root = Path(datasets_root)
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            self.m = json.load(f)
        self.dataset = self.m["dataset"]
        self.category = self.m["category"]
        self.split_hash = self.m["split_hash"]
        self.config = self.m["config"]

    # --- 不同用途的条目（统一返回 list[dict]）---
    def dev_items(self) -> List[dict]:
        """正常开发集（仅正常图，无异常标签）。"""
        return [self._item(e["path"], 0, "", []) for e in self.m["dev"]]

    def fit_pool_items(self) -> List[dict]:
        """完整拟合池（80% train；LOCO 为全部 train）。"""
        return [self._item(e["path"], 0, "", []) for e in self.m["fit_pool"]]

    def fit_items(self, seed: int, n: int) -> List[dict]:
        """某次 run 的拟合子集（manifest 已保证 20⊂50⊂100）。"""
        paths = self.m["runs"][str(seed)][str(n)]
        return [self._item(p, 0, "", []) for p in paths]

    def test_items(self) -> List[dict]:
        """官方测试集（正常 + 异常），顺序：先 good 后按缺陷类型。"""
        items = [self._item(e["path"], 0, "good", [])
                 for e in self.m["test"]["good"]]
        for a in self.m["test"]["anomalies"]:
            masks = [x["path"] for x in a["masks"]]
            items.append(self._item(a["path"], a["label"],
                                    a["defect_type"], masks))
        return items

    def all_image_items(self) -> List[dict]:
        """特征缓存用：dev + fit_pool + test 的全部去重图片（正常图 1 份掩膜占位）。"""
        seen = set()
        out = []
        for it in self.dev_items() + self.fit_pool_items() + self.test_items():
            if it["path"] not in seen:
                seen.add(it["path"])
                out.append(it)
        return out

    def _item(self, path: str, label: int, defect_type: str,
              mask_paths: Sequence[str]) -> dict:
        return {"path": path, "label": label,
                "defect_type": defect_type, "masks": list(mask_paths)}


# ---------------------------------------------------------------------------
# 图像/掩膜 IO
# ---------------------------------------------------------------------------
_image_tf = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE), interpolation=IMAGE_RESAMPLE),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])


def load_image(path: Path) -> Tuple[torch.Tensor, Tuple[int, int]]:
    """读图 → 归一化张量 (3,256,256)，并返回原始 (H,W)。"""
    with Image.open(path) as im:
        im = im.convert("RGB")
        orig_size = (im.height, im.width)
        tensor = _image_tf(im)
    return tensor, orig_size


def load_mask(paths: Sequence[Path], size: int = IMAGE_SIZE) -> torch.Tensor:
    """读一个或多个掩膜，resize(NEAREST)、二值化、多掩膜取并集 → (size,size)。"""
    mask = np.zeros((size, size), dtype=np.uint8)
    for p in paths:
        with Image.open(p) as im:
            im = im.convert("L").resize((size, size), MASK_RESAMPLE)
            arr = np.asarray(im, dtype=np.uint8)
        mask = np.maximum(mask, (arr > 0).astype(np.uint8))
    return torch.from_numpy(mask.astype(np.float32))


def denormalize(x: torch.Tensor) -> torch.Tensor:
    """逆 ImageNet 归一化，输出 [0,1] 浮点张量（可视化/图像聚合用）。"""
    mean = torch.tensor(IMAGENET_MEAN, device=x.device).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD, device=x.device).view(3, 1, 1)
    return (x * std + mean).clamp(0.0, 1.0)


# ---------------------------------------------------------------------------
# Dataset / DataLoader
# ---------------------------------------------------------------------------
class ManifestDataset(Dataset):
    def __init__(self, datasets_root: str | Path, items: Sequence[dict]):
        self.root = Path(datasets_root)
        self.items = list(items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx: int) -> dict:
        it = self.items[idx]
        img_path = self.root / it["path"]
        image, orig_size = load_image(img_path)
        mask_paths = [self.root / m for m in it["masks"]]
        if mask_paths:
            mask = load_mask(mask_paths)
        else:
            mask = torch.zeros((IMAGE_SIZE, IMAGE_SIZE), dtype=torch.float32)
        return {
            "image": image,
            "mask": mask,
            "label": int(it["label"]),
            "path": it["path"],
            "defect_type": it["defect_type"],
            "orig_size": torch.tensor(orig_size, dtype=torch.long),
        }


def make_loader(datasets_root: str | Path, items: Sequence[dict],
                batch_size: int = 8, shuffle: bool = False,
                num_workers: int = 2) -> DataLoader:
    """统一 DataLoader；评估/拟合均默认不 shuffle，顺序由 manifest 决定。"""
    ds = ManifestDataset(datasets_root, items)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle,
                      num_workers=num_workers, pin_memory=True,
                      persistent_workers=(num_workers > 0))
