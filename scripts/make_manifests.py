#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_manifests.py — CA6129 小组项目：统一数据划分与 manifest 生成
======================================================================

遵循《CA6129 工业异常检测小组选题与分工手册》第 2 页的划分协议：

  1. 固定 split seed = 20261017；MVTec AD 每类从官方 train/good 中约 20%
     划为「正常开发集」（只有正常图，用于校准分布/工作阈值，不用于选模型），
     其余 80% 作为「正常拟合池」（fit pool）。
  2. MVTec LOCO 不做切分：官方 validation/good 直接作为正常开发集，
     train/good 全部作为拟合池。
  3. 官方 test 与 ground_truth 全部锁定，绝不进入开发集/拟合池。
  4. 标准实验 run seeds = 17 / 29 / 43，每个 seed 从拟合池抽 100 张；
     同一 seed 下 20 / 50 / 100 张构成嵌套子集（20 ⊂ 50 ⊂ 100）；
     同一 seed 下 PaDiM 与 PatchCore 共用同一份清单（本脚本只生成一份）。
  5. 每个文件记录 SHA-256；每个类别输出一个 split_hash，供 run 证据记录。

仅使用 Python 标准库，Python 3.8+ 可直接运行，无需 GPU。

用法（在 scripts/ 目录下）：
    py make_manifests.py
    py make_manifests.py --datasets-root ../../datasets --out-dir ../manifests
    py make_manifests.py --rehash        # 不信任 file_inventory.csv，重新计算全部哈希

输出（写入 --out-dir，默认 ../manifests/）：
    manifest_<dataset>_<category>.json   每类完整清单（8 个）
    manifest_index.json                  全局配置、计数与 split_hash 汇总
    splits_overview.csv                  人类可读的划分总览
"""

import argparse
import csv
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 固定实验协议（不要随意改动；如改动需在报告中记录并更新 split_hash）
# ---------------------------------------------------------------------------
SPLIT_SEED = 20261017          # 开发集/拟合池划分种子（MVTec AD 用）
DEV_RATIO = 0.20               # 开发集占 train/good 的比例
RUN_SEEDS = [17, 29, 43]       # 标准实验 run seeds
FIT_SIZES = [100, 50, 20]      # 嵌套拟合子集（脚本保证 20 ⊂ 50 ⊂ 100）
MAIN_FIT_N = 100               # B0 主实验拟合张数

MANIFEST_VERSION = "1.0"

# 数据集与类别（与 datasets/ 目录一致）
DATASETS = {
    "mvtec_ad": {
        "categories": ["bottle", "cable", "capsule", "screw", "tile", "wood"],
        "dev_mode": "split_train",          # 从 train/good 切 20%
    },
    "mvtec_loco": {
        "categories": ["juice_bottle", "screw_bag"],
        "dev_mode": "official_validation",  # 直接用官方 validation/good
    },
}

# 小组：MVTec AD 6 类为标准；LOCO 2 类为第二数据集扩展
MASK_SUBDIR = "ground_truth"


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def log(msg):
    print(f"[make_manifests] {msg}", flush=True)


def sha256_file(path, bufsize=1 << 20):
    """计算单个文件的 SHA-256（1MB 缓冲区）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(bufsize)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().upper()


def list_png(directory):
    """列出目录下（不递归）所有 .png 文件，按文件名字典序返回绝对路径。"""
    if not directory.is_dir():
        return []
    return sorted([p for p in directory.iterdir() if p.is_file() and p.suffix == ".png"],
                  key=lambda p: p.name)


def rel(datasets_root, path):
    """相对 datasets 根目录的 POSIX 路径（跨平台、可移植到 HPC）。"""
    return Path(path).resolve().relative_to(Path(datasets_root).resolve()).as_posix()


