#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 CPU 上按同一协议重测 B0 的耗时和内存。

不覆盖 run/results。官方实验日志里前几次在 GPU、后面在 CPU，不能放进同一张速度图。
本脚本：batch=1，预测前预热 20 次，拟合 / 预测 / 评估分开计时。
特征来自已有缓存，所以不含图像解码和 ResNet 前向；骨干耗时单独测一次。
"""
from __future__ import annotations

import os
import sys

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["NUMEXPR_NUM_THREADS"] = "4"

import ctypes
import json
import time
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import run as run_mod  # noqa: E402
from data import load_image  # noqa: E402
from feature_cache import ResNet18FeatureExtractor  # noqa: E402
from scoring import aggregate_batch, to_image_score_grid  # noqa: E402


CATS = ["bottle", "cable", "capsule", "screw", "tile", "wood"]


def rss_mb() -> float:
    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.K32GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    kernel.K32GetProcessMemoryInfo.restype = ctypes.c_int
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = kernel.K32GetProcessMemoryInfo(
        kernel.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    if not ok:
        return -1.0
    return pmc.PeakWorkingSetSize / 1e6


def backbone_seconds() -> dict:
    """CPU 上测共享 ResNet18。预热 20 张，再计 32 张，batch=1。"""
    manifest = run_mod.Manifest(
        run_mod.MANIFEST_DIR / "manifest_mvtec_ad_bottle.json",
        run_mod.DATASETS_ROOT)
    paths = [it["path"] for it in manifest.fit_items(17, 100)[:32]]
    images = []
    for p in paths:
        tensor, _ = load_image(run_mod.DATASETS_ROOT / p)
        images.append(tensor)
    batch = torch.stack(images)
    model = ResNet18FeatureExtractor().to("cpu").eval()
    with torch.inference_mode():
        for i in range(20):
            model(batch[i % batch.shape[0]: i % batch.shape[0] + 1])
        t0 = time.perf_counter()
        for i in range(batch.shape[0]):
            model(batch[i:i + 1])
        elapsed = time.perf_counter() - t0
    return {
        "device": "cpu",
        "batch_size": 1,
        "warmup_images": 20,
        "timed_images": int(batch.shape[0]),
        "seconds": round(elapsed, 4),
        "seconds_per_image": round(elapsed / batch.shape[0], 4),
        "includes": "ResNet18 layer1-3 forward only",
        "excludes": "image decode, disk write, coreset, gaussian, evaluation",
    }


def bench_case(method: str, category: str) -> dict:
    cfg = run_mod.load_config(ROOT / "configs" / f"b0_{method}.yaml", {})
    cfg.update({
        "run_tag": "B0", "dataset": "mvtec_ad", "category": category,
        "seed": 17, "n": 100, "workers": 0, "batch_size": 1,
        "image_score_grid": 256, "run_suffix": "",
    })
    device = torch.device("cpu")
    manifest = run_mod.Manifest(
        run_mod.MANIFEST_DIR / f"manifest_mvtec_ad_{category}.json",
        run_mod.DATASETS_ROOT)
    fit_items = manifest.fit_items(17, 100)
    dev_items = manifest.dev_items()
    test_items = manifest.test_items()
    fit_meta = run_mod.items_with_meta(manifest, fit_items, run_mod.DATASETS_ROOT)
    dev_meta = run_mod.items_with_meta(manifest, dev_items, run_mod.DATASETS_ROOT)
    test_meta = run_mod.items_with_meta(manifest, test_items, run_mod.DATASETS_ROOT)
    cp = run_mod.cache_path(run_mod.CACHE_DIR, "mvtec_ad", category)
    fit_feats = run_mod.load_features(
        cp, [it["path"] for it in fit_items], layers=cfg["layers"])
    fit_feats = {k: v.to(device) for k, v in fit_feats.items()}

    if method == "patchcore":
        from patchcore_adapter import PatchCoreConfig, fit_patchcore
        pcfg = PatchCoreConfig(
            coreset_ratio=cfg["patchcore"]["coreset_ratio"],
            num_neighbors=cfg["patchcore"]["num_neighbors"],
            sampling=cfg["patchcore"]["sampling"],
            sampling_seed=cfg["patchcore"].get("sampling_seed", 17),
        )
        t0 = time.perf_counter()
        model = fit_patchcore(fit_feats, pcfg, device=device)
        fit_s = time.perf_counter() - t0
        storage_mb = model.bank.numel() * model.bank.element_size() / 1e6
        detail = dict(model.info)
    else:
        from padim_adapter import PaDiMConfig, fit_padim
        pcfg = PaDiMConfig(
            n_dims=cfg["padim"]["n_dims"], eps=cfg["padim"]["eps"],
            dims_seed=17, layers=tuple(cfg["layers"]))
        t0 = time.perf_counter()
        model = fit_padim(fit_feats, pcfg, device=device)
        fit_s = time.perf_counter() - t0
        storage_mb = (model.means.numel() + model.inv_covs.numel()) * 4 / 1e6
        detail = dict(model.info)
        detail.pop("dim_indices", None)

    one = test_items[:1]
    with torch.inference_mode():
        for _ in range(20):
            run_mod.collect_maps(
                manifest, one, run_mod.DATASETS_ROOT, model, cfg, device,
                pcfg, 1, 0, method)
        t0 = time.perf_counter()
        dev_maps = run_mod.collect_maps(
            manifest, dev_items, run_mod.DATASETS_ROOT, model, cfg, device,
            pcfg, 1, 0, method)
        test_maps = run_mod.collect_maps(
            manifest, test_items, run_mod.DATASETS_ROOT, model, cfg, device,
            pcfg, 1, 0, method)
    predict_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    sc_test = {k: v.cpu().numpy()
               for k, v in aggregate_batch(to_image_score_grid(test_maps)).items()}
    sc_dev = {k: v.cpu().numpy()
              for k, v in aggregate_batch(to_image_score_grid(dev_maps)).items()}
    metrics = run_mod.evaluate_all(
        test_meta, dev_meta, test_maps.cpu(), dev_maps.cpu(),
        sc_test, sc_dev, run_mod.DATASETS_ROOT, device)
    eval_s = time.perf_counter() - t0
    return {
        "method": method,
        "category": category,
        "seed": 17,
        "n": 100,
        "batch_size": 1,
        "warmup_predicts": 20,
        "device": "cpu",
        "fit_seconds": round(fit_s, 4),
        "predict_seconds": round(predict_s, 4),
        "evaluate_seconds": round(eval_s, 4),
        "n_test": len(test_items),
        "storage_mb": round(storage_mb, 3),
        "peak_rss_mb": round(rss_mb(), 1),
        "image_auroc_max": metrics["image"]["max"]["image_auroc"],
        "pixel_auroc": metrics["pixel"]["pixel_auroc"],
        "detail": {k: v for k, v in detail.items()
                   if k != "dim_indices"},
    }


def main():
    run_mod.prepare_runtime("cpu")
    if torch.cuda.is_available():
        raise RuntimeError("CUDA 仍然可见，停止计时以免碰到独显")
    out = {
        "purpose": "CPU-only B0 resource table. Do not mix with earlier GPU timings.",
        "includes_predict": "load cached features and score, batch=1, after 20 warmups",
        "excludes_predict": "JPEG decode and ResNet forward",
        "backbone": backbone_seconds(),
        "runs": [],
    }
    dest = ROOT / "run" / "resource_benchmark.json"
    print(f"[bench] backbone {out['backbone']['seconds_per_image']} s/img", flush=True)
    for method in ("patchcore", "padim"):
        for cat in CATS:
            print(f"[bench] {method} {cat}", flush=True)
            row = bench_case(method, cat)
            out["runs"].append(row)
            dest.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            print(f"[bench] done {method} {cat} "
                  f"fit={row['fit_seconds']} predict={row['predict_seconds']} "
                  f"eval={row['evaluate_seconds']} rss={row['peak_rss_mb']}",
                  flush=True)
    print(f"[bench] wrote {dest}", flush=True)


if __name__ == "__main__":
    main()
