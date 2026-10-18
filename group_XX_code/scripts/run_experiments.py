#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_experiments.py — 全实验矩阵批量执行（手册第 5 页）
======================================================

矩阵（共 66 次 fit；其中 MVTec 62 次、LOCO 基线 4 次）：
  B0  6 类 × 2 方法 × seed17（MVTec 12）+ LOCO 2 类 × 2 方法（4）
  R0  6 类 × 2 方法 × seed 29/43（24）
  H1  PaDiM 维度 50/200 × cable/screw（4）
  H2  coreset 1%/10% × cable/screw（4）
  C1  随机采样替换 coreset × cable/screw（2）；C1R 另两个 seed（4）
  C2  PaDiM 层组合 layer2+3 / layer3 × cable/screw（4）
  F1  N=20/50 × 2 方法 × cable/screw（8）

特性：
  - 幂等：输出目录已有 SUCCESS 则跳过（--force 重跑）
  - 容错：单次失败记录后继续，最后给出失败清单与耗时汇总
  - 结果汇总写 run/batch_summary.json

用法：
  py scripts/run_experiments.py                 # 跑全部
  py scripts/run_experiments.py --tags B0       # 只跑指定阶段
"""
from __future__ import annotations

import os
import sys

# 在导入 torch 之前锁定 CPU，避免独显被初始化。
if "--device" in sys.argv:
    _i = sys.argv.index("--device")
    if _i + 1 < len(sys.argv) and sys.argv[_i + 1] == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        os.environ["OMP_NUM_THREADS"] = "4"
        os.environ["MKL_NUM_THREADS"] = "4"
        os.environ["OPENBLAS_NUM_THREADS"] = "4"
        os.environ["NUMEXPR_NUM_THREADS"] = "4"

import argparse
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import run as run_mod  # noqa: E402

MVTEC_CATS = ["bottle", "cable", "capsule", "screw", "tile", "wood"]
LOCO_CATS = ["juice_bottle", "screw_bag"]
SEEDS = [17, 29, 43]


def load_base(method: str) -> dict:
    return run_mod.load_config(
        ROOT / "configs" / f"b0_{method}.yaml", {})


def spec(tag, dataset, cat, method, seed, n, *, suffix="",
         sampling=None, n_dims=None, coreset_ratio=None, layers=None):
    cfg = load_base(method)
    cfg["run_tag"] = tag
    cfg["dataset"] = dataset
    cfg["category"] = cat
    cfg["seed"] = seed
    cfg["n"] = n
    cfg["run_suffix"] = suffix
    if sampling is not None:
        cfg["sampling"] = sampling
    if n_dims is not None:
        cfg["padim"]["n_dims"] = n_dims
    if coreset_ratio is not None:
        cfg["patchcore"]["coreset_ratio"] = coreset_ratio
    if layers is not None:
        cfg["layers"] = layers
    return cfg


def build_matrix() -> list[dict]:
    m = []
    # B0：MVTec + LOCO（seed17, N=100）
    for cat in MVTEC_CATS:
        for method in ("patchcore", "padim"):
            m.append(spec("B0", "mvtec_ad", cat, method, 17, 100))
    for cat in LOCO_CATS:
        for method in ("patchcore", "padim"):
            m.append(spec("B0", "mvtec_loco", cat, method, 17, 100))
    # R0：另两个 seed
    for seed in (29, 43):
        for cat in MVTEC_CATS:
            for method in ("patchcore", "padim"):
                m.append(spec("R0", "mvtec_ad", cat, method, seed, 100))
    # H1：PaDiM 维度消融
    for d in (50, 200):
        for cat in ("cable", "screw"):
            m.append(spec("H1", "mvtec_ad", cat, "padim", 17, 100,
                          suffix=f"_d{d}", n_dims=d))
    # H2：coreset 比例消融
    for r in (0.01, 0.10):
        for cat in ("cable", "screw"):
            tag_r = f"{r:.2f}".split(".")[1]
            m.append(spec("H2", "mvtec_ad", cat, "patchcore", 17, 100,
                          suffix=f"_coreset{tag_r}", coreset_ratio=r))
    # C1：随机采样替换 coreset（cable/screw，三 seed）
    for seed in SEEDS:
        tag = "C1" if seed == 17 else "C1R"
        for cat in ("cable", "screw"):
            m.append(spec(tag, "mvtec_ad", cat, "patchcore", seed, 100,
                          sampling="random"))
    # C2：PaDiM 层组合消融
    for lname, layers in (("l23", ["layer2", "layer3"]),
                          ("l3", ["layer3"])):
        for cat in ("cable", "screw"):
            m.append(spec("C2", "mvtec_ad", cat, "padim", 17, 100,
                          suffix=f"_{lname}", layers=layers))
    # F1：N=20/50
    for n in (20, 50):
        for cat in ("cable", "screw"):
            for method in ("patchcore", "padim"):
                m.append(spec("F1", "mvtec_ad", cat, method, 17, n))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="*", default=None,
                    help="只执行指定阶段（B0/R0/H1/H2/C1/C1R/C2/F1）")
    ap.add_argument("--datasets", nargs="*", default=None,
                    help="只跑指定数据集，例如 mvtec_ad")
    ap.add_argument("--force", action="store_true", help="重跑已完成的实验")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    matrix = build_matrix()
    if args.tags:
        tags = set(args.tags)
        matrix = [c for c in matrix if c["run_tag"] in tags]
    if args.datasets:
        ds = set(args.datasets)
        matrix = [c for c in matrix if c["dataset"] in ds]
    print(f"[batch] 实验矩阵共 {len(matrix)} 次 fit，device={args.device}，"
          f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES', '<unset>')!r}")

    results_dir = ROOT / "run" / "results"
    done, failed, skipped = [], [], []
    t_start = time.perf_counter()
    for i, cfg in enumerate(matrix, 1):
        run_id = (f"{cfg['run_tag']}_{cfg['category']}_{cfg['method']}_"
                  f"s{cfg['seed']}_n{cfg['n']}{cfg.get('run_suffix','')}")
        out = results_dir / run_id
        if out.joinpath("SUCCESS").is_file() and not args.force:
            print(f"[batch] ({i}/{len(matrix)}) 跳过（已完成）：{run_id}")
            skipped.append(run_id)
            continue
        print(f"\n[batch] ({i}/{len(matrix)}) 开始：{run_id}")
        t0 = time.perf_counter()
        try:
            r = run_mod.run_once(cfg, device_name=args.device)
            dt = time.perf_counter() - t0
            done.append({"run_id": run_id, "seconds": round(dt, 1),
                         "image_auroc_max":
                             r["metrics"]["image"]["max"]["image_auroc"],
                         "pixel_auroc": r["metrics"]["pixel"]["pixel_auroc"]})
            print(f"[batch] ({i}/{len(matrix)}) 完成：{run_id}，{dt:.0f}s")
        except Exception as e:  # noqa: BLE001
            dt = time.perf_counter() - t0
            import traceback
            traceback.print_exc()
            failed.append({"run_id": run_id, "error": repr(e),
                           "seconds": round(dt, 1)})
            print(f"[batch] ({i}/{len(matrix)}) 失败：{run_id} -> {e}")

    summary = {
        "total": len(matrix), "completed": len(done),
        "skipped": len(skipped), "failed": len(failed),
        "total_seconds": round(time.perf_counter() - t_start, 1),
        "done": done, "failed_list": failed,
    }
    (ROOT / "run" / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[batch] 汇总：完成 %d，跳过 %d，失败 %d，总耗时 %.1f 分钟" % (
        len(done), len(skipped), len(failed),
        (time.perf_counter() - t_start) / 60))
    if failed:
        print("[batch] 失败清单：")
        for f in failed:
            print("  -", f["run_id"], f["error"])


if __name__ == "__main__":
    main()
