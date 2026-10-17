#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — 单次实验的统一入口（手册第 10 页“每个运行的最小证据”）
=============================================================

用法（在 group_XX_code/ 下）：
  py run.py --config configs/b0_patchcore.yaml --dataset mvtec_ad \
            --category bottle --seed 17 --n 100

输出 run/results/<run_id>/：
  config.yaml         实际生效配置（含命令行覆盖）
  metrics.json        图像/像素指标（多聚合规则 + 95 百分位阈值统计）
  evidence.json       运行证据：哈希、版本、耗时、显存、设备
  predictions.npz     原始预测（test/dev 异常图、图像分数、路径、标签）
  SUCCESS             完成标记（仅当全链路成功）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
import yaml

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from data import Manifest, make_loader  # noqa: E402
from feature_cache import load_features, cache_path  # noqa: E402
from scoring import aggregate_batch, RULES  # noqa: E402
from evaluate import evaluate_all  # noqa: E402
from patchcore_adapter import (PatchCoreConfig, fit_patchcore,  # noqa: E402
                               anomaly_maps)

DATASETS_ROOT = (HERE / ".." / "datasets").resolve()
MANIFEST_DIR = (HERE / "manifests").resolve()
CACHE_DIR = (HERE / "run" / "feature_cache").resolve()
RESULTS_DIR = (HERE / "run" / "results").resolve()


def load_config(path: Path, overrides: dict) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for k, v in overrides.items():
        if v is not None:
            cfg[k] = v
    return cfg


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")
                         ).hexdigest().upper()


def items_with_meta(manifest, items, datasets_root):
    """补充原图尺寸与掩膜路径（供像素级评估）。"""
    from PIL import Image
    out = []
    for it in items:
        with Image.open(datasets_root / it["path"]) as im:
            hw = (im.height, im.width)
        out.append({"path": it["path"], "label": it["label"],
                    "defect_type": it["defect_type"],
                    "mask_paths": it["masks"], "orig_hw": hw})
    return out


