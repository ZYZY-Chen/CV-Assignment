#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggregate_results.py — 汇总全部实验结果（手册第 6 页统计口径）
============================================================

读取 run/results/*/metrics.json + evidence.json，输出：
  run/results_summary.csv      逐次实验的扁平指标表（报告附表用）
  run/results_summary.json     宏平均汇总（供报告直接引用）
控制台打印：
  1. B0 六类逐类图像 AUROC（max / top1%）与像素指标 + 六类宏平均
  2. B0 LOCO 两类结果
  3. R0 三 seed 六类宏平均（均值±标准差）
  4. H1/H2/C1/C2/F1 消融结果

口径：图像 AUROC 按类别先算，六类再等权宏平均；
      每个 seed 报告六类均值，再报告三 seed 均值±标准差；
      缺陷类型不作为随机种子。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESULTS = ROOT / "run" / "results"
MVTEC_CATS = ["bottle", "cable", "capsule", "screw", "tile", "wood"]
LOCO_CATS = ["juice_bottle", "screw_bag"]
RULES = ["max", "top_0.001", "top_0.01", "top_0.05"]
RUN_RE = re.compile(
    r"^(?P<tag>[A-Z0-9]+)_(?P<cat>[a-z_]+)_(?P<method>patchcore|padim)"
    r"_s(?P<seed>\d+)_n(?P<n>\d+)(?P<suffix>.*)$")


def load_all():
    rows = []
    for d in sorted(RESULTS.iterdir()):
        if not d.is_dir() or not (d / "SUCCESS").is_file():
            continue
        m = RUN_RE.match(d.name)
        if m is None:
            continue
        metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        evidence = json.loads((d / "evidence.json").read_text(encoding="utf-8"))
        r = {"run_id": d.name, "tag": m.group("tag"),
             "category": m.group("cat"), "method": m.group("method"),
             "seed": int(m.group("seed")), "n": int(m.group("n")),
             "suffix": m.group("suffix"),
             "dataset": evidence["dataset"],
             "pixel_auroc": metrics["pixel"]["pixel_auroc"],
             "pixel_ap": metrics["pixel"]["pixel_ap"],
             "fit_seconds": evidence["fit_seconds"],
             "predict_seconds": evidence["predict_seconds"],
             "evaluate_seconds": evidence["evaluate_seconds"],
             "gpu_peak_memory_mb": evidence["gpu_peak_memory_mb"]}
        for rule in RULES:
            im = metrics["image"][rule]
            r[f"{rule}_image_auroc"] = im["image_auroc"]
            r[f"{rule}_image_ap"] = im["image_ap"]
            r[f"{rule}_normal_fpr"] = im["normal_fpr"]
            r[f"{rule}_anomaly_recall"] = im["anomaly_recall"]
        for gname, g in (metrics.get("groups") or {}).items():
            r[f"{gname}_image_auroc"] = g["image"]["max"]["image_auroc"]
            r[f"{gname}_top1_auroc"] = g["image"]["top_0.01"]["image_auroc"]
            r[f"{gname}_pixel_auroc"] = g["pixel"]["pixel_auroc"]
        rows.append(r)
    return rows


def write_csv(rows):
    out = ROOT / "run" / "results_summary.csv"
    keys, seen = [], set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval="")
        w.writeheader()
        w.writerows(rows)
    return out


def macro(rows, cats, rule):
    """指定类别集合上的图像 AUROC 宏平均。"""
    vals = [r[f"{rule}_image_auroc"] for r in rows if r["category"] in cats]
    return sum(vals) / len(vals) if vals else None


def macro_pixel(rows, cats):
    vals = [r["pixel_auroc"] for r in rows if r["category"] in cats]
    return sum(vals) / len(vals) if vals else None


def fmt(x, nd=4):
    return "-" if x is None else f"{x:.{nd}f}"


def main():
    rows = load_all()
    if not rows:
        print("没有找到已完成的实验（run/results/*/SUCCESS）")
        return
    csv_path = write_csv(rows)
    print(f"[aggregate] 共 {len(rows)} 次完成实验，CSV -> {csv_path}")

    by = {}
    for r in rows:
        by.setdefault((r["tag"], r["method"], r["seed"], r["suffix"]),
                      []).append(r)

    summary = {"per_run": rows}

    print("\n=== 1. B0 六类 MVTec 逐类图像 AUROC（seed17, N=100） ===")
    for method in ("patchcore", "padim"):
        print(f"\n  {method}")
        print(f"  {'类别':<10} {'max':>8} {'top1%':>8} {'top5%':>8} "
              f"{'像素AUROC':>10} {'像素AP':>8}")
        grp = [r for r in rows if r["tag"] == "B0"
               and r["method"] == method and r["dataset"] == "mvtec_ad"]
        for cat in MVTEC_CATS:
            r = next(x for x in grp if x["category"] == cat)
            print(f"  {cat:<10} {fmt(r['max_image_auroc']):>8} "
                  f"{fmt(r['top_0.01_image_auroc']):>8} "
                  f"{fmt(r['top_0.05_image_auroc']):>8} "
                  f"{fmt(r['pixel_auroc']):>10} {fmt(r['pixel_ap']):>8}")
        print(f"  {'六类宏平均':<10} {fmt(macro(grp, MVTEC_CATS, 'max')):>8} "
              f"{fmt(macro(grp, MVTEC_CATS, 'top_0.01')):>8} "
              f"{fmt(macro(grp, MVTEC_CATS, 'top_0.05')):>8} "
              f"{fmt(macro_pixel(grp, MVTEC_CATS)):>10}")

    print("\n=== 2. B0 LOCO 两类（逻辑异常数据集） ===")
    loco_any = False
    for method in ("patchcore", "padim"):
        grp = [r for r in rows if r["tag"] == "B0"
               and r["method"] == method and r["dataset"] == "mvtec_loco"]
        if not grp:
            continue
        loco_any = True
        line = f"  {method:<11}"
        for cat in LOCO_CATS:
            matches = [x for x in grp if x["category"] == cat]
            if not matches:
                line += f" | {cat}: not run"
                continue
            r = matches[0]
            line += (
                f" | {cat}: logical={fmt(r.get('logical_anomalies_image_auroc'))}"
                f"/{fmt(r.get('logical_anomalies_pixel_auroc'))}"
                f" structural={fmt(r.get('structural_anomalies_image_auroc'))}"
                f"/{fmt(r.get('structural_anomalies_pixel_auroc'))}"
                f" (image/pixel, pooled image={fmt(r['max_image_auroc'])})"
            )
        print(line)
    if not loco_any:
        print("  not run yet")

    print("\n=== 3. R0 三 seed 六类宏平均（mean±std） ===")
    import statistics
    r0 = {}
    for method in ("patchcore", "padim"):
        for rule in ("max", "top_0.01"):
            per_seed = []
            for seed in (17, 29, 43):
                tag = "B0" if seed == 17 else "R0"
                grp = [r for r in rows if r["tag"] == tag
                       and r["method"] == method and r["seed"] == seed
                       and r["dataset"] == "mvtec_ad"]
                if len(grp) == 6:
                    per_seed.append(macro(grp, MVTEC_CATS, rule))
            if len(per_seed) > 1:
                mean = statistics.mean(per_seed)
                sd = statistics.stdev(per_seed)
                r0[f"{method}_{rule}"] = {"per_seed": per_seed,
                                          "mean": mean, "std": sd}
                print(f"  {method:<11} {rule:<10} "
                      f"{mean:.4f} ± {sd:.4f}  （逐seed: "
                      f"{', '.join(f'{x:.4f}' for x in per_seed)}）")
            elif len(per_seed) == 1:
                print(f"  {method:<11} {rule:<10} "
                      f"only seed so far {per_seed[0]:.4f}，暂不报告标准差")

    print("\n=== 4. 消融（cable/screw 两类宏平均，seed17） ===")
    for tag, label in [("H1", "PaDiM 维度"), ("H2", "coreset 比例"),
                       ("C1", "随机采样替换"), ("C2", "PaDiM 层组合")]:
        grp = [r for r in rows if r["tag"] == tag]
        if not grp:
            continue
        for r in sorted(grp, key=lambda x: (x["method"], x["suffix"])):
            print(f"  {label} {r['run_id']:<42} "
                  f"max={fmt(r['max_image_auroc'])} "
                  f"top1%={fmt(r['top_0.01_image_auroc'])} "
                  f"像素={fmt(r['pixel_auroc'])}")
    f1 = [r for r in rows if r["tag"] == "F1"]
    for n in (20, 50):
        for method in ("patchcore", "padim"):
            grp = [r for r in f1 if r["n"] == n and r["method"] == method]
            if grp:
                print(f"  F1 N={n:<3} {method:<11} "
                      f"max宏平均={fmt(macro(grp, ['cable','screw'],'max'))} "
                      f"像素={fmt(macro_pixel(grp, ['cable','screw']))}")
    # B0 对应 cable/screw 基线（供 F1 对比）
    for method in ("patchcore", "padim"):
        grp = [r for r in rows if r["tag"] == "B0"
               and r["method"] == method and r["category"] in ("cable", "screw")]
        print(f"  B0 N=100 {method:<10} "
              f"max宏平均={fmt(macro(grp, ['cable','screw'],'max'))} "
              f"像素={fmt(macro_pixel(grp, ['cable','screw']))}")

    (ROOT / "run" / "results_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[aggregate] JSON 明细 -> {ROOT / 'run' / 'results_summary.json'}")


if __name__ == "__main__":
    main()
