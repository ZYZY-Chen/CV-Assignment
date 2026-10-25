#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用已保存的 16×16 异常图重算 256×256 图像分数。不重新拟合，不改像素指标。"""
from __future__ import annotations

import os
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

import json
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from evaluate import image_ap, image_auroc, test_threshold_stats, threshold_from_dev  # noqa: E402
from scoring import RULES, aggregate_batch, to_image_score_grid  # noqa: E402


def _check_grid() -> None:
    """单峰图上，top-q 均值必须低于最大值，否则 256 网格没有生效。"""
    m = torch.zeros(1, 16, 16)
    m[0, 8, 8] = 10.0
    m[0, 0, 0] = 1.0
    scores = aggregate_batch(to_image_score_grid(m))
    mx = float(scores["max"][0])
    t001 = float(scores["top_0.001"][0])
    t01 = float(scores["top_0.01"][0])
    if not (mx > t001 > t01):
        raise RuntimeError(f"256 网格聚合异常: max={mx} top0.1%={t001} top1%={t01}")
    if tuple(to_image_score_grid(m).shape[-2:]) != (256, 256):
        raise RuntimeError("图像分数网格不是 256×256")


def recompute_dir(out_dir: Path) -> str:
    metrics_path = out_dir / "metrics.json"
    pred_path = out_dir / "predictions.npz"
    evidence_path = out_dir / "evidence.json"
    backup = out_dir / "metrics_grid16.json"
    if not metrics_path.is_file() or not pred_path.is_file():
        return "skip-missing"
    evidence = {}
    if evidence_path.is_file():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("image_score_grid") == 256 and backup.is_file():
        return "skip-already"
    if not backup.is_file():
        backup.write_text(metrics_path.read_text(encoding="utf-8"), encoding="utf-8")
    old = json.loads(backup.read_text(encoding="utf-8"))
    with np.load(pred_path, allow_pickle=False) as z:
        test_maps = torch.from_numpy(z["test_maps"].astype(np.float32))
        dev_maps = torch.from_numpy(z["dev_maps"].astype(np.float32))
        labels = z["test_labels"].astype(int)
        defect_types = [str(x) for x in z["test_defect_types"].tolist()]
    sc_test = aggregate_batch(to_image_score_grid(test_maps))
    sc_dev = aggregate_batch(to_image_score_grid(dev_maps))
    image = {}
    for rule in RULES:
        test_s = sc_test[rule].cpu().numpy()
        dev_s = sc_dev[rule].cpu().numpy()
        image[rule] = {
            "image_auroc": image_auroc(labels, test_s),
            "image_ap": image_ap(labels, test_s),
        }
        thr = threshold_from_dev(dev_s)
        image[rule].update(test_threshold_stats(labels, test_s, defect_types, thr))
    new_metrics = {"image": image, "pixel": old["pixel"]}
    metrics_path.write_text(json.dumps(new_metrics, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    evidence["image_score_grid"] = 256
    evidence["image_scores_recomputed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    evidence["image_scores_source"] = "predictions.npz float16 maps bilinear to 256"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    old_max = old["image"]["max"]["image_auroc"]
    new_max = image["max"]["image_auroc"]
    return (f"max {old_max:.4f}->{new_max:.4f}  "
            f"top1% {image['top_0.01']['image_auroc']:.4f}  "
            f"top0.1% {image['top_0.001']['image_auroc']:.4f}")


def main():
    _check_grid()
    results = ROOT / "run" / "results"
    n = 0
    for d in sorted(p for p in results.iterdir() if p.is_dir()):
        if not (d / "SUCCESS").is_file():
            print(f"[recompute] {d.name}: 无 SUCCESS，跳过")
            continue
        msg = recompute_dir(d)
        print(f"[recompute] {d.name}: {msg}")
        if msg.startswith("max"):
            n += 1
    print(f"[recompute] 重算 {n} 个运行")


if __name__ == "__main__":
    main()
