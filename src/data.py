# -*- coding: utf-8 -*-
"""
data.py — CA6129 group project: manifest-driven data loading
=========================================================

Protocol summary (consistent with page 2 of the project handbook):
  - Convert inputs to RGB, resize to 256x256 using bilinear interpolation,
    and normalize with the ImageNet mean and standard deviation.
  - Apply no random augmentation or center cropping.
  - Resize masks with nearest-neighbor interpolation (NEAREST), then binarize.
    Take the union when a LOCO image has multiple masks.
  - Return an all-zero mask for a normal image.
  - Also return the original resolution so continuous anomaly maps can be
    resized to the original image dimensions with bilinear interpolation.

Data item (dict):
  image       : float32 Tensor (3, 256, 256)
  mask        : float32 Tensor (256, 256), binary values 0/1
  label       : int, 0=normal, 1=anomalous
  path        : str, path relative to the datasets root
  defect_type : str, "" for a normal image
  orig_size   : (H, W), original image dimensions
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

# Images: bilinear; masks: nearest neighbor (never bilinear).
IMAGE_RESAMPLE = Image.BILINEAR
MASK_RESAMPLE = Image.NEAREST


# ---------------------------------------------------------------------------
# Manifest loading and item organization
# ---------------------------------------------------------------------------
class Manifest:
    """Read-only wrapper for one category's manifest JSON."""

    def __init__(self, manifest_path: str | Path, datasets_root: str | Path):
        self.manifest_path = Path(manifest_path)
        self.datasets_root = Path(datasets_root)
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            self.m = json.load(f)
        self.dataset = self.m["dataset"]
        self.category = self.m["category"]
        self.split_hash = self.m["split_hash"]
        self.config = self.m["config"]

    # --- Items for each purpose (all methods return list[dict])---
    def dev_items(self) -> List[dict]:
        """Normal development set (normal images only, without anomaly labels)."""
        return [self._item(e["path"], 0, "", []) for e in self.m["dev"]]

    def fit_pool_items(self) -> List[dict]:
        """Complete fitting pool (80% of AD train; all LOCO train)."""
        return [self._item(e["path"], 0, "", []) for e in self.m["fit_pool"]]

    def fit_items(self, seed: int, n: int) -> List[dict]:
        """Fitting subset for one run (the manifest guarantees 20⊂50⊂100)."""
        paths = self.m["runs"][str(seed)][str(n)]
        return [self._item(p, 0, "", []) for p in paths]

    def test_items(self) -> List[dict]:
        """Official test set (normal and anomalous), ordered by good images then defect type."""
        items = [self._item(e["path"], 0, "good", [])
                 for e in self.m["test"]["good"]]
        for a in self.m["test"]["anomalies"]:
            masks = [x["path"] for x in a["masks"]]
            items.append(self._item(a["path"], a["label"],
                                    a["defect_type"], masks))
        return items

    def all_image_items(self) -> List[dict]:
        """Unique dev + fit_pool + test images for caching (normal images use a mask placeholder)."""
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
# Image/mask I/O
# ---------------------------------------------------------------------------
_image_tf = transforms.Compose([
    transforms.Resize((IMAGE_SIZE, IMAGE_SIZE), interpolation=IMAGE_RESAMPLE),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])


def load_image(path: Path) -> Tuple[torch.Tensor, Tuple[int, int]]:
    """Load an image as a normalized (3,256,256) tensor and return its original (H,W)."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        orig_size = (im.height, im.width)
        tensor = _image_tf(im)
    return tensor, orig_size


def load_mask(paths: Sequence[Path],
              size: int | tuple[int, int] = IMAGE_SIZE) -> torch.Tensor:
    """Load masks, resize with NEAREST, then binarize. Take the union of multiple masks.

    An integer size produces a square. Pixel evaluation passes (H, W), since LOCO originals are not square.
    """
    if isinstance(size, int):
        height, width = size, size
    else:
        height, width = int(size[0]), int(size[1])
    mask = np.zeros((height, width), dtype=np.uint8)
    for p in paths:
        with Image.open(p) as im:
            im = im.convert("L").resize((width, height), MASK_RESAMPLE)
            arr = np.asarray(im, dtype=np.uint8)
        mask = np.maximum(mask, (arr > 0).astype(np.uint8))
    return torch.from_numpy(mask.astype(np.float32))


def denormalize(x: torch.Tensor) -> torch.Tensor:
    """Undo ImageNet normalization to return a [0,1] float tensor for visualization or image aggregation."""
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
                num_workers: int = 2, pin_memory: bool = False) -> DataLoader:
    """Create a DataLoader; evaluation and fitting default to manifest order without shuffling."""
    ds = ManifestDataset(datasets_root, items)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle,
                      num_workers=num_workers, pin_memory=pin_memory,
                      persistent_workers=(num_workers > 0))