def load_inventory(datasets_root):
    """读取 datasets/file_inventory.csv，返回 relative_path -> sha256 映射。"""
    inv_path = Path(datasets_root) / "file_inventory.csv"
    table = {}
    if not inv_path.is_file():
        log("未找到 file_inventory.csv，将现场计算哈希（耗时会增加）。")
        return table, False
    with open(inv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            table[row["relative_path"]] = row["sha256"].strip().upper()
    log(f"已载入哈希清单 {inv_path.name}：{len(table)} 条。")
    return table, True


def make_entry(datasets_root, path, inventory, rehash, missing_hashes):
    """生成 {path, sha256} 条目；优先用清单哈希，缺失则现场计算。"""
    r = rel(datasets_root, path)
    if rehash or r not in inventory:
        digest = sha256_file(path)
        missing_hashes.append(r)
    else:
        digest = inventory[r]
    return {"path": r, "sha256": digest}


# ---------------------------------------------------------------------------
# 掩膜路径映射
# ---------------------------------------------------------------------------
def masks_for_ad(datasets_root, cat_root, defect, image_path):
    """MVTec AD：test/<defect>/<id>.png ↔ ground_truth/<defect>/<id>_mask.png。"""
    mask = cat_root / MASK_SUBDIR / defect / f"{image_path.stem}_mask.png"
    return [mask] if mask.is_file() else []


def masks_for_loco(datasets_root, cat_root, defect, image_path):
    """LOCO：test/<defect>/<id>.png ↔ ground_truth/<defect>/<id>/000.png[、001.png...]。"""
    mask_dir = cat_root / MASK_SUBDIR / defect / image_path.stem
    if not mask_dir.is_dir():
        return []
    return sorted([p for p in mask_dir.iterdir() if p.is_file() and p.suffix == ".png"],
                  key=lambda p: p.name)


# ---------------------------------------------------------------------------
# 单个类别构建
# ---------------------------------------------------------------------------
def build_category(dataset, category, datasets_root, inventory, rehash):
    cfg = DATASETS[dataset]
    cat_root = Path(datasets_root) / dataset / category
    missing_hashes = []
    errors = []

    # --- 官方 train/good 全量 ---
    train_all = list_png(cat_root / "train" / "good")
    if not train_all:
        raise RuntimeError(f"{dataset}/{category}: train/good 为空，路径是否正确？")

    # --- 开发集与拟合池 ---
    if cfg["dev_mode"] == "split_train":
        n_dev = int(round(len(train_all) * DEV_RATIO + 1e-9))
        order = list(train_all)
        random.Random(SPLIT_SEED).shuffle(order)  # 每类同一固定种子，可复现
        dev_abs = sorted(order[:n_dev], key=lambda p: p.name)
        fit_abs = sorted(order[n_dev:], key=lambda p: p.name)
        dev_note = f"train/good 的 {DEV_RATIO:.0%}（split seed={SPLIT_SEED}）"
    elif cfg["dev_mode"] == "official_validation":
        dev_abs = list_png(cat_root / "validation" / "good")
        fit_abs = train_all
        if not dev_abs:
            raise RuntimeError(f"{dataset}/{category}: validation/good 为空。")
        dev_note = "官方 validation/good（未从 train 切分）"
    else:
        raise ValueError(cfg["dev_mode"])

    if len(fit_abs) < MAIN_FIT_N:
        errors.append(f"拟合池仅 {len(fit_abs)} 张，不足主实验 {MAIN_FIT_N} 张！")

    # --- 官方测试集（锁定）---
    test_dir = cat_root / "test"
    good_abs = list_png(test_dir / "good")
    mask_fn = masks_for_ad if dataset == "mvtec_ad" else masks_for_loco
    anomalies = []
    defect_dirs = sorted([d for d in test_dir.iterdir()
                          if d.is_dir() and d.name != "good"], key=lambda d: d.name)
    for d in defect_dirs:
        for img in list_png(d):
            mask_abs = mask_fn(datasets_root, cat_root, d.name, img)
            if not mask_abs:
                errors.append(f"异常图缺少掩膜：{rel(datasets_root, img)}")
            anomalies.append({
                "path": rel(datasets_root, img),
                "sha256": (sha256_file(img) if rehash or rel(datasets_root, img) not in inventory
                           else inventory[rel(datasets_root, img)]),
                "label": 1,
                "defect_type": d.name,
                "masks": [make_entry(datasets_root, m, inventory, rehash, missing_hashes)
                          for m in mask_abs],
            })
    anomalies.sort(key=lambda x: (x["defect_type"], x["path"]))

    # --- 条目化（带哈希）---
    dev_entries = [make_entry(datasets_root, p, inventory, rehash, missing_hashes) for p in dev_abs]
    fit_entries = [make_entry(datasets_root, p, inventory, rehash, missing_hashes) for p in fit_abs]
    good_entries = [make_entry(datasets_root, p, inventory, rehash, missing_hashes) for p in good_abs]
    # 异常图哈希若在上面现场计算过，补登 missing_hashes
    for a in anomalies:
        if rehash or a["path"] not in inventory:
            if a["path"] not in missing_hashes:
                missing_hashes.append(a["path"])

    # --- 三个 run seed 的嵌套拟合子集 ---
    fit_paths = [e["path"] for e in fit_entries]
    runs = {}
    for seed in RUN_SEEDS:
        shuffled = list(fit_paths)
        random.Random(seed).shuffle(shuffled)
        picks = {MAIN_FIT_N: shuffled[:MAIN_FIT_N]}
        for n in FIT_SIZES:
            if n not in picks:
                picks[n] = shuffled[:n]
        runs[str(seed)] = {str(n): picks[n] for n in FIT_SIZES}

    # --- 一致性校验 ---
    dev_set = {e["path"] for e in dev_entries}
    fit_set = set(fit_paths)
    test_set = {e["path"] for e in good_entries} | {a["path"] for a in anomalies}
    if dev_set & fit_set:
        errors.append("开发集与拟合池存在交集！")
    if (dev_set | fit_set) & test_set:
        errors.append("train 与官方 test 存在交集！")
    for seed in RUN_SEEDS:
        s20, s50, s100 = (set(runs[str(seed)][str(n)]) for n in (20, 50, 100))
        if not (s20 <= s50 <= s100):
            errors.append(f"seed={seed} 嵌套关系 20⊂50⊂100 不成立！")
        if len(s100) != MAIN_FIT_N:
            errors.append(f"seed={seed} 主实验抽取数 != {MAIN_FIT_N}。")

    # --- split_hash（对划分本身做确定性哈希，供 run 证据记录）---
    canonical = json.dumps({
        "manifest_version": MANIFEST_VERSION,
        "dataset": dataset,
        "category": category,
        "dev_mode": cfg["dev_mode"],
        "split_seed": SPLIT_SEED,
        "dev_ratio": DEV_RATIO,
        "run_seeds": RUN_SEEDS,
        "fit_sizes": FIT_SIZES,
        "dev": sorted(dev_set),
        "fit_pool": sorted(fit_set),
        "test_good": sorted(e["path"] for e in good_entries),
        "test_anomaly": sorted(a["path"] for a in anomalies),
        "masks": sorted(m["path"] for a in anomalies for m in a["masks"]),
    }, sort_keys=True, ensure_ascii=False)
    split_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "dataset": dataset,
        "category": category,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "split_seed": SPLIT_SEED,
            "dev_ratio": DEV_RATIO,
            "dev_mode": cfg["dev_mode"],
            "dev_note": dev_note,
            "run_seeds": RUN_SEEDS,
            "fit_sizes": FIT_SIZES,
            "main_fit_n": MAIN_FIT_N,
            "image_size": 256,
            "backbone": "ResNet18 (ImageNet pretrain)",
        },
        "split_hash": split_hash,
        "counts": {
            "train_good_total": len(train_all),
            "dev_normal": len(dev_entries),
            "fit_pool": len(fit_entries),
            "test_good": len(good_entries),
            "test_anomaly": len(anomalies),
            "defect_types": len(defect_dirs),
            "masks": sum(len(a["masks"]) for a in anomalies),
        },
        "dev": dev_entries,
        "fit_pool": fit_entries,
        "test": {
            "good": [dict(e, label=0) for e in good_entries],
            "anomalies": anomalies,
        },
        "runs": runs,
        "notes": [
            "路径相对 datasets 根目录；运行时以 --datasets-root 拼接。",
            "runs 中为拟合图片路径，哈希见 fit_pool。",
            "test/ground_truth 已锁定，禁止用于阈值或模型选择。",
            "LOCO 评估时 logical_anomalies 与 structural_anomalies 分开报指标。",
        ],
    }
    overview_row = {
        "dataset": dataset,
        "category": category,
        "dev_mode": cfg["dev_mode"],
        "train_good_total": len(train_all),
        "dev_normal": len(dev_entries),
        "fit_pool": len(fit_entries),
        "test_good": len(good_entries),
        "test_anomaly": len(anomalies),
        "defect_types": len(defect_dirs),
        "masks": sum(len(a["masks"]) for a in anomalies),
        "fit_n100": len(runs[str(RUN_SEEDS[0])]["100"]),
        "fit_n50": len(runs[str(RUN_SEEDS[0])]["50"]),
        "fit_n20": len(runs[str(RUN_SEEDS[0])]["20"]),
        "split_hash": split_hash,
    }
    return manifest, overview_row, errors, missing_hashes


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="CA6129 统一数据划分与 manifest 生成")
    parser.add_argument("--datasets-root", default=str(here / ".." / "datasets"),
                        help="datasets 目录路径（默认 ../datasets）")
    parser.add_argument("--out-dir", default=str(here / ".." / "manifests"),
                        help="manifest 输出目录（默认 ../manifests）")
    parser.add_argument("--rehash", action="store_true",
                        help="忽略 file_inventory.csv，重新计算全部文件 SHA-256")
    args = parser.parse_args()

    datasets_root = Path(args.datasets_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    if not datasets_root.is_dir():
        log(f"错误：找不到数据集目录 {datasets_root}")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory, have_inv = load_inventory(datasets_root)
    if args.rehash:
        log("--rehash：将重新计算全部文件 SHA-256。")

    index = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "split_seed": SPLIT_SEED,
            "dev_ratio": DEV_RATIO,
            "run_seeds": RUN_SEEDS,
            "fit_sizes": FIT_SIZES,
            "main_fit_n": MAIN_FIT_N,
        },
        "datasets": [],
    }
    overview_rows = []
    total_errors = []
    total_rehashed = 0

    for dataset, cfg in DATASETS.items():
        for category in cfg["categories"]:
            manifest, row, errors, rehashed = build_category(
                dataset, category, datasets_root, inventory, args.rehash)
            total_rehashed += len(rehashed)
            total_errors.extend([f"{dataset}/{category}: {e}" for e in errors])
            out_path = out_dir / f"manifest_{dataset}_{category}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            index["datasets"].append({
                "dataset": dataset, "category": category,
                "file": out_path.name,
                "counts": manifest["counts"],
                "split_hash": manifest["split_hash"],
            })
            overview_rows.append(row)
            log(f"{dataset}/{category}: dev={row['dev_normal']} "
                f"fit={row['fit_pool']} good={row['test_good']} "
                f"anom={row['test_anomaly']} masks={row['masks']} -> {out_path.name}")

    # 全局 split_hash（跨类别汇总，供整体复现核对）
    index["global_split_hash"] = hashlib.sha256(
        json.dumps([d["split_hash"] for d in index["datasets"]],
                   sort_keys=True).encode("utf-8")).hexdigest().upper()
    with open(out_dir / "manifest_index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    cols = ["dataset", "category", "dev_mode", "train_good_total", "dev_normal",
            "fit_pool", "test_good", "test_anomaly", "defect_types", "masks",
            "fit_n100", "fit_n50", "fit_n20", "split_hash"]
    with open(out_dir / "splits_overview.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(overview_rows)

    # 控制台总览
    log("")
    log("划分总览（每类；fit 子集以 seed 17 为例）：")
    colw = 12
    header = f"{'dataset':<{colw}}{'category':<{colw}}{'dev':>4}{'fit':>5}{'good':>5}{'anom':>5}{'masks':>6}"
    print(header)
    for r in overview_rows:
        print(f"{r['dataset']:<{colw}}{r['category']:<{colw}}{r['dev_normal']:>4}"
              f"{r['fit_pool']:>5}{r['test_good']:>5}{r['test_anomaly']:>5}{r['masks']:>6}")

    log("")
    if total_errors:
        log("校验发现问题：")
        for e in total_errors:
            print("  [ERROR]", e)
        sys.exit(2)
    log("全部一致性校验通过：开发集/拟合池/测试集互斥；20⊂50⊂100 嵌套成立；掩膜齐全。")
    log(f"全局 global_split_hash = {index['global_split_hash']}")
    if total_rehashed:
        log(f"现场补算哈希 {total_rehashed} 个文件。")
    log(f"输出目录：{out_dir}")


if __name__ == "__main__":
    main()