def collect_maps(manifest, items, datasets_root, model, cfg, device,
                 pc_cfg, batch_size, num_workers):
    """逐批从缓存取特征并计算异常图，返回 (N,16,16)。"""
    loader = make_loader(datasets_root, items, batch_size=batch_size,
                         shuffle=False, num_workers=num_workers)
    layers = cfg["layers"]
    maps = []
    for batch in loader:
        paths = list(batch["path"])
        feats = load_features(
            cache_path(CACHE_DIR, manifest.dataset, manifest.category),
            paths, layers=layers, dtype=torch.float32)
        feats = {k: v.to(device) for k, v in feats.items()}
        m = anomaly_maps(model, feats, pc_cfg)
        maps.append(m.cpu())
    return torch.cat(maps, dim=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--category", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--n", type=int, default=None, dest="n")
    ap.add_argument("--sampling", default=None, help="coreset|random（覆盖配置）")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    cfg_path = (HERE / args.config).resolve()
    cfg = load_config(cfg_path, {
        "dataset": args.dataset, "category": args.category,
        "seed": args.seed, "n": args.n, "sampling": args.sampling,
    })
    if args.workers is not None:
        cfg["workers"] = args.workers

    dataset, category, seed, n = cfg["dataset"], cfg["category"], cfg["seed"], cfg["n"]
    method = cfg["method"]
    device = torch.device(args.device if args.device == "cpu"
                          else ("cuda" if torch.cuda.is_available() else "cpu"))

    manifest = Manifest(MANIFEST_DIR / f"manifest_{dataset}_{category}.json",
                        DATASETS_ROOT)
    run_id = f"{cfg.get('run_tag','EXP')}_{category}_{method}_s{seed}_n{n}"
    out_dir = RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cfghash = config_hash(cfg)
    print(f"[run] {run_id}")
    print(f"[run] config_hash={cfghash[:16]} split_hash={manifest.split_hash[:16]}")

    # ---- 数据子集（路径顺序严格按 manifest）----
    fit_items = manifest.fit_items(seed, n)
    dev_items = manifest.dev_items()
    test_items = manifest.test_items()
    fit_meta = items_with_meta(manifest, fit_items, DATASETS_ROOT)
    dev_meta = items_with_meta(manifest, dev_items, DATASETS_ROOT)
    test_meta = items_with_meta(manifest, test_items, DATASETS_ROOT)

    # ---- 缓存特征（拟合/开发/测试）----
    cp = cache_path(CACHE_DIR, dataset, category)
    if not cp.is_file():
        raise FileNotFoundError(
            f"缺少特征缓存 {cp}，请先运行 scripts/extract_features.py "
            f"--dataset {dataset} --category {category}")
    fit_paths = [it["path"] for it in fit_items]
    fit_feats = load_features(cp, fit_paths, layers=cfg["layers"],
                              dtype=torch.float32)
    fit_feats = {k: v.to(device) for k, v in fit_feats.items()}

    # ---- 建模 ----
    if method == "patchcore":
        pcfg = PatchCoreConfig(
            coreset_ratio=cfg["patchcore"]["coreset_ratio"],
            num_neighbors=cfg["patchcore"]["num_neighbors"],
            sampling=cfg.get("sampling", cfg["patchcore"]["sampling"]),
            sampling_seed=cfg["patchcore"].get("sampling_seed", seed),
        )
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        model = fit_patchcore(fit_feats, pcfg, device=device)
        fit_seconds = time.perf_counter() - t0
        method_detail = model.info
    else:
        raise NotImplementedError(f"方法 {method} 尚未实现")

    # ---- 预测（开发集 + 测试集）----
    t0 = time.perf_counter()
    with torch.inference_mode():
        dev_maps = collect_maps(manifest, dev_items, DATASETS_ROOT, model, cfg,
                                device, pcfg, cfg["batch_size"], cfg["workers"])
        test_maps = collect_maps(manifest, test_items, DATASETS_ROOT, model, cfg,
                                 device, pcfg, cfg["batch_size"], cfg["workers"])
    if device.type == "cuda":
        torch.cuda.synchronize()
    predict_seconds = time.perf_counter() - t0

    # ---- 图像分数（多规则）----
    t0 = time.perf_counter()
    sc_test = aggregate_batch(test_maps.float())
    sc_dev = aggregate_batch(dev_maps.float())
    image_scores_test = {k: v.cpu().numpy() for k, v in sc_test.items()}
    image_scores_dev = {k: v.cpu().numpy() for k, v in sc_dev.items()}

    # ---- 评估 ----
    metrics = evaluate_all(test_meta, dev_meta, test_maps.cpu(), dev_maps.cpu(),
                           image_scores_test, image_scores_dev,
                           DATASETS_ROOT, device)
    eval_seconds = time.perf_counter() - t0

    # ---- 证据 ----
    gpu_name = (torch.cuda.get_device_name(0) if device.type == "cuda"
                else "cpu")
    evidence = {
        "run_id": run_id,
        "config_hash": cfghash,
        "split_hash": manifest.split_hash,
        "dataset": dataset, "category": category,
        "method": method, "backbone": cfg["backbone"],
        "layers": cfg["layers"], "seed": seed, "normal_train_n": n,
        "method_detail": method_detail,
        "device": gpu_name,
        "torch_version": torch.__version__,
        "platform": platform.platform(),
        "n_dev": len(dev_items), "n_test": len(test_items),
        "fit_seconds": round(fit_seconds, 4),
        "predict_seconds": round(predict_seconds, 4),
        "evaluate_seconds": round(eval_seconds, 4),
        "gpu_peak_memory_mb": (round(torch.cuda.max_memory_allocated(0) / 1e6, 1)
                               if device.type == "cuda" else None),
        "slurm_job_id": __import__("os").environ.get("SLURM_JOB_ID"),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # ---- 落盘 ----
    with open(out_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    with open(out_dir / "evidence.json", "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    np.savez_compressed(
        out_dir / "predictions.npz",
        test_paths=np.array([it["path"] for it in test_meta]),
        test_labels=np.array([it["label"] for it in test_meta]),
        test_defect_types=np.array([it["defect_type"] for it in test_meta]),
        dev_paths=np.array([it["path"] for it in dev_meta]),
        test_maps=test_maps.half().numpy(),
        dev_maps=dev_maps.half().numpy(),
        **{f"test_score_{r}": image_scores_test[r] for r in RULES},
        **{f"dev_score_{r}": image_scores_dev[r] for r in RULES},
    )
    (out_dir / "SUCCESS").write_text("ok\n", encoding="utf-8")

    # ---- 控制台摘要 ----
    print("\n=== 图像 AUROC（聚合规则） ===")
    for r in RULES:
        print(f"  {r:<10} AUROC={metrics['image'][r]['image_auroc']:.4f}  "
              f"AP={metrics['image'][r]['image_ap']:.4f}  "
              f"正常误报={metrics['image'][r]['normal_fpr']:.3f}  "
              f"异常召回={metrics['image'][r]['anomaly_recall']:.3f}")
    pm = metrics["pixel"]
    print(f"像素 AUROC={pm['pixel_auroc']:.4f}  像素 AP={pm['pixel_ap']:.4f}")
    print(f"耗时 fit={fit_seconds:.2f}s predict={predict_seconds:.2f}s "
          f"eval={eval_seconds:.2f}s；显存峰值={evidence['gpu_peak_memory_mb']} MB")
    print(f"输出：{out_dir}")


if __name__ == "__main__":
    main()
