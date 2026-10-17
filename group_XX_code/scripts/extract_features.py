#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_features.py — 按类别提取并缓存 ResNet18 layer1-3 特征

用法（在 scripts/ 下）：
  py extract_features.py --dataset mvtec_ad --category bottle
  py extract_features.py --all
  py extract_features.py --all --force        # 忽略已有缓存，强制重算

注意：
  - 首次运行会下载 ImageNet 预训练 ResNet18 权重（约 45 MB，需联网一次）。
  - 缓存与 manifest 的 split_hash 绑定；manifest 未变则自动跳过。
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / ".." / "src"))

from data import Manifest  # noqa: E402
from feature_cache import extract_and_cache, cache_path  # noqa: E402

MANIFEST_DIR = HERE / ".." / "manifests"
DATASETS_ROOT = HERE / ".." / ".." / "datasets"
CACHE_DIR = HERE / ".." / "run" / "feature_cache"

ALL_CATEGORIES = [
    ("mvtec_ad", "bottle"), ("mvtec_ad", "cable"), ("mvtec_ad", "capsule"),
    ("mvtec_ad", "screw"), ("mvtec_ad", "tile"), ("mvtec_ad", "wood"),
    ("mvtec_loco", "juice_bottle"), ("mvtec_loco", "screw_bag"),
]


def main():
    ap = argparse.ArgumentParser(description="提取 ResNet18 特征缓存")
    ap.add_argument("--dataset", choices=["mvtec_ad", "mvtec_loco"])
    ap.add_argument("--category")
    ap.add_argument("--all", action="store_true", help="提取全部 8 类")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.all:
        targets = ALL_CATEGORIES
    else:
        if not args.dataset or not args.category:
            ap.error("请指定 --dataset 与 --category，或使用 --all")
        targets = [(args.dataset, args.category)]

    results = []
    for ds, cat in targets:
        mp = (MANIFEST_DIR / f"manifest_{ds}_{cat}.json").resolve()
        if not mp.is_file():
            print(f"找不到 manifest: {mp}，请先运行 make_manifests.py")
            sys.exit(1)
        manifest = Manifest(mp, DATASETS_ROOT.resolve())
        t0 = time.perf_counter()
        info = extract_and_cache(
            manifest, DATASETS_ROOT.resolve(), CACHE_DIR.resolve(),
            device=args.device, batch_size=args.batch_size,
            num_workers=args.workers, force=args.force)
        info["total_seconds"] = round(time.perf_counter() - t0, 2)
        results.append(info)
        if info["status"] == "extracted":
            print(f"[extract] {ds}/{cat}: {info['n_images']} 张, "
                  f"挂钟 {info['wall_seconds']}s（预热后 {info['timed_seconds_after_warmup']}s）, "
                  f"缓存 {info['cache_mb']} MB, 设备 {info['device']}")
        else:
            print(f"[extract] {ds}/{cat}: 已存在有效缓存，跳过 -> {info['path']}")

    # 写一份提取记录，便于环境/计时核对
    log_path = (CACHE_DIR / "extraction_log.json").resolve()
    existing = []
    if log_path.is_file():
        existing = json.loads(log_path.read_text(encoding="utf-8"))
    by_key = {(r["path"]): r for r in existing}
    by_key.update({r["path"]: r for r in results})
    log_path.write_text(json.dumps(list(by_key.values()), ensure_ascii=False,
                                  indent=2), encoding="utf-8")
    print(f"[extract] 提取记录已写入 {log_path}")


if __name__ == "__main__":
    main()
